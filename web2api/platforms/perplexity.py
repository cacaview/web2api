"""Perplexity platform - perplexity.ai"""

from web2api.platforms.base import BaseAutomator


class PerplexityAutomator(BaseAutomator):
    PLATFORM_NAME = "perplexity"
    URLS = {"base": "https://www.perplexity.ai", "new_chat": "https://www.perplexity.ai"}
    REQUIRES_LOGIN = False
    SUPPORTS_GUEST = True

    SELECTORS = {
        "input": [
            'textarea[placeholder*="Ask"]',
            'textarea',
            'div[contenteditable="true"]',
        ],
        "send": [
            'button[aria-label="Submit"]',
            'button[aria-label="Search"]',
            'button[class*="submit"]',
        ],
        "response": [
            'div[class*="prose"]',
            'div[class*="markdown"]',
            'div[class*="answer"]',
        ],
        "new_chat": [
            'a[href="/"]',
            'button:has-text("New")',
        ],
    }

    ERROR_PATTERNS = {
        "rate_limit": ["rate limit", "too many requests", "please slow down"],
        "banned": ["suspended", "banned"],
        "captcha": ["captcha", "verify you are human"],
        "login_required": ["sign in", "log in", "session expired"],
        "content_blocked": ["blocked", "content policy"],
        "maintenance": ["under maintenance", "temporarily unavailable"],
    }
