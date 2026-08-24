"""
Universal Novel Extractor Engine (Facade).
Integrates URLClassifier, HeuristicCatalogExtractor, ChainedChapterCrawler, HeuristicExtractor,
FallbackRouter, and Multi-Format Formatters into a unified extraction pipeline.
"""

import asyncio
import os
import time
from typing import List, Optional, Tuple, Dict
import httpx

from core.url_classifier import URLClassifier, InputType
from core.heuristic_catalog import HeuristicCatalogExtractor
from core.chain_crawler import ChainedChapterCrawler
from core.heuristic_extractor import HeuristicExtractor
from core.pipeline import RegexCleaningPipeline
from core.fallback_router import FallbackRouter
from core.exceptions import DataIncompleteError, SourceExhaustedError
from core.formatters import TxtFormatter, JsonFormatter, EpubFormatter
from sources import SourceManager


class UniversalNovelExtractor:
    def __init__(
        self,
        output_dir: str = "downloads",
        concurrency: int = 12,
        timeout: float = 10.0,
        min_char_length: int = 400
    ):
        self.output_dir = output_dir
        self.concurrency = concurrency
        self.timeout = timeout
        self.classifier = URLClassifier(timeout=timeout)
        self.catalog_extractor = HeuristicCatalogExtractor(timeout=timeout)
        self.chain_crawler = ChainedChapterCrawler(timeout=timeout, min_char_length=min_char_length)
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

    async def _fetch_single_chapter(
        self,
        client: httpx.AsyncClient,
        novel_name: str,
        chap_tuple: Tuple[int, str, str, float],
        semaphore: asyncio.Semaphore
    ) -> Tuple[int, str, str, str]:
        """Fetch single chapter with heuristic extraction and fallback routing."""
        idx, title, url, num = chap_tuple
        async with semaphore:
            clean_body = None
            source_info = "主源"

            try:
                resp = await client.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    enc = resp.encoding if resp.encoding and resp.encoding != 'iso-8859-1' else 'utf-8'
                    try:
                        html = resp.content.decode(enc, errors='replace')
                    except Exception:
                        html = resp.text

                    raw_text = self.extractor.extract_article_text(html, url=url)
                    clean_body = self.pipeline.clean_text(raw_text, chapter_title=title, source_url=url)
            except Exception:
                clean_body = None

            if not clean_body:
                try:
                    fallback_text, fallback_url = await self.router.fallback_route(
                        novel_name=novel_name,
                        chapter_title=title
                    )
                    clean_body = fallback_text
                    source_info = f"降级回源 ({fallback_url[:25]}...)"
                except Exception:
                    clean_body = f"    (该章节提取受限或暂未开放免费正文)\n"
                    source_info = "回源受限"

            formatted_block = f"\n\n{title}\n\n{clean_body}\n"
            return idx, title, formatted_block, source_info

    async def extract(
        self,
        input_target: str,
        formats: Optional[List[str]] = None,
        start_chapter: int = 1,
        limit_chapters: Optional[int] = None,
        custom_output_dir: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Main universal extraction entry point.
        """
        if formats is None:
            formats = ["txt"]
        if "all" in formats:
            formats = ["txt", "epub", "json"]

        target_out_dir = custom_output_dir or self.output_dir
        os.makedirs(target_out_dir, exist_ok=True)

        print("=" * 65)
        print("🌐 【UniversalNovelExtractor 通用小说提取器】启动")
        print(f"🎯 目标输入: {input_target}")
        print("=" * 65)

        start_time = time.time()
        input_type, meta_info = await self.classifier.classify(input_target)
        print(f"🔍 [Classifier] 识别输入类型: [{input_type.value.upper()}]")

        book_meta = {"title": "未知小说", "author": "未知"}
        chapters_data: List[Tuple[int, str, str]] = []
        source_url = input_target if input_type != InputType.BOOK_NAME else ""

        # Case 1: Pure Book Name -> Multi-source Search first
        if input_type == InputType.BOOK_NAME:
            book_name = meta_info.get("book_name", input_target)
            print(f"🔎 [Search] 正在全网检索《{book_name}》目录入口...")
            source_mgr = SourceManager()
            best, all_res = await source_mgr.search_novel(book_name)
            if best and best.book_url:
                print(f"✅ 锁定优选数据源: {best.source_name} -> {best.book_url}")
                book_meta, chap_list = await self.catalog_extractor.discover_catalog(best.book_url)
                if not book_meta.get("title") or book_meta["title"] == "未知小说":
                    book_meta["title"] = book_name
                source_url = best.book_url
            else:
                # Fallback to direct catalog search
                from core.downloader import NovelDownloader
                dl = NovelDownloader()
                found_url = await dl.find_catalog_url(book_name)
                if found_url:
                    book_meta, chap_list = await self.catalog_extractor.discover_catalog(found_url)
                    book_meta["title"] = book_name
                    source_url = found_url
                else:
                    print(f"❌ 未能检索到《{book_name}》的可用目录。")
                    return {}

        # Case 2: Catalog Page or Book Detail Page -> Heuristic Catalog Extraction
        elif input_type in (InputType.CATALOG_PAGE, InputType.BOOK_DETAIL_PAGE):
            print(f"📖 [Catalog] 正在启发式扫描全书目录与分页结构...")
            book_meta, chap_list = await self.catalog_extractor.discover_catalog(
                input_target,
                html_preset=meta_info.get("html")
            )

        # Case 3: Single Chapter Page -> Chained Crawler
        elif input_type == InputType.CHAPTER_PAGE:
            print(f"🔗 [Chain] 正在沿单章阅读页链式拓扑抓取...")
            book_meta, chapters_data = await self.chain_crawler.crawl_chain(
                input_target,
                max_chapters=limit_chapters or 2000,
                progress_callback=lambda idx, t: print(f"\r📥 链式抓取进度: [第 {idx} 章] ({t[:20]}...)", end="", flush=True)
            )
            chap_list = []

        else:
            print(f"⚠️ 无法识别或访问该输入目标: {input_target}")
            return {}

        # If we got chapter list from catalog, download concurrently
        if 'chap_list' in locals() and chap_list:
            if start_chapter > 1:
                chap_list = [c for c in chap_list if c[0] >= start_chapter]
            if limit_chapters:
                chap_list = chap_list[:limit_chapters]

            total = len(chap_list)
            print(f"📚 共探测到 {total} 个有效章节，准备并发抓取完整正文...")

            semaphore = asyncio.Semaphore(self.concurrency)
            async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True, verify=False) as client:
                tasks = [
                    self._fetch_single_chapter(client, book_meta.get("title", "小说"), c, semaphore)
                    for c in chap_list
                ]
                completed = 0
                results_raw = []
                for f in asyncio.as_completed(tasks):
                    res = await f
                    results_raw.append(res)
                    completed += 1
                    percent = (completed / total) * 100
                    print(f"\r📥 采集进度: [{completed}/{total}] {percent:.1f}% [{res[3]}] ({res[1][:18]}...)", end="", flush=True)

            results_raw.sort(key=lambda x: x[0])
            chapters_data = [(r[0], r[1], r[2]) for r in results_raw]

        if not chapters_data:
            print("\n❌ 未能成功提取到章节正文。")
            return {}

        print(f"\n\n💾 采集完毕 (共 {len(chapters_data)} 章)，正在导出指定格式...")
        book_title = book_meta.get("title", "未命名小说")
        exported_files = {}

        # Export TXT
        if "txt" in formats:
            txt_path = os.path.join(target_out_dir, f"《{book_title}》.txt")
            TxtFormatter.export(txt_path, book_meta, chapters_data, source_url)
            exported_files["txt"] = txt_path
            print(f"  📄 [TXT 导出成功] -> {txt_path}")

        # Export EPUB
        if "epub" in formats:
            epub_path = os.path.join(target_out_dir, f"《{book_title}》.epub")
            EpubFormatter.export(epub_path, book_meta, chapters_data, source_url)
            exported_files["epub"] = epub_path
            print(f"  📚 [EPUB 导出成功] -> {epub_path}")

        # Export JSON
        if "json" in formats:
            json_path = os.path.join(target_out_dir, f"《{book_title}》.json")
            JsonFormatter.export(json_path, book_meta, chapters_data, source_url)
            exported_files["json"] = json_path
            print(f"  📊 [JSON 导出成功] -> {json_path}")

        elapsed = time.time() - start_time
        print(f"\n🎉 全流程提取完成！耗时 {elapsed:.2f} 秒。\n")
        return exported_files
