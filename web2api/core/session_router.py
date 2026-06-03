"""Session router - SQLite-based session management"""

import json
import time
import uuid
from typing import Optional, List
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger


class ConversationStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    MEMORY_BLOWN = "memory_blown"
    DELETED = "deleted"


@dataclass
class ConversationMetadata:
    client_conversation_id: str
    bound_account_id: str
    web_chat_url_id: str = ""
    created_at: float = field(default_factory=time.time)
    last_used_time: float = field(default_factory=time.time)
    interaction_count: int = 0
    status: ConversationStatus = ConversationStatus.ACTIVE
    memory_usage_mb: float = 0.0

    def to_dict(self) -> dict:
        return {
            "client_conversation_id": self.client_conversation_id,
            "bound_account_id": self.bound_account_id,
            "web_chat_url_id": self.web_chat_url_id,
            "created_at": self.created_at,
            "last_used_time": self.last_used_time,
            "interaction_count": self.interaction_count,
            "status": self.status.value,
            "memory_usage_mb": self.memory_usage_mb,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationMetadata":
        return cls(
            client_conversation_id=data["client_conversation_id"],
            bound_account_id=data["bound_account_id"],
            web_chat_url_id=data.get("web_chat_url_id", ""),
            created_at=data.get("created_at", time.time()),
            last_used_time=data.get("last_used_time", time.time()),
            interaction_count=data.get("interaction_count", 0),
            status=ConversationStatus(data.get("status", "active")),
            memory_usage_mb=data.get("memory_usage_mb", 0.0),
        )


class SessionRouter:
    """SQLite-based session router"""

    def __init__(self, db, ttl_days: int = 3):
        self.db = db
        self.ttl_days = ttl_days

    async def create_session(self, account_id: str) -> str:
        conv_id = str(uuid.uuid4())
        self.db.save_session(conv_id, account_id, "", 0, "active")
        logger.info(f"📝 Created session {conv_id} for account {account_id}")
        return conv_id

    async def get_session(self, client_conversation_id: str) -> Optional[ConversationMetadata]:
        data = self.db.get_session(client_conversation_id)
        if not data:
            return None
        return ConversationMetadata.from_dict(data)

    async def update_web_url(self, client_conversation_id: str, web_chat_url_id: str):
        self.db.update_session(client_conversation_id, web_chat_url_id=web_chat_url_id)

    async def update_interaction_count(self, client_conversation_id: str) -> int:
        data = self.db.get_session(client_conversation_id)
        if not data:
            return 0
        count = data.get("interaction_count", 0) + 1
        self.db.update_session(client_conversation_id, interaction_count=count)
        return count

    async def check_memory_limit(self, client_conversation_id: str, memory_mb: float) -> bool:
        data = self.db.get_session(client_conversation_id)
        if not data:
            return False
        count = data.get("interaction_count", 0)
        if count >= 40 or memory_mb > 1500:
            self.db.update_session(client_conversation_id, status="memory_blown")
            return True
        return False

    async def mark_expired(self, client_conversation_id: str):
        self.db.update_session(client_conversation_id, status="deleted")
        logger.info(f"⏰ Marked session {client_conversation_id} as expired")

    async def delete_session(self, client_conversation_id: str):
        self.db.update_session(client_conversation_id, status="deleted")
        logger.info(f"🗑️  Deleted session {client_conversation_id}")

    async def list_all_sessions(self) -> List[dict]:
        sessions = self.db.get_all_sessions()
        for s in sessions:
            s["ttl_remaining_hours"] = None
            if s.get("last_used_time"):
                elapsed = time.time() - s["last_used_time"]
                remaining = self.ttl_days * 86400 - elapsed
                s["ttl_remaining_hours"] = max(0, remaining / 3600)
        return sessions

    async def cleanup_expired_sessions(self, ttl_days: int = 3) -> int:
        return self.db.delete_expired_sessions(ttl_days)
