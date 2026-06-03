"""Qwen platform - qianwen.com (通义千问)"""

from web2api.platforms.base import BaseAutomator


class QwenAutomator(BaseAutomator):
    PLATFORM_NAME = "qwen"
    URLS = {"base": "https://www.qianwen.com/", "new_chat": "https://www.qianwen.com/"}
    REQUIRES_LOGIN = True
    SUPPORTS_GUEST = False  # Guest 可浏览但不能发消息

    SELECTORS = {
        "input": [
            'div.whitespace-pre-wrap[contenteditable]',
            'div[class*="chat-input"] [contenteditable]',
            'div[contenteditable="true"][role="textbox"]',
        ],
        "send": [
            'button[aria-label="发送"]',
            'button[aria-label="Send"]',
            'div[class*="send-btn"] button',
        ],
        "response": [
            'div[class*="message-content"]',
            'div[class*="markdown"]',
            'div[class*="assistant"] .content',
        ],
        "new_chat": [
            'button:has-text("新建对话")',
            'a[href="/"]',
            'div[class*="new-chat"]',
        ],
    }

    ERROR_PATTERNS = {
        "rate_limit": ["rate limit", "too many requests", "请求过于频繁", "请稍后再试"],
        "banned": ["suspended", "banned", "账号被封禁"],
        "captcha": ["captcha", "验证码", "verify you are human"],
        "login_required": ["session expired", "请重新登录", "登录已过期"],
        "content_blocked": ["blocked", "content policy", "内容被拦截"],
        "maintenance": ["under maintenance", "维护中", "暂时不可用"],
    }
