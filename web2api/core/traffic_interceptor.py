"""Traffic interception and request filtering"""

import re
from typing import List, Optional
from fnmatch import fnmatch
from loguru import logger
from playwright.async_api import Route, Request


class TrafficInterceptor:
    """网络流量拦截器 - 实现住宅代理流量瘦身"""
    
    def __init__(self, block_patterns: List[str]):
        """
        初始化拦截器
        
        Args:
            block_patterns: 要拦截的URL模式列表（支持通配符）
        """
        self.block_patterns = block_patterns
        self.blocked_count = 0
        self.allowed_count = 0
    
    def should_block(self, url: str, resource_type: str) -> bool:
        """
        判断是否应该拦截该请求
        
        Args:
            url: 请求URL
            resource_type: 资源类型 (image, stylesheet, font, media 等)
        
        Returns:
            是否应该拦截
        """
        # 按资源类型快速检查
        if resource_type in ['image', 'media', 'font', 'stylesheet']:
            return True
        
        # 按模式检查
        url_lower = url.lower()
        for pattern in self.block_patterns:
            if fnmatch(url_lower, pattern.lower()):
                return True
        
        # 特殊检查：分析埋点脚本
        if 'analytics' in url_lower or 'tracking' in url_lower:
            return True
        
        return False
    
    async def intercept_route(self, route: Route) -> None:
        """
        Playwright路由拦截处理器
        
        该方法应该在page.route中注册：
        await page.route('**/*', interceptor.intercept_route)
        """
        request = route.request
        resource_type = request.resource_type
        url = request.url
        
        if self.should_block(url, resource_type):
            self.blocked_count += 1
            logger.debug(f"⛔ Blocked {resource_type}: {url[:80]}")
            await route.abort()
        else:
            self.allowed_count += 1
            await route.continue_()
    
    def get_stats(self) -> dict:
        """获取拦截统计信息"""
        total = self.blocked_count + self.allowed_count
        return {
            "blocked": self.blocked_count,
            "allowed": self.allowed_count,
            "total": total,
            "block_ratio": f"{100 * self.blocked_count / total:.1f}%" if total > 0 else "0%"
        }


class ContentDisabler:
    """DOM内容禁用器 - 二次防护：注入JS禁用重型资源加载"""
    
    @staticmethod
    async def inject_blockers(page) -> None:
        """
        注入JavaScript来禁用资源加载
        适用于某些绕过route的异步加载资源
        """
        # 禁用图片加载
        await page.evaluate("""
            () => {
                const observer = new MutationObserver((mutations) => {
                    mutations.forEach((mutation) => {
                        mutation.addedNodes.forEach((node) => {
                            if (node.nodeName === 'IMG') {
                                node.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
                            }
                            if (node.nodeName === 'LINK' && node.rel === 'stylesheet') {
                                node.disabled = true;
                            }
                        });
                    });
                });
                observer.observe(document.documentElement, {childList: true, subtree: true});
            }
        """)
        
        logger.info("✅ Content blockers injected")
