"""
Novel Downloader with Multi-Source Fallback Routing and Heuristic Content Extraction.
Orchestrates MasterProbe, FallbackRouter, HeuristicExtractor, and RegexCleaningPipeline.
"""

import asyncio
import os
from typing import List, Optional, Tuple
from urllib.parse import quote
import httpx
from bs4 import BeautifulSoup

from core.exceptions import DataIncompleteError, SourceExhaustedError
from core.heuristic_extractor import HeuristicExtractor
from core.pipeline import RegexCleaningPipeline
from core.fallback_router import FallbackRouter
from core.probe import MasterProbe, ChapterMetadata


class NovelDownloader:
    def __init__(
        self,
        output_dir: str = "downloads",
        concurrency: int = 12,
        timeout: float = 10.0,
        min_char_length: int = 500
    ):
        self.output_dir = output_dir
        self.concurrency = concurrency
        self.timeout = timeout
        self.probe = MasterProbe(timeout=timeout)
        self.extractor = HeuristicExtractor()
        self.pipeline = RegexCleaningPipeline(min_char_length=min_char_length)
        self.router = FallbackRouter(timeout=timeout, min_char_length=min_char_length)
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        os.makedirs(self.output_dir, exist_ok=True)

    async def fetch_single_chapter(
        self,
        client: httpx.AsyncClient,
        novel_name: str,
        chapter: ChapterMetadata,
        semaphore: asyncio.Semaphore
    ) -> Tuple[int, str, str, str]:
        """
        Fetches single chapter content. If primary source is incomplete or errors,
        triggers FallbackRouter to query alternate sources.
        Returns:
            (chapter_index, chapter_title, clean_content, source_status)
        """
        async with semaphore:
            clean_body: Optional[str] = None
            source_info = "主节点"

            # 1. Attempt primary node extraction
            try:
                resp = await client.get(chapter.url, timeout=self.timeout)
                if resp.status_code == 200:
                    enc = resp.encoding if resp.encoding and resp.encoding != 'iso-8859-1' else 'utf-8'
                    try:
                        html = resp.content.decode(enc, errors='replace')
                    except Exception:
                        html = resp.text

                    # Heuristic extraction
                    raw_text = self.extractor.extract_article_text(html, url=chapter.url)
                    # Pipeline cleaning & validation (raises DataIncompleteError if length < min_char_length)
                    clean_body = self.pipeline.clean_text(
                        raw_text=raw_text,
                        chapter_title=chapter.title,
                        source_url=chapter.url
                    )
            except (DataIncompleteError, Exception):
                clean_body = None

            # 2. Fallback routing if primary extraction failed or was incomplete
            if not clean_body:
                try:
                    fallback_text, fallback_url = await self.router.fallback_route(
                        novel_name=novel_name,
                        chapter_title=chapter.title
                    )
                    clean_body = fallback_text
                    source_info = f"降级回源 ({fallback_url[:30]}...)"
                except SourceExhaustedError:
                    clean_body = f"    (全网源站暂未获取到本章完整正文)\n"
                    source_info = "回源耗尽"
                except Exception:
                    clean_body = f"    (抓取异常)\n"
                    source_info = "异常"

            formatted_content = f"\n\n{chapter.title}\n\n{clean_body}\n"
            return chapter.index, chapter.title, formatted_content, source_info

    async def download_novel(
        self,
        novel_name: str,
        catalog_url: str,
        start_chapter: int = 1,
        limit_chapters: Optional[int] = None
    ) -> Optional[str]:
        """
        Downloads novel chapters using MasterProbe + FallbackRouter architecture.
        """
        print(f"📡 [MasterProbe] 正在探测目录元数据: {catalog_url} ...")
        chapters = await self.probe.probe_catalog(catalog_url)

        if not chapters:
            print(f"⚠️ [MasterProbe] 未能从 {catalog_url} 获取到章节元数据。")
            return None

        chapters_to_download = [ch for ch in chapters if ch.index >= start_chapter]
        if limit_chapters:
            chapters_to_download = chapters_to_download[:limit_chapters]

        total = len(chapters_to_download)
        print(f"📚 [Scheduler] 已就绪 {len(chapters)} 章元数据，准备调度下载 {total} 章完整正文...")

        output_filename = f"《{novel_name}》.txt"
        output_file_path = os.path.join(self.output_dir, output_filename)

        semaphore = asyncio.Semaphore(self.concurrency)
        results = []
        fallback_count = 0

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True, verify=False) as client:
            tasks = [
                self.fetch_single_chapter(client, novel_name, ch, semaphore)
                for ch in chapters_to_download
            ]

            completed = 0
            for f in asyncio.as_completed(tasks):
                res = await f
                results.append(res)
                completed += 1
                if "降级" in res[3]:
                    fallback_count += 1
                percent = (completed / total) * 100
                print(f"\r📥 采集进度: [{completed}/{total}] {percent:.1f}% [{res[3]}] ({res[1][:18]}...)", end="", flush=True)

        print(f"\n\n💾 采集完毕 (共触发 {fallback_count} 次多源降级回源)，正在规范化合并至落盘文件...")
        results.sort(key=lambda x: x[0])

        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(f"《{novel_name}》\n\n")
            f.write(f"【多源保障完整正文版】共 {len(results)} 章\n")
            f.write(f"主索引源: {catalog_url}\n")
            f.write("=" * 60 + "\n\n")
            for _, _, content, _ in results:
                f.write(content + "\n")

        print(f"🎉 规范化文本已成功落盘至: {output_file_path}")
        return output_file_path
