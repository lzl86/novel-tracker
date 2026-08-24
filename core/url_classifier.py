"""
Smart URL and Input Classifier for Universal Novel Extractor.
Classifies input string into: BOOK_NAME, CATALOG_PAGE, CHAPTER_PAGE, BOOK_DETAIL_PAGE.
"""

import enum
import re
from urllib.parse import urlparse
from typing import Tuple, Optional
import httpx
from bs4 import BeautifulSoup


class InputType(enum.Enum):
    BOOK_NAME = "book_name"
    CATALOG_PAGE = "catalog_page"
    CHAPTER_PAGE = "chapter_page"
    BOOK_DETAIL_PAGE = "book_detail_page"
    UNKNOWN_URL = "unknown_url"


class URLClassifier:
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

    def is_url(self, text: str) -> bool:
        """Checks if input is an HTTP/HTTPS URL."""
        if not text:
            return False
        text_clean = text.strip()
        if text_clean.startswith("http://") or text_clean.startswith("https://"):
            try:
                result = urlparse(text_clean)
                return all([result.scheme, result.netloc])
            except Exception:
                return False
        return False

    async def classify(self, input_str: str) -> Tuple[InputType, Optional[dict]]:
        """
        Classifies input string and returns (InputType, metadata_dict).
        """
        text = input_str.strip()
        if not self.is_url(text):
            return InputType.BOOK_NAME, {"book_name": text}

        # Analyze URL structure and fetch HTML for deep classification
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True, verify=False) as client:
                html = ""
                status_code = 0
                try:
                    resp = await client.get(text)
                    status_code = resp.status_code
                    if resp.status_code == 200:
                        enc = resp.encoding if resp.encoding and resp.encoding != 'iso-8859-1' else 'utf-8'
                        try:
                            html = resp.content.decode(enc, errors='replace')
                        except Exception:
                            html = resp.text
                except Exception:
                    pass

                # If 403 / 503 or Cloudflare 5s challenge, fallback to BrowserFetcher
                if status_code in (403, 503) or "Just a moment" in html or "请稍候" in html or not html:
                    try:
                        from core.browser_fetcher import BrowserFetcher
                        bf = BrowserFetcher()
                        rendered = await bf.fetch_html(text)
                        if rendered:
                            html = rendered
                    except Exception:
                        pass

                if not html:
                    return InputType.UNKNOWN_URL, {"url": text, "status_code": status_code}

                soup = BeautifulSoup(html, "html.parser")
                page_title = soup.title.get_text(strip=True) if soup.title else ""

                # Feature 1: Check if it's a chapter reading page
                # (Contains navigation like "上一章" / "下一章" / "目 录" or long story text with few links)
                nav_texts = [a.get_text(strip=True) for a in soup.find_all("a", href=True)]
                has_chap_nav = any(k in "".join(nav_texts) for k in ("下一章", "上一章", "下一页", "上一页"))
                content_container = soup.select_one("#content, #chaptercontent, .read-content, #txtContent, .chapter-box, article")

                # Feature 2: Check chapter anchor density
                all_a = soup.find_all("a", href=True)
                chapter_links = [
                    a for a in all_a 
                    if re.search(r'第\s*[0-9零一二两三四五六七八九十百千万]+\s*[章节回集卷篇节]', a.get_text(strip=True))
                ]

                # Classification Rules:
                # 0. If URL ends with /<digits>.html (e.g. /54444583.html, /123.html) -> CHAPTER_PAGE
                if re.search(r'/\d+(?:_\d+)?\.html$', text):
                    return InputType.CHAPTER_PAGE, {
                        "url": str(resp.url) if 'resp' in locals() and hasattr(resp, 'url') else text,
                        "page_title": page_title,
                        "html": html
                    }

                # 1. If page contains "章节目录", "开始阅读", "加入书架" -> Book Detail Page
                if any(btn in "".join(nav_texts) for btn in ("章节目录", "查看目录", "全部章节", "开始阅读", "免费试读", "加入书架")):
                    return InputType.BOOK_DETAIL_PAGE, {
                        "url": str(resp.url),
                        "page_title": page_title,
                        "html": html
                    }

                # 2. If page contains >= 10 chapter links -> Catalog Page
                if len(chapter_links) >= 10:
                    return InputType.CATALOG_PAGE, {
                        "url": str(resp.url),
                        "page_title": page_title,
                        "chapter_count": len(chapter_links),
                        "html": html
                    }

                # 3. If page has chapter nav ("下一章", "上一章") -> Chapter Page
                if has_chap_nav:
                    return InputType.CHAPTER_PAGE, {
                        "url": str(resp.url),
                        "page_title": page_title,
                        "html": html
                    }

                # 4. If URL indicates chapter / reading and has content
                if any(k in str(resp.url) for k in ("/read/", "/zhangjie/", "/chapter/")) and content_container:
                    return InputType.CHAPTER_PAGE, {
                        "url": str(resp.url),
                        "page_title": page_title,
                        "html": html
                    }

                # Fallback: check chapter link count
                if len(chapter_links) >= 5:
                    return InputType.CATALOG_PAGE, {
                        "url": str(resp.url),
                        "page_title": page_title,
                        "chapter_count": len(chapter_links),
                        "html": html
                    }

                return InputType.BOOK_DETAIL_PAGE, {
                    "url": str(resp.url),
                    "page_title": page_title,
                    "html": html
                }

        except Exception as e:
            return InputType.UNKNOWN_URL, {"url": text, "error": str(e)}
