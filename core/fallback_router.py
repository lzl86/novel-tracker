"""
Multi-source Fallback Router.
Handles dynamic search query building, lightweight SERP querying, domain scoring/routing,
and heuristic content retrieval when the primary source fails or returns incomplete data.
"""

import asyncio
import re
import urllib.parse
from typing import List, Optional, Tuple
import httpx
from bs4 import BeautifulSoup

from core.exceptions import DataIncompleteError, SourceExhaustedError
from core.heuristic_extractor import HeuristicExtractor
from core.pipeline import RegexCleaningPipeline


# Domain Routing Strategy Table
DOMAIN_PRIORITY = {
    # High quality, full-text novel mirrors (+100 to +50)
    "51read.org": 100,
    "bige3.cc": 90,
    "bqg123.net": 85,
    "xbiquwx.la": 80,
    "bqg.biz": 80,
    "69shuba.cx": 75,
    "69shu.me": 75,
    "shuhaige.net": 70,
    "ttkan.co": 65,
    "piaotia.com": 60,
    "89wx.cc": 60,
    "ddxs.com": 50,
}

DOMAIN_BLACKLIST = {
    # Forum, social media, video and preview-only paywalled domains
    "tieba.baidu.com",
    "zhihu.com",
    "bilibili.com",
    "weibo.com",
    "douban.com",
    "xiaohongshu.com",
    "qidian.com",
    "readnovel.com",
    "hongxiu.com",
    "yunqi.qq.com",
    "chuangshi.qq.com",
    "wenku.novel.qq.com",
    "fanqienovel.com",
    "faloo.com",
    "zongheng.com",
}


class DomainStrategy:
    @staticmethod
    def score_url(url: str) -> int:
        """Returns priority score for a URL. Negative score indicates blacklisted domain."""
        try:
            parsed = urllib.parse.urlparse(url)
            netloc = parsed.netloc.lower().split(':')[0]
            
            # Check blacklist
            for bl in DOMAIN_BLACKLIST:
                if bl in netloc:
                    return -1000

            # Check whitelist priority
            for wl, score in DOMAIN_PRIORITY.items():
                if wl in netloc:
                    return score

            # Default positive score for unclassified domains
            return 10
        except Exception:
            return -1000

    @staticmethod
    def filter_and_sort_candidates(urls: List[str]) -> List[str]:
        """Filters out blacklisted URLs and sorts candidates by domain score."""
        scored = []
        seen = set()
        for u in urls:
            if u not in seen and u.startswith("http"):
                seen.add(u)
                score = DomainStrategy.score_url(u)
                if score > 0:
                    scored.append((score, u))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [u for _, u in scored]


class FallbackRouter:
    def __init__(self, timeout: float = 8.0, min_char_length: int = 500):
        self.timeout = timeout
        self.extractor = HeuristicExtractor()
        self.pipeline = RegexCleaningPipeline(min_char_length=min_char_length)
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }

    def build_query(self, novel_name: str, chapter_title: str) -> str:
        """
        Dynamically construct a structured search query.
        """
        # Clean chapter title from brackets and noise
        clean_ch = re.sub(r'[\(（].*?[\)）]', '', chapter_title).strip()
        negative_filters = "-site:tieba.baidu.com -site:zhihu.com -site:bilibili.com -site:weibo.com"
        return f'"{novel_name}" "{clean_ch}" "完整" {negative_filters}'

    async def query_serp(self, query: str, limit: int = 5) -> List[str]:
        """
        Query lightweight static SERP endpoints (DuckDuckGo / Sogou) to get top candidate URLs.
        """
        candidates: List[str] = []
        encoded_q = urllib.parse.quote(query)

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True, verify=False) as client:
            # 1. DuckDuckGo HTML endpoint
            try:
                ddg_url = f"https://html.duckduckgo.com/html/?q={encoded_q}"
                resp = await client.post(ddg_url, data={"q": query})
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.select(".result__url, .result__title a"):
                        href = a.get("href", "")
                        if "uddg=" in href:
                            m = re.search(r'uddg=([^&]+)', href)
                            if m:
                                href = urllib.parse.unquote(m.group(1))
                        if href.startswith("http"):
                            candidates.append(href)
            except Exception:
                pass

            # 2. Sogou Web search fallback
            if len(candidates) < limit:
                try:
                    sogou_url = f"https://www.sogou.com/web?query={encoded_q}"
                    resp = await client.get(sogou_url)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        for a in soup.select(".results .vrwrap a, .results .rb a"):
                            href = a.get("href", "")
                            if href.startswith("/"):
                                href = f"https://www.sogou.com{href}"
                            if href.startswith("http") and "sogou.com/link" in href:
                                candidates.append(href)
                except Exception:
                    pass

        return DomainStrategy.filter_and_sort_candidates(candidates)[:limit]

    async def probe_and_extract(
        self,
        novel_name: str,
        chapter_title: str,
        target_url: str,
        client: httpx.AsyncClient
    ) -> Optional[str]:
        """
        Probe a candidate URL, heuristically extract content and validate via pipeline.
        """
        try:
            resp = await client.get(target_url, timeout=self.timeout)
            if resp.status_code != 200:
                return None

            enc = resp.encoding if resp.encoding and resp.encoding != 'iso-8859-1' else 'utf-8'
            try:
                html = resp.content.decode(enc, errors='replace')
            except Exception:
                html = resp.text

            # Heuristic extraction
            raw_extracted = self.extractor.extract_article_text(html, url=target_url)
            if not raw_extracted:
                return None

            # Pipeline cleaning & minimum threshold validation
            clean_body = self.pipeline.clean_text(
                raw_text=raw_extracted,
                chapter_title=chapter_title,
                source_url=target_url
            )
            return clean_body
        except DataIncompleteError:
            return None
        except Exception:
            return None

    async def fallback_route(self, novel_name: str, chapter_title: str) -> Tuple[str, str]:
        """
        Main fallback entry point. Dispatches dynamic SERP query and probes top candidates.
        Returns:
            (clean_chapter_content, matched_source_url)
        Raises:
            SourceExhaustedError if no candidate returns valid full text.
        """
        query = self.build_query(novel_name, chapter_title)
        candidate_urls = await self.query_serp(query, limit=6)

        if not candidate_urls:
            raise SourceExhaustedError(chapter_title, [])

        attempted = []
        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True, verify=False) as client:
            for url in candidate_urls:
                attempted.append(url)
                content = await self.probe_and_extract(novel_name, chapter_title, url, client)
                if content:
                    return content, url

        raise SourceExhaustedError(chapter_title, attempted)
