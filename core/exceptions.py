"""
Custom exceptions for novel scraping, fallback routing and content validation.
"""


class NovelTrackerException(Exception):
    """Base exception for all novel tracker errors."""
    pass


class DataIncompleteError(NovelTrackerException):
    """
    Raised when chapter content is incomplete (e.g. preview snippet,
    length below minimum threshold, or paywall truncation).
    """
    def __init__(self, chapter_title: str, url: str, content_length: int, reason: str = ""):
        self.chapter_title = chapter_title
        self.url = url
        self.content_length = content_length
        self.reason = reason
        super().__init__(
            f"DATA_INCOMPLETE: '{chapter_title}' at {url} (Length: {content_length} chars, Reason: {reason})"
        )


class SourceExhaustedError(NovelTrackerException):
    """Raised when all primary and fallback sources for a chapter fail."""
    def __init__(self, chapter_title: str, attempted_sources: list):
        self.chapter_title = chapter_title
        self.attempted_sources = attempted_sources
        super().__init__(
            f"SOURCE_EXHAUSTED: Could not retrieve full content for '{chapter_title}' after trying {len(attempted_sources)} sources."
        )


class NetworkProbeError(NovelTrackerException):
    """Raised when metadata probing fails due to network or anti-bot restriction."""
    pass
