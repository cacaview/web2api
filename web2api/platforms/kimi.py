"""Kimi platform - kimi.com (moonshot)"""

from web2api.platforms.base import BaseAutomator, PlatformError


class KimiAutomator(BaseAutomator):
    PLATFORM_NAME = "kimi"
    URLS = {"base": "https://www.kimi.com/", "new_chat": "https://www.kimi.com/?chat_enter_method=new_chat"}
    REQUIRES_LOGIN = True
    SUPPORTS_GUEST = False  # Guest 可浏览但不能发消息

    SELECTORS = {
        "input": [
            'div.chat-input-editor[role="textbox"]',
            'div[contenteditable="true"][role="textbox"]',
        ],
        "send": [
            'div.send-button-container:not(.disabled)',
            'div.send-button-container svg',
            'div[class*="send-button"]',
        ],
        "response": [
            'div[class*="message-content"]',
            '.chat-message--assistant .content',
            'div[class*="markdown"]',
        ],
        "new_chat": [
            'a.new-chat-btn',
            'a[href*="new_chat"]',
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

    async def _check_accessibility(self) -> bool:
        """Kimi 即使有登录提示，输入框仍可使用"""
        return await super()._check_accessibility()

    async def detect_page_errors(self):
        """检测登录弹窗"""
        # 检测登录弹窗
        login_popup = await self.page.query_selector('[class*="login-modal"], [class*="login-dialog"], [class*="LoginModal"]')
        if login_popup and await login_popup.is_visible():
            return PlatformError("login_required", "Login popup detected", should_kill_worker=False, cooldown_minutes=0)
        return await super().detect_page_errors()
