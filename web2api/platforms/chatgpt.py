"""ChatGPT platform - chatgpt.com"""

from web2api.platforms.base import BaseAutomator


class ChatGPTAutomator(BaseAutomator):
    PLATFORM_NAME = "chatgpt"
    URLS = {"base": "https://chatgpt.com", "new_chat": "https://chatgpt.com"}
    REQUIRES_LOGIN = True
    SUPPORTS_GUEST = False

    SELECTORS = {
        "input": [
            'div#prompt-textarea[contenteditable="true"]',
            '#prompt-textarea',
            'textarea[placeholder*="Message"]',
        ],
        "send": [
            'button[data-testid="send-button"]',
            'button[aria-label="Send prompt"]',
            'button[aria-label="发送"]',
        ],
        "response": [
            'div.markdown',
            'div[data-message-author-role="assistant"]',
            '.agent-turn .markdown',
        ],
        "new_chat": [
            'a[href="/"]',
            'nav a[href="/"]',
        ],
    }

    ERROR_PATTERNS = {
        "rate_limit": ["rate limit", "too many requests", "please slow down", "you've reached"],
        "banned": ["suspended", "banned", "account disabled", "violated"],
        "captcha": ["captcha", "verify you are human", "security check"],
        "login_required": ["sign in", "log in", "session expired", "unauthorized"],
        "content_blocked": ["blocked", "content policy", "against our policies"],
        "maintenance": ["under maintenance", "temporarily unavailable"],
    }
