"""
Unit tests for chapter parser and tracker state.
"""

import unittest
from core.parser import chinese_to_int, extract_chapter_number
from core.tracker import NovelTracker


class TestChapterParser(unittest.TestCase):
    def test_chinese_to_int(self):
        self.assertEqual(chinese_to_int("123"), 123)
        self.assertEqual(chinese_to_int("一"), 1)
        self.assertEqual(chinese_to_int("十"), 10)
        self.assertEqual(chinese_to_int("十五"), 15)
        self.assertEqual(chinese_to_int("二十三"), 23)
        self.assertEqual(chinese_to_int("一百零八"), 108)
        self.assertEqual(chinese_to_int("一千零五十章"), 1050)
        self.assertEqual(chinese_to_int("两千三百二十"), 2320)

    def test_extract_chapter_number(self):
        cases = [
            ("第1234章 决战时刻", 1234.0),
            ("第一千零五十章 宿命的对决", 1050.0),
            ("1024. 逆转", 1024.0),
            ("第999节 终末之海", 999.0),
            ("第1卷 第50章 启程", 50.0),
            ("终章 回归", 999998.0),
            ("大结局（完）", 999999.0),
            ("完本感言", 1000000.0),
        ]
        for title, expected_num in cases:
            num, clean = extract_chapter_number(title)
            self.assertEqual(num, expected_num, f"Failed for {title}: got {num}, expected {expected_num}")


if __name__ == "__main__":
    unittest.main()
