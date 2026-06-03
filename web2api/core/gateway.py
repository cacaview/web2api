"""API Gateway - 核心网关路由

整合 AccountPool、BrowserPool、SessionRouter、QuotaEngine，
实现 PRD 3.1 核心请求处理链路（新会话 / 老会话两条路径）。
"""

from typing import Optional, Dict
from datetime import datetime
import asyncio
import uuid
import redis.asyncio as aioredis
from loguru import logger

from web2api.config import AppConfig
from web2api.core.browser_pool import BrowserPool
from web2api.core.session_router import SessionRouter, ConversationStatus
from web2api.core.quota_engine import QuotaEngine
from web2api.core.account_pool import AccountPool
from web2api.core.storage import get_store, SQLiteStore
from web2api.platforms import resolve_platform, PLATFORMS, get_automator_class
from web2api.platforms.base import PlatformError


class APIGateway:
    """
    web2api 核心API网关

    职责：
    1. 请求路由与分发
    2. 账号与会话映射
    3. 配额控制与风险防护
    4. 流式数据转发
    5. 内存熔断
    """

    def __init__(self, config: AppConfig):
        self.config = config

        self.redis: Optional[aioredis.Redis] = None
        self.browser_pool: Optional[BrowserPool] = None
        self.session_router: Optional[SessionRouter] = None
        self.quota_engine: Optional[QuotaEngine] = None
        self.account_pool: Optional[AccountPool] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._redis_available = False
        self.db: Optional[SQLiteStore] = None

        logger.info(f"🎯 APIGateway initialized (debug={config.debug})")

    async def initialize(self):
        logger.info("🚀 Initializing APIGateway...")

        try:
            self.redis = aioredis.from_url(
                f"redis://{self.config.redis.host}:{self.config.redis.port}",
                db=self.config.redis.db,
                password=self.config.redis.password if self.config.redis.password else None,
                decode_responses=False,
            )
            await self.redis.ping()
            logger.info(f"✅ Redis connected: {self.config.redis.host}:{self.config.redis.port}")
            self._redis_available = True
        except Exception as e:
            logger.warning(f"⚠️  Redis unavailable ({e}), running in standalone mode")
            self.redis = None
            self._redis_available = False

        self.account_pool = AccountPool(self.config.account_pool.accounts)

        # 初始化 SQLite 持久化存储
        self.db = get_store()
        self._load_accounts_from_db()

        self.browser_pool = BrowserPool(
            self.config.browser,
            self.config.traffic_intercept,
        )
        await self.browser_pool.initialize()

        if self._redis_available:
            self.session_router = SessionRouter(self.redis, self.config.session.ttl_days)
            self.quota_engine = QuotaEngine(self.redis, self.config.rate_limit)
            await self.browser_pool.start_health_check(self.config.gemini.health_check_interval_sec)
            self._cleanup_task = asyncio.create_task(self._ttl_cleanup_loop())
        else:
            logger.info("📦 SQLite 本地持久化已启用 (无 Redis)")

        logger.info("✅ APIGateway initialized successfully")

    async def shutdown(self):
        logger.info("🛑 Shutting down APIGateway...")
        if self._cleanup_task:
            self._cleanup_task.cancel()
        self._save_accounts_to_db()
        if self.browser_pool:
            await self.browser_pool.shutdown()
        if self.redis:
            await self.redis.close()
        if self.db:
            self.db.close()
        logger.info("✅ APIGateway shutdown complete")

    def _load_accounts_from_db(self):
        """从 SQLite 加载账号状态"""
        if not self.db or not self.account_pool:
            return
        try:
            for acc_data in self.db.get_all_accounts():
                acc = self.account_pool.get_account(acc_data["account_id"])
                if acc:
                    acc.status = acc_data["status"]
                    acc.current_usage_3h = acc_data.get("current_usage_3h", 0)
                    acc.cooldown_until = acc_data.get("cooldown_until", 0)
                    acc.worker_id = acc_data.get("worker_id")
            logger.info(f"📦 Loaded {len(self.db.get_all_accounts())} accounts from SQLite")
        except Exception as e:
            logger.error(f"Failed to load accounts from DB: {e}")

    def _save_accounts_to_db(self):
        """保存账号状态到 SQLite"""
        if not self.db or not self.account_pool:
            return
        try:
            for acc in self.account_pool.accounts.values():
                self.db.save_account(
                    acc.account_id, acc.status.value,
                    acc.current_usage_3h, acc.cooldown_until, acc.worker_id
                )
        except Exception as e:
            logger.error(f"Failed to save accounts to DB: {e}")

    def _persist_account(self, account_id: str):
        """单个账号状态变更时持久化"""
        if not self.db:
            return
        acc = self.account_pool.get_account(account_id) if self.account_pool else None
        if acc:
            self.db.save_account(
                acc.account_id, acc.status.value,
                acc.current_usage_3h, acc.cooldown_until, acc.worker_id
            )

    async def _ttl_cleanup_loop(self):
        """PRD: 3天生命周期自动清理器 - 扫地僧任务"""
        interval = self.config.session.cleanup_interval_sec
        logger.info(f"🧹 TTL cleanup task started (interval={interval}s)")
        while True:
            try:
                await asyncio.sleep(interval)
                if self.session_router:
                    cleaned = await self.session_router.cleanup_expired_sessions(
                        self.config.session.ttl_days
                    )
                    if cleaned > 0:
                        logger.info(f"🧹 TTL cleanup: removed {cleaned} expired sessions")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"TTL cleanup error: {e}")

    async def handle_message(
        self,
        conversation_id: Optional[str],
        message: str,
        account_id: str,
        platform: str = "gemini",
    ) -> Dict:
        """
        处理客户端消息（PRD 3.1 完整链路）。
        支持多平台：gemini / chatgpt / claude / deepseek / kimi / qwen
        """
        logger.info(f"📨 Handling message (conv={conversation_id}, account={account_id})")

        try:
            # === 场景 B/B': 老会话 ===
            if conversation_id:
                session = await self.session_router.get_session(conversation_id)

                # 会话已过期/被熔断 → 无感重建
                if session and session.status == ConversationStatus.DELETED:
                    logger.info(f"♻️  Session {conversation_id} expired, rebuilding...")
                    conversation_id = None  # 转入场景 A
                # 会话被熔断但未删除 → 触发清理
                elif session and session.status == ConversationStatus.MEMORY_BLOWN:
                    logger.info(f"🔥 Session {conversation_id} memory-blown, cleaning...")
                    await self._handle_meltdown(session)
                    conversation_id = None
                # 会话正常 → 使用映射的 account
                elif session:
                    account_id = session.bound_account_id

            # === 场景 A: 新会话（或 B' 重建） ===
            if not conversation_id:
                return await self._handle_new_session(message, account_id, platform)

            # === 场景 B: 老会话正常续接 ===
            return await self._handle_existing_session(conversation_id, message, account_id, platform)

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return {
                "status": "error",
                "error": str(e),
                "http_status": 500,
            }

    async def _handle_new_session(self, message: str, account_id: str, platform: str = "gemini") -> Dict:
        """场景 A: 新建会话完整流程"""

        # 1. 选择可用账号
        acc = self.account_pool.select_account(account_id, platform)
        if not acc:
            return {"status": "error", "error": "No available accounts", "http_status": 503}
        account_id = acc.account_id

        # 2. 检查配额
        if self.quota_engine:
            quota = await self.quota_engine.check_quota(account_id)
            if not quota["is_available"]:
                acc.set_cooldown(self.config.rate_limit.cooldown_minutes)
                return {
                    "status": "rate_limited",
                    "error": f"Account {account_id} rate limited",
                    "quota_info": quota,
                    "http_status": 429,
                }

        # 3. 获取 Worker
        worker = await self.browser_pool.acquire_worker(account_id, platform)
        if not worker:
            return {"status": "error", "error": "No available workers", "http_status": 503}

        acc.set_busy(worker.id)

        try:
            # 4. 初始化平台页面
            if not await worker.gemini.initialize():
                return {"status": "error", "error": f"Failed to initialize {platform}", "http_status": 500}

            # 5. 创建新对话
            if not await worker.gemini.create_new_chat():
                return {"status": "error", "error": "Failed to create new chat", "http_status": 500}

            # 6. 发送首条消息
            if not await worker.gemini.send_message(message):
                return {"status": "error", "error": "Failed to send message", "http_status": 500}

            # 7. 等待流式响应
            response = await worker.gemini.wait_for_response()

            # 8. 检查官方错误（结构化）
            gemini_error = await worker.gemini.check_for_errors()
            if not gemini_error:
                gemini_error = worker.gemini.get_last_error()
            if gemini_error:
                return await self._handle_gemini_error(gemini_error, worker, acc, account_id)

            # 9. 异步捕获 URL 并创建会话
            web_url_id = worker.gemini.get_conversation_id() or ""
            conv_id = f"local_{uuid.uuid4().hex[:8]}"
            count = 1
            quota_info = {}

            if self.session_router:
                conv_id = await self.session_router.create_session(account_id)
                if web_url_id:
                    await self.session_router.update_web_url(conv_id, web_url_id)
                count = await self.session_router.update_interaction_count(conv_id)
            elif self.db:
                # SQLite 持久化（无 Redis 模式）
                self.db.save_session(conv_id, account_id, web_url_id, 1, "active")
                count = 1

            if self.quota_engine:
                quota_info = await self.quota_engine.record_request(
                    account_id, f"req_{conv_id}_{count}"
                )

            # 11. 检查内存
            mem = await worker.gemini.get_memory_usage()
            worker.memory_usage_mb = mem
            should_blow = mem > self.config.account_pool.memory_limit_mb

            if self.session_router:
                should_blow = await self.session_router.check_memory_limit(conv_id, mem)

            if should_blow:
                await self._trigger_meltdown(worker, conv_id)
                response = response + "\n\n[Note: Session reset due to memory limit]"

            await self.browser_pool.release_worker(worker.id)
            acc.set_idle()

            return {
                "status": "success",
                "conversation_id": conv_id,
                "response": response,
                "interaction_count": count,
                "quota_info": quota_info,
                "metadata": {
                    "worker_id": worker.id,
                    "account_id": account_id,
                    "memory_mb": mem,
                    "timestamp": datetime.now().isoformat(),
                },
            }

        except Exception as e:
            logger.error(f"Error in new session: {e}")
            await self._safe_release(worker, acc)
            return {"status": "error", "error": str(e), "http_status": 500}

    async def _handle_existing_session(
        self, conversation_id: str, message: str, account_id: str, platform: str = "gemini"
    ) -> Dict:
        """场景 B: 老会话续接流程"""

        if not self.session_router:
            return {"status": "error", "error": "Session management unavailable (no Redis)", "http_status": 503}

        # 1. 获取会话映射
        session = await self.session_router.get_session(conversation_id)
        if not session or not session.web_chat_url_id:
            return {"status": "error", "error": "Session not found or no URL mapped", "http_status": 404}

        account_id = session.bound_account_id

        # 2. 检查配额
        if self.quota_engine:
            quota = await self.quota_engine.check_quota(account_id)
            if not quota["is_available"]:
                return {
                    "status": "rate_limited",
                    "error": f"Account {account_id} rate limited",
                    "quota_info": quota,
                    "http_status": 429,
                }

        # 3. 获取 Worker
        acc = self.account_pool.get_account(account_id)
        if acc:
            worker = await self.browser_pool.acquire_worker(account_id, platform)
        else:
            # 账号不在池中，尝试分配任意账号
            acc = self.account_pool.select_account(platform=platform)
            if not acc:
                return {"status": "error", "error": "No available accounts", "http_status": 503}
            account_id = acc.account_id
            worker = await self.browser_pool.acquire_worker(account_id, platform)

        if not worker:
            return {"status": "error", "error": "No available workers", "http_status": 503}

        acc.set_busy(worker.id)

        try:
            # 4. 导航到已有对话
            if not await worker.gemini.navigate_to_conversation(session.web_chat_url_id):
                return {"status": "error", "error": "Failed to navigate to conversation", "http_status": 500}

            # 5. 检查内存（PRD 3.2）
            mem = await worker.gemini.get_memory_usage()
            worker.memory_usage_mb = mem
            mem_killed = await self.browser_pool.check_worker_memory(worker.id, self.config.account_pool.memory_limit_mb)
            if mem_killed:
                await self._handle_meltdown(session)
                return {
                    "status": "error",
                    "error": "Memory circuit breaker triggered",
                    "http_status": 500,
                }

            # 6. 发送消息
            if not await worker.gemini.send_message(message):
                return {"status": "error", "error": "Failed to send message", "http_status": 500}

            # 7. 等待响应
            response = await worker.gemini.wait_for_response()

            # 8. 检查错误（结构化）
            gemini_error = await worker.gemini.check_for_errors()
            if not gemini_error:
                gemini_error = worker.gemini.get_last_error()
            if gemini_error:
                return await self._handle_gemini_error(gemini_error, worker, acc, account_id)

            # 9. 更新交互计数 & 配额
            count = await self.session_router.update_interaction_count(conversation_id)
            quota_info = await self.quota_engine.record_request(
                account_id, f"req_{conversation_id}_{count}"
            )

            # 10. 内存熔断检查（PRD 3.2）
            should_blow = await self.session_router.check_memory_limit(conversation_id, mem)
            if should_blow:
                await self._trigger_meltdown(worker, conversation_id)
                response = response + "\n\n[Note: Session reset due to memory limit]"

            await self.browser_pool.release_worker(worker.id)
            if acc:
                acc.set_idle()

            return {
                "status": "success",
                "conversation_id": conversation_id,
                "response": response,
                "interaction_count": count,
                "quota_info": quota_info,
                "metadata": {
                    "worker_id": worker.id,
                    "account_id": account_id,
                    "memory_mb": mem,
                    "timestamp": datetime.now().isoformat(),
                },
            }

        except Exception as e:
            logger.error(f"Error in existing session: {e}")
            await self._safe_release(worker, acc)
            return {"status": "error", "error": str(e), "http_status": 500}

    async def _trigger_meltdown(self, worker, conversation_id: str):
        """PRD 3.2: 长会话内存熔断"""
        logger.warning(f"🔥 Memory meltdown triggered for {conversation_id}")
        try:
            await worker.gemini.delete_conversation()
        except Exception as e:
            logger.debug(f"Delete conversation failed: {e}")
        await self.session_router.mark_expired(conversation_id)

    async def _handle_meltdown(self, session):
        """处理已标记为 memory_blown 的会话"""
        logger.info(f"🔥 Cleaning up memory-blown session {session.client_conversation_id}")
        await self.session_router.mark_expired(session.client_conversation_id)

    async def _safe_release(self, worker, acc=None):
        try:
            await self.browser_pool.release_worker(worker.id)
            if acc:
                acc.set_idle()
        except Exception:
            pass

    async def _handle_gemini_error(
        self, error: PlatformError, worker, acc, account_id: str
    ) -> Dict:
        """根据 PlatformError 类型自动更新账号状态并返回错误响应"""
        logger.warning(f"🚨 [{account_id}] Platform error [{error.error_type}]: {error.message}")

        # 更新账号状态
        if acc:
            if error.error_type == "rate_limit":
                acc.set_cooldown(error.cooldown_minutes or 90)
            elif error.error_type == "banned":
                acc.set_maintenance()
            elif error.error_type == "captcha":
                acc.set_cooldown(error.cooldown_minutes or 30)
            elif error.error_type == "login_required":
                acc.set_maintenance()
            elif error.error_type == "content_blocked":
                acc.set_cooldown(error.cooldown_minutes or 10)
            elif error.error_type == "maintenance":
                acc.set_cooldown(error.cooldown_minutes or 15)
            self._persist_account(account_id)
            if self.db:
                self.db.log_event("error", account_id, error.error_type, error.message)

        # 终止 Worker（严重错误）
        if error.should_kill_worker:
            await self.browser_pool.kill_worker(worker.id)
        else:
            await self._safe_release(worker, acc)

        # 映射到 HTTP 状态码
        http_status_map = {
            "rate_limit": 429,
            "banned": 503,
            "captcha": 503,
            "login_required": 503,
            "content_blocked": 400,
            "maintenance": 503,
            "unknown": 500,
        }
        http_status = http_status_map.get(error.error_type, 500)

        return {
            "status": "error",
            "error": error.message,
            "error_type": error.error_type,
            "account_id": account_id,
            "http_status": http_status,
        }

    def get_gateway_stats(self) -> dict:
        return {
            "browser_pool": self.browser_pool.get_pool_stats() if self.browser_pool else {},
            "account_pool": self.account_pool.get_pool_stats() if self.account_pool else {},
            "timestamp": datetime.now().isoformat(),
        }
