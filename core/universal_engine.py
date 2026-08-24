"""
Universal Novel Extractor Engine (Facade).
Integrates URLClassifier, HeuristicCatalogExtractor, ChainedChapterCrawler, HeuristicExtractor,
FallbackRouter, and Multi-Format Formatters into a unified extraction pipeline.
"""

import asyncio
import os
import time
import urllib.parse
from typing import List, Optional, Tuple, Dict
import httpx
from bs4 import BeautifulSoup

from core.url_classifier import URLClassifier, InputType
from core.heuristic_catalog import HeuristicCatalogExtractor
from core.chain_crawler import ChainedChapterCrawler
from core.heuristic_extractor import HeuristicExtractor
from core.pipeline import RegexCleaningPipeline
from core.fallback_router import FallbackRouter, DomainStrategy
from core.formatters import TxtFormatter, JsonFormatter, EpubFormatter


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

    async def find_authentic_catalog_candidates(self, book_name: str) -> List[str]:
        """
        Searches across DirectSiteSearchHub (站内直连检索池) and multi-engine SERP.
        """
        candidates: List[str] = []

        # 1. First priority: Direct novel site search endpoints (Bypasses SEO noindex & search blocks)
        try:
            from core.direct_site_search import DirectSiteSearchHub
            hub = DirectSiteSearchHub()
            direct_hits = await hub.search_all_direct_sites(book_name)
            candidates.extend(direct_hits)
        except Exception:
            pass

        queries = [
            f"{book_name} 章节目录",
            f"{book_name} 小说 目录",
            f"\"{book_name}\" 最新章节列表",
            f"{book_name} 51read",
            f"{book_name} 笔趣阁 目录"
        ]

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True, verify=False) as client:
            for q in queries:
                encoded_q = urllib.parse.quote(q)
                # Engine 1: Baidu
                try:
                    r = await client.get(f"https://www.baidu.com/s?wd={encoded_q}&rn=10")
                    if r.status_code == 200:
                        soup = BeautifulSoup(r.text, "html.parser")
                        for a in soup.select(".result h3 a, .c-container h3 a"):
                            href = a.get("href")
                            if href and href.startswith("http"):
                                candidates.append(href)
                except Exception:
                    pass

                # Engine 2: Sogou
                try:
                    r = await client.get(f"https://www.sogou.com/web?query={encoded_q}")
                    if r.status_code == 200:
                        soup = BeautifulSoup(r.text, "html.parser")
                        for a in soup.select(".results a"):
                            href = a.get("href")
                            if href and href.startswith("/"):
                                href = f"https://www.sogou.com{href}"
                            if href and "sogou.com/link" in href:
                                candidates.append(href)
                except Exception:
                    pass

                # Engine 3: Bing
                try:
                    r = await client.get(f"https://cn.bing.com/search?q={encoded_q}")
                    if r.status_code == 200:
                        soup = BeautifulSoup(r.content.decode("utf-8", errors="ignore"), "html.parser")
                        for a in soup.select("#b_results li.b_algo h2 a"):
                            href = a.get("href")
                            if href and href.startswith("http"):
                                candidates.append(href)
                except Exception:
                    pass

                if len(candidates) >= 15:
                    break

        return DomainStrategy.filter_and_sort_candidates(candidates)

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
                elif resp.status_code == 403:
                    # Cloudflare 403 fallback
                    from core.browser_fetcher import BrowserFetcher
                    bf = BrowserFetcher()
                    rendered = await bf.fetch_html(url)
                    if rendered:
                        raw_text = self.extractor.extract_article_text(rendered, url=url)
                        clean_body = self.pipeline.clean_text(raw_text, chapter_title=title, source_url=url)
                        source_info = "浏览器抗盾"
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
        chap_list = []

        # Case 1: Pure Book Name -> Multi-engine Candidate Catalog Probing
        if input_type == InputType.BOOK_NAME:
            book_name = meta_info.get("book_name", input_target)
            print(f"🔎 [Search] 正在全网检索《{book_name}》的可用目录...")
            candidates = await self.find_authentic_catalog_candidates(book_name)
            print(f"📋 发现 {len(candidates)} 个潜在书源候选，正在逐一进行真目录校验...")

            matched_catalog = False
            for idx, cand_url in enumerate(candidates[:10], 1):
                try:
                    meta_cand, chaps_cand = await self.catalog_extractor.discover_catalog(cand_url)
                    if chaps_cand and len(chaps_cand) >= 5:
                        print(f"  ✅ [有效目录锁定] 候选 #{idx} ({cand_url[:35]}...) 成功识别 {len(chaps_cand)} 章")
                        book_meta = meta_cand
                        if not book_meta.get("title") or book_meta["title"] == "未知小说":
                            book_meta["title"] = book_name
                        chap_list = chaps_cand
                        source_url = cand_url
                        matched_catalog = True
                        break
                except Exception:
                    continue

            if not matched_catalog:
                print(f"\n❌ 未能在开放网络中匹配到《{book_name}》的有效全本目录。")
                print("💡 建议：请检查书名拼写是否正确，或直接复制该小说在任意网站的目录页/详情页 URL 传入提取！")
                return {}

        # Case 2: Catalog Page or Book Detail Page -> Heuristic Catalog Extraction
        elif input_type in (InputType.CATALOG_PAGE, InputType.BOOK_DETAIL_PAGE):
            print(f"📖 [Catalog] 正在启发式扫描全书目录与分页结构...")
            book_meta, chap_list = await self.catalog_extractor.discover_catalog(
                input_target,
                html_preset=meta_info.get("html")
            )
            if not chap_list:
                print(f"\n❌ 该页面未能识别为有效的小说章节目录，可能是搜索聚合页或非小说网页。")
                return {}

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
        if chap_list:
            if start_chapter > 1:
                chap_list = [c for c in chap_list if c[0] >= start_chapter]
            if limit_chapters:
                chap_list = chap_list[:limit_chapters]

            total = len(chap_list)
            print(f"📚 共锁定 {total} 个正文章节，准备并发采集完整正文...")

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
