"""Configuration management for web2api"""

from dataclasses import dataclass, field
from typing import Dict, List
from enum import Enum
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass
class BrowserConfig:
    """浏览器配置"""
    headless: bool = False
    max_workers: int = int(os.getenv("MAX_WORKERS", "5"))
    worker_memory_limit_mb: int = 1500
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    viewport_width: int = 1920
    viewport_height: int = 1080
    timeout_ms: int = 30000
    idle_timeout_min: int = 10  # 10分钟无请求自动kill


@dataclass
class RateLimitConfig:
    """官方速率限制配置"""
    window_hours: int = 3
    max_requests_per_window: int = 40
    cooldown_minutes: int = 90  # 冷却时间
    threshold_warning: int = 38  # 预警阈值（为max留2次容错）


@dataclass
class SessionConfig:
    """会话配置"""
    ttl_days: int = 3
    max_interactions_per_session: int = 40  # 长对话内存熔断阈值
    memory_check_interval_sec: int = 60
    cleanup_interval_sec: int = 300  # 扫地僧任务间隔 (5分钟)


@dataclass
class AccountPoolConfig:
    """账号池配置"""
    accounts: List[str] = field(default_factory=lambda: [
        f"account_{i:02d}" for i in range(1, 6)
    ])
    max_concurrent_workers: int = int(os.getenv("MAX_WORKERS", "5"))
    hot_start_timeout_sec: float = 3.0  # 热启动恢复超时
    memory_limit_mb: float = 1500  # 单Worker内存限制
    memory_check_enabled: bool = True


@dataclass
class TrafficInterceptConfig:
    """流量拦截配置"""
    enabled: bool = True
    block_patterns: List[str] = field(default_factory=lambda: [
        # 媒体资源
        "*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg", "*.mp4",
        # 样式与字体
        "*.css", "*.woff", "*.woff2", "*.ttf",
        # 第三方埋点
        "*analytics*", "*sentry*", "*mixpanel*", "*datadog*", "*google-analytics*"
    ])


@dataclass
class GeminiConfig:
    """Google Gemini 特定配置 - 基于 2025年6月 真实网页验证"""
    base_url: str = "https://gemini.google.com"
    health_check_interval_sec: int = 300  # 5分钟检查一次
    health_check_action: str = "click_history"  # 点击历史保活

    # ===== 基于 Chrome DevTools MCP 实时验证的选择器 (2025-06) =====

    # 新建对话：侧边栏 <a> 链接 (role=button) 或撰写卡片按钮
    new_chat_selector: str = 'a[aria-label="发起新对话"]'
    compose_button_selector: str = 'button[aria-label*="撰写"]'

    # 消息输入框：Quill 编辑器 contenteditable div
    message_input_selector: str = '.ql-editor[contenteditable="true"]'

    # 发送按钮：Material icon button，带 .submit 类
    send_button_selector: str = 'button.send-button[aria-label="发送"]'

    # AI回复容器 - 按优先级排序
    message_container_selector: str = 'div[role="article"], message-content .text-message-content'

    # 删除按钮（对话列表右键菜单或操作区）
    delete_button_selector: str = 'button[aria-label*="delete"], button[aria-label*="Delete"], button[aria-label*="删除"]'

    # 对话列表容器
    conversation_list_selector: str = 'bard-sidenav [role="button"], .conversation-item'

    # 模型选择器按钮
    model_selector_selector: str = 'button[aria-label*="模式"]'

    # 登录检测
    login_link_selector: str = 'a[href*="ServiceLogin"]'

    rate_limit_error_patterns: List[str] = field(default_factory=lambda: [
        "Rate limit",
        "Too many requests",
        "已达到使用限制",
        "Please try again later",
        "配额",
        "限制",
        "频率限制",
        "You have exceeded",
        "slow down",
    ])

    # === 分类错误模式 ===
    error_patterns: Dict[str, List[str]] = field(default_factory=lambda: {
        "rate_limit": [
            "rate limit", "too many requests", "已达到使用限制",
            "频率限制", "you have exceeded", "slow down",
            "please try again later", "请求过于频繁",
        ],
        "banned": [
            "suspended", "banned", "封禁", "账号已被停用",
            "account has been disabled", "违反了我们的条款",
            "violated our terms", "permanently blocked",
        ],
        "captcha": [
            "captcha", "验证码", "需要验证", "verify you are human",
            "recaptcha", "人机验证", "prove you're not a robot",
        ],
        "login_required": [
            "sign in", "请登录", "session expired", "登录过期",
            "please sign in", "log in", "认证已过期",
        ],
        "content_blocked": [
            "blocked", "not available", "无法提供", "不支持",
            "can't answer", "不能生成", "content policy",
            "违反了使用政策", "against our policy",
        ],
        "maintenance": [
            "under maintenance", "维护中", "暂时不可用",
            "temporarily unavailable", "service disruption",
        ],
    })


@dataclass
class RedisConfig:
    """Redis 配置"""
    host: str = os.getenv("REDIS_HOST", "localhost")
    port: int = int(os.getenv("REDIS_PORT", "6379"))
    db: int = int(os.getenv("REDIS_DB", "0"))
    password: str = os.getenv("REDIS_PASSWORD", "")
    pool_size: int = 10


@dataclass
class DatabaseConfig:
    """数据库配置"""
    sqlite_path: str = os.getenv("DB_PATH", "./data/web2api.db")
    enable_wal: bool = True


@dataclass
class AppConfig:
    """主应用配置"""
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    account_pool: AccountPoolConfig = field(default_factory=AccountPoolConfig)
    traffic_intercept: TrafficInterceptConfig = field(default_factory=TrafficInterceptConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        """从环境变量创建配置"""
        return cls()


# 全局配置实例
config = AppConfig.from_env()
