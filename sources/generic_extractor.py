"""
Generic novel directory page parser.
Takes a URL of a novel detail or directory page and attempts to extract the latest chapter.
"""

import re
from typing import Optional, Tuple
import httpx
from bs4 import BeautifulSoup
from core.parser import extract_chapter_number


async def extract_latest_from_page(url: str, timeout: float = 5.0) -> Optional[Tuple[str, str, float]]:
    """
    Given a novel detail/directory page URL, extracts the latest chapter title, url, and chapter number.
    Returns:
        (latest_chapter_title, chapter_url, chapter_num) or None
    """
    if not url or not url.startswith("http"):
        return None

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }

    try:
        async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True, verify=False) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "html.parser")

            # Strategy 1: Look for explicit '最新章节' or '最近更新' elements
            update_nodes = soup.find_all(lambda tag: tag.name in ('p', 'div', 'span', 'li') and any(k in tag.text for k in ('最新章节', '最近更新', '最新更新', '最新：')))
            for node in update_nodes:
                a_tag = node.find('a', href=True)
                if a_tag:
                    title = a_tag.get_text(strip=True)
                    num, _ = extract_chapter_number(title)
                    if num > 0:
                        href = a_tag['href']
                        if href.startswith('/'):
                            from urllib.parse import urljoin
                            href = urljoin(url, href)
                        return title, href, num

            # Strategy 2: Scan all <a> tags for chapter patterns
            all_a = soup.find_all('a', href=True)
            candidate_chapters = []
            for a in all_a:
                text = a.get_text(strip=True)
                if re.search(r'第\s*[0-9零一二两三四五六七八九十百千万]+\s*[章节回集卷篇节]', text):
                    num, _ = extract_chapter_number(text)
                    href = a['href']
                    if href.startswith('/'):
                        from urllib.parse import urljoin
                        href = urljoin(url, href)
                    candidate_chapters.append((text, href, num))

            if candidate_chapters:
                # Pick the highest chapter number
                candidate_chapters.sort(key=lambda x: x[2], reverse=True)
                return candidate_chapters[0]

    except Exception:
        pass

    return None
