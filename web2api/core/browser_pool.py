"""Browser pool manager - 浏览器并发调度池

支持热启动、延迟假休眠、内存监控、流量拦截、反自动化检测。
"""

import asyncio
import time
from typing import Optional, Dict
from enum import Enum
from dataclasses import dataclass, field
from loguru import logger
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from web2api.config import BrowserConfig, TrafficInterceptConfig
from web2api.core.traffic_interceptor import TrafficInterceptor, ContentDisabler
from web2api.platforms.base import BaseAutomator


# === 反自动化检测 Stealth 脚本 ===
# 在所有页面脚本之前执行，覆盖 Playwright 留下的自动化指纹
STEALTH_SCRIPT = """
(() => {
    // 1. 覆盖 navigator.webdriver → false
    Object.defineProperty(navigator, 'webdriver', {
        get: () => false,
        configurable: true,
    });

    // 2. 删除 window.__playwright / __pw_manual 等 Playwright 内部变量
    delete window.__playwright;
    delete window.__pw_manual;
    delete window.__PW_inspect;

    // 3. 覆盖 navigator.plugins（无头浏览器默认为空）
    if (navigator.plugins.length === 0) {
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
                ];
                plugins.length = 3;
                return plugins;
            },
        });
    }

    // 4. 覆盖 navigator.languages（确保不为空）
    if (!navigator.languages || navigator.languages.length === 0) {
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en-US', 'en'],
        });
    }

    // 5. 修复 window.chrome 对象（无头浏览器可能缺失）
    if (!window.chrome) {
        window.chrome = {};
    }
    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            connect: () => {},
            sendMessage: () => {},
        };
    }

    // 6. 覆盖 navigator.permissions.query（避免自动化检测）
    const originalQuery = window.navigator.permissions?.query;
    if (originalQuery) {
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters)
        );
    }

    // 7. 修复 WebGL vendor/renderer（无头浏览器可能暴露 "Google SwiftShader"）
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter.call(this, parameter);
    };
})();
"""


class WorkerStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    COOLDOWN = "cooldown"
    MAINTENANCE = "maintenance"
    DEAD = "dead"


@dataclass
class Worker:
    """浏览器Worker"""
    id: str
    browser: Optional[Browser] = None
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None
    gemini: Optional[BaseAutomator] = None

    status: WorkerStatus = WorkerStatus.IDLE
    account_id: Optional[str] = None
    conversation_id: Optional[str] = None

    created_at: float = field(default_factory=time.time)
    last_used_time: float = field(default_factory=time.time)
    memory_usage_mb: float = 0.0
    pid: Optional[int] = None

    async def cleanup(self):
        try:
            if self.page:
                try:
                    await self.page.close()
                except Exception:
                    pass
            if self.context:
                try:
                    await self.context.close()
                except Exception:
                    pass
            if self.browser:
                try:
                    self.pid = self.browser.process.pid if self.browser.process else None
                    await self.browser.close()
                except Exception:
                    pass
            self.browser = None
            self.context = None
            self.page = None
            self.gemini = None
            self.status = WorkerStatus.DEAD
        except Exception as e:
            logger.error(f"Error cleaning up worker {self.id}: {e}")


class BrowserPool:
    """
    浏览器并发调度池

    核心职责：
    - 生命周期管理：热启动、延迟假休眠、自动kill
    - 流量拦截：100%封杀静态资源
    - 状态追踪：Idle/Busy/Cooldown/Maintenance
    - 内存监控：超出限制时主动kill
    """

    def __init__(
        self,
        browser_config: BrowserConfig,
        traffic_config: TrafficInterceptConfig,
    ):
        self.browser_config = browser_config
        self.traffic_config = traffic_config

        self.workers: Dict[str, Worker] = {}
        self.worker_counter = 0
        self.account_to_worker: Dict[str, str] = {}

        self.playwright = None
        self.idle_timer_tasks: Dict[str, asyncio.Task] = {}
        self.health_check_task: Optional[asyncio.Task] = None
        self._db = None  # SQLite store for cookie persistence

        logger.info(f"🔧 BrowserPool initialized (max_workers={browser_config.max_workers})")

    async def initialize(self):
        self.playwright = await async_playwright().start()
        logger.info("✅ Playwright initialized")

    async def shutdown(self):
        logger.info("🛑 Shutting down BrowserPool...")
        if self.health_check_task:
            self.health_check_task.cancel()
        for task in self.idle_timer_tasks.values():
            task.cancel()
        for worker in list(self.workers.values()):
            await worker.cleanup()
        self.workers.clear()
        self.account_to_worker.clear()
        if self.playwright:
            await self.playwright.stop()
        logger.info("✅ BrowserPool shutdown complete")

    async def acquire_worker(self, account_id: str, platform: str = "gemini") -> Optional[Worker]:
        """
        获取或创建Worker。
        优先复用已有该账号的 Idle Worker；否则从池中分配或创建新的。
        """
        logger.debug(f"🔍 Acquiring worker for account {account_id} (platform={platform})")

        # 1. 复用该账号已有 Worker
        if account_id in self.account_to_worker:
            wid = self.account_to_worker[account_id]
            w = self.workers.get(wid)
            if w and w.status == WorkerStatus.IDLE:
                w.status = WorkerStatus.BUSY
                w.last_used_time = time.time()
                await self._cancel_idle_timer(wid)
                logger.debug(f"♻️  Reusing worker {wid}")
                return w

        # 2. 创建新 Worker（如果池未满）
        if len(self.workers) < self.browser_config.max_workers:
            w = await self._create_worker(account_id, platform)
            if w:
                return w

        # 3. 从 Idle 池中抢占一个
        for w in self.workers.values():
            if w.status == WorkerStatus.IDLE:
                w.status = WorkerStatus.BUSY
                w.account_id = account_id
                w.last_used_time = time.time()
                self.account_to_worker[account_id] = w.id
                await self._cancel_idle_timer(w.id)
                logger.debug(f"🔄 Reassigned idle worker {w.id} to {account_id}")
                return w

        logger.warning(f"❌ No available workers for account {account_id}")
        return None

    async def _create_worker(self, account_id: str, platform: str = "gemini") -> Optional[Worker]:
        try:
            self.worker_counter += 1
            worker_id = f"worker_{self.worker_counter}"
            logger.debug(f"🚀 Creating worker {worker_id}...")

            browser = await self.playwright.chromium.launch(
                headless=self.browser_config.headless,
                executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )

            context = await browser.new_context(
                viewport={
                    "width": self.browser_config.viewport_width,
                    "height": self.browser_config.viewport_height,
                },
                user_agent=self.browser_config.user_agent,
            )

            # === 反自动化检测 Stealth 注入 ===
            # 在所有页面脚本之前执行，覆盖 navigator.webdriver 等指纹
            await context.add_init_script(STEALTH_SCRIPT)

            # === 加载已保存的 Cookie ===
            if self._db:
                cookie_data = self._db.load_cookies(account_id)
                if cookie_data:
                    cookies, local_storage = cookie_data
                    if cookies:
                        await context.add_cookies(cookies)
                        logger.debug(f"🍪 Loaded {len(cookies)} cookies for {account_id}")
                    if local_storage:
                        page = await context.new_page()
                        await page.goto("about:blank")
                        for k, v in local_storage.items():
                            await page.evaluate(f"localStorage.setItem('{k}', '{v}')")
                        logger.debug(f"🍪 Loaded {len(local_storage)} localStorage items")

            page = await context.new_page()

            if self.traffic_config.enabled and platform == "gemini":
                interceptor = TrafficInterceptor(self.traffic_config.block_patterns)
                await page.route("**/*", interceptor.intercept_route)
                await ContentDisabler.inject_blockers(page)
                logger.debug(f"✅ Traffic interceptor enabled for {worker_id}")

            page.set_default_timeout(self.browser_config.timeout_ms)

            from web2api.platforms import get_automator_class
            automator_cls = get_automator_class(platform)
            automator = automator_cls(page)

            pid = None
            try:
                proc = browser.process
                pid = proc.pid if proc else None
            except (AttributeError, TypeError):
                pass

            worker = Worker(
                id=worker_id,
                browser=browser,
                context=context,
                page=page,
                gemini=automator,
                account_id=account_id,
                status=WorkerStatus.BUSY,
                pid=pid,
            )

            self.workers[worker_id] = worker
            self.account_to_worker[account_id] = worker_id

            logger.info(f"✅ Worker {worker_id} created (pid={pid})")
            return worker

        except Exception as e:
            logger.error(f"Failed to create worker: {e}")
            return None

    async def release_worker(self, worker_id: str):
        worker = self.workers.get(worker_id)
        if not worker:
            return
        # 保存 Cookie 到数据库
        if self._db and worker.context and worker.account_id:
            try:
                cookies = await worker.context.cookies()
                if cookies:
                    self._db.save_cookies(worker.account_id, "unknown", cookies)
            except Exception as e:
                logger.debug(f"Failed to save cookies for {worker.account_id}: {e}")
        worker.status = WorkerStatus.IDLE
        worker.last_used_time = time.time()
        logger.debug(f"✓ Worker {worker_id} released to idle")
        await self._start_idle_timer(worker_id)

    async def _start_idle_timer(self, worker_id: str):
        await self._cancel_idle_timer(worker_id)

        async def idle_timeout():
            try:
                await asyncio.sleep(self.browser_config.idle_timeout_min * 60)
                w = self.workers.get(worker_id)
                if w and w.status == WorkerStatus.IDLE:
                    logger.info(f"⏰ Idle timeout for {worker_id}, killing...")
                    await self.kill_worker(worker_id)
            except asyncio.CancelledError:
                pass

        self.idle_timer_tasks[worker_id] = asyncio.create_task(idle_timeout())

    async def _cancel_idle_timer(self, worker_id: str):
        task = self.idle_timer_tasks.pop(worker_id, None)
        if task:
            task.cancel()

    async def kill_worker(self, worker_id: str):
        worker = self.workers.pop(worker_id, None)
        if not worker:
            return
        await self._cancel_idle_timer(worker_id)
        if worker.account_id in self.account_to_worker:
            del self.account_to_worker[worker.account_id]
        await worker.cleanup()
        logger.info(f"💀 Worker {worker_id} killed")

    async def start_health_check(self, interval_sec: int = 300):
        async def health_check_loop():
            while True:
                try:
                    await asyncio.sleep(interval_sec)
                    for w in list(self.workers.values()):
                        if w.status == WorkerStatus.IDLE and w.gemini:
                            try:
                                await w.gemini.health_check()
                            except Exception as e:
                                logger.warning(f"Health check failed for {w.id}: {e}")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Health check loop error: {e}")

        self.health_check_task = asyncio.create_task(health_check_loop())
        logger.info(f"❤️  Health check started (interval={interval_sec}s)")

    async def check_worker_memory(self, worker_id: str, limit_mb: float = 1500) -> bool:
        """
        检查 Worker 内存使用，超限则 kill。

        Returns:
            True 表示触发了熔断（Worker 被杀）
        """
        w = self.workers.get(worker_id)
        if not w or not w.gemini:
            return False

        mem = await w.gemini.get_memory_usage()
        w.memory_usage_mb = mem

        if mem > limit_mb:
            logger.warning(
                f"🔥 Worker {worker_id} memory {mem:.0f}MB exceeds limit {limit_mb}MB, killing"
            )
            await self.kill_worker(worker_id)
            return True
        return False

    def get_pool_stats(self) -> dict:
        stats = {
            "total_workers": len(self.workers),
            "idle_workers": sum(1 for w in self.workers.values() if w.status == WorkerStatus.IDLE),
            "busy_workers": sum(1 for w in self.workers.values() if w.status == WorkerStatus.BUSY),
            "cooldown_workers": sum(1 for w in self.workers.values() if w.status == WorkerStatus.COOLDOWN),
            "total_memory_mb": sum(w.memory_usage_mb for w in self.workers.values()),
            "max_workers": self.browser_config.max_workers,
        }
        stats["pool_usage"] = f"{stats['total_workers']}/{stats['max_workers']}"
        return stats
