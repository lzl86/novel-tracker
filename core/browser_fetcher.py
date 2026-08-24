"""
Browser Fetcher and Anti-WAF Challenge Bridge.
Launches system browser (Edge / Chrome) via Playwright or uses injected clearance cookies
to bypass Cloudflare Turnstile, 5-second challenges, and JavaScript rendering barriers.
"""

import asyncio
import json
import os
import re
from typing import Optional, Dict


class BrowserFetcher:
    def __init__(self, headless: bool = True, timeout: int = 25000):
        self.headless = headless
        self.timeout = timeout
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    async def fetch_html(self, url: str, wait_seconds: int = 6) -> Optional[str]:
        """
        Fetches full rendered HTML by launching system browser context.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print("⚠️ Playwright 未安装，请运行 `pip install playwright` 以启用浏览器抗盾功能。")
            return None

        print(f"🛡️ [Anti-WAF] 正在启动浏览器内核穿透 Cloudflare 盾: {url[:45]}...")

        async with async_playwright() as p:
            # Prefer system Edge, fallback to Chrome or default chromium
            browser = None
            for channel in ["msedge", "chrome", None]:
                try:
                    if channel:
                        browser = await p.chromium.launch(channel=channel, headless=self.headless)
                    else:
                        browser = await p.chromium.launch(headless=self.headless)
                    if browser:
                        break
                except Exception:
                    continue

            if not browser:
                print("❌ 未能在本地检测到可用的 Edge 或 Chrome 浏览器内核。")
                return None

            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800}
                )

                # Inject cookies from config if present
                cookie_str = self.config.get("cloudflare_cookie", "")
                if cookie_str:
                    # Parse cookies
                    cookies = []
                    for item in cookie_str.split(";"):
                        if "=" in item:
                            k, v = item.strip().split("=", 1)
                            domain = re.sub(r'^https?://([^/]+).*$', r'\1', url)
                            cookies.append({"name": k, "value": v, "domain": domain, "path": "/"})
                    if cookies:
                        await context.add_cookies(cookies)

                page = await context.new_page()
                await page.goto(url, timeout=self.timeout, wait_until="domcontentloaded")

                # Wait for Cloudflare challenge redirect
                for _ in range(int(wait_seconds)):
                    title = await page.title()
                    if "Just a moment" not in title and "请稍候" not in title and "Cloudflare" not in title:
                        break
                    # Attempt clicking turnstile checkbox
                    for f in page.frames:
                        if "cloudflare.com" in f.url:
                            try:
                                box = await f.query_selector("input, label, span, .ctp-checkbox-label")
                                if box:
                                    await box.click()
                            except Exception:
                                pass
                    await page.wait_for_timeout(1000)

                html = await page.content()
                await browser.close()
                return html

            except Exception as e:
                print(f"❌ 浏览器渲染异常: {e}")
                if browser:
                    await browser.close()
                return None
