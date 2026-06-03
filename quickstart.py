#!/usr/bin/env python
"""Quick start test script for web2api"""

import asyncio
import sys
from pathlib import Path

# 添加项目目录到path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from web2api.dev_utils import run_all_tests


async def main():
    print("""
    ╔════════════════════════════════════════════════════════╗
    ║      🚀 Web2API Quick Start Test                      ║
    ║                                                        ║
    ║  This script will verify your environment setup       ║
    ║  before running the full gateway.                     ║
    ╚════════════════════════════════════════════════════════╝
    """)
    
    success = await run_all_tests()
    
    if success:
        print("""
    ╔════════════════════════════════════════════════════════╗
    ║  ✅ All checks passed!                                ║
    ║                                                        ║
    ║  Next steps:                                          ║
    ║  1. Start Redis: redis-server                         ║
    ║  2. Run gateway: python main.py                       ║
    ║  3. Test API: curl http://localhost:8000/health      ║
    ║                                                        ║
    ║  📖 Full docs: https://github.com/web2api/web2api    ║
    ╚════════════════════════════════════════════════════════╝
        """)
        return 0
    else:
        print("""
    ╔════════════════════════════════════════════════════════╗
    ║  ❌ Some checks failed                                ║
    ║                                                        ║
    ║  Troubleshooting:                                     ║
    ║  1. Check Redis is installed: redis-server --version ║
    ║  2. Start Redis: redis-server                         ║
    ║  3. Verify Gemini is accessible via browser          ║
    ║  4. Check .env configuration                          ║
    ║                                                        ║
    ║  📖 See DEPLOYMENT.md for detailed instructions      ║
    ╚════════════════════════════════════════════════════════╝
        """)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
