"""Platform registry - 平台注册表"""

from typing import Dict
from web2api.platforms.base import BaseAutomator, PlatformError
from web2api.platforms.gemini import GeminiAutomator
from web2api.platforms.chatgpt import ChatGPTAutomator
from web2api.platforms.claude import ClaudeAutomator
from web2api.platforms.deepseek import DeepSeekAutomator
from web2api.platforms.kimi import KimiAutomator
from web2api.platforms.qwen import QwenAutomator
from web2api.platforms.doubao import DoubaoAutomator
from web2api.platforms.glm import GLMAutomator
from web2api.platforms.copilot import CopilotAutomator
from web2api.platforms.yuanbao import YuanbaoAutomator
from web2api.platforms.perplexity import PerplexityAutomator
from web2api.platforms.grok import GrokAutomator

# 平台注册表
PLATFORMS: Dict[str, type] = {
    "gemini": GeminiAutomator,
    "chatgpt": ChatGPTAutomator,
    "claude": ClaudeAutomator,
    "deepseek": DeepSeekAutomator,
    "kimi": KimiAutomator,
    "qwen": QwenAutomator,
    "doubao": DoubaoAutomator,
    "glm": GLMAutomator,
    "copilot": CopilotAutomator,
    "yuanbao": YuanbaoAutomator,
    "perplexity": PerplexityAutomator,
    "grok": GrokAutomator,
}

# Model 名称 → 平台映射
MODEL_TO_PLATFORM = {
    # Gemini
    "gemini": "gemini", "gemini-2.0": "gemini", "gemini-2.0-flash": "gemini",
    # ChatGPT
    "gpt": "chatgpt", "gpt-4": "chatgpt", "gpt-4o": "chatgpt", "gpt-4-turbo": "chatgpt",
    "chatgpt": "chatgpt", "o1": "chatgpt", "o3": "chatgpt", "o4-mini": "chatgpt",
    # Claude
    "claude": "claude", "claude-3": "claude", "claude-3-opus": "claude",
    "claude-3-sonnet": "claude", "claude-3-haiku": "claude", "claude-sonnet": "claude",
    # DeepSeek
    "deepseek": "deepseek", "deepseek-chat": "deepseek", "deepseek-reasoner": "deepseek",
    "deepseek-v3": "deepseek", "deepseek-r1": "deepseek",
    # Kimi
    "kimi": "kimi", "kimi-k2": "kimi", "moonshot": "kimi",
    # Qwen
    "qwen": "qwen", "qwen-max": "qwen", "qwen-plus": "qwen", "qwen-turbo": "qwen",
    "tongyi": "qwen", "通义": "qwen", "千问": "qwen",
    # Doubao
    "doubao": "doubao", "豆包": "doubao",
    # GLM
    "glm": "glm", "chatglm": "glm", "智谱": "glm", "智谱清言": "glm", "glm-4": "glm",
    # Copilot
    "copilot": "copilot", "bing": "copilot", "ms-copilot": "copilot",
    # Yuanbao
    "yuanbao": "yuanbao", "元宝": "yuanbao", "腾讯元宝": "yuanbao",
    # Perplexity
    "perplexity": "perplexity", "pplx": "perplexity",
    # Grok
    "grok": "grok", "grok-2": "grok", "grok-3": "grok", "xai": "grok",
}


def resolve_platform(model_or_platform: str) -> str:
    """从 model 名称或平台名解析出平台标识"""
    key = model_or_platform.lower().strip()
    if key in PLATFORMS:
        return key
    return MODEL_TO_PLATFORM.get(key, "gemini")


def get_automator_class(platform: str):
    """获取平台的 Automator 类"""
    return PLATFORMS.get(platform, PLATFORMS["gemini"])


__all__ = [
    "BaseAutomator", "PlatformError",
    "PLATFORMS", "MODEL_TO_PLATFORM", "resolve_platform", "get_automator_class",
]
