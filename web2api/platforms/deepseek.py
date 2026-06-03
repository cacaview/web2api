"""DeepSeek platform - chat.deepseek.com"""

from web2api.platforms.base import BaseAutomator


class DeepSeekAutomator(BaseAutomator):
    PLATFORM_NAME = "deepseek"
    URLS = {"base": "https://chat.deepseek.com", "new_chat": "https://chat.deepseek.com/new"}
    REQUIRES_LOGIN = True
    SUPPORTS_GUEST = False

    SELECTORS = {
        "input": [
            'textarea#chat-input',
            'textarea[placeholder*="发送消息"]',
            'textarea[placeholder*="Send"]',
            'textarea[placeholder*="输入"]',
        ],
        "send": [
            'div[class*="_74361"]',  # DeepSeek send icon container
            'button[aria-label*="发送"]',
            'button[aria-label*="Send"]',
            'div[class*="send-btn"]',
        ],
        "response": [
            'div.ds-markdown',
            'div[class*="markdown-body"]',
            'div[class*="message-content"]',
        ],
        "new_chat": [
            'div[class*="new-chat"]',
            'a[href="/new"]',
        ],
    }

    ERROR_PATTERNS = {
        "rate_limit": ["rate limit", "too many requests", "请求过于频繁", "请稍后再试"],
        "banned": ["suspended", "banned", "账号被封禁", "account disabled"],
        "captcha": ["captcha", "验证码", "verify you are human"],
        "login_required": ["sign in", "log in", "登录", "请先登录", "session expired"],
        "content_blocked": ["blocked", "content policy", "内容被拦截", "违反"],
        "maintenance": ["under maintenance", "维护中", "暂时不可用"],
    }
