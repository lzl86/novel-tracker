"""
Watchlist and state manager for followed novels.
Persists tracked novels and their latest known chapters to a JSON file.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple


class NovelTracker:
    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            # Default to watchlist.json in current work directory
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.storage_path = os.path.join(base_dir, "watchlist.json")
        else:
            self.storage_path = storage_path
            
        self.data: Dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        """Load watchlist from disk."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def save(self) -> None:
        """Save watchlist to disk."""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get_all(self) -> List[dict]:
        """Return all tracked novels as a list."""
        return list(self.data.values())

    def get_book(self, book_name: str) -> Optional[dict]:
        """Get a specific tracked novel."""
        return self.data.get(book_name.strip())

    def add_book(
        self,
        book_name: str,
        author: str = "",
        latest_chapter: str = "",
        latest_chapter_num: float = 0.0,
        latest_chapter_url: str = "",
        source_name: str = ""
    ) -> dict:
        """
        Add or update a book in the watchlist.
        """
        name = book_name.strip()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        book_entry = {
            "book_name": name,
            "author": author.strip() if author else "未知",
            "last_known_chapter": latest_chapter,
            "last_known_chapter_num": latest_chapter_num,
            "last_known_chapter_url": latest_chapter_url,
            "source_name": source_name,
            "added_at": self.data.get(name, {}).get("added_at", now_str),
            "updated_at": now_str,
            "last_checked_at": now_str
        }
        self.data[name] = book_entry
        self.save()
        return book_entry

    def remove_book(self, book_name: str) -> bool:
        """Remove a book from the watchlist."""
        name = book_name.strip()
        if name in self.data:
            del self.data[name]
            self.save()
            return True
        return False

    def check_and_update(
        self,
        book_name: str,
        new_chapter_title: str,
        new_chapter_num: float,
        new_chapter_url: str,
        source_name: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if the incoming chapter is newer than recorded.
        Returns:
            (is_updated: bool, old_chapter_title: Optional[str])
        """
        name = book_name.strip()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if name not in self.data:
            # First time seeing this book, register it
            self.add_book(
                book_name=name,
                latest_chapter=new_chapter_title,
                latest_chapter_num=new_chapter_num,
                latest_chapter_url=new_chapter_url,
                source_name=source_name
            )
            return False, None

        current = self.data[name]
        current["last_checked_at"] = now_str
        old_title = current.get("last_known_chapter", "")
        old_num = current.get("last_known_chapter_num", 0.0)

        # Compare: either chapter number is greater, or title changed (when numbers are equal or 0)
        is_newer = False
        if new_chapter_num > old_num and new_chapter_num > 0:
            is_newer = True
        elif new_chapter_title and new_chapter_title != old_title and old_title == "":
            is_newer = True
        elif new_chapter_title and new_chapter_title != old_title and old_num == 0:
            is_newer = True

        if is_newer:
            current["last_known_chapter"] = new_chapter_title
            current["last_known_chapter_num"] = new_chapter_num
            current["last_known_chapter_url"] = new_chapter_url
            current["source_name"] = source_name
            current["updated_at"] = now_str
            self.save()
            return True, old_title

        self.save()
        return False, old_title
