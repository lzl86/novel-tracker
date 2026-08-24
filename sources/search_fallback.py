"""
Search Engine Fallback Source (Bing).
Retrieves novel latest chapters using search engine snippets and result pages.
"""

import re
import urllib.parse
from typing import List
import httpx
from bs4 import BeautifulSoup

from .base import BaseSource, NovelSearchResult
from core.parser import extract_chapter_number


class SearchEngineSource(BaseSource):
    name = "搜索引擎聚合(Bing)"
    domain = "cn.bing.com"

    async def search(self, novel_name: str) -> List[NovelSearchResult]:
        results: List[NovelSearchResult] = []
        query = f"{novel_name} 最新章节"
        encoded_query = urllib.parse.quote(query)
        url = f"https://cn.bing.com/search?q={encoded_query}&setlang=zh-Hans"

        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=self.timeout,
                follow_redirects=True,
                verify=False
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return results

                soup = BeautifulSoup(resp.content, "html.parser")
                algo_items = soup.select("#b_results > li.b_algo")

                for item in algo_items:
                    h2_a = item.select_one("h2 a")
                    if not h2_a:
                        continue

                    title_text = h2_a.get_text(strip=True)
                    page_url = h2_a.get("href", "")

                    # Extract snippet text
                    caption_p = item.select_one(".b_caption p, .b_snippet")
                    snippet_text = caption_p.get_text(" ", strip=True) if caption_p else ""
                    combined_text = f"{title_text} {snippet_text}"

                    # Only process if it mentions the novel name
                    if novel_name not in combined_text:
                        continue

                    # Look for chapter patterns in title and snippet
                    # e.g., 最新章节：第1234章 xxx 或 第1234章
                    chapter_match = re.search(
                        r'(?:最新(?:章节|更新)?[:：\s]*)(第[0-9零一二两三四五六七八九十百千万]+[章节回集卷篇节][^\s,，。；\n\r<]{0,35})',
                        combined_text
                    )

                    if not chapter_match:
                        # Try broader pattern
                        chapter_match = re.search(
                            r'(第[0-9零一二两三四五六七八九十百千万]+[章节回集卷篇节][^\s,，。；\n\r<]{0,35})',
                            combined_text
                        )

                    if chapter_match:
                        latest_chapter = chapter_match.group(1).strip()
                        # Clean up punctuation
                        latest_chapter = re.sub(r'[_|\-—].*$', '', latest_chapter).strip()

                        # Extract possible author
                        author_match = re.search(r'作者[:：\s]*([^\s,，。；|_\-—]{1,10})', combined_text)
                        author = author_match.group(1).strip() if author_match else "未知"

                        # Extract possible time
                        time_match = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}|\d+\s*(?:小时|分钟|天)前)', combined_text)
                        update_time = time_match.group(1).strip() if time_match else "近期"

                        parsed_result = NovelSearchResult.create(
                            book_name=novel_name,
                            author=author,
                            latest_chapter_title=latest_chapter,
                            latest_chapter_url=page_url,
                            book_url=page_url,
                            update_time=update_time,
                            source_name="Bing 检索",
                            source_domain="bing.com"
                        )
                        results.append(parsed_result)

        except Exception as e:
            # Silently catch network or parsing exceptions to avoid breaking the aggregator
            pass

        return results
