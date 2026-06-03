"""Microsoft Copilot platform - copilot.microsoft.com"""

from web2api.platforms.base import BaseAutomator


class CopilotAutomator(BaseAutomator):
    PLATFORM_NAME = "copilot"
    URLS = {"base": "https://copilot.microsoft.com", "new_chat": "https://copilot.microsoft.com"}
    REQUIRES_LOGIN = False
    SUPPORTS_GUEST = True

    SELECTORS = {
        "input": [
            'textarea#userInput',
            'textarea[placeholder*="Message"]',
            'textarea[placeholder*="Copilot"]',
        ],
        "send": [
            'button[data-testid="submit-button"]',
            'button[aria-label="Submit message"]',
            'button[aria-label="Submit"]',
        ],
        "response": [
            'div[class*="response"]',
            'div[class*="message-content"]',
            'div[class*="markdown"]',
        ],
        "new_chat": [
            'button[data-testid="sidebar-new-conversation-nav-item"]',
            'button[aria-label="New chat"]',
        ],
    }

    ERROR_PATTERNS = {
        "rate_limit": ["rate limit", "too many requests", "please slow down"],
        "banned": ["suspended", "banned", "account disabled"],
        "captcha": ["captcha", "verify you are human", "checking your browser"],
        "login_required": ["session expired", "unauthorized", "please log in to continue"],
        "content_blocked": ["blocked", "content policy"],
        "maintenance": ["under maintenance", "temporarily unavailable"],
    }
