"""Rate limit quota engine - 官方配额滑动窗口引擎"""

import time
from typing import Optional
import redis.asyncio as aioredis
from loguru import logger
from web2api.config import RateLimitConfig


class QuotaEngine:
    """
    Redis滑动窗口配额管理器
    
    使用ZSET实现精确的3小时滑动窗口计数
    """
    
    def __init__(self, redis: aioredis.Redis, config: RateLimitConfig):
        self.redis = redis
        self.config = config
        self.window_seconds = config.window_hours * 3600  # 转换为秒
    
    def _get_rate_key(self, account_id: str) -> str:
        """获取Redis key"""
        return f"rate:{account_id}"
    
    def _get_cooldown_key(self, account_id: str) -> str:
        """获取冷却状态key"""
        return f"cooldown:{account_id}"
    
    async def record_request(
        self,
        account_id: str,
        request_id: str
    ) -> dict:
        """
        记录一次请求 - 写入时间戳到ZSET
        
        Args:
            account_id: 账号ID
            request_id: 请求ID（用于去重）
        
        Returns:
            {
                'current_count': 当前窗口内的请求数,
                'limit': 限制数,
                'remaining': 剩余次数,
                'is_limited': 是否已达到限制,
                'cooldown_until': 冷却截止时间戳(如果在冷却中)
            }
        """
        rate_key = self._get_rate_key(account_id)
        now = time.time()
        
        # 先清除3小时外的旧请求
        await self.redis.zremrangebyscore(
            rate_key,
            0,
            now - self.window_seconds
        )
        
        # 添加当前请求
        await self.redis.zadd(rate_key, {request_id: now})
        
        # 设置key过期时间（4小时，防止垃圾堆积）
        await self.redis.expire(rate_key, int(self.window_seconds) + 3600)
        
        # 获取当前窗口计数
        current_count = await self.redis.zcard(rate_key)
        
        is_limited = current_count >= self.config.max_requests_per_window
        
        if is_limited:
            # 标记冷却状态
            cooldown_until = now + self.config.cooldown_minutes * 60
            await self.redis.set(
                self._get_cooldown_key(account_id),
                int(cooldown_until),
                ex=int(self.config.cooldown_minutes * 60)
            )
            logger.warning(
                f"⚠️  Account {account_id} hit rate limit! "
                f"Requests: {current_count}/{self.config.max_requests_per_window}"
            )
        
        return {
            'current_count': current_count,
            'limit': self.config.max_requests_per_window,
            'remaining': max(0, self.config.max_requests_per_window - current_count),
            'is_limited': is_limited,
            'cooldown_until': (
                int(await self.redis.get(self._get_cooldown_key(account_id)) or 0)
            )
        }
    
    async def check_quota(self, account_id: str) -> dict:
        """
        检查账号是否在配额内（不记录请求）
        
        Returns:
            {
                'is_available': 是否可用,
                'current_count': 当前计数,
                'limit': 限制数,
                'remaining': 剩余次数,
                'in_cooldown': 是否在冷却中,
                'cooldown_until': 冷却截止时间戳
            }
        """
        rate_key = self._get_rate_key(account_id)
        now = time.time()
        
        # 清除过期记录
        await self.redis.zremrangebyscore(
            rate_key,
            0,
            now - self.window_seconds
        )
        
        # 获取计数
        current_count = await self.redis.zcard(rate_key)
        
        # 检查冷却状态
        cooldown_until_str = await self.redis.get(self._get_cooldown_key(account_id))
        cooldown_until = int(cooldown_until_str) if cooldown_until_str else 0
        in_cooldown = cooldown_until > now
        
        is_available = (
            not in_cooldown and
            current_count < self.config.max_requests_per_window
        )
        
        return {
            'is_available': is_available,
            'current_count': current_count,
            'limit': self.config.max_requests_per_window,
            'remaining': max(0, self.config.max_requests_per_window - current_count),
            'in_cooldown': in_cooldown,
            'cooldown_until': cooldown_until,
            'warning_threshold': self.config.threshold_warning
        }
    
    async def reset_account(self, account_id: str) -> None:
        """重置账号的配额计数（用于手动恢复）"""
        rate_key = self._get_rate_key(account_id)
        await self.redis.delete(rate_key)
        await self.redis.delete(self._get_cooldown_key(account_id))
        logger.info(f"✅ Account {account_id} quota reset")
    
    async def get_all_account_status(self) -> dict:
        """获取所有账号的配额状态"""
        # 扫描所有rate:*的key
        cursor = 0
        accounts_status = {}
        
        while True:
            cursor, keys = await self.redis.scan(cursor, match="rate:*", count=100)
            
            for key in keys:
                account_id = key.decode().replace("rate:", "")
                status = await self.check_quota(account_id)
                accounts_status[account_id] = status
            
            if cursor == 0:
                break
        
        return accounts_status
