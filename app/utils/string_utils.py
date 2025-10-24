"""
String utility functions for text normalization and comparison.
"""
import unicodedata
from difflib import SequenceMatcher
from typing import Optional

__all__ = [
    "strip_accents",
    "norm_text",
    "similarity_ratio",
]


def strip_accents(s: Optional[str]) -> str:
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def norm_text(s: Optional[str]) -> str:
    if s is None:
        return ""
    return strip_accents(s).lower().strip()


def similarity_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, norm_text(a), norm_text(b)).ratio()
