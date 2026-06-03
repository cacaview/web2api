"""Humanized interaction utilities - 拟人化操作"""

import asyncio
import random
from typing import List
from loguru import logger


class GaussianHumanizer:
    """高斯分布与贝塞尔曲线拟人化操作器"""
    
    @staticmethod
    def gaussian_noise(mu: float = 0.0, sigma: float = 0.1) -> float:
        """
        生成高斯分布随机抖动
        用于模拟人类的不规则操作
        """
        return random.gauss(mu, sigma)
    
    @staticmethod
    def bezier_curve(start: float, end: float, steps: int = 10) -> List[float]:
        """
        使用贝塞尔曲线生成平滑的过渡
        模拟人类的加速/减速动作
        """
        # 简化的3阶贝塞尔曲线
        control_p1 = start + (end - start) * 0.33
        control_p2 = start + (end - start) * 0.67
        
        curve = []
        for i in range(steps):
            t = i / (steps - 1) if steps > 1 else 0
            
            # B(t) = (1-t)³P0 + 3(1-t)²t·P1 + 3(1-t)t²·P2 + t³·P3
            b0 = (1 - t) ** 3
            b1 = 3 * (1 - t) ** 2 * t
            b2 = 3 * (1 - t) * t ** 2
            b3 = t ** 3
            
            point = b0 * start + b1 * control_p1 + b2 * control_p2 + b3 * end
            curve.append(point)
        
        return curve
    
    @staticmethod
    async def humanized_type(
        page,
        selector_or_handle,
        text: str,
        delay_min: float = 50,
        delay_max: float = 200,
        typo_rate: float = 0.02
    ) -> None:
        """
        拟人化打字 - 带随机延迟和偶尔的输入错误纠正
        
        Args:
            page: Playwright Page对象
            selector_or_handle: CSS选择器或元素句柄
            text: 要输入的文本
            delay_min: 最小延迟（毫秒）
            delay_max: 最大延迟（毫秒）
            typo_rate: 输入错误率（0.0-1.0）
        """
        # 获取元素句柄
        if isinstance(selector_or_handle, str):
            handle = await page.query_selector(selector_or_handle)
            if not handle:
                raise ValueError(f"Element not found: {selector_or_handle}")
        else:
            handle = selector_or_handle
        
        logger.debug(f"📝 Typing: {text[:50]}...")
        
        for char in text:
            # 随机输入错误
            if random.random() < typo_rate:
                typo_char = random.choice('abcdefghijklmnopqrstuvwxyz')
                await handle.type(typo_char)
                await asyncio.sleep(random.uniform(delay_min, delay_max) / 1000)
                # 纠正错误（退格）
                await handle.press('Backspace')
                await asyncio.sleep(random.uniform(50, 100) / 1000)
            
            # 正常输入
            await handle.type(char)
            
            # 随机延迟 + 高斯抖动
            base_delay = random.uniform(delay_min, delay_max)
            noise = GaussianHumanizer.gaussian_noise(0, delay_max * 0.1)
            final_delay = max(delay_min, base_delay + noise) / 1000
            await asyncio.sleep(final_delay)
    
    @staticmethod
    async def humanized_click(
        page,
        selector_or_handle,
        move_delay_min: float = 100,
        move_delay_max: float = 500,
        click_delay: float = 100
    ) -> None:
        """
        拟人化点击 - 模拟鼠标移动然后点击
        
        Args:
            page: Playwright Page对象
            selector_or_handle: CSS选择器或元素句柄
            move_delay_min: 鼠标移动最小延迟（毫秒）
            move_delay_max: 鼠标移动最大延迟（毫秒）
            click_delay: 点击延迟（毫秒）
        """
        # 获取元素句柄和位置
        if isinstance(selector_or_handle, str):
            handle = await page.query_selector(selector_or_handle)
            if not handle:
                raise ValueError(f"Element not found: {selector_or_handle}")
        else:
            handle = selector_or_handle
        
        # 获取元素中心坐标
        box = await handle.bounding_box()
        if not box:
            logger.warning("Element has no bounding box, using regular click")
            await handle.click()
            return
        
        target_x = box['x'] + box['width'] / 2
        target_y = box['y'] + box['height'] / 2
        
        # 从当前位置移动到目标位置，使用贝塞尔曲线分步移动
        move_duration = random.uniform(move_delay_min, move_delay_max)

        logger.debug(f"🖱️  Moving to ({target_x:.0f}, {target_y:.0f})")

        # 贝塞尔曲线分步移动
        start_x, start_y = 0, 0
        try:
            # 尝试获取当前鼠标位置
            pos = await page.evaluate("() => ({ x: window._lastMouseX || 0, y: window._lastMouseY || 0 })")
            start_x, start_y = pos.get("x", 0), pos.get("y", 0)
        except Exception:
            pass

        steps = random.randint(8, 15)
        x_curve = GaussianHumanizer.bezier_curve(start_x, target_x, steps)
        y_curve = GaussianHumanizer.bezier_curve(start_y, target_y, steps)

        step_delay = move_duration / steps / 1000
        for sx, sy in zip(x_curve, y_curve):
            await page.mouse.move(sx, sy)
            await asyncio.sleep(step_delay + random.uniform(-0.005, 0.005))

        # 记录最终位置供下次使用
        try:
            await page.evaluate(
                f"() => {{ window._lastMouseX = {target_x}; window._lastMouseY = {target_y}; }}"
            )
        except Exception:
            pass
        
        # 点击
        await page.mouse.click(target_x, target_y)
        logger.debug(f"✓ Clicked")
        await asyncio.sleep(click_delay / 1000)
    
    @staticmethod
    async def random_scroll(
        page,
        min_pixels: int = 100,
        max_pixels: int = 500,
        delay_ms: float = 200
    ) -> None:
        """
        随机滚动页面 - 模拟人类浏览行为
        """
        pixels = random.randint(min_pixels, max_pixels)
        direction = random.choice([-1, 1])
        
        await page.evaluate(f"window.scrollBy(0, {direction * pixels})")
        await asyncio.sleep(delay_ms / 1000)
    
    @staticmethod
    async def random_pause(min_sec: float = 1.0, max_sec: float = 3.0) -> None:
        """
        随机暂停 - 模拟人类思考时间
        """
        pause_duration = random.uniform(min_sec, max_sec)
        logger.debug(f"⏸️  Pausing for {pause_duration:.1f}s")
        await asyncio.sleep(pause_duration)
