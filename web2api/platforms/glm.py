"""GLM platform - chatglm.cn (智谱清言)"""

from web2api.platforms.base import BaseAutomator


class GLMAutomator(BaseAutomator):
    PLATFORM_NAME = "glm"
    URLS = {"base": "https://chatglm.cn/main/alltoolsdetail", "new_chat": "https://chatglm.cn/main/alltoolsdetail"}
    REQUIRES_LOGIN = True
    SUPPORTS_GUEST = False

    SELECTORS = {
        "input": [
            'textarea.scroll-display-none',
            'textarea[placeholder]',
            'textarea',
        ],
        "send": [
            'button[aria-label="发送"]',
            'div[class*="send-btn"]',
            'button[class*="send"]',
        ],
        "response": [
            'div[class*="message-content"]',
            'div[class*="markdown"]',
            'div[class*="assistant"]',
        ],
        "new_chat": [
            'button:has-text("新对话")',
            'a[href*="new"]',
        ],
    }

    ERROR_PATTERNS = {
        "rate_limit": ["rate limit", "too many requests", "请求过于频繁"],
        "banned": ["suspended", "banned"],
        "captcha": ["captcha", "验证码"],
        "login_required": ["session expired", "请重新登录"],
        "content_blocked": ["blocked", "内容被拦截"],
        "maintenance": ["维护中", "暂时不可用"],
    }
