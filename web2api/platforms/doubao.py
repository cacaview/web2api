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
        ],
        "send": [
            'div[class*="send-msg-btn"]',
            'div[class*="send-btn"]',
        ],
        "response": [
            'div[class*="message-content"]',
            'div[class*="markdown"]',
            'div[class*="assistant"]',
        ],
        "new_chat": [
            'a[href="/chat"]',
            'a[href="/chat/"]',
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

    async def send_message(self, message: str) -> bool:
        """豆包发送按钮是 DIV 而非 BUTTON，需要特殊处理"""
        try:
            from web2api.core.humanizer import GaussianHumanizer
            from loguru import logger
            import asyncio

            logger.debug(f"[doubao] Sending: {message[:50]}...")

            pre_error = await self.detect_page_errors()
            if pre_error:
                self._last_error = pre_error
                return False

            input_field = await self._find_element("input")
            if not input_field:
                logger.error("[doubao] Input field not found")
                return False

            await GaussianHumanizer.humanized_click(self.page, input_field)
            await asyncio.sleep(0.3)
            await input_field.press("Control+a")
            await asyncio.sleep(0.1)
            await input_field.press("Backspace")
            await asyncio.sleep(0.2)

            await GaussianHumanizer.humanized_type(
                self.page, input_field, message, delay_min=30, delay_max=100
            )
            await asyncio.sleep(1.0)

            # 豆包发送按钮是 div，用 CSS 选择器直接点击
            for attempt in range(3):
                send_btn = await self._find_element("send")
                if send_btn:
                    cached_sel = self._cached_selectors.get("send")
                    if cached_sel:
                        try:
                            await self.page.click(cached_sel, timeout=3000)
                        except Exception:
                            await GaussianHumanizer.humanized_click(self.page, send_btn)
                    else:
                        # 尝试直接点击选择器
                        for sel in self.SELECTORS.get("send", []):
                            try:
                                await self.page.click(sel, timeout=3000)
                                break
                            except Exception:
                                continue

                    self.is_streaming = True
                    self.response_buffer = ""
                    await asyncio.sleep(2)
                    post_error = await self.detect_page_errors()
                    if post_error and post_error.error_type in ("rate_limit", "banned", "captcha"):
                        self._last_error = post_error
                        self.is_streaming = False
                        return False
                    logger.info("[doubao] Message sent")
                    return True
                await asyncio.sleep(0.5)

            # 备选: Enter 键
            try:
                await input_field.press("Enter")
                self.is_streaming = True
                self.response_buffer = ""
                logger.info("[doubao] Message sent via Enter")
                return True
            except Exception:
                pass

            logger.error("[doubao] Could not send message")
            return False
        except Exception as e:
            from loguru import logger
            logger.error(f"[doubao] send_message failed: {e}")
            return False

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
