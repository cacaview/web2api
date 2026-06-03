"""Development utilities and debugging tools"""

import asyncio
from loguru import logger
from web2api.config import config


async def test_gemini_connection() -> bool:
    """
    测试Gemini连接

    用法：
    python -c "from web2api.dev_utils import *; import asyncio; asyncio.run(test_gemini_connection())"
    """
    logger.info("🧪 Testing Gemini connection...")

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            logger.info(f"📍 Navigating to {config.gemini.base_url}...")
            await page.goto(config.gemini.base_url, wait_until="networkidle", timeout=30000)

            new_chat_btn = await page.query_selector(config.gemini.new_chat_selector)

            if new_chat_btn:
                logger.info("✅ Gemini is accessible and you appear to be logged in")
                result = True
            else:
                logger.warning("⚠️  Gemini loaded but new chat button not found - you may need to log in")
                result = False

            await page.close()
            await browser.close()

            return result

    except Exception as e:
        logger.error(f"❌ Connection test failed: {e}")
        return False


async def test_sqlite_connection() -> bool:
    """
    测试SQLite连接

    用法：
    python -c "from web2api.dev_utils import *; import asyncio; asyncio.run(test_sqlite_connection())"
    """
    logger.info("🧪 Testing SQLite connection...")

    try:
        from web2api.core.storage import get_store

        store = get_store()
        # 简单查询验证连接
        accounts = store.get_all_accounts()
        logger.info(f"✅ SQLite connected: {len(accounts)} accounts found")
        return True

    except Exception as e:
        logger.error(f"❌ SQLite connection failed: {e}")
        return False


async def run_all_tests():
    """运行所有诊断测试"""
    logger.info("""
    ╔════════════════════════════════════════════╗
    ║   Web2API Diagnostic Tests                 ║
    ╚════════════════════════════════════════════╝
    """)

    logger.info("🔍 Configuration:")
    logger.info(f"   Host: {config.host}")
    logger.info(f"   Port: {config.port}")
    logger.info(f"   Gemini: {config.gemini.base_url}")
    logger.info(f"   Debug: {config.debug}")
    logger.info("")

    tests = [
        ("SQLite Connection", test_sqlite_connection),
        ("Gemini Connection", test_gemini_connection),
    ]

    results = {}
    for name, test_func in tests:
        logger.info(f"📋 Running: {name}...")
        try:
            result = await test_func()
            results[name] = "✅ PASS" if result else "❌ FAIL"
        except Exception as e:
            logger.error(f"Exception during {name}: {e}")
            results[name] = "❌ ERROR"
        logger.info("")

    logger.info("📊 Test Results:")
    for name, status in results.items():
        logger.info(f"   {status} - {name}")

    all_passed = all(status.startswith("✅") for status in results.values())

    if all_passed:
        logger.info("\n🎉 All tests passed! You're ready to run web2api.")
    else:
        logger.warning("\n⚠️  Some tests failed. Please review the errors above.")

    return all_passed


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        if test_name == "sqlite":
            asyncio.run(test_sqlite_connection())
        elif test_name == "gemini":
            asyncio.run(test_gemini_connection())
        else:
            logger.error(f"Unknown test: {test_name}")
            logger.info("Available tests: sqlite, gemini")
    else:
        asyncio.run(run_all_tests())
