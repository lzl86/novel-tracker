"""
Regex Cleaning Pipeline for novel text standardization.
Processes raw scraped chapter text through multi-stage filters to produce clean, well-formatted paragraphs.
"""

import re
from typing import List, Optional, Tuple
from core.exceptions import DataIncompleteError


# Common novel site noise & ad patterns
NOISE_PATTERNS = [
    re.compile(r'请记住本书首发域名[：:\s]*[a-zA-Z0-9\.\/]+', re.IGNORECASE),
    re.compile(r'最新章节更新[：:\s]*[a-zA-Z0-9\.\/]+', re.IGNORECASE),
    re.compile(r'天才一秒记住.*?[网站|域名]', re.IGNORECASE),
    re.compile(r'(?:手机版|移动端|手机用户请)?(?:访问|阅读|浏览)[：:\s]*[a-zA-Z0-9\.\/]+', re.IGNORECASE),
    re.compile(r'点击下一页继续阅读.*', re.IGNORECASE),
    re.compile(r'[\(（]?\s*本章完\s*[\)）]?', re.IGNORECASE),
    re.compile(r'[\(（]?\s*未完待续\s*[\)）]?', re.IGNORECASE),
    re.compile(r'https?://[^\s<>"]+', re.IGNORECASE),
    re.compile(r'(?:www\.)?[a-zA-Z0-9\-]+\.(?:com|net|org|cc|la|tv|biz|me|tw|hk|info|co)(?:/[^\s<>"]*)?', re.IGNORECASE),
    re.compile(r'^(?:笔趣阁|顶点小说|飘天文学|69书吧|51read|番茄小说|起点中文网|创世中文网|飞卢小说).*$', re.MULTILINE),
    re.compile(r'^\s*[-=_]{3,}\s*$', re.MULTILINE),
]

# Patterns for author notes / promos that should be filtered if standalone lines
STANDALONE_PROMO_PATTERNS = [
    re.compile(r'^(?:求[月推荐点追收订精]+[票读藏阅品]?|打赏|加更|盟主|[!！。~～\s，,]|感谢)+$'),
    re.compile(r'^(?:书友群|官方群|交流群|QQ群|读者群)[：:\s]*\d+'),
    re.compile(r'^感谢.*?打赏.*?$'),
]

# Truncation markers for preview detection
TRUNCATION_MARKERS = [
    re.compile(r'\.{3,}$'),
    re.compile(r'……$'),
    re.compile(r'（未完）$'),
    re.compile(r'\(待续\)$'),
    re.compile(r'【剩余字数.*?请前往.*?阅读】'),
]


class RegexCleaningPipeline:
    def __init__(self, min_char_length: int = 500):
        self.min_char_length = min_char_length

    def clean_text(self, raw_text: str, chapter_title: str = "", source_url: str = "") -> str:
        """
        Runs raw chapter text through the cleaning pipeline and formats standard paragraphs.
        Raises DataIncompleteError if the cleaned text length is below the minimum threshold.
        """
        if not raw_text:
            raise DataIncompleteError(chapter_title, source_url, 0, "Empty content returned")

        # Stage 1: Global pattern removal
        text = raw_text
        for pattern in NOISE_PATTERNS:
            text = pattern.sub('', text)

        # Stage 2: Line-by-line filtering
        lines = text.split('\n')
        cleaned_paragraphs: List[str] = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Skip redundant chapter title at top of body
            if chapter_title and (line_str == chapter_title or line_str in chapter_title):
                continue
            if re.match(r'^第\s*[0-9零一二两三四五六七八九十百千万]+\s*[章节回集卷篇节]\b', line_str) and len(line_str) < 30:
                continue

            # Skip standalone promos
            if any(p.match(line_str) for p in STANDALONE_PROMO_PATTERNS):
                continue

            cleaned_paragraphs.append(line_str)

        # Re-assemble body text
        clean_body = "\n\n".join("    " + p for p in cleaned_paragraphs)
        char_count = sum(len(p) for p in cleaned_paragraphs)

        # Stage 3: Anomaly & Incomplete Content Detection
        if char_count < self.min_char_length:
            raise DataIncompleteError(
                chapter_title=chapter_title,
                url=source_url,
                content_length=char_count,
                reason=f"Character count ({char_count}) is below minimum threshold ({self.min_char_length})"
            )

        # Check for trailing preview truncation markers
        if cleaned_paragraphs:
            last_p = cleaned_paragraphs[-1]
            if char_count < 1000 and any(m.search(last_p) for m in TRUNCATION_MARKERS):
                raise DataIncompleteError(
                    chapter_title=chapter_title,
                    url=source_url,
                    content_length=char_count,
                    reason=f"Trailing preview truncation marker detected in short chapter: '{last_p[-20:]}'"
                )

        return clean_body
