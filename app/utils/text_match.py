# utils/text_match.py
import unicodedata
import re
from difflib import SequenceMatcher
from typing import Set

def strip_accents(s: str) -> str:
    if s is None:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))

def norm_text(s: str) -> str:
    return strip_accents(s).lower().strip()

def tokenize(s: str) -> list[str]:
    return [t for t in re.split(r"\W+", norm_text(s)) if t]

def token_set_score(a: str, b: str) -> float:
    A: Set[str] = set(tokenize(a))
    B: Set[str] = set(tokenize(b))
    if not A or not B:
        return 0.0
    inter = len(A & B)
    return 2 * inter / (len(A) + len(B))  # 1.0 nếu cùng bộ từ

def fuzzy_score(a: str, b: str) -> float:
    s1 = SequenceMatcher(None, norm_text(a), norm_text(b)).ratio()
    s2 = token_set_score(a, b)
    return 0.5 * s1 + 0.5 * s2
