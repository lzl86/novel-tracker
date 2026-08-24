"""
Universal Novel Extractor and Pipeline Orchestrator.
Coordinates URL classification, heuristic catalog discovery, candidate discovery,
parallel chapter fetching, clean regex extraction, and EPUB/TXT/JSON formatting.
"""

import asyncio
import os
import re
import time
import urllib.parse
from typing import Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from core.url_classifier import URLClassifier, InputType
from core.heuristic_catalog import HeuristicCatalogExtractor
from core.chain_crawler import ChainedChapterCrawler
from core.heuristic_extractor import HeuristicExtractor
from core.pipeline import RegexCleaningPipeline
from core.fallback_router import FallbackRouter, DomainStrategy
from core.formatters import TxtFormatter, JsonFormatter, EpubFormatter
from core.source_cache import SourceCache


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
        self.source_cache = SourceCache()
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

    async def find_authentic_catalog_candidates(self, book_name: str) -> List[str]:
        """
        Searches across SourceManager (DuckDuckGo, Baidu, Sogou, Fallback engines),
        DirectSiteSearchHub (站内直连检索池), and multi-engine SERP.
        """
        candidates: List[str] = []

        # 1. First priority: Multi-source search manager (DuckDuckGo, SearchFallback, etc.)
        try:
            from sources.manager import SourceManager
            sm = SourceManager(timeout=self.timeout)
            _, all_res = await sm.search_novel(book_name)
            for r in all_res:
                if r.book_url and r.book_url not in candidates:
                    candidates.append(r.book_url)
                if r.latest_chapter_url and r.latest_chapter_url not in candidates:
                    candidates.append(r.latest_chapter_url)
        except Exception:
            pass

        # 2. Second priority: DirectSiteSearchHub (biquge, 51read, piaotian, 89wx)
        try:
            from core.direct_site_search import DirectSiteSearchHub
            hub = DirectSiteSearchHub(timeout=self.timeout)
            direct_results = await hub.search_all(book_name)
            for r in direct_results:
                if r.catalog_url and r.catalog_url not in candidates:
                    candidates.append(r.catalog_url)
        except Exception:
            pass

        # 3. Third priority: Multi-Engine Fallback SERP search
        search_queries = [
            f"{book_name} 目录",
            f"{book_name} 最新章节",
            f"{book_name} 笔趣阁",
            f"{book_name} 小说阅读"
        ]

        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=self.timeout,
            follow_redirects=True,
            verify=False
        ) as client:
            for q in search_queries:
                # DuckDuckGo HTML endpoint
                try:
                    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(q)}"
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        for a in soup.select(".results .result__url"):
                            href = a.get_text(strip=True)
                            if not href.startswith("http"):
                                href = f"https://{href}"
                            if href not in candidates and not any(k in href for k in ("baike.baidu.com", "zhihu.com", "tieba.baidu.com", "douban.com")):
                                candidates.append(href)
                except Exception:
                    pass

                # Bing search endpoint
                try:
                    bing_url = f"https://cn.bing.com/search?q={urllib.parse.quote(q)}&setlang=zh-Hans"
                    resp = await client.get(bing_url)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        for a in soup.select("#b_results .b_algo h2 a[href]"):
                            href = a["href"].strip()
                            if href.startswith("http") and href not in candidates and not any(k in href for k in ("baike.baidu.com", "zhihu.com", "tieba.baidu.com", "douban.com")):
                                candidates.append(href)
                except Exception:
                    pass

        return candidates

    async def fetch_single_chapter(
        self,
        chap_index: int,
        chap_title: str,
        chap_url: str,
        semaphore: asyncio.Semaphore,
        log_callback: Optional[callable] = None
    ) -> Tuple[int, str, str]:
        """
        Fetches and extracts clean text for a single chapter with fallback routing.
        """
        async with semaphore:
            # First attempt: direct fetch + heuristic extraction
            try:
                async with httpx.AsyncClient(
                    headers=self.headers,
                    timeout=self.timeout,
                    follow_redirects=True,
                    verify=False
                ) as client:
                    resp = await client.get(chap_url)
                    resp.encoding = resp.apparent_encoding or "utf-8"
                    if resp.status_code == 200:
                        clean_text = self.extractor.extract(resp.text, chap_url)
                        if self.pipeline.is_valid_chapter(clean_text):
                            if log_callback:
                                await log_callback(f"  ✓ [{chap_index}] 提取成功: {chap_title[:20]} ({len(clean_text)} 字)")
                            return (chap_index, chap_title, clean_text)
            except Exception:
                pass

            # Second attempt: Smart fallback router with mirror mutations
            res = await self.router.fetch_chapter_with_fallback(chap_title, chap_url)
            if res:
                _, content = res
                if log_callback:
                    await log_callback(f"  ✓ [{chap_index}] 备用镜像提取成功: {chap_title[:20]} ({len(content)} 字)")
                return (chap_index, chap_title, content)

            if log_callback:
                await log_callback(f"  ✗ [{chap_index}] 提取失败/内容过短: {chap_title[:20]}")
            return (chap_index, chap_title, f"【本章《{chap_title}》抓取异常或源站防爬拦截，暂缺】\n")

    async def extract(
        self,
        input_target: str,
        formats: Optional[List[str]] = None,
        start_chapter: int = 1,
        limit_chapters: Optional[int] = None,
        custom_output_dir: Optional[str] = None,
        log_callback: Optional[callable] = None
    ) -> Dict[str, str]:
        """
        Main entry point for universal novel extraction.
        """
        if formats is None:
            formats = ["epub", "txt"]

        out_dir = custom_output_dir or self.output_dir
        os.makedirs(out_dir, exist_ok=True)

        async def _log(msg: str):
            print(msg)
            if log_callback:
                try:
                    if asyncio.iscoroutinefunction(log_callback):
                        await log_callback(msg)
                    else:
                        log_callback(msg)
                except Exception:
                    pass

        await _log("=" * 65)
        await _log("🌐 【UniversalNovelExtractor 通用小说提取器】启动")
        await _log(f"🎯 目标输入: {input_target}")
        await _log("=" * 65)

        start_time = time.time()
        input_type, meta_info = await self.classifier.classify(input_target)
        await _log(f"🔍 [Classifier] 识别输入类型: [{input_type.value.upper()}]")

        book_meta = {"title": "未知小说", "author": "未知"}
        chapters_data: List[Tuple[int, str, str]] = []
        source_url = input_target if input_type != InputType.BOOK_NAME else ""
        chap_list = []

        # Case 1: Pure Book Name -> Multi-engine Candidate Catalog Probing
        if input_type == InputType.BOOK_NAME:
            book_name = meta_info.get("book_name", input_target)
            
            # Step 1: Check SourceCache (Persistent Memory)
            cached = self.source_cache.get(book_name)
            if cached and cached.get("catalog_url"):
                cached_url = cached["catalog_url"]
                cached_total = cached.get("total_chapters", 0)
                await _log(f"⚡ [Cache 命中] 正在直连已知优质书源: {cached_url} (记忆库: {cached_total} 章)...")
                try:
                    meta_cand, chaps_cand = await self.catalog_extractor.discover_catalog(cached_url)
                    if chaps_cand and len(chaps_cand) >= max(5, int(cached_total * 0.7)):
                        await _log(f"  ✅ [书源探活成功] 直连锁定最新 {len(chaps_cand)} 章目录 (跳过盲搜耗时)")
                        book_meta = meta_cand
                        if not book_meta.get("title") or book_meta["title"] == "未知小说":
                            book_meta["title"] = book_name
                        chap_list = chaps_cand
                        source_url = cached_url
                        # Update cache with freshest stats
                        self.source_cache.set(
                            book_name=book_name,
                            catalog_url=cached_url,
                            total_chapters=len(chap_list),
                            last_chapter_title=chap_list[-1][1] if chap_list else "",
                            author=book_meta.get("author", "未知"),
                            source_name=cached.get("source_name", "全网聚合")
                        )
                except Exception as e:
                    await _log(f"  ⚠️ [Cache 失效] 已知书源访问异常 ({e})，自动触发全网重新检索与自愈...")

            # Step 2: If no cache or cache failed, probe all candidate engines
            if not chap_list:
                await _log(f"🔎 [Search] 正在全网检索《{book_name}》的可用目录...")
                candidates = await self.find_authentic_catalog_candidates(book_name)
                await _log(f"📋 发现 {len(candidates)} 个潜在书源候选，正在逐一进行真目录校验...")

                best_meta = None
                best_chaps = []
                best_url = ""

                for idx, cand_url in enumerate(candidates[:10], 1):
                    try:
                        meta_cand, chaps_cand = await self.catalog_extractor.discover_catalog(cand_url)
                        if chaps_cand and len(chaps_cand) >= 5:
                            await _log(f"  ✅ [有效目录发现] 候选 #{idx} ({cand_url[:35]}...) 识别到 {len(chaps_cand)} 章")
                            if len(chaps_cand) > len(best_chaps):
                                best_meta = meta_cand
                                best_chaps = chaps_cand
                                best_url = cand_url
                    except Exception:
                        continue

                if best_chaps:
                    book_meta = best_meta
                    if not book_meta.get("title") or book_meta["title"] == "未知小说":
                        book_meta["title"] = book_name
                    chap_list = best_chaps
                    source_url = best_url
                    await _log(f"🏆 [锁定最优目录源] 选用包含 {len(chap_list)} 章的高质量源 ({source_url})")
                    # Save to cache
                    self.source_cache.set(
                        book_name=book_name,
                        catalog_url=source_url,
                        total_chapters=len(chap_list),
                        last_chapter_title=chap_list[-1][1] if chap_list else "",
                        author=book_meta.get("author", "未知")
                    )
                    await _log(f"💾 [Cache 存储] 已将《{book_name}》最优书源持久化至本地记忆库")
                else:
                    await _log(f"\n❌ 未能在开放网络中匹配到《{book_name}》的有效全本目录。")
                    await _log("💡 建议：请检查书名拼写是否正确，或直接复制该小说在任意网站的目录页/详情页 URL 传入提取！")
                    return {}

        # Case 2: Catalog Page or Book Detail Page -> Heuristic Catalog Extraction
        elif input_type in (InputType.CATALOG_PAGE, InputType.BOOK_DETAIL_PAGE):
            await _log(f"📖 [Catalog] 正在启发式扫描全书目录与分页结构...")
            book_meta, chap_list = await self.catalog_extractor.discover_catalog(
                input_target,
                html_preset=meta_info.get("html")
            )
            if not chap_list:
                await _log(f"\n❌ 该页面未能识别为有效的小说章节目录，可能是搜索聚合页或非小说网页。")
                return {}
            # Persist URL to cache
            extracted_title = book_meta.get("title", "")
            if extracted_title and extracted_title != "未知小说":
                self.source_cache.set(
                    book_name=extracted_title,
                    catalog_url=input_target,
                    total_chapters=len(chap_list),
                    last_chapter_title=chap_list[-1][1] if chap_list else "",
                    author=book_meta.get("author", "未知")
                )

        # Case 3: Single Chapter Page -> Chained Crawler
        elif input_type == InputType.CHAPTER_PAGE:
            await _log(f"🔗 [Chain] 正在沿单章阅读页链式拓扑追溯...")
            book_meta, chapters_data = await self.chain_crawler.crawl_chain(
                input_target,
                start_chapter=start_chapter,
                max_chapters=limit_chapters,
                log_callback=log_callback
            )

        # Fetch chapters concurrently if discovered via Case 1 or Case 2
        if chap_list:
            # Filter chapters by start_chapter and limit_chapters
            target_chaps = [c for c in chap_list if c[0] >= start_chapter]
            if limit_chapters:
                target_chaps = target_chaps[:limit_chapters]

            await _log(f"📚 共锁定 {len(target_chaps)} 个正文章节，准备并发采集完整正文...")

            semaphore = asyncio.Semaphore(self.concurrency)
            tasks = [
                self.fetch_single_chapter(idx, title, url, semaphore, log_callback=None)
                for idx, title, url, _ in target_chaps
            ]

            completed = 0
            total = len(tasks)
            for coro in asyncio.as_completed(tasks):
                res = await coro
                chapters_data.append(res)
                completed += 1
                if completed % 10 == 0 or completed == total:
                    pct = completed / total * 100
                    await _log(f"📥 采集进度: [{completed}/{total}] {pct:.1f}% [主源] ({res[1][:15]}...)")

            chapters_data.sort(key=lambda x: x[0])

        if not chapters_data:
            await _log("\n❌ 未能提取到任何有效章节正文。")
            return {}

        await _log(f"\n💾 采集完毕 (共 {len(chapters_data)} 章)，正在导出指定格式...")
        results = {}

        book_title = book_meta.get("title", "未命名小说")
        author = book_meta.get("author", "未知")

        if "txt" in formats:
            txt_path = os.path.join(out_dir, f"《{book_title}》.txt")
            TxtFormatter.export(book_title, author, chapters_data, txt_path)
            results["txt"] = txt_path
            await _log(f"  📄 [TXT 导出成功] -> {txt_path}")

        if "json" in formats:
            json_path = os.path.join(out_dir, f"《{book_title}》.json")
            JsonFormatter.export(book_title, author, source_url, chapters_data, json_path)
            results["json"] = json_path
            await _log(f"  📦 [JSON 导出成功] -> {json_path}")

        if "epub" in formats:
            epub_path = os.path.join(out_dir, f"《{book_title}》.epub")
            EpubFormatter.export(book_title, author, chapters_data, epub_path)
            results["epub"] = epub_path
            await _log(f"  📚 [EPUB 导出成功] -> {epub_path}")

        elapsed = time.time() - start_time
        await _log(f"\n🎉 全流程提取完成！耗时 {elapsed:.2f} 秒。\n")
        return results
