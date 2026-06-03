"""Tencent Yuanbao platform - yuanbao.tencent.com (腾讯元宝)"""

from web2api.platforms.base import BaseAutomator


class YuanbaoAutomator(BaseAutomator):
    PLATFORM_NAME = "yuanbao"
    URLS = {"base": "https://yuanbao.tencent.com", "new_chat": "https://yuanbao.tencent.com/chat/new"}
    REQUIRES_LOGIN = False
    SUPPORTS_GUEST = True

    SELECTORS = {
        "input": [
            '.ql-editor[contenteditable="true"]',
            'div[contenteditable="true"][role="textbox"]',
        ],
        "send": [
            'button[aria-label="发送"]',
            'div[class*="send-btn"] button',
            'button[class*="send"]',
        ],
        "response": [
            'div[class*="message-content"]',
            '.ql-editor',
            'div[class*="markdown"]',
        ],
        "new_chat": [
            'a[href*="/chat/new"]',
            'button:has-text("新对话")',
        ],
    }

    ERROR_PATTERNS = {
        "rate_limit": ["rate limit", "too many requests", "请求过于频繁"],
        "banned": ["suspended", "banned"],
        "captcha": ["captcha", "验证码"],
        "login_required": ["session expired", "请重新登录", "登录已过期"],
        "content_blocked": ["blocked", "内容被拦截"],
        "maintenance": ["维护中", "暂时不可用"],
    }

    async def _extract_response(self) -> str:
        """元宝使用 Quill 编辑器"""
        return await self.page.evaluate("""
            () => {
                const msgs = document.querySelectorAll('.ql-editor, div[class*="message-content"]');
                if (msgs.length === 0) return '';
                const last = msgs[msgs.length - 1];
                return (last.innerText || '').trim();
            }
        """) or await super()._extract_response()
