"""
Unit tests for HeuristicExtractor and RegexCleaningPipeline.
"""

import unittest
from core.heuristic_extractor import HeuristicExtractor
from core.pipeline import RegexCleaningPipeline
from core.exceptions import DataIncompleteError


class TestExtractionAndPipeline(unittest.TestCase):
    def setUp(self):
        self.extractor = HeuristicExtractor()
        self.pipeline = RegexCleaningPipeline(min_char_length=100)

    def test_heuristic_extraction_and_cleaning(self):
        messy_html = """
        <!DOCTYPE html>
        <html>
        <head><title>第10章 决战 - 笔趣阁</title></head>
        <body>
            <header><nav><a href="/">首页</a> | <a href="/login">登录</a></nav></header>
            <div class="sidebar">推荐小说：斗破苍穹 热门排行</div>
            <div class="comment">书友评论：这章太精彩了！</div>
            <div id="chapter_wrap">
                <h1>第10章 决战</h1>
                <p>请记住本书首发域名：www.biquge.com</p>
                <p>夜幕降临，天空中乌云密布，雷声滚滚而来。</p>
                <p>张羽手持三尺青锋，目光如电般注视着前方的黑袍修士。</p>
                <p>“你以为凭借这区区微末伎俩，便能抵挡我的仙法吗？”黑袍人冷冷一笑，浑身真气瞬间爆发。</p>
                <p>狂暴的灵力如潮水般席卷四周，大地震颤，尘土飞扬。</p>
                <p>张羽身形一动，化作一道青色剑光，以迅雷不及掩耳之势直刺而出！</p>
                <p>双方激战数十回合，虚空震荡，最终黑袍人闷哼一声倒飞而出。</p>
                <p>求月票！求推荐票！</p>
                <p>(本章完)</p>
            </div>
            <footer>最新章节更新：www.biquge.com 手机用户请访问 wap.biquge.com</footer>
        </body>
        </html>
        """
        extracted = self.extractor.extract_article_text(messy_html)
        self.assertIn("张羽", extracted)
        self.assertIn("黑袍人", extracted)

        cleaned = self.pipeline.clean_text(extracted, chapter_title="第10章 决战", source_url="http://test.com")
        self.assertIn("夜幕降临", cleaned)
        self.assertIn("张羽手持三尺青锋", cleaned)
        self.assertNotIn("请记住本书首发域名", cleaned)
        self.assertNotIn("www.biquge.com", cleaned)
        self.assertNotIn("求月票", cleaned)
        self.assertNotIn("本章完", cleaned)

    def test_incomplete_content_raises_error(self):
        short_text = "这是一段不到一百字的短文本，只有一点点内容。"
        with self.assertRaises(DataIncompleteError):
            self.pipeline.clean_text(short_text, chapter_title="测试短章节", source_url="http://test.com")

    def test_trailing_truncation_detection(self):
        truncated_text = "张羽走进了仙人洞天，看着前方无边无际的云海，心中充满了震撼与期待，随后他迈出脚步向前走去……"
        # Length is around 50 chars, below threshold, raises DataIncompleteError
        with self.assertRaises(DataIncompleteError):
            self.pipeline.clean_text(truncated_text, chapter_title="截断章节", source_url="http://test.com")


if __name__ == "__main__":
    unittest.main()
