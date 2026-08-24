"""
Enhanced Incremental Gap-Filling and Chapter Repair Tool (NovelTracker GapFiller 2.0).
Extracts incomplete/failed chapters, cleans query titles, expands SERP candidate depth to Top-10
across multiple search engines (Baidu, Sogou, Bing, DuckDuckGo), and backfills missing chapters in-place.
"""

import asyncio
import os
import re
import sys
import urllib.parse
from typing import List, Dict, Optional, Tuple
import httpx
from bs4 import BeautifulSoup

# Ensure utf-8 stdout
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from core.heuristic_extractor import HeuristicExtractor
from core.pipeline import RegexCleaningPipeline
from core.fallback_router import DomainStrategy


class DeepFallbackRouter:
    """
    Enhanced multi-engine router with Top-10 SERP depth.
    """
    def __init__(self, timeout: float = 8.0, min_char_length: int = 300):
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

    def clean_query_title(self, raw_title: str) -> str:
        """Strips redundant chapter numbers and brackets for high search recall."""
        # Strip all chapter numbers (e.g. 第336章 第332章 -> empty prefix)
        t = re.sub(r'第\s*[0-9零一二两三四五六七八九十百千万]+\s*[章节回集卷篇节]', '', raw_title)
        # Strip brackets
        t = re.sub(r'[\(（\[【].*?[\)）\]】]', '', t)
        # Strip trailing noise
        t = re.sub(r'(?:求月票|求推荐票|求追读|感谢.*?盟主|还月票贷.*|打赏).*$', '', t)
        return t.strip()

    async def search_candidates_top10(self, novel_name: str, chapter_title: str) -> List[str]:
        """
        Multi-engine SERP retrieval returning up to Top-10 filtered candidates.
        """
        candidates: List[str] = []
        pure_title = self.clean_query_title(chapter_title)
        if not pure_title:
            pure_title = chapter_title

        query = f"{novel_name} {pure_title}"
        encoded_q = urllib.parse.quote(query)

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True, verify=False) as client:
            # Engine 1: Baidu Search
            try:
                baidu_url = f"https://www.baidu.com/s?wd={encoded_q}&rn=10"
                resp = await client.get(baidu_url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.select(".result h3 a, .c-container h3 a"):
                        href = a.get("href", "")
                        if href.startswith("http"):
                            candidates.append(href)
            except Exception:
                pass

            # Engine 2: Sogou Search
            try:
                sogou_url = f"https://www.sogou.com/web?query={encoded_q}"
                resp = await client.get(sogou_url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.select(".results a"):
                        href = a.get("href", "")
                        if href.startswith("/"):
                            href = f"https://www.sogou.com{href}"
                        if href.startswith("http") and "sogou.com/link" in href:
                            candidates.append(href)
            except Exception:
                pass

            # Engine 3: Bing Search
            try:
                bing_url = f"https://cn.bing.com/search?q={encoded_q}"
                resp = await client.get(bing_url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.content.decode("utf-8", errors="ignore"), "html.parser")
                    for a in soup.select("#b_results li.b_algo h2 a"):
                        href = a.get("href", "")
                        if href.startswith("http"):
                            candidates.append(href)
            except Exception:
                pass

        return DomainStrategy.filter_and_sort_candidates(candidates)[:10]

    async def recover_chapter(self, novel_name: str, chapter_title: str) -> Optional[Tuple[str, str]]:
        """
        Attempts to recover a single chapter by probing Top-10 candidates.
        """
        candidates = await self.search_candidates_top10(novel_name, chapter_title)
        if not candidates:
            return None

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True, verify=False) as client:
            for url in candidates:
                try:
                    resp = await client.get(url, timeout=self.timeout)
                    if resp.status_code != 200:
                        continue

                    enc = resp.encoding if resp.encoding and resp.encoding != 'iso-8859-1' else 'utf-8'
                    try:
                        html = resp.content.decode(enc, errors='replace')
                    except Exception:
                        html = resp.text

                    raw_text = self.extractor.extract_article_text(html, url=str(resp.url))
                    if not raw_text or len(raw_text) < 300:
                        continue

                    clean_text = self.pipeline.clean_text(raw_text, chapter_title=chapter_title, source_url=str(resp.url))
                    if len(clean_text) >= 300:
                        return clean_text, str(resp.url)
                except Exception:
                    continue

        return None


class NovelGapFiller:
    def __init__(self, file_path: str, novel_name: str = "没钱修什么仙", concurrency: int = 8):
        self.file_path = file_path
        self.novel_name = novel_name
        self.concurrency = concurrency
        self.router = DeepFallbackRouter()

    def identify_failed_chapters(self) -> Tuple[str, List[Dict]]:
        """
        Scans file and extracts failed / incomplete chapter blocks.
        """
        with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        raw_parts = re.split(r'\n{2,}(?=第\s*[0-9零一二两三四五六七八九十百千万]+\s*[章节回集卷篇节])', content)
        header = raw_parts[0] if raw_parts else ""
        chapter_blocks = raw_parts[1:] if len(raw_parts) > 1 else raw_parts

        failed_items = []
        for idx, block in enumerate(chapter_blocks):
            lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
            title = lines[0] if lines else f"第{idx+1}章"
            body = "\n".join(lines[1:]) if len(lines) > 1 else ""

            is_failed = False
            if any(k in block for k in ("(该章节获取失败)", "(主站 VIP 锁定", "全网源站暂未获取到", "抓取异常")):
                is_failed = True
            elif len(body) < 300 and not any(k in title for k in ("上架", "请假", "预告", "活动", "感言", "信", "说明")):
                is_failed = True

            if is_failed:
                failed_items.append({
                    "block_index": idx,
                    "title": title,
                    "raw_block": block,
                    "current_len": len(body)
                })

        return content, failed_items

    async def run_repair(self):
        """
        Executes the concurrent repair and in-place document backfilling.
        """
        print("=" * 65)
        print(f"🔧 【NovelTracker 增量修复引擎 2.0】启动")
        print(f"📁 目标文档: {self.file_path}")
        print("=" * 65)

        full_content, failed_chapters = self.identify_failed_chapters()
        total_failed = len(failed_chapters)
        print(f"\n🔍 [Scan] 扫描完毕，锁定 {total_failed} 个待回填章节。")

        if total_failed == 0:
            print("🎉 所有章节均已完整，无需执行增量修复。")
            return

        semaphore = asyncio.Semaphore(self.concurrency)
        recovered_count = 0
        repaired_map = {}

        async def worker(item):
            nonlocal recovered_count
            async with semaphore:
                res = await self.router.recover_chapter(self.novel_name, item["title"])
                if res:
                    recovered_count += 1
                    clean_text, source_url = res
                    repaired_block = f"\n\n{item['title']}\n\n{clean_text}\n"
                    repaired_map[item["block_index"]] = repaired_block
                    print(f"  ✅ [回填成功] {item['title'][:25]}... (字数: {len(clean_text)}, 来源: {source_url[:35]}...)")
                else:
                    print(f"  ❌ [回源耗尽] {item['title'][:25]}... (Top-10 候选源未发现解密正文)")

        tasks = [worker(item) for item in failed_chapters]
        await asyncio.gather(*tasks)

        print("\n" + "=" * 65)
        print(f"📊 [Repair Summary] 修复统计：")
        print(f"  - 待修复总数: {total_failed}")
        print(f"  - 成功回填数: {recovered_count}")
        print(f"  - 仍受限章节: {total_failed - recovered_count}")
        print("=" * 65)

        if recovered_count > 0:
            print("\n💾 正在就地回填并更新桌面文档...")
            raw_parts = re.split(r'\n{2,}(?=第\s*[0-9零一二两三四五六七八九十百千万]+\s*[章节回集卷篇节])', full_content)
            header = raw_parts[0] if raw_parts else ""
            chapter_blocks = raw_parts[1:] if len(raw_parts) > 1 else raw_parts

            for idx, block in enumerate(chapter_blocks):
                if idx in repaired_map:
                    chapter_blocks[idx] = repaired_map[idx].strip()

            new_header = re.sub(r'\(失败 \d+ 章\)', f'(已增量修复 {recovered_count} 章)', header)
            reconstructed_content = new_header.strip() + "\n\n" + "\n\n".join(chapter_blocks)

            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(reconstructed_content)

            print(f"🎉 桌面文档已成功就地更新！路径: {self.file_path}\n")


if __name__ == "__main__":
    file_target = r"C:\Users\Lenovo\Desktop\《没钱修什么仙》.txt"
    if len(sys.argv) > 1:
        file_target = sys.argv[1]
    
    filler = NovelGapFiller(file_path=file_target, novel_name="没钱修什么仙", concurrency=6)
    asyncio.run(filler.run_repair())
