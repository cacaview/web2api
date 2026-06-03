"""Claude platform - claude.ai"""

from web2api.platforms.base import BaseAutomator


class ClaudeAutomator(BaseAutomator):
    PLATFORM_NAME = "claude"
    URLS = {"base": "https://claude.ai/new", "new_chat": "https://claude.ai/new"}
    REQUIRES_LOGIN = True
    SUPPORTS_GUEST = False

    SELECTORS = {
        "input": [
            'div.ProseMirror[contenteditable="true"]',
            '[data-placeholder*="Reply"]',
            '.ͼ1 .ProseMirror',
        ],
        "send": [
            'button[aria-label="Send Message"]',
            'button[aria-label="发送消息"]',
            'button.send-button',
        ],
        "response": [
            'div.font-claude-message',
            'div[data-testid="assistant-message"]',
            '.assistant-message',
        ],
        "new_chat": [
            'a[href="/new"]',
            'button:has-text("Start new chat")',
        ],
    }

    ERROR_PATTERNS = {
        "rate_limit": ["rate limit", "too many requests", "please wait", "you've been sending"],
        "banned": ["suspended", "banned", "account disabled"],
        "captcha": ["captcha", "verify you are human"],
        "login_required": ["sign in", "log in", "session expired", "unauthorized"],
        "content_blocked": ["blocked", "content policy", "against our usage policy"],
        "maintenance": ["under maintenance", "temporarily unavailable"],
    }
