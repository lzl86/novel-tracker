"""
Direct Site Search Hub (站内直连检索池).
Bypasses public search engines by dispatching search queries directly to known novel CMS endpoints.
Solves the '搜不到' (noindex/nofollow exclusion) and '不让搜' (public SERP blocking) problems.
"""

import asyncio
import re
import urllib.parse
from typing import List, Tuple, Dict, Optional
import httpx
from bs4 import BeautifulSoup

from core.fallback_router import DomainStrategy


class DirectSiteSearchHub:
    """
    Directly queries private search endpoints of novel sites (JieQi, YGBook, KuangXiang, etc.).
    """
    SEARCH_ENDPOINTS = [
        # 1. 51read
        {
            "name": "51read",
            "url": "https://m.51read.org/search/?searchkey={encoded_utf8}",
            "method": "GET",
            "encoding": "utf-8",
            "link_selector": "a[href*='/xiaoshuo/'], a[href*='/zhangjiemulu/']",
            "base_url": "https://m.51read.org"
        },
        # 2. 笔趣阁 3 (bige3)
        {
            "name": "bige3",
            "url": "https://www.bige3.cc/s?q={encoded_utf8}",
            "method": "GET",
            "encoding": "utf-8",
            "link_selector": ".bookbox a, .search-list li a, .common-book a, a[href*='/book/']",
            "base_url": "https://www.bige3.cc"
        },
        # 3. 新笔趣微 (xbiquwx)
        {
            "name": "xbiquwx",
            "url": "https://www.xbiquwx.la/modules/article/search.php?searchkey={encoded_gbk}",
            "method": "GET",
            "encoding": "gbk",
            "link_selector": "a[href*='/book/'], a[href*='/modules/']",
            "base_url": "https://www.xbiquwx.la"
        },
        # 4. 89文学 (89wx)
        {
            "name": "89wx",
            "url": "https://www.89wx.cc/search/?searchkey={encoded_utf8}",
            "method": "GET",
            "encoding": "utf-8",
            "link_selector": "a[href*='/book/'], a[href*='/read/']",
            "base_url": "https://www.89wx.cc"
        },
        # 5. 飘天文学 (piaotian)
        {
            "name": "piaotian",
            "url": "https://www.piaotia.com/modules/article/search.php?searchkey={encoded_gbk}",
            "method": "GET",
            "encoding": "gbk",
            "link_selector": "a[href*='/book/'], a[href*='/html/']",
            "base_url": "https://www.piaotia.com"
        },
        # 6. 书海阁 (shuhaige)
        {
            "name": "shuhaige",
            "url": "https://www.shuhaige.net/search/?searchkey={encoded_utf8}",
            "method": "GET",
            "encoding": "utf-8",
            "link_selector": "a[href*='/book/'], a[href*='/shu/']",
            "base_url": "https://www.shuhaige.net"
        }
    ]

    def __init__(self, timeout: float = 6.0):
        self.timeout = timeout
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }

    async def _query_single_site(
        self,
        client: httpx.AsyncClient,
        site_cfg: Dict,
        book_name: str
    ) -> List[Tuple[str, str, str]]:
        """
        Queries a single direct novel site search endpoint.
        Returns: [(book_title, matched_url, site_name), ...]
        """
        results: List[Tuple[str, str, str]] = []
        try:
            enc_utf8 = urllib.parse.quote(book_name, encoding="utf-8")
            try:
                enc_gbk = urllib.parse.quote(book_name, encoding="gbk")
            except Exception:
                enc_gbk = enc_utf8

            target_url = site_cfg["url"].format(
                encoded_utf8=enc_utf8,
                encoded_gbk=enc_gbk
            )

            resp = await client.get(target_url, timeout=self.timeout)
            if resp.status_code != 200:
                return []

            enc = site_cfg.get("encoding", "utf-8")
            try:
                html = resp.content.decode(enc, errors="replace")
            except Exception:
                html = resp.text

            soup = BeautifulSoup(html, "html.parser")
            seen_hrefs = set()

            for a in soup.select(site_cfg.get("link_selector", "a")):
                title_text = a.get_text(strip=True)
                href = a.get("href", "")
                if not href or href.startswith("javascript") or href.startswith("#"):
                    continue

                full_url = urllib.parse.urljoin(site_cfg["base_url"], href)
                if full_url in seen_hrefs:
                    continue
                seen_hrefs.add(full_url)

                # Match relevant title
                clean_name = re.sub(r'[\(（《》）\s]', '', book_name)
                clean_title = re.sub(r'[\(（《》）\s]', '', title_text)

                if clean_name in clean_title or clean_title in clean_name:
                    results.append((title_text, full_url, site_cfg["name"]))

        except Exception:
            pass

        return results

    async def search_all_direct_sites(self, book_name: str) -> List[str]:
        """
        Dispatches concurrent search across all direct novel site endpoints.
        Returns sorted list of validated novel URLs.
        """
        candidates: List[str] = []
        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True, verify=False) as client:
            tasks = [
                self._query_single_site(client, cfg, book_name)
                for cfg in self.SEARCH_ENDPOINTS
            ]
            all_batches = await asyncio.gather(*tasks, return_exceptions=True)

            for batch in all_batches:
                if isinstance(batch, list):
                    for _, url, _ in batch:
                        candidates.append(url)

        return DomainStrategy.filter_and_sort_candidates(candidates)
