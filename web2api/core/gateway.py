"""API Gateway - SQLite-only mode (no Redis dependency)"""

from typing import Optional, Dict
from datetime import datetime
import asyncio
import uuid
from loguru import logger

from web2api.config import AppConfig
from web2api.core.browser_pool import BrowserPool
from web2api.core.session_router import SessionRouter, ConversationStatus
from web2api.core.quota_engine import QuotaEngine
from web2api.core.account_pool import AccountPool
from web2api.core.storage import get_store, SQLiteStore
from web2api.platforms import resolve_platform, PLATFORMS
from web2api.platforms.base import PlatformError


class APIGateway:
    def __init__(self, config: AppConfig):
        self.config = config
        self.browser_pool: Optional[BrowserPool] = None
        self.session_router: Optional[SessionRouter] = None
        self.quota_engine: Optional[QuotaEngine] = None
        self.account_pool: Optional[AccountPool] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self.db: Optional[SQLiteStore] = None
        logger.info(f"🎯 APIGateway initialized (debug={config.debug})")

    async def initialize(self):
        logger.info("🚀 Initializing APIGateway...")

        # SQLite 存储
        self.db = get_store()
        self._load_accounts_from_db()

        # 账号池
        self.account_pool = AccountPool(self.config.account_pool.accounts)

        # 浏览器池
        self.browser_pool = BrowserPool(self.config.browser, self.config.traffic_intercept)
        self.browser_pool._db = self.db
        await self.browser_pool.initialize()

        # Session 路由 (SQLite)
        self.session_router = SessionRouter(self.db, self.config.session.ttl_days)

        # 配额引擎 (SQLite)
        self.quota_engine = QuotaEngine(self.db, self.config.rate_limit)

        # 启动清理任务
        self._cleanup_task = asyncio.create_task(self._ttl_cleanup_loop())

        logger.info("✅ APIGateway initialized successfully (SQLite mode)")

    async def shutdown(self):
        logger.info("🛑 Shutting down APIGateway...")
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self.browser_pool:
            await self.browser_pool.shutdown()
        if self.db:
            self.db.close()
        logger.info("✅ APIGateway shutdown complete")

    async def _ttl_cleanup_loop(self):
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

    def _load_accounts_from_db(self):
        if not self.db:
            return
        try:
            for acc_data in self.db.get_all_accounts():
                # SQLite accounts are loaded into pool during init
                pass
            logger.info(f"📦 Loaded accounts from SQLite")
        except Exception as e:
            logger.error(f"Failed to load accounts from DB: {e}")

    def _save_accounts_to_db(self):
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
        if not self.db:
            return
        acc = self.account_pool.get_account(account_id) if self.account_pool else None
        if acc:
            self.db.save_account(
                acc.account_id, acc.status.value,
                acc.current_usage_3h, acc.cooldown_until, acc.worker_id
            )

    async def handle_message(
        self,
        conversation_id: Optional[str],
        message: str,
        account_id: str,
        platform: str = "gemini",
    ) -> Dict:
        logger.info(f"📨 Handling message (conv={conversation_id}, account={account_id}, platform={platform})")

        try:
            # 场景 B/B': 老会话
            if conversation_id:
                session = await self.session_router.get_session(conversation_id)
                if session and session.status == ConversationStatus.DELETED:
                    logger.info(f"♻️  Session {conversation_id} expired, rebuilding...")
                    conversation_id = None
                elif session and session.status == ConversationStatus.MEMORY_BLOWN:
                    logger.info(f"🔥 Session {conversation_id} memory-blown, cleaning...")
                    await self.session_router.mark_expired(conversation_id)
                    conversation_id = None
                elif session:
                    account_id = session.bound_account_id

            # 场景 A: 新会话
            if not conversation_id:
                return await self._handle_new_session(message, account_id, platform)

            # 场景 B: 老会话续接
            return await self._handle_existing_session(conversation_id, message, account_id, platform)

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return {"status": "error", "error": str(e), "http_status": 500}

    async def _handle_new_session(self, message: str, account_id: str, platform: str = "gemini") -> Dict:
        # 1. 选择账号
        acc = self.account_pool.select_account(account_id, platform)
        if not acc:
            return {"status": "error", "error": "No available accounts", "http_status": 503}
        account_id = acc.account_id

        # 2. 检查配额
        quota = await self.quota_engine.check_quota(account_id)
        if not quota["is_available"]:
            acc.set_cooldown(self.config.rate_limit.cooldown_minutes)
            return {"status": "rate_limited", "error": f"Account {account_id} rate limited", "quota_info": quota, "http_status": 429}

        # 3. 获取 Worker
        worker = await self.browser_pool.acquire_worker(account_id, platform)
        if not worker:
            return {"status": "error", "error": "No available workers", "http_status": 503}
        acc.set_busy(worker.id)

        try:
            # 4. 初始化
            if not await worker.gemini.initialize():
                return {"status": "error", "error": f"Failed to initialize {platform}", "http_status": 500}

            # 5. 新建对话
            if not await worker.gemini.create_new_chat():
                return {"status": "error", "error": "Failed to create new chat", "http_status": 500}

            # 6. 发送消息
            if not await worker.gemini.send_message(message):
                return {"status": "error", "error": "Failed to send message", "http_status": 500}

            # 7. 等待响应
            response = await worker.gemini.wait_for_response()

            # 8. 检查错误
            gemini_error = await worker.gemini.check_for_errors()
            if not gemini_error:
                gemini_error = worker.gemini.get_last_error()
            if gemini_error:
                return await self._handle_platform_error(gemini_error, worker, acc, account_id)

            # 9. 创建会话
            web_url_id = worker.gemini.get_conversation_id() or ""
            conv_id = await self.session_router.create_session(account_id)
            if web_url_id:
                await self.session_router.update_web_url(conv_id, web_url_id)
            count = await self.session_router.update_interaction_count(conv_id)

            # 10. 记录配额
            quota_info = await self.quota_engine.record_request(account_id, f"req_{conv_id}_{count}")

            # 11. 内存检查
            mem = await worker.gemini.get_memory_usage()
            worker.memory_usage_mb = mem
            should_blow = await self.session_router.check_memory_limit(conv_id, mem)
            if should_blow:
                await self._trigger_meltdown(worker, conv_id)
                response = response + "\n\n[Note: Session reset due to memory limit]"

            await self.browser_pool.release_worker(worker.id)
            acc.set_idle()
            self._persist_account(account_id)

            return {
                "status": "success",
                "conversation_id": conv_id,
                "response": response,
                "interaction_count": count,
                "quota_info": quota_info,
                "metadata": {"worker_id": worker.id, "account_id": account_id, "memory_mb": mem, "timestamp": datetime.now().isoformat()},
            }

        except Exception as e:
            logger.error(f"Error in new session: {e}")
            await self._safe_release(worker, acc)
            return {"status": "error", "error": str(e), "http_status": 500}

    async def _handle_existing_session(self, conversation_id: str, message: str, account_id: str, platform: str = "gemini") -> Dict:
        session = await self.session_router.get_session(conversation_id)
        if not session or not session.web_chat_url_id:
            return {"status": "error", "error": "Session not found or no URL mapped", "http_status": 404}

        account_id = session.bound_account_id

        quota = await self.quota_engine.check_quota(account_id)
        if not quota["is_available"]:
            return {"status": "rate_limited", "error": f"Account {account_id} rate limited", "quota_info": quota, "http_status": 429}

        acc = self.account_pool.get_account(account_id)
        if acc:
            worker = await self.browser_pool.acquire_worker(account_id, platform)
        else:
            acc = self.account_pool.select_account(platform=platform)
            if not acc:
                return {"status": "error", "error": "No available accounts", "http_status": 503}
            account_id = acc.account_id
            worker = await self.browser_pool.acquire_worker(account_id, platform)

        if not worker:
            return {"status": "error", "error": "No available workers", "http_status": 503}
        acc.set_busy(worker.id)

        try:
            if not await worker.gemini.navigate_to_conversation(session.web_chat_url_id):
                return {"status": "error", "error": "Failed to navigate to conversation", "http_status": 500}

            mem = await worker.gemini.get_memory_usage()
            worker.memory_usage_mb = mem
            if mem > self.config.account_pool.memory_limit_mb:
                await self.browser_pool.kill_worker(worker.id)
                await self.session_router.mark_expired(conversation_id)
                return {"status": "error", "error": "Memory circuit breaker triggered", "http_status": 500}

            if not await worker.gemini.send_message(message):
                return {"status": "error", "error": "Failed to send message", "http_status": 500}

            response = await worker.gemini.wait_for_response()

            gemini_error = await worker.gemini.check_for_errors()
            if not gemini_error:
                gemini_error = worker.gemini.get_last_error()
            if gemini_error:
                return await self._handle_platform_error(gemini_error, worker, acc, account_id)

            count = await self.session_router.update_interaction_count(conversation_id)
            quota_info = await self.quota_engine.record_request(account_id, f"req_{conversation_id}_{count}")

            should_blow = await self.session_router.check_memory_limit(conversation_id, mem)
            if should_blow:
                await self._trigger_meltdown(worker, conversation_id)
                response = response + "\n\n[Note: Session reset due to memory limit]"

            await self.browser_pool.release_worker(worker.id)
            acc.set_idle()
            self._persist_account(account_id)

            return {
                "status": "success",
                "conversation_id": conversation_id,
                "response": response,
                "interaction_count": count,
                "quota_info": quota_info,
                "metadata": {"worker_id": worker.id, "account_id": account_id, "memory_mb": mem, "timestamp": datetime.now().isoformat()},
            }

        except Exception as e:
            logger.error(f"Error in existing session: {e}")
            await self._safe_release(worker, acc)
            return {"status": "error", "error": str(e), "http_status": 500}

    async def _trigger_meltdown(self, worker, conversation_id: str):
        logger.warning(f"🔥 Memory meltdown triggered for {conversation_id}")
        try:
            await worker.gemini.delete_conversation()
        except Exception:
            pass
        await self.session_router.mark_expired(conversation_id)

    async def _safe_release(self, worker, acc=None):
        try:
            await self.browser_pool.release_worker(worker.id)
            if acc:
                acc.set_idle()
        except Exception:
            pass

    async def _handle_platform_error(self, error: PlatformError, worker, acc, account_id: str) -> Dict:
        logger.warning(f"🚨 [{account_id}] Platform error [{error.error_type}]: {error.message}")
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

        if error.should_kill_worker:
            await self.browser_pool.kill_worker(worker.id)
        else:
            await self._safe_release(worker, acc)

        http_status_map = {"rate_limit": 429, "banned": 503, "captcha": 503, "login_required": 503, "content_blocked": 400, "maintenance": 503, "unknown": 500}
        return {"status": "error", "error": error.message, "error_type": error.error_type, "account_id": account_id, "http_status": http_status_map.get(error.error_type, 500)}

    def get_gateway_stats(self) -> dict:
        return {
            "browser_pool": self.browser_pool.get_pool_stats() if self.browser_pool else {},
            "account_pool": self.account_pool.get_pool_stats() if self.account_pool else {},
            "timestamp": datetime.now().isoformat(),
        }
