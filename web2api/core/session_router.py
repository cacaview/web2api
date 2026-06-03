"""Session router and lifecycle management - 会话路由与生命周期管理"""

import json
import time
import uuid
from typing import Optional, Dict
from dataclasses import dataclass, field
from enum import Enum
import redis.asyncio as aioredis
from loguru import logger


class ConversationStatus(str, Enum):
    """会话状态枚举"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    MEMORY_BLOWN = "memory_blown"
    DELETED = "deleted"


@dataclass
class ConversationMetadata:
    """会话元数据"""
    client_conversation_id: str  # 客户端生成的UUID
    bound_account_id: str
    web_chat_url_id: str  # 网页端真实路径ID（如 c/1234-5678）
    created_at: float = field(default_factory=time.time)
    last_used_time: float = field(default_factory=time.time)
    interaction_count: int = 0
    status: ConversationStatus = ConversationStatus.ACTIVE
    memory_usage_mb: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            'client_conversation_id': self.client_conversation_id,
            'bound_account_id': self.bound_account_id,
            'web_chat_url_id': self.web_chat_url_id,
            'created_at': self.created_at,
            'last_used_time': self.last_used_time,
            'interaction_count': self.interaction_count,
            'status': self.status.value,
            'memory_usage_mb': self.memory_usage_mb,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ConversationMetadata":
        data['status'] = ConversationStatus(data.get('status', 'active'))
        return cls(**data)


class SessionRouter:
    """
    会话路由管理器
    - 维护client_id -> account_id -> web_url的映射
    - 管理会话生命周期（TTL、内存限制）
    - 异步URL捕获与更新
    """
    
    def __init__(self, redis: aioredis.Redis, ttl_days: int = 3):
        self.redis = redis
        self.ttl_seconds = ttl_days * 24 * 3600
    
    def _get_conv_key(self, client_conversation_id: str) -> str:
        """获取会话元数据key"""
        return f"conv:{client_conversation_id}"
    
    def _get_account_conv_index(self, account_id: str) -> str:
        """获取账号会话索引"""
        return f"account_conversations:{account_id}"
    
    def _get_ttl_index_key(self) -> str:
        """获取TTL索引（用于扫地僧清理）"""
        return "conversations:ttl_index"
    
    async def create_session(
        self,
        account_id: str
    ) -> str:
        """
        创建新会话
        
        Returns:
            client_conversation_id (UUID)
        """
        client_conversation_id = str(uuid.uuid4())
        
        metadata = ConversationMetadata(
            client_conversation_id=client_conversation_id,
            bound_account_id=account_id,
            web_chat_url_id=""  # 等待异步捕获
        )
        
        # 存储元数据
        key = self._get_conv_key(client_conversation_id)
        await self.redis.set(
            key,
            json.dumps(metadata.to_dict()),
            ex=self.ttl_seconds
        )
        
        # 索引到账号
        await self.redis.sadd(
            self._get_account_conv_index(account_id),
            client_conversation_id
        )
        
        # 添加到TTL索引
        await self.redis.zadd(
            self._get_ttl_index_key(),
            {client_conversation_id: time.time()}
        )
        
        logger.info(
            f"📝 Created session {client_conversation_id} for account {account_id}"
        )
        
        return client_conversation_id
    
    async def update_web_url(
        self,
        client_conversation_id: str,
        web_chat_url_id: str
    ) -> None:
        """
        异步捕获后更新网页URL
        
        Args:
            client_conversation_id: 客户端会话ID
            web_chat_url_id: 网页端路径ID (如 c/1234-5678)
        """
        key = self._get_conv_key(client_conversation_id)
        
        # 获取现有数据
        data_str = await self.redis.get(key)
        if not data_str:
            logger.warning(
                f"Session {client_conversation_id} not found during URL update"
            )
            return
        
        # 更新URL并刷新TTL
        try:
            data = json.loads(data_str)
            metadata = ConversationMetadata.from_dict(data)
            metadata.web_chat_url_id = web_chat_url_id
            metadata.last_used_time = time.time()

            await self.redis.set(
                key,
                json.dumps(metadata.to_dict()),
                ex=self.ttl_seconds
            )

            logger.debug(f"✅ Updated URL for {client_conversation_id}: {web_chat_url_id}")
        except Exception as e:
            logger.error(f"Failed to update URL: {e}")
    
    async def get_session(
        self,
        client_conversation_id: str
    ) -> Optional[ConversationMetadata]:
        """获取会话元数据"""
        key = self._get_conv_key(client_conversation_id)
        data_str = await self.redis.get(key)
        
        if not data_str:
            return None

        data = json.loads(data_str)
        return ConversationMetadata.from_dict(data)
    
    async def update_interaction_count(
        self,
        client_conversation_id: str
    ) -> int:
        """
        增加交互计数，返回当前计数
        同时刷新TTL
        """
        metadata = await self.get_session(client_conversation_id)
        if not metadata:
            return 0
        
        metadata.interaction_count += 1
        metadata.last_used_time = time.time()
        
        key = self._get_conv_key(client_conversation_id)
        await self.redis.set(
            key,
            json.dumps(metadata.to_dict()),
            ex=self.ttl_seconds
        )

        return metadata.interaction_count
    
    async def check_memory_limit(
        self,
        client_conversation_id: str,
        current_memory_mb: float,
        memory_limit_mb: float = 1500
    ) -> bool:
        """
        检查是否超出内存限制
        
        Returns:
            True 表示已触发熔断，需要删除会话
        """
        metadata = await self.get_session(client_conversation_id)
        if not metadata:
            return False
        
        should_blow = (
            current_memory_mb > memory_limit_mb or
            metadata.interaction_count > 40
        )
        
        if should_blow:
            metadata.status = ConversationStatus.MEMORY_BLOWN
            key = self._get_conv_key(client_conversation_id)
            await self.redis.set(
                key,
                json.dumps(metadata.to_dict()),
                ex=self.ttl_seconds
            )
            logger.warning(
                f"🔥 Memory limit blown for {client_conversation_id}: "
                f"memory={current_memory_mb}MB, interactions={metadata.interaction_count}"
            )
        
        return should_blow
    
    async def delete_session(
        self,
        client_conversation_id: str
    ) -> None:
        """删除会话"""
        metadata = await self.get_session(client_conversation_id)
        if not metadata:
            return
        
        # 标记为已删除
        metadata.status = ConversationStatus.DELETED
        key = self._get_conv_key(client_conversation_id)
        
        # 可选：立即删除，或标记后由TTL自动清理
        await self.redis.delete(key)
        
        # 从账号索引移除
        await self.redis.srem(
            self._get_account_conv_index(metadata.bound_account_id),
            client_conversation_id
        )
        
        logger.info(f"🗑️  Deleted session {client_conversation_id}")

    async def mark_expired(self, client_conversation_id: str) -> None:
        """
        标记会话为已过期/已销毁（内存熔断后的软重置）。
        下次客户端携带该 conversation_id 接入时，网关判定为过期并自动新建。
        """
        key = self._get_conv_key(client_conversation_id)
        metadata = await self.get_session(client_conversation_id)
        if metadata:
            metadata.status = ConversationStatus.DELETED
            metadata.web_chat_url_id = ""
            await self.redis.set(
                key,
                json.dumps(metadata.to_dict()),
                ex=300  # 保留5分钟供客户端感知过期
            )
        logger.info(f"⏰ Marked session {client_conversation_id} as expired")
    
    async def cleanup_expired_sessions(self, ttl_days: int = 3) -> int:
        """
        清理过期会话 - "扫地僧"任务
        
        Returns:
            清理的会话数
        """
        now = time.time()
        ttl_seconds = ttl_days * 24 * 3600
        cutoff_time = now - ttl_seconds
        
        index_key = self._get_ttl_index_key()
        
        # 获取所有过期会话
        expired = await self.redis.zrangebyscore(
            index_key,
            0,
            cutoff_time
        )
        
        deleted_count = 0
        for conv_id in expired:
            try:
                await self.delete_session(conv_id.decode() if isinstance(conv_id, bytes) else conv_id)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to clean up {conv_id}: {e}")
        
        # 从索引中移除
        if expired:
            await self.redis.zremrangebyscore(index_key, 0, cutoff_time)
            logger.info(f"🧹 Cleaned up {deleted_count} expired sessions")
        
        return deleted_count
    
    async def get_account_conversations(self, account_id: str) -> list:
        """获取账号的所有活跃会话"""
        conv_ids = await self.redis.smembers(self._get_account_conv_index(account_id))
        
        conversations = []
        for conv_id in conv_ids:
            conv_id_str = conv_id.decode() if isinstance(conv_id, bytes) else conv_id
            metadata = await self.get_session(conv_id_str)
            if metadata:
                conversations.append(metadata.to_dict())
        
        return conversations

    async def list_all_sessions(self) -> list:
        """
        扫描 Redis 获取所有会话（用于 Dashboard 展示）。
        返回包含 TTL 剩余时间的会话列表。
        """
        sessions = []
        cursor = 0

        while True:
            cursor, keys = await self.redis.scan(cursor, match="conv:*", count=100)
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                try:
                    data_str = await self.redis.get(key_str)
                    if not data_str:
                        continue
                    data = json.loads(data_str)
                    ttl = await self.redis.ttl(key_str)
                    data["ttl_remaining_hours"] = ttl / 3600 if ttl > 0 else None
                    sessions.append(data)
                except Exception as e:
                    logger.debug(f"Failed to read session {key_str}: {e}")
            if cursor == 0:
                break

        return sessions
