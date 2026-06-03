"""Qwen platform - qianwen.com (通义千问)

经 2026年6月 浏览器验证:
- 输入框: contenteditable div (非 textarea)
- 发送按钮: aria-label="发送消息" (非 "发送")
- 新建对话: button "新建对话"
- Guest 模式可访问页面，但需要登录才能发送消息
"""

from web2api.platforms.base import BaseAutomator


class QwenAutomator(BaseAutomator):
    PLATFORM_NAME = "qwen"
    URLS = {"base": "https://www.qianwen.com/", "new_chat": "https://www.qianwen.com/"}
    REQUIRES_LOGIN = True
    SUPPORTS_GUEST = False

    SELECTORS = {
        "input": [
            'div[contenteditable="true"][role="textbox"]',
            'div.whitespace-pre-wrap[contenteditable]',
        ],
        "send": [
            'button[aria-label="发送消息"]',
            'button[aria-label="发送"]',
        ],
        "response": [
            'div[class*="message-content"]',
            'div[class*="markdown"]',
            'div[class*="assistant"] .content',
        ],
        "new_chat": [
            'button:has-text("新建对话")',
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
