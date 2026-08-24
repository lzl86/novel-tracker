"""Novel data sources module."""
from .base import BaseSource, NovelSearchResult
from .baidu_source import BaiduSearchSource
from .sogou_source import SogouSearchSource
from .duckduckgo_source import DuckDuckGoSearchSource
from .search_fallback import SearchEngineSource
from .manager import SourceManager

__all__ = [
    'BaseSource',
    'NovelSearchResult',
    'BaiduSearchSource',
    'SogouSearchSource',
    'DuckDuckGoSearchSource',
    'SearchEngineSource',
    'SourceManager',
]
