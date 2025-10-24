"""
Number utility functions for parsing and converting numeric values.
"""
from typing import Union

__all__ = [
    "parse_number",
    "parse_quantity",
]


def parse_number(v) -> Union[float, any]:
    try:
        return float(v)
    except Exception:
        return v


def parse_quantity(quantity_str: str) -> float:
    quantity_str = quantity_str.strip()
    
    if '/' in quantity_str:
        parts = quantity_str.split()
        if len(parts) == 2: 
            whole = float(parts[0])
            frac = parts[1].split('/')
            return whole + float(frac[0]) / float(frac[1])
        else:  
            frac = quantity_str.split('/')
            return float(frac[0]) / float(frac[1])
    
    return float(quantity_str)
