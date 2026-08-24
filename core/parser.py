"""
Chapter title parsing and numeral conversion utility.
Converts Chinese and Arabic numerals in novel chapter titles into comparable integer values.
"""

import re
from typing import Optional, Tuple

CHINESE_NUM_MAP = {
    '零': 0, '〇': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
    '十': 10, '百': 100, '千': 1000, '万': 10000
}

def chinese_to_int(cn_num_str: str) -> Optional[int]:
    """
    Convert Chinese numeral string (e.g., '一千零五十章', '两百二十三', '123') to integer.
    """
    if not cn_num_str:
        return None
    
    # If it's already purely digits
    if cn_num_str.isdigit():
        return int(cn_num_str)
    
    # Remove leading/trailing spaces
    cn_num_str = cn_num_str.strip()
    
    total = 0
    current_val = 0
    has_digit = False
    
    # Handle special case: '十几' -> 10 + x
    if cn_num_str.startswith('十'):
        current_val = 1
    
    for char in cn_num_str:
        if char in ('零', '〇'):
            continue
        elif char in ('一', '二', '两', '三', '四', '五', '六', '七', '八', '九'):
            current_val = CHINESE_NUM_MAP[char]
            has_digit = True
        elif char in ('十', '百', '千'):
            multiplier = CHINESE_NUM_MAP[char]
            if current_val == 0 and not has_digit:
                current_val = 1
            total += current_val * multiplier
            current_val = 0
            has_digit = False
        elif char == '万':
            total = (total + current_val) * 10000
            current_val = 0
            has_digit = False
        else:
            # Non-numeral char encountered
            break
            
    total += current_val
    return total if (total > 0 or has_digit) else None


CHAPTER_PATTERNS = [
    # 第1234章 / 第1234节 / 第一千二百三十四章 / 第1234回
    re.compile(r'第\s*([0-9零一二两三四五六七八九十百千万]+)\s*[章节回集卷篇节]'),
    # 1234. 章节名 / 1234、章节名 / 1234 章节名
    re.compile(r'^\s*([0-9]+)\s*[\.、\s\-_]'),
    # Chapter 123
    re.compile(r'Chapter\s*([0-9]+)', re.IGNORECASE),
    # 纯数字开头
    re.compile(r'^\s*([0-9]{1,5})\b')
]

SPECIAL_CHAPTERS = {
    '终章': 999998,
    '大结局': 999999,
    '完本感言': 1000000,
    '完结感言': 1000000,
    '后记': 999990,
    '番外': 999900,
    '序章': 0,
    '楔子': 0,
    '引子': 0,
    '前言': 0,
}

def extract_chapter_number(title: str) -> Tuple[float, str]:
    """
    Extracts the estimated chapter number and a cleaned title from a raw chapter title string.
    Returns:
        (chapter_number: float, clean_title: str)
    """
    if not title:
        return 0.0, ""
    
    clean_title = title.strip()
    
    # Check for specific chapter keyword patterns: 第xxx章, 第xxx节, 第xxx回
    primary_pattern = re.compile(r'第\s*([0-9零一二两三四五六七八九十百千万]+)\s*([章节回集篇节])')
    matches = primary_pattern.findall(clean_title)
    if matches:
        # If there are multiple matches (e.g., 第1卷 第50章), prioritize '章'/'回'/'节'
        best_num = 0.0
        for num_str, unit_type in matches:
            val = chinese_to_int(num_str)
            if val is not None:
                if unit_type in ('章', '回', '节', '篇'):
                    best_num = max(best_num, float(val))
                elif best_num == 0.0:
                    best_num = float(val)
        if best_num > 0.0:
            return best_num, clean_title

    # Try fallback regex patterns
    for pattern in CHAPTER_PATTERNS:
        match = pattern.search(clean_title)
        if match:
            raw_num = match.group(1)
            parsed_num = chinese_to_int(raw_num)
            if parsed_num is not None:
                return float(parsed_num), clean_title

    # Check for special keywords
    for key, val in SPECIAL_CHAPTERS.items():
        if key in clean_title:
            return float(val), clean_title
                
    # If no number matched, return default 0.0
    return 0.0, clean_title
