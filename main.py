"""Main entry point for web2api"""

import asyncio
import sys
import os
from loguru import logger
import uvicorn
from web2api.config import config
from web2api.api.routes import app

# Fix Windows GBK encoding for emoji output
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def setup_logging():
    """配置日志"""
    logger.remove()
    logger.add(
        "logs/web2api.log",
        rotation="500 MB",
        retention="7 days",
        level="DEBUG" if config.debug else "INFO"
    )
    logger.add(
        lambda msg: print(msg, end='', flush=True),
        level="DEBUG" if config.debug else "INFO",
        format="{time:HH:mm:ss} | {level:<7} | {message}",
    )


if __name__ == "__main__":
    setup_logging()
    
    logger.info(f"""
    ╔═══════════════════════════════════════════════╗
    ║          🚀 Web2API Gateway v1.3.0           ║
    ║  AI Web Interface to OpenAI API Gateway      ║
    ║                                              ║
    ║  📖 http://{config.host}:{config.port}                       ║
    ║  🔗 OpenAI API: POST /v1/chat/completions   ║
    ║  🔗 Native API: POST /api/v1/message        ║
    ║  📊 Stats: GET /api/v1/stats                ║
    ║  🏦 Accounts: GET /api/v1/admin/accounts    ║
    ╚═══════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="debug" if config.debug else "info"
    )
