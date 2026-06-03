"""Tencent Yuanbao platform - yuanbao.tencent.com (腾讯元宝)

经 2026年6月 浏览器验证:
- 输入框: Quill 编辑器 (.ql-editor contenteditable)
- 发送按钮: div[class*="send-btn"] (非 button)
- 页面可能弹出登录弹窗，需要关闭
"""

import asyncio
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
            'div[class*="send-btn"]',
            'div[class*="send-msg"]',
        ],
        "response": [
            'div[class*="message-content"]',
            '.ql-editor',
            'div[class*="markdown"]',
        ],
        "new_chat": [
            'a[href*="/chat/new"]',
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

    async def initialize(self) -> bool:
        """元宝初始化 - 关闭登录弹窗"""
        result = await super().initialize()
        if result:
            # 关闭可能弹出的登录弹窗
            try:
                close_btn = await self.page.query_selector('button[class*="close"], .hyc-login__close')
                if close_btn and await close_btn.is_visible():
                    await close_btn.click()
                    await asyncio.sleep(0.5)
            except Exception:
                pass
        return result

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
