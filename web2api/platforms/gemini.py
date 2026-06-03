"""Google Gemini platform - gemini.google.com"""

import asyncio
from web2api.platforms.base import BaseAutomator


class GeminiAutomator(BaseAutomator):
    PLATFORM_NAME = "gemini"
    URLS = {"base": "https://gemini.google.com/app", "new_chat": "https://gemini.google.com/app"}
    REQUIRES_LOGIN = False
    SUPPORTS_GUEST = True

    SELECTORS = {
        "input": [
            '.ql-editor[contenteditable="true"]',
            'div[contenteditable="true"][role="textbox"]',
        ],
        "send": [
            'button.send-button[aria-label="发送"]',
            'button.send-button.submit',
            'button[aria-label="Send"]',
        ],
        "response": [
            'div[aria-live="polite"]',
            'message-content .text-message-content',
        ],
        "new_chat": [
            'a[aria-label="发起新对话"]',
            'button[aria-label*="撰写"]',
        ],
    }

    ERROR_PATTERNS = {
        "rate_limit": ["rate limit", "too many requests", "已达到使用限制", "频率限制", "you have exceeded", "slow down"],
        "banned": ["suspended", "banned", "封禁", "账号已被停用", "account has been disabled"],
        "captcha": ["captcha", "验证码", "需要验证", "verify you are human"],
        "login_required": ["sign in", "请登录", "session expired", "登录过期"],
        "content_blocked": ["blocked", "not available", "无法提供", "不支持", "content policy"],
        "maintenance": ["under maintenance", "维护中", "暂时不可用"],
    }

    async def initialize(self) -> bool:
        """Gemini SPA 需要 networkidle 等待完整渲染"""
        try:
            from loguru import logger as lg
            lg.info(f"🚀 [{self.PLATFORM_NAME}] Initializing at {self.URLS['base']}")
            await self.page.goto(self.URLS["base"], wait_until="networkidle")
            await asyncio.sleep(3)
            accessible = await self._check_accessibility()
            if not accessible:
                lg.error(f"❌ [{self.PLATFORM_NAME}] Not accessible")
                return False
            lg.info(f"✅ [{self.PLATFORM_NAME}] Initialized successfully")
            return True
        except Exception as e:
            from loguru import logger as lg
            lg.error(f"[{self.PLATFORM_NAME}] Init failed: {e}")
            return False

    async def _check_accessibility(self) -> bool:
        """Gemini 即使显示登录链接，输入框仍可使用"""
        input_field = await self._find_element("input")
        return input_field is not None

    async def create_new_chat(self) -> bool:
        """Gemini 首次加载时新对话按钮 disabled，使用撰写按钮"""
        try:
            # 尝试侧边栏按钮
            new_chat = await self.page.query_selector('a[aria-label="发起新对话"]')
            if new_chat:
                is_disabled = await new_chat.get_attribute("aria-disabled")
                if is_disabled != "true":
                    await self.page.click('a[aria-label="发起新对话"]')
                    await asyncio.sleep(2)
                    return True

            # 使用撰写按钮
            compose = await self._find_element("new_chat")
            if compose:
                await self.page.click(self._cached_selectors.get("new_chat", 'button[aria-label*="撰写"]'))
                await asyncio.sleep(2)
                return True

            # 已在 /app 页面
            return True
        except Exception:
            return True

    async def _extract_response(self) -> str:
        """Gemini 回复在 aria-live 区域"""
        return await self.page.evaluate("""
            () => {
                const r = document.querySelector('div[aria-live="polite"]');
                return r ? (r.innerText || '').trim() : '';
            }
        """) or await super()._extract_response()
