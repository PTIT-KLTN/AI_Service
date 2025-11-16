from typing import Union

__all__ = [
    "parse_number",
    "parse_quantity",
]


def parse_number(value):
    """
    Parse a value to number (int or float).
    Returns None if cannot parse or if value is empty/None.
    """
    if value is None:
        return None
    
    # Convert to string and strip whitespace
    s = str(value).strip()
    
    # Return None for empty strings
    if not s or s == '':
        return None
    
    # Remove common separators
    s = s.replace(',', '').replace(' ', '')
    
    try:
        # Try integer first
        if '.' not in s:
            return int(float(s))
        # Otherwise return float
        return float(s)
    except (ValueError, TypeError):
        return None


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
