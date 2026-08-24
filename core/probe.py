"""
Master Index Probe.
Responsible for lightweight metadata monitoring and catalog probing.
"""

import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin
import httpx
from bs4 import BeautifulSoup

from core.parser import extract_chapter_number
from core.exceptions import NetworkProbeError


@dataclass
class ChapterMetadata:
    index: int
    title: str
    url: str
    chapter_num: float


class MasterProbe:
    def __init__(self, timeout: float = 10.0):
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

    async def probe_catalog(self, catalog_url: str) -> List[ChapterMetadata]:
        """
        Extract list of chapter metadata items from a catalog URL, supporting multi-page catalogs.
        """
        chapters: List[ChapterMetadata] = []
        raw_items = []
        seen_urls = set()

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True, verify=False) as client:
            page = 1
            max_pages = 60

            while page <= max_pages:
                current_url = catalog_url
                if page > 1:
                    if "/zhangjiemulu/" in catalog_url:
                        base = re.sub(r'(/zhangjiemulu/\d+)(?:/\d+)?$', r'\1', catalog_url.rstrip('/'))
                        current_url = f"{base}/{page}"
                    elif "page=" in catalog_url:
                        current_url = re.sub(r'page=\d+', f'page={page}', catalog_url)
                    elif re.search(r'_\d+\.html', catalog_url):
                        current_url = re.sub(r'_\d+\.html', f'_{page}.html', catalog_url)
                    else:
                        break

                try:
                    resp = await client.get(current_url)
                    if resp.status_code != 200:
                        break

                    enc = resp.encoding if resp.encoding and resp.encoding != 'iso-8859-1' else 'utf-8'
                    try:
                        html = resp.content.decode(enc, errors='replace')
                    except Exception:
                        html = resp.text

                    soup = BeautifulSoup(html, "html.parser")
                    all_a = soup.find_all("a", href=True)
                    page_new_count = 0

                    for a in all_a:
                        raw_title = a.get_text(strip=True)
                        href = a["href"]

                        if any(nav in raw_title for nav in ("上一页", "下一页", "目录", "首页", "书架", "返回", "最新章节", "开始阅读")):
                            continue

                        clean_title = re.sub(r'(?:APP免费|VIP免费|免费阅读|更新时间.*$)', '', raw_title).strip()

                        if re.search(r'(第\s*[0-9零一二两三四五六七八九十百千万]+\s*[章节回集卷篇节]|^\s*[0-9]+[\.、\s]|终章|大结局|完本感言|序章|楔子)', clean_title):
                            full_url = urljoin(current_url, href)
                            if full_url not in seen_urls:
                                seen_urls.add(full_url)
                                num, _ = extract_chapter_number(clean_title)
                                raw_items.append((num, clean_title, full_url))
                                page_new_count += 1

                    if page_new_count == 0:
                        break

                    has_next = any("下一页" in a.get_text() for a in all_a)
                    if not has_next and page > 1:
                        break

                    if not has_next and "/zhangjiemulu/" not in catalog_url:
                        break

                    page += 1
                except Exception as e:
                    raise NetworkProbeError(f"Failed to probe catalog at {current_url}: {e}")

        # Chronological sort
        if len(raw_items) > 1 and raw_items[0][0] > raw_items[-1][0] and raw_items[-1][0] > 0:
            raw_items.reverse()
        else:
            valid_nums = [item for item in raw_items if item[0] > 0]
            if len(valid_nums) > len(raw_items) * 0.7:
                raw_items.sort(key=lambda x: x[0])

        for idx, (num, c_title, c_url) in enumerate(raw_items, start=1):
            chapters.append(ChapterMetadata(index=idx, title=c_title, url=c_url, chapter_num=num))

        return chapters
