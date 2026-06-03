"""Account pool manager - 账号池生命周期管理

管理所有 AI 账号的状态机：Idle → Busy → Cooldown → Maintenance
"""

import time
from enum import Enum
from typing import Dict, Optional
from loguru import logger


class AccountStatus(str, Enum):
    IDLE = "Idle"
    BUSY = "Busy"
    COOLDOWN = "Cooldown"
    MAINTENANCE = "Maintenance"


class AccountInfo:
    __slots__ = (
        "account_id", "platform", "status", "current_usage_3h", "last_ping_time",
        "cooldown_until", "worker_id", "display_name",
    )

    def __init__(self, account_id: str, platform: str = "gemini", display_name: str = ""):
        self.account_id = account_id
        self.platform = platform
        self.status = AccountStatus.IDLE
        self.current_usage_3h: int = 0
        self.last_ping_time: float = time.time()
        self.cooldown_until: float = 0.0
        self.worker_id: Optional[str] = None
        self.display_name = display_name or account_id

    def is_available(self) -> bool:
        now = time.time()
        if self.status == AccountStatus.COOLDOWN:
            if now >= self.cooldown_until:
                self.status = AccountStatus.IDLE
                logger.info(f"✅ Account {self.account_id} cooldown expired, back to Idle")
                return True
            return False
        return self.status == AccountStatus.IDLE

    def set_busy(self, worker_id: str):
        self.status = AccountStatus.BUSY
        self.worker_id = worker_id
        self.last_ping_time = time.time()

    def set_idle(self):
        self.status = AccountStatus.IDLE
        self.worker_id = None
        self.last_ping_time = time.time()

    def set_cooldown(self, cooldown_minutes: int = 90):
        self.status = AccountStatus.COOLDOWN
        self.cooldown_until = time.time() + cooldown_minutes * 60
        self.worker_id = None
        logger.warning(
            f"🧊 Account {self.account_id} entering cooldown for {cooldown_minutes}min "
            f"(until {time.ctime(self.cooldown_until)})"
        )

    def set_maintenance(self):
        self.status = AccountStatus.MAINTENANCE
        self.worker_id = None
        logger.warning(f"🔧 Account {self.account_id} entering maintenance mode")

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "platform": self.platform,
            "display_name": self.display_name,
            "status": self.status.value,
            "current_usage_3h": self.current_usage_3h,
            "last_ping_time": self.last_ping_time,
            "cooldown_until": self.cooldown_until,
            "worker_id": self.worker_id,
        }


class AccountPool:
    """
    账号池管理器

    职责：
    - 维护所有账号的状态机
    - 根据配额和状态智能分配可用账号
    - 支持动态注册/移除账号
    """

    def __init__(self, account_ids: list[str]):
        self.accounts: Dict[str, AccountInfo] = {}
        for aid in account_ids:
            self.accounts[aid] = AccountInfo(aid)
        logger.info(
            f"🏦 AccountPool initialized with {len(self.accounts)} accounts: "
            f"{list(self.accounts.keys())}"
        )

    def select_account(self, preferred_id: Optional[str] = None, platform: Optional[str] = None) -> Optional[AccountInfo]:
        """
        选择一个可用账号。
        优先选择指定账号，否则按平台筛选后找到第一个 Idle 账号。
        """
        if preferred_id and preferred_id in self.accounts:
            acc = self.accounts[preferred_id]
            if acc.is_available():
                return acc
            logger.debug(f"Preferred account {preferred_id} not available (status={acc.status.value})")

        # 按平台筛选
        candidates = self.accounts.values()
        if platform:
            platform_accounts = [a for a in candidates if a.platform == platform]
            if platform_accounts:
                candidates = platform_accounts

        for acc in candidates:
            if acc.is_available():
                return acc

        logger.warning(f"❌ No available accounts (platform={platform})")
        return None

    def get_account(self, account_id: str) -> Optional[AccountInfo]:
        return self.accounts.get(account_id)

    def add_account(self, account_id: str, platform: str = "gemini", display_name: str = "") -> AccountInfo:
        if account_id not in self.accounts:
            self.accounts[account_id] = AccountInfo(account_id, platform, display_name)
            logger.info(f"➕ Added account {account_id} (platform={platform})")
        return self.accounts[account_id]

    def batch_add_accounts(self, platform: str, count: int, prefix: str = "") -> list[AccountInfo]:
        """批量添加账号"""
        added = []
        for i in range(1, count + 1):
            aid = f"{prefix}{i:02d}" if prefix else f"{platform}_{i:02d}"
            if aid not in self.accounts:
                acc = AccountInfo(aid, platform, f"{platform} #{i}")
                self.accounts[aid] = acc
                added.append(acc)
        if added:
            logger.info(f"➕ Batch added {len(added)} {platform} accounts: {[a.account_id for a in added]}")
        return added

    def get_accounts_by_platform(self, platform: str) -> list[AccountInfo]:
        return [a for a in self.accounts.values() if a.platform == platform]

    def remove_account(self, account_id: str):
        if account_id in self.accounts:
            del self.accounts[account_id]
            logger.info(f"➖ Removed account {account_id} from pool")

    def get_idle_accounts(self) -> list[AccountInfo]:
        return [a for a in self.accounts.values() if a.is_available()]

    def get_pool_stats(self) -> dict:
        stats = {
            "total": len(self.accounts),
            "by_platform": {},
            "idle": 0, "busy": 0, "cooldown": 0, "maintenance": 0,
        }
        for acc in self.accounts.values():
            p = acc.platform
            if p not in stats["by_platform"]:
                stats["by_platform"][p] = {"total": 0, "idle": 0, "busy": 0, "cooldown": 0}
            stats["by_platform"][p]["total"] += 1

            if acc.status == AccountStatus.IDLE:
                stats["idle"] += 1
                stats["by_platform"][p]["idle"] += 1
            elif acc.status == AccountStatus.BUSY:
                stats["busy"] += 1
                stats["by_platform"][p]["busy"] += 1
            elif acc.status == AccountStatus.COOLDOWN:
                if acc.is_available():
                    stats["idle"] += 1
                    stats["by_platform"][p]["idle"] += 1
                else:
                    stats["cooldown"] += 1
                    stats["by_platform"][p]["cooldown"] += 1
            elif acc.status == AccountStatus.MAINTENANCE:
                stats["maintenance"] += 1
        return stats
