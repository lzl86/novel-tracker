"""
Heuristic Catalog and Pagination Discovery Engine with Catalog Cohesion & Anti-Noise Validation.
Extracts book metadata, catalog links, and dynamically follows pagination links without hardcoded site rules.
"""

import re
from typing import List, Optional, Tuple, Dict
from urllib.parse import urljoin
import httpx
from bs4 import BeautifulSoup

from core.parser import extract_chapter_number


class HeuristicCatalogExtractor:
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

    def extract_metadata_from_soup(self, soup: BeautifulSoup, page_url: str) -> Dict[str, str]:
        """Extracts book title, author, and description heuristically."""
        meta = {"title": "", "author": "未知", "description": ""}

        # 1. OpenGraph / Novel Meta Tags
        og_title = soup.find("meta", property=re.compile(r"og:(?:novel:)?book_name|og:title", re.I))
        if og_title and og_title.get("content"):
            meta["title"] = og_title["content"].strip()

        og_author = soup.find("meta", property=re.compile(r"og:(?:novel:)?author", re.I))
        if og_author and og_author.get("content"):
            meta["author"] = og_author["content"].strip()

        # 2. Heading inspection
        if not meta["title"]:
            h1 = soup.find("h1")
            if h1:
                meta["title"] = h1.get_text(strip=True)

        if not meta["title"] and soup.title:
            t = soup.title.get_text(strip=True)
            m = re.search(r'《(.*?)》', t)
            if m:
                meta["title"] = m.group(1)
            else:
                meta["title"] = re.sub(r'[_|\-—].*$', '', t).replace('最新章节', '').replace('全文阅读', '').strip()

        if meta["author"] == "未知":
            full_text = soup.get_text()
            m = re.search(r'作\s*者[：:\s]*([^\s,，。；|_\-—\n\r<]{1,12})', full_text)
            if m:
                meta["author"] = m.group(1).strip()

        return meta

    def find_catalog_link_from_detail(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """Finds entry link to full catalog from a book detail page."""
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if any(k in text for k in ("全部章节", "章节目录", "查看目录", "完整目录", "目录列表", "更多章节")):
                return urljoin(current_url, a["href"])

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(k in href for k in ("/mulu", "/catalog", "/chapters", "/zhangjie", "/dir")):
                return urljoin(current_url, href)

        return None

    def find_next_page_link(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """Finds dynamic '下一页' link from catalog page."""
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if any(k == text for k in ("下一页", "下页", "下一頁", "下頁", "下一组", "Next")):
                href = a["href"]
                if not href.startswith("javascript") and not href.startswith("#"):
                    target = urljoin(current_url, href)
                    if target != current_url:
                        return target
        return None

    @staticmethod
    def is_valid_catalog(chapters: List[Tuple[float, str, str]]) -> bool:
        """
        Validates if extracted chapter list belongs to a genuine single novel catalog,
        and not a random multi-book search/tag aggregation snippet.
        """
        if not chapters:
            return False

        # If we have >= 15 chapters, it's very likely a genuine catalog
        if len(chapters) >= 15:
            return True

        # If < 15 chapters, check numerical continuity
        nums = [num for num, title, url in chapters if num > 0]
        if not nums:
            # If all are unnumbered, require at least 5 chapters
            return len(chapters) >= 5

        # Check if numbers start from 1..N (e.g. chapters 1, 2, 3...)
        if min(nums) <= 3 and (max(nums) - min(nums)) <= len(nums) * 3:
            return True

        # If chapters have massive jump gaps (e.g. 111, 343, 912, 1053), this is an aggregator page
        if len(nums) >= 3:
            jumps = [nums[i+1] - nums[i] for i in range(len(nums)-1)]
            avg_jump = sum(jumps) / len(jumps)
            if avg_jump > 30:
                # Discontinuous aggregator page -> Invalid catalog
                return False

        return True

    async def discover_catalog(
        self,
        start_url: str,
        html_preset: Optional[str] = None
    ) -> Tuple[Dict[str, str], List[Tuple[int, str, str, float]]]:
        """
        Discovers all chapter items by dynamically traversing catalog pagination.
        Returns:
            (metadata_dict, chapters_list: [(index, title, url, chapter_num), ...])
        """
        chapters_raw: List[Tuple[float, str, str]] = []
        seen_urls = set()
        visited_pages = set()
        meta = {"title": "未知小说", "author": "未知"}

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True, verify=False) as client:
            current_url = start_url

            if html_preset:
                soup = BeautifulSoup(html_preset, "html.parser")
            else:
                resp = await client.get(current_url)
                soup = BeautifulSoup(resp.text, "html.parser")

            meta = self.extract_metadata_from_soup(soup, current_url)

            # Pivot from detail page to catalog page if link exists
            catalog_pivot = self.find_catalog_link_from_detail(soup, current_url)
            if catalog_pivot and catalog_pivot != current_url:
                current_url = catalog_pivot

            page_count = 0
            max_pages = 60

            while current_url and page_count < max_pages:
                if current_url in visited_pages:
                    break
                visited_pages.add(current_url)
                page_count += 1

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
                    if not meta["title"] or meta["title"] == "未知小说":
                        meta = self.extract_metadata_from_soup(soup, current_url)

                    all_a = soup.find_all("a", href=True)

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
                                chapters_raw.append((num, clean_title, full_url))

                    # Look for next page link
                    next_page = self.find_next_page_link(soup, current_url)
                    if next_page and next_page not in visited_pages:
                        current_url = next_page
                    else:
                        break

                except Exception:
                    break

        # Validate catalog cohesion
        if not self.is_valid_catalog(chapters_raw):
            return meta, []

        # Chronological sort
        if len(chapters_raw) > 1 and chapters_raw[0][0] > chapters_raw[-1][0] and chapters_raw[-1][0] > 0:
            chapters_raw.reverse()
        else:
            valid_nums = [item for item in chapters_raw if item[0] > 0]
            if len(valid_nums) > len(chapters_raw) * 0.7:
                chapters_raw.sort(key=lambda x: x[0])

        final_chapters = [
            (idx, title, url, num)
            for idx, (num, title, url) in enumerate(chapters_raw, start=1)
        ]
        return meta, final_chapters
