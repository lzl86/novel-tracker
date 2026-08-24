"""
DuckDuckGo HTML Search Source.
"""

import re
import urllib.parse
from typing import List
import httpx
from bs4 import BeautifulSoup

from .base import BaseSource, NovelSearchResult
from core.parser import extract_chapter_number


class DuckDuckGoSearchSource(BaseSource):
    name = "DuckDuckGo聚合"
    domain = "duckduckgo.com"

    async def search(self, novel_name: str) -> List[NovelSearchResult]:
        results: List[NovelSearchResult] = []
        query = f"{novel_name} 最新章节"
        encoded_query = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=self.timeout,
                follow_redirects=True,
                verify=False
            ) as client:
                resp = await client.post(url, data={"q": query})
                if resp.status_code != 200:
                    resp = await client.get(f"https://html.duckduckgo.com/html/?q={encoded_query}")
                
                if resp.status_code != 200:
                    return results

                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select(".result__body")

                for item in items:
                    title_elem = item.select_one(".result__title")
                    snippet_elem = item.select_one(".result__snippet")
                    
                    title_text = title_elem.get_text(strip=True) if title_elem else ""
                    snippet_text = snippet_elem.get_text(" ", strip=True) if snippet_elem else ""
                    combined = f"{title_text} {snippet_text}"

                    a_tag = item.select_one(".result__url, .result__title a")
                    page_url = a_tag.get("href", "") if a_tag else ""
                    if "uddg=" in page_url:
                        # Extract unescaped url from DDG redirect
                        m = re.search(r'uddg=([^&]+)', page_url)
                        if m:
                            page_url = urllib.parse.unquote(m.group(1))

                    if novel_name not in combined:
                        continue

                    # Find chapters
                    matches = re.findall(
                        r'(第\s*[0-9零一二两三四五六七八九十百千万]+\s*[章节回集卷篇节][^\s,，。；\n\r<]{0,30})',
                        combined
                    )
                    # Count chapters like "全书1195章完结"
                    count_match = re.search(r'(?:全书|共)\s*([0-9]+)\s*章', combined)
                    if count_match:
                        matches.append(f"第{count_match.group(1)}章")

                    special_matches = re.findall(
                        r'(终章[^\s,，。；\n\r<]{0,20}|大结局[^\s,，。；\n\r<]{0,20}|完本感言[^\s,，。；\n\r<]{0,20})',
                        combined
                    )

                    all_matches = matches + special_matches
                    if not all_matches:
                        continue

                    best_ch_title = ""
                    best_ch_num = -1.0
                    for ch in all_matches:
                        ch_clean = ch.strip().replace(" ", "")
                        num, _ = extract_chapter_number(ch_clean)
                        if num > best_ch_num:
                            best_ch_num = num
                            best_ch_title = ch_clean

                    if best_ch_title:
                        author_match = re.search(r'作者[:：\s]*([^\s,，。；|_\-—]{1,10})', combined)
                        author = author_match.group(1).strip() if author_match else "未知"

                        results.append(NovelSearchResult.create(
                            book_name=novel_name,
                            author=author,
                            latest_chapter_title=best_ch_title,
                            latest_chapter_url=page_url,
                            book_url=page_url,
                            update_time="近期",
                            source_name="DuckDuckGo",
                            source_domain="duckduckgo.com"
                        ))
        except Exception:
            pass

        return results
