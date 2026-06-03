"""Base automator for all AI platforms - 通用平台自动化基类"""

import asyncio
import re
from dataclasses import dataclass
from typing import Optional, Dict, List
from loguru import logger
from playwright.async_api import Page
from web2api.core.humanizer import GaussianHumanizer


@dataclass
class PlatformError:
    """平台返回的结构化错误"""
    error_type: str       # rate_limit / banned / captcha / login_required / content_blocked / maintenance / unknown
    message: str
    raw_text: str = ""
    should_kill_worker: bool = False
    cooldown_minutes: int = 0


class BaseAutomator:
    """
    所有 AI 平台的统一自动化基类。

    子类只需覆写：
    - SELECTORS: 平台特有的CSS选择器
    - URLS: 平台URL配置
    - ERROR_PATTERNS: 平台特有的错误模式
    - send_message(): 平台特有的输入方式（如 textarea vs contenteditable）
    """

    # 子类必须覆写
    PLATFORM_NAME = "base"
    URLS = {
        "base": "https://example.com",
        "new_chat": "https://example.com/new",
    }
    SELECTORS: Dict[str, List[str]] = {}
    ERROR_PATTERNS: Dict[str, List[str]] = {
        "rate_limit": ["rate limit", "too many requests", "please slow down"],
        "banned": ["suspended", "banned", "account disabled"],
        "captcha": ["captcha", "verify you are human"],
        "login_required": ["sign in", "log in", "session expired"],
        "content_blocked": ["blocked", "content policy", "not available"],
    }
    REQUIRES_LOGIN = True
    SUPPORTS_GUEST = False

    def __init__(self, page: Page):
        self.page = page
        self.conversation_url_id: Optional[str] = None
        self.response_buffer = ""
        self.is_streaming = False
        self._cached_selectors: dict = {}
        self._last_error: Optional[PlatformError] = None

    def get_last_error(self) -> Optional[PlatformError]:
        return self._last_error

    async def initialize(self) -> bool:
        """初始化：导航到平台并检测可用性"""
        try:
            logger.info(f"🚀 [{self.PLATFORM_NAME}] Initializing at {self.URLS['base']}")
            await self.page.goto(self.URLS["base"], wait_until="domcontentloaded")
            # 等待 SPA 渲染
            await asyncio.sleep(5)

            accessible = await self._check_accessibility()
            if not accessible:
                logger.error(f"❌ [{self.PLATFORM_NAME}] Not accessible")
                return False

            logger.info(f"✅ [{self.PLATFORM_NAME}] Initialized successfully")
            return True
        except Exception as e:
            logger.error(f"[{self.PLATFORM_NAME}] Init failed: {e}")
            return False

    async def _check_accessibility(self) -> bool:
        """检测页面是否可用"""
        # 先尝试直接查找
        input_field = await self._find_element("input")
        if input_field:
            return True
        # 等待 SPA 渲染
        for sel in self.SELECTORS.get("input", []):
            try:
                await self.page.wait_for_selector(sel, timeout=15000)
                return True
            except Exception:
                continue
        # Debug: 打印页面信息
        try:
            title = await self.page.title()
            url = self.page.url
            text = await self.page.evaluate("() => document.body?.innerText?.substring(0, 200) || ''")
            logger.debug(f"[{self.PLATFORM_NAME}] Page: title={title}, url={url}, text={text[:100]}")
        except Exception:
            pass
        return False

    async def create_new_chat(self) -> bool:
        """创建新对话"""
        try:
            logger.debug(f"[{self.PLATFORM_NAME}] Creating new chat")

            # 尝试新对话按钮
            new_chat_btn = await self._find_element("new_chat")
            if new_chat_btn:
                await GaussianHumanizer.humanized_click(self.page, new_chat_btn)
                await asyncio.sleep(2)
                logger.info(f"✅ [{self.PLATFORM_NAME}] New chat created")
                return True

            # 尝试导航到新对话URL
            if "new_chat" in self.URLS:
                current = self.page.url
                target = self.URLS["new_chat"]
                if current != target:
                    await self.page.goto(target, wait_until="networkidle")
                    await asyncio.sleep(2)
                    logger.info(f"✅ [{self.PLATFORM_NAME}] New chat via navigation")
                    return True

            logger.info(f"✅ [{self.PLATFORM_NAME}] Already on fresh page")
            return True
        except Exception as e:
            logger.error(f"[{self.PLATFORM_NAME}] Failed to create new chat: {e}")
            return False

    async def send_message(self, message: str) -> bool:
        """发送消息（子类可覆写）"""
        try:
            logger.debug(f"[{self.PLATFORM_NAME}] Sending: {message[:50]}...")

            # 检查页面错误
            pre_error = await self.detect_page_errors()
            if pre_error:
                self._last_error = pre_error
                logger.error(f"[{self.PLATFORM_NAME}] Pre-send error: {pre_error.error_type}")
                return False

            input_field = await self._find_element("input")
            if not input_field:
                logger.error(f"[{self.PLATFORM_NAME}] Input field not found")
                return False

            logger.debug(f"[{self.PLATFORM_NAME}] Input found, clicking...")

            # 点击输入框获取焦点
            await GaussianHumanizer.humanized_click(self.page, input_field)
            await asyncio.sleep(0.3)

            # 清空并输入
            await input_field.press("Control+a")
            await asyncio.sleep(0.1)
            await input_field.press("Backspace")
            await asyncio.sleep(0.2)

            await GaussianHumanizer.humanized_type(
                self.page, input_field, message, delay_min=30, delay_max=100
            )
            await asyncio.sleep(1.0)

            logger.debug(f"[{self.PLATFORM_NAME}] Typed message, looking for send button...")

            # 点击发送
            for attempt in range(3):
                send_btn = await self._find_element("send")
                if send_btn:
                    # 优先用 page.click 直接点击选择器（坐标更准确）
                    cached_sel = self._cached_selectors.get("send")
                    if cached_sel:
                        try:
                            await self.page.click(cached_sel, timeout=3000)
                        except Exception:
                            await GaussianHumanizer.humanized_click(self.page, send_btn)
                    else:
                        await GaussianHumanizer.humanized_click(self.page, send_btn)

                    self.is_streaming = True
                    self.response_buffer = ""

                    # 发送后检测错误
                    await asyncio.sleep(2)
                    post_error = await self.detect_page_errors()
                    if post_error and post_error.error_type in ("rate_limit", "banned", "captcha"):
                        self._last_error = post_error
                        self.is_streaming = False
                        return False

                    logger.info(f"✅ [{self.PLATFORM_NAME}] Message sent")
                    return True
                await asyncio.sleep(0.5)

            # 备选 Enter
            try:
                await input_field.press("Enter")
                self.is_streaming = True
                self.response_buffer = ""
                logger.info(f"✅ [{self.PLATFORM_NAME}] Message sent via Enter")
                return True
            except Exception:
                pass

            logger.error(f"[{self.PLATFORM_NAME}] Could not send message")
            return False
        except Exception as e:
            logger.error(f"[{self.PLATFORM_NAME}] send_message failed: {e}")
            return False

    async def wait_for_response(self, timeout_sec: float = 120) -> str:
        """等待响应完成"""
        try:
            logger.debug(f"[{self.PLATFORM_NAME}] Waiting for response...")
            stable_count = 0
            required_stable = 3
            poll_interval = 0.5
            last_text = ""
            elapsed = 0.0

            while elapsed < timeout_sec:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                # 定期检测错误
                if int(elapsed) % 5 == 0 and int(elapsed) > 0:
                    err = await self.detect_page_errors()
                    if err and err.error_type in ("rate_limit", "banned", "captcha", "login_required"):
                        self._last_error = err
                        self.is_streaming = False
                        return ""

                current_text = await self._extract_response()

                if current_text and current_text == last_text:
                    stable_count += 1
                    if stable_count >= required_stable and current_text.strip():
                        self.response_buffer = current_text
                        self.is_streaming = False
                        logger.info(f"✅ [{self.PLATFORM_NAME}] Response ({len(current_text)} chars, {elapsed:.1f}s)")
                        return current_text
                else:
                    stable_count = 0
                    last_text = current_text

            logger.warning(f"[{self.PLATFORM_NAME}] Timeout after {timeout_sec}s")
            self.response_buffer = last_text
            self.is_streaming = False
            return last_text
        except Exception as e:
            logger.error(f"[{self.PLATFORM_NAME}] wait_for_response failed: {e}")
            self.is_streaming = False
            return self.response_buffer

    async def _extract_response(self) -> str:
        """提取最新响应文本"""
        selectors = self.SELECTORS.get("response", [])
        for sel in selectors:
            try:
                elements = await self.page.query_selector_all(sel)
                if elements:
                    last = elements[-1]
                    text = (await last.inner_text()).strip()
                    if text:
                        return text
            except Exception:
                continue
        return ""

    async def check_for_errors(self) -> Optional[PlatformError]:
        """检测页面错误"""
        try:
            page_text = await self.page.evaluate("() => document.body.innerText")
            lower = page_text.lower()

            priority = ["captcha", "banned", "rate_limit", "content_blocked", "login_required", "maintenance"]
            for error_type in priority:
                patterns = self.ERROR_PATTERNS.get(error_type, [])
                for pattern in patterns:
                    if pattern.lower() in lower:
                        return self._classify_error(error_type, pattern, page_text[:500])
            return None
        except Exception:
            return None

    async def detect_page_errors(self) -> Optional[PlatformError]:
        """全面页面错误检测"""
        try:
            # URL 检测
            url = self.page.url
            if "accounts.google.com" in url or "/sorry" in url or "/blocked" in url:
                return PlatformError("login_required", "Redirected to login/block page", url)

            # CAPTCHA 检测（多种类型）
            captcha_selectors = [
                'iframe[src*="captcha"]', 'iframe[src*="recaptcha"]',
                '.g-recaptcha', '[class*="captcha"]', '[id*="captcha"]',
                'iframe[src*="challenges.cloudflare"]',  # Cloudflare Turnstile
                '[class*="turnstile"]',
                'div:has-text("请验证您是真人")',  # Chinese CAPTCHA
                'div:has-text("Verify you are human")',
            ]
            for sel in captcha_selectors:
                try:
                    el = await self.page.query_selector(sel)
                    if el and await el.is_visible():
                        return PlatformError("captcha", "CAPTCHA/verification detected", should_kill_worker=False, cooldown_minutes=30)
                except Exception:
                    pass

            # 检测 Cloudflare challenge 页面
            page_text = await self.page.evaluate("() => document.body?.innerText?.substring(0, 500) || ''")
            if "checking your browser" in page_text.lower() or "just a moment" in page_text.lower():
                return PlatformError("captcha", "Cloudflare challenge page", should_kill_worker=False, cooldown_minutes=30)

            # 文本错误检测
            text_err = await self.check_for_errors()
            if text_err:
                return text_err

            return None
        except Exception:
            return None

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            input_field = await self._find_element("input")
            if input_field:
                await GaussianHumanizer.humanized_click(self.page, input_field)
                await input_field.type(".", delay=30)
                await asyncio.sleep(0.2)
                await input_field.press("Backspace")
                return True
            return False
        except Exception:
            return False

    async def get_memory_usage(self) -> float:
        try:
            mem = await self.page.evaluate("""
                () => performance.memory ? performance.memory.usedJSHeapSize / (1024*1024) : 0
            """)
            return mem
        except Exception:
            return 0.0

    def get_conversation_id(self) -> Optional[str]:
        return self.conversation_url_id

    async def _find_element(self, element_type: str):
        """查找页面元素"""
        if element_type in self._cached_selectors:
            cached = self._cached_selectors[element_type]
            try:
                el = await self.page.query_selector(cached)
                if el and await el.is_visible():
                    return el
            except Exception:
                del self._cached_selectors[element_type]

        for sel in self.SELECTORS.get(element_type, []):
            try:
                el = await self.page.query_selector(sel)
                if el:
                    # 对发送按钮，即使 disabled 也返回（输入后会启用）
                    if element_type == "send" or await el.is_visible():
                        self._cached_selectors[element_type] = sel
                        return el
            except Exception:
                pass
        return None

    def _classify_error(self, error_type: str, pattern: str, raw: str) -> PlatformError:
        configs = {
            "rate_limit": ("Rate limit exceeded", False, 90),
            "banned": ("Account banned/suspended", True, 0),
            "captcha": ("CAPTCHA verification required", False, 30),
            "login_required": ("Login required", False, 0),
            "content_blocked": ("Content blocked by safety filter", False, 10),
            "maintenance": ("Service temporarily unavailable", False, 15),
        }
        msg, kill, cd = configs.get(error_type, (f"Unknown: {pattern}", False, 0))
        return PlatformError(error_type, msg, raw, kill, cd)
