# utils/text_match.py
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, List, Set, Optional

__all__ = [
    "strip_accents",
    "norm_text",
    "tokenize",
    "token_set_score",
    "fuzzy_score",
    "unique",
]

_WORD_SPLIT_RE = re.compile(r"\W+")


def strip_accents(s: Optional[str]) -> str:
    """Loại bỏ dấu/diacritics khỏi chuỗi. Trả về '' nếu đầu vào là None."""
    if s is None:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def norm_text(s: Optional[str]) -> str:
    """Chuẩn hoá: bỏ dấu, lower-case, trim."""
    return strip_accents(s).lower().strip()


def tokenize(s: Optional[str]) -> List[str]:
    """Tách từ theo ký tự không phải \w sau khi chuẩn hoá; bỏ token rỗng."""
    return [t for t in _WORD_SPLIT_RE.split(norm_text(s)) if t]


def token_set_score(a: Optional[str], b: Optional[str]) -> float:
    """
    Jaccard-like score theo kích thước giao và hợp (dạng trung bình điều hoà):
    2 * |A∩B| / (|A| + |B|). Trả về 0.0 nếu một trong hai rỗng.
    """
    A: Set[str] = set(tokenize(a))
    B: Set[str] = set(tokenize(b))
    if not A or not B:
        return 0.0
    inter = len(A & B)
    return 2.0 * inter / (len(A) + len(B))


def fuzzy_score(a: Optional[str], b: Optional[str]) -> float:
    """
    Điểm mờ kết hợp:
    - s1: SequenceMatcher trên chuỗi chuẩn hoá
    - s2: token_set_score
    Trả về 0.0 nếu cả hai chuỗi rỗng sau chuẩn hoá.
    """
    na = norm_text(a)
    nb = norm_text(b)
    if not na and not nb:
        return 0.0
    s1 = SequenceMatcher(None, na, nb).ratio()
    s2 = token_set_score(a, b)
    return 0.5 * s1 + 0.5 * s2


def unique(items: Iterable[str]) -> List[str]:
    """
    Giữ thứ tự xuất hiện, loại trùng (so sánh lower-case). Bỏ item rỗng/None.
    """
    seen: Set[str] = set()
    result: List[str] = []
    for item in items:
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
