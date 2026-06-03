"""Rate limit quota engine - SQLite-based sliding window"""

import time
from typing import Optional
from loguru import logger
from web2api.config import RateLimitConfig


class QuotaEngine:
    """
    SQLite 滑动窗口配额管理器

    使用 SQLite 表实现精确的 3 小时滑动窗口计数
    """

    def __init__(self, db, config: RateLimitConfig):
        self.db = db
        self.config = config
        self.window_hours = config.window_hours

    async def record_request(self, account_id: str, request_id: str) -> dict:
        """记录一次请求"""
        self.db.record_rate_request(account_id, request_id, self.window_hours)
        current_count = self.db.get_rate_count(account_id, self.window_hours)

        is_limited = current_count >= self.config.max_requests_per_window

        if is_limited:
            logger.warning(
                f"⚠️  Account {account_id} hit rate limit! "
                f"Requests: {current_count}/{self.config.max_requests_per_window}"
            )

        return {
            "current_count": current_count,
            "limit": self.config.max_requests_per_window,
            "remaining": max(0, self.config.max_requests_per_window - current_count),
            "is_limited": is_limited,
            "cooldown_until": 0,
        }

    async def check_quota(self, account_id: str) -> dict:
        """检查账号是否在配额内"""
        current_count = self.db.get_rate_count(account_id, self.window_hours)
        is_available = current_count < self.config.max_requests_per_window

        return {
            "is_available": is_available,
            "current_count": current_count,
            "limit": self.config.max_requests_per_window,
            "remaining": max(0, self.config.max_requests_per_window - current_count),
            "in_cooldown": False,
            "cooldown_until": 0,
            "warning_threshold": self.config.threshold_warning,
        }

    async def reset_account(self, account_id: str) -> None:
        """重置账号的配额计数"""
        self.db.reset_rate_limit(account_id)
        logger.info(f"✅ Account {account_id} quota reset")

    async def get_all_account_status(self) -> dict:
        """获取所有账号的配额状态"""
        accounts_status = {}
        # 从 accounts 表获取所有账号
        all_accounts = self.db.get_all_accounts()
        for acc in all_accounts:
            aid = acc["account_id"]
            status = await self.check_quota(aid)
            accounts_status[aid] = status
        return accounts_status
