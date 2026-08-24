"""
Base classes and data models for novel sources.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from core.parser import extract_chapter_number


@dataclass
class NovelSearchResult:
    book_name: str
    author: str
    latest_chapter_title: str
    latest_chapter_num: float
    latest_chapter_url: str
    book_url: str
    update_time: str
    source_name: str
    source_domain: str

    @classmethod
    def create(
        cls,
        book_name: str,
        author: str,
        latest_chapter_title: str,
        latest_chapter_url: str,
        book_url: str,
        update_time: str,
        source_name: str,
        source_domain: str
    ) -> 'NovelSearchResult':
        num, _ = extract_chapter_number(latest_chapter_title)
        return cls(
            book_name=book_name.strip(),
            author=author.strip() if author else "未知",
            latest_chapter_title=latest_chapter_title.strip(),
            latest_chapter_num=num,
            latest_chapter_url=latest_chapter_url.strip(),
            book_url=book_url.strip(),
            update_time=update_time.strip() if update_time else "未知",
            source_name=source_name,
            source_domain=source_domain
        )


class BaseSource(ABC):
    name: str = "BaseSource"
    domain: str = ""

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }

    @abstractmethod
    async def search(self, novel_name: str) -> List[NovelSearchResult]:
        """
        Search for novel by name and return a list of NovelSearchResult.
        """
        pass
