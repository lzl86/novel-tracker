"""
Unit tests for NovelTracker.
"""

import os
import tempfile
import unittest
from core.tracker import NovelTracker


class TestTracker(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.close()
        self.tracker = NovelTracker(storage_path=self.temp_file.name)

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    def test_add_and_get(self):
        self.tracker.add_book("赤心巡天", author="情何以甚", latest_chapter="第1000章 决战", latest_chapter_num=1000.0)
        book = self.tracker.get_book("赤心巡天")
        self.assertIsNotNone(book)
        self.assertEqual(book["book_name"], "赤心巡天")
        self.assertEqual(book["last_known_chapter"], "第1000章 决战")

    def test_update_detection(self):
        self.tracker.add_book("宿命之环", author="爱潜水的乌贼", latest_chapter="第100章", latest_chapter_num=100.0)
        
        # Test no update with same or lower chapter
        is_new, old_title = self.tracker.check_and_update(
            "宿命之环",
            new_chapter_title="第100章",
            new_chapter_num=100.0,
            new_chapter_url="http://test.com",
            source_name="Test"
        )
        self.assertFalse(is_new)
        
        # Test update with higher chapter
        is_new, old_title = self.tracker.check_and_update(
            "宿命之环",
            new_chapter_title="第101章 新世界",
            new_chapter_num=101.0,
            new_chapter_url="http://test.com/101",
            source_name="Test"
        )
        self.assertTrue(is_new)
        self.assertEqual(old_title, "第100章")

    def test_remove(self):
        self.tracker.add_book("道诡异仙")
        self.assertTrue(self.tracker.remove_book("道诡异仙"))
        self.assertIsNone(self.tracker.get_book("道诡异仙"))


if __name__ == "__main__":
    unittest.main()
