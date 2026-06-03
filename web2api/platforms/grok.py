"""Grok platform - x.com/i/grok (xAI)"""

from web2api.platforms.base import BaseAutomator


class GrokAutomator(BaseAutomator):
    PLATFORM_NAME = "grok"
    URLS = {"base": "https://x.com/i/grok", "new_chat": "https://x.com/i/grok"}
    REQUIRES_LOGIN = True
    SUPPORTS_GUEST = False

    SELECTORS = {
        "input": [
            'div[data-testid="tweetTextarea_0"]',
            'div[role="textbox"][contenteditable="true"]',
            'textarea',
        ],
        "send": [
            'button[data-testid="tweetButton"]',
            'button[aria-label="Send"]',
            'button[aria-label="发送"]',
        ],
        "response": [
            'div[class*="message-content"]',
            'div[data-testid="botMessage"]',
            'div[class*="markdown"]',
        ],
        "new_chat": [
            'a[href="/i/grok"]',
        ],
    }

    ERROR_PATTERNS = {
        "rate_limit": ["rate limit", "too many requests", "please slow down"],
        "banned": ["suspended", "banned", "account locked"],
        "captcha": ["captcha", "verify you are human"],
        "login_required": ["sign in", "log in", "session expired", "unauthorized"],
        "content_blocked": ["blocked", "content policy"],
        "maintenance": ["under maintenance", "temporarily unavailable"],
    }
