"""SQLite 数据持久化存储

在无 Redis 时提供本地持久化，存储账号状态和会话映射。
有 Redis 时作为备份存储。
"""

import json
import time
import sqlite3
import asyncio
from pathlib import Path
from typing import Optional, Dict, List
from loguru import logger

DB_PATH = Path(__file__).parent.parent.parent / "data" / "web2api.db"


class SQLiteStore:
    """SQLite 持久化存储"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'Idle',
                current_usage_3h INTEGER DEFAULT 0,
                last_ping_time REAL DEFAULT 0,
                cooldown_until REAL DEFAULT 0,
                worker_id TEXT,
                updated_at REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS sessions (
                client_conversation_id TEXT PRIMARY KEY,
                bound_account_id TEXT,
                web_chat_url_id TEXT DEFAULT '',
                interaction_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at REAL DEFAULT 0,
                last_used_time REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                level TEXT,
                account_id TEXT,
                event_type TEXT,
                detail TEXT
            );

            CREATE TABLE IF NOT EXISTS browser_cookies (
                account_id TEXT PRIMARY KEY,
                platform TEXT,
                cookies TEXT,
                local_storage TEXT,
                saved_at REAL,
                expires_at REAL
            );

            CREATE TABLE IF NOT EXISTS rate_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                request_id TEXT,
                timestamp REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_rate_account ON rate_limits(account_id);
            CREATE INDEX IF NOT EXISTS idx_rate_ts ON rate_limits(timestamp);

            CREATE INDEX IF NOT EXISTS idx_sessions_account ON sessions(bound_account_id);
            CREATE INDEX IF NOT EXISTS idx_log_time ON activity_log(timestamp);
        """)
        conn.commit()
        logger.info(f"✅ SQLite initialized: {self.db_path}")

    # ===== Account CRUD =====

    def save_account(self, account_id: str, status: str, usage: int = 0,
                     cooldown_until: float = 0, worker_id: str = None):
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO accounts (account_id, status, current_usage_3h, cooldown_until, worker_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                status=excluded.status,
                current_usage_3h=excluded.current_usage_3h,
                cooldown_until=excluded.cooldown_until,
                worker_id=excluded.worker_id,
                updated_at=excluded.updated_at
        """, (account_id, status, usage, cooldown_until, worker_id, time.time()))
        conn.commit()

    def get_account(self, account_id: str) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM accounts WHERE account_id=?", (account_id,)).fetchone()
        return dict(row) if row else None

    def get_all_accounts(self) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM accounts ORDER BY account_id").fetchall()
        return [dict(r) for r in rows]

    def update_account_status(self, account_id: str, status: str, **kwargs):
        conn = self._get_conn()
        sets = ["status=?", "updated_at=?"]
        vals = [status, time.time()]
        for k, v in kwargs.items():
            if k in ("current_usage_3h", "cooldown_until", "worker_id", "last_ping_time"):
                sets.append(f"{k}=?")
                vals.append(v)
        vals.append(account_id)
        conn.execute(f"UPDATE accounts SET {', '.join(sets)} WHERE account_id=?", vals)
        conn.commit()

    # ===== Session CRUD =====

    def save_session(self, client_id: str, account_id: str, web_url: str = "",
                     interaction_count: int = 0, status: str = "active"):
        conn = self._get_conn()
        now = time.time()
        conn.execute("""
            INSERT INTO sessions (client_conversation_id, bound_account_id, web_chat_url_id,
                                  interaction_count, status, created_at, last_used_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(client_conversation_id) DO UPDATE SET
                bound_account_id=excluded.bound_account_id,
                web_chat_url_id=excluded.web_chat_url_id,
                interaction_count=excluded.interaction_count,
                status=excluded.status,
                last_used_time=excluded.last_used_time
        """, (client_id, account_id, web_url, interaction_count, status, now, now))
        conn.commit()

    def get_session(self, client_id: str) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM sessions WHERE client_conversation_id=?", (client_id,)).fetchone()
        return dict(row) if row else None

    def get_all_sessions(self) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM sessions WHERE status != 'deleted' ORDER BY last_used_time DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_session(self, client_id: str, **kwargs):
        conn = self._get_conn()
        sets = ["last_used_time=?"]
        vals = [time.time()]
        for k, v in kwargs.items():
            if k in ("web_chat_url_id", "interaction_count", "status"):
                sets.append(f"{k}=?")
                vals.append(v)
        vals.append(client_id)
        conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE client_conversation_id=?", vals)
        conn.commit()

    def delete_expired_sessions(self, ttl_days: int = 3) -> int:
        conn = self._get_conn()
        cutoff = time.time() - ttl_days * 86400
        cur = conn.execute("DELETE FROM sessions WHERE last_used_time < ? AND status != 'active'", (cutoff,))
        conn.commit()
        return cur.rowcount

    # ===== Activity Log =====

    def log_event(self, level: str, account_id: str, event_type: str, detail: str = ""):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO activity_log (timestamp, level, account_id, event_type, detail) VALUES (?,?,?,?,?)",
            (time.time(), level, account_id, event_type, detail[:500])
        )
        conn.commit()

    def get_recent_logs(self, limit: int = 50) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def cleanup_old_logs(self, days: int = 7):
        conn = self._get_conn()
        cutoff = time.time() - days * 86400
        conn.execute("DELETE FROM activity_log WHERE timestamp < ?", (cutoff,))
        conn.commit()

    # ===== Browser Cookies =====

    def save_cookies(self, account_id: str, platform: str, cookies: list, local_storage: dict = None, ttl_days: int = 30):
        """保存浏览器 Cookie 到数据库"""
        import json
        conn = self._get_conn()
        now = time.time()
        conn.execute("""
            INSERT INTO browser_cookies (account_id, platform, cookies, local_storage, saved_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                cookies=excluded.cookies, local_storage=excluded.local_storage,
                saved_at=excluded.saved_at, expires_at=excluded.expires_at
        """, (account_id, platform, json.dumps(cookies), json.dumps(local_storage or {}), now, now + ttl_days * 86400))
        conn.commit()
        logger.info(f"🍪 Saved {len(cookies)} cookies for {account_id}")

    def load_cookies(self, account_id: str) -> Optional[tuple]:
        """加载浏览器 Cookie，返回 (cookies, local_storage) 或 None"""
        import json
        conn = self._get_conn()
        row = conn.execute("SELECT cookies, local_storage, expires_at FROM browser_cookies WHERE account_id=?", (account_id,)).fetchone()
        if not row:
            return None
        if time.time() > row["expires_at"]:
            conn.execute("DELETE FROM browser_cookies WHERE account_id=?", (account_id,))
            conn.commit()
            return None
        return (json.loads(row["cookies"]), json.loads(row["local_storage"] or "{}"))

    def delete_cookies(self, account_id: str):
        """删除浏览器 Cookie"""
        conn = self._get_conn()
        conn.execute("DELETE FROM browser_cookies WHERE account_id=?", (account_id,))
        conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ===== Rate Limits =====

    def record_rate_request(self, account_id: str, request_id: str, window_hours: float = 3.0):
        """记录一次请求到滑动窗口"""
        conn = self._get_conn()
        now = time.time()
        cutoff = now - window_hours * 3600
        conn.execute("DELETE FROM rate_limits WHERE account_id=? AND timestamp<?", (account_id, cutoff))
        conn.execute("INSERT INTO rate_limits (account_id, request_id, timestamp) VALUES (?,?,?)",
                      (account_id, request_id, now))
        conn.commit()

    def get_rate_count(self, account_id: str, window_hours: float = 3.0) -> int:
        """获取窗口内的请求数"""
        conn = self._get_conn()
        cutoff = time.time() - window_hours * 3600
        row = conn.execute("SELECT COUNT(*) as cnt FROM rate_limits WHERE account_id=? AND timestamp>?",
                           (account_id, cutoff)).fetchone()
        return row["cnt"] if row else 0

    def reset_rate_limit(self, account_id: str):
        """重置配额计数"""
        conn = self._get_conn()
        conn.execute("DELETE FROM rate_limits WHERE account_id=?", (account_id,))
        conn.commit()


# 全局实例
store: Optional[SQLiteStore] = None


def get_store() -> SQLiteStore:
    global store
    if store is None:
        store = SQLiteStore()
    return store
