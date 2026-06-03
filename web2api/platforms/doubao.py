"""Doubao platform - doubao.com (字节跳动豆包)"""

import asyncio
from web2api.platforms.base import BaseAutomator


class DoubaoAutomator(BaseAutomator):
    PLATFORM_NAME = "doubao"
    URLS = {"base": "https://www.doubao.com/chat/", "new_chat": "https://www.doubao.com/chat/"}
    REQUIRES_LOGIN = False
    SUPPORTS_GUEST = True

    SELECTORS = {
        "input": [
            'textarea.semi-input-textarea',
            'textarea[placeholder*="发消息"]',
            'textarea[placeholder*="发送"]',
        ],
        "send": [
            'button[aria-label="发送"]',
            'button[data-testid="send-button"]',
        ],
        "response": [
            'div[class*="message-content"]',
            'div[class*="markdown"]',
            'div[class*="assistant"]',
        ],
        "new_chat": [
            'a[href="/chat/"]',
            'button:has-text("新对话")',
        ],
    }

    ERROR_PATTERNS = {
        "rate_limit": ["rate limit", "too many requests", "请求过于频繁"],
        "banned": ["suspended", "banned", "账号被封禁"],
        "captcha": ["captcha", "验证码"],
        "login_required": ["session expired", "请重新登录", "登录已过期"],
        "content_blocked": ["blocked", "内容被拦截", "违反"],
        "maintenance": ["维护中", "暂时不可用"],
    }

    async def _extract_response(self) -> str:
        """豆包回复提取"""
        return await self.page.evaluate("""
            () => {
                const msgs = document.querySelectorAll('div[class*="message-content"], div[class*="markdown"]');
                if (msgs.length === 0) return '';
                const last = msgs[msgs.length - 1];
                return (last.innerText || '').trim();
            }
        """) or await super()._extract_response()
