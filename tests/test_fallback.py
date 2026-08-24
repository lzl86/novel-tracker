"""
Unit tests for FallbackRouter, DomainStrategy, and Dynamic Query construction.
"""

import unittest
from core.fallback_router import FallbackRouter, DomainStrategy
from core.exceptions import DataIncompleteError


class TestFallbackRouter(unittest.TestCase):
    def setUp(self):
        self.router = FallbackRouter()

    def test_domain_strategy_scoring(self):
        # Whitelisted high quality domains
        self.assertEqual(DomainStrategy.score_url("https://www.51read.org/xiaoshuo/123"), 100)
        self.assertEqual(DomainStrategy.score_url("https://www.bige3.cc/book/123"), 95)

        # Blacklisted / noise domains
        self.assertEqual(DomainStrategy.score_url("https://tieba.baidu.com/p/123456"), -1000)
        self.assertEqual(DomainStrategy.score_url("https://www.zhihu.com/question/123"), -1000)
        self.assertEqual(DomainStrategy.score_url("https://wenku.novel.qq.com/read/123"), -500)

        # Candidate filtering & sorting
        raw_urls = [
            "https://tieba.baidu.com/p/123456",
            "https://www.bige3.cc/book/123",
            "https://www.zhihu.com/question/123",
            "https://www.51read.org/xiaoshuo/123",
            "https://random-novel-site.com/chap/1"
        ]
        sorted_urls = DomainStrategy.filter_and_sort_candidates(raw_urls)
        self.assertEqual(len(sorted_urls), 3)
        self.assertEqual(sorted_urls[0], "https://www.51read.org/xiaoshuo/123")
        self.assertEqual(sorted_urls[1], "https://www.bige3.cc/book/123")
        self.assertEqual(sorted_urls[2], "https://random-novel-site.com/chap/1")

    def test_dynamic_query_builder(self):
        q = self.router.build_query("宿命之环", "第100章 迷雾中的抉择（求月票）")
        self.assertIn("宿命之环", q)
        self.assertIn("迷雾中的抉择", q)


if __name__ == "__main__":
    unittest.main()
