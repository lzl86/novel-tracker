"""
Source manager that coordinates multi-source concurrent novel searches.
"""

import asyncio
from typing import List, Tuple, Optional
from .base import BaseSource, NovelSearchResult
from .baidu_source import BaiduSearchSource
from .sogou_source import SogouSearchSource
from .duckduckgo_source import DuckDuckGoSearchSource
from .search_fallback import SearchEngineSource


class SourceManager:
    def __init__(self, sources: Optional[List[BaseSource]] = None, timeout: float = 6.0):
        self.timeout = timeout
        if sources is not None:
            self.sources = sources
        else:
            self.sources = [
                BaiduSearchSource(timeout=timeout),
                SogouSearchSource(timeout=timeout),
                DuckDuckGoSearchSource(timeout=timeout),
                SearchEngineSource(timeout=timeout),
            ]

    def register_source(self, source: BaseSource) -> None:
        """Add a new source to the manager."""
        self.sources.append(source)

    async def search_novel(self, novel_name: str) -> Tuple[Optional[NovelSearchResult], List[NovelSearchResult]]:
        """
        Search for novel across all registered sources concurrently.
        Returns:
            (best_result: Optional[NovelSearchResult], all_results: List[NovelSearchResult])
        """
        name = novel_name.strip()
        if not name:
            return None, []

        tasks = [source.search(name) for source in self.sources]
        results_nested = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: List[NovelSearchResult] = []
        for res in results_nested:
            if isinstance(res, list):
                all_results.extend(res)

        if not all_results:
            return None, []

        # Deduplicate results by (source_name, latest_chapter_title)
        seen = set()
        deduped_results: List[NovelSearchResult] = []
        for item in all_results:
            key = (item.source_name, item.latest_chapter_title)
            if key not in seen and item.latest_chapter_title:
                seen.add(key)
                deduped_results.append(item)

        # Sort by chapter number descending (highest chapter first)
        deduped_results.sort(key=lambda x: x.latest_chapter_num, reverse=True)

        best_result = deduped_results[0] if deduped_results else None
        return best_result, deduped_results
