"""Development utilities and debugging tools"""

import asyncio
from typing import Optional
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
            
            # 检查登录状态
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


async def test_redis_connection() -> bool:
    """
    测试Redis连接
    
    用法：
    python -c "from web2api.dev_utils import *; import asyncio; asyncio.run(test_redis_connection())"
    """
    logger.info("🧪 Testing Redis connection...")
    
    try:
        import redis.asyncio as aioredis

        redis = aioredis.from_url(
            f"redis://{config.redis.host}:{config.redis.port}",
            db=config.redis.db,
            decode_responses=False,
        )
        result = await redis.ping()
        
        if result:
            logger.info(f"✅ Redis connected: {config.redis.host}:{config.redis.port}")
            result_success = True
        else:
            logger.error("❌ Redis ping failed")
            result_success = False
        
        redis.close()
        await redis.wait_closed()
        
        return result_success
    
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        logger.info("💡 Make sure Redis is running: redis-server")
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
    logger.info(f"   Redis: {config.redis.host}:{config.redis.port}")
    logger.info(f"   Gemini: {config.gemini.base_url}")
    logger.info(f"   Debug: {config.debug}")
    logger.info("")
    
    tests = [
        ("Redis Connection", test_redis_connection),
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
        if test_name == "redis":
            asyncio.run(test_redis_connection())
        elif test_name == "gemini":
            asyncio.run(test_gemini_connection())
        else:
            logger.error(f"Unknown test: {test_name}")
            logger.info("Available tests: redis, gemini")
    else:
        asyncio.run(run_all_tests())
