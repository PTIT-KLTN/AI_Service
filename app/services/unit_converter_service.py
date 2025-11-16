import re
from app.utils.number_utils import parse_quantity

class UnitConverterService:
    def __init__(self):
        self.weight_to_gram = {
            'kg': 1000,
            'kilogram': 1000,
            'lạng': 100,
            'cân': 600,
            'g': 1,
            'gr': 1,  # gr là viết tắt của gram
            'gram': 1,
            'tạ': 100000,
            'yến': 10,
            'mg': 0.001,
            'miligram': 0.001
        }
        
        self.volume_to_ml = {
            'l': 1000,
            'lít': 1000,
            'liter': 1000,
            'ml': 1,
            'mililít': 1,
            'milliliter': 1,
            'chén': 240,
            'chen': 240,
            'muỗng canh': 15,
            'muong canh': 15,
            'tbsp': 15,
            'tablespoon': 15,
            'muỗng cà phê': 5,
            'muong ca phe': 5,
            'tsp': 5,
            'teaspoon': 5,
            'muỗng': 15,
            'muong': 15,
            'ly': 200,
            'cốc': 240,
            'coc': 240
        }
        
        self.count_estimation = {
            'củ hành': ('củ', 100, 'g'),
            'hành': ('củ', 100, 'g'),
            'củ tỏi': ('củ', 50, 'g'),
            'tỏi': ('củ', 50, 'g'),
            'cây sả': ('cây', 20, 'g'),
            'sả': ('cây', 20, 'g'),
            'quả cà chua': ('quả', 150, 'g'),
            'cà chua': ('quả', 150, 'g'),
            'quả chanh': ('quả', 80, 'g'),
            'chanh': ('quả', 80, 'g'),
            'củ gừng': ('củ', 80, 'g'),
            'gừng': ('củ', 80, 'g'),
            'củ cà rót': ('củ', 200, 'g'),
            'cà rót': ('củ', 200, 'g'),
            'trái ớt': ('trái', 10, 'g'),
            'ớt': ('trái', 10, 'g')
        }
        
        self.liquid_keywords = [
            'nước', 'dầu', 'mắm', 'tương', 'sữa', 'giấm', 
            'rượu', 'nước cốt', 'nước dừa', 'nước mía'
        ]

        self.count_units = {
            'cái','chiếc','quả','trái','nhánh','cọng','nắm','miếng','tép','lá','con',
            'ổ','ổ bánh','ổ mì','bó','gói','lát'
        }
    def normalize_ingredients(self, ingredients: list) -> list:
        if not ingredients:
            return []
        
        result = []
        for item in ingredients:
            converted = self._convert_single(item)
            
            # converted now has a combined 'unit' field
            result.append({
                **item,
                'unit': converted['unit']
            })
        
        return result
    
    def _convert_single(self, item: dict) -> dict:
        # Parse combined 'unit' field into quantity and unit parts
        combined_unit = str(item.get('unit', '')).strip()
        
        # Try to split into quantity and unit
        # Format: "500 g" or "2 củ" or "1.0 kg" or just "g" or just "500"
        parts = combined_unit.split(None, 1)  # Split on first whitespace
        
        if len(parts) == 2:
            quantity_str, unit = parts
        elif len(parts) == 1:
            # Could be just quantity or just unit
            # Try to parse as number first
            try:
                from app.utils.number_utils import parse_number
                parse_number(parts[0])
                quantity_str = parts[0]
                unit = ''
            except:
                quantity_str = ''
                unit = parts[0]
        else:
            quantity_str = ''
            unit = ''
        
        unit = unit.lower()
        name = str(item.get('name_vi') or item.get('vietnamese_name') or item.get('name') or '').strip().lower()
        
        if not quantity_str or quantity_str == '':
            # Normalize gr to g
            normalized_unit = 'g' if unit == 'gr' else unit
            return {'unit': normalized_unit or 'tùy thích'}
        
        try:
            qty_value = parse_quantity(quantity_str)
        except:
            # Normalize gr to g in combined string
            normalized_combined = combined_unit.replace(' gr', ' g').replace(' gr,', ' g,')
            return {'unit': normalized_combined}
        
        if (not unit) or (unit in self.count_units):
            return {'unit': f"{quantity_str} {unit}".strip() if unit else quantity_str}

        is_liquid = any(keyword in name for keyword in self.liquid_keywords)
        
        # Normalize gr to g
        if unit == 'gr':
            unit = 'g'
        
        if unit in self.weight_to_gram:
            converted_qty = qty_value * self.weight_to_gram[unit]
            qty_str = str(int(converted_qty)) if converted_qty.is_integer() else str(round(converted_qty, 1))
            return {'unit': f"{qty_str} g"}
        
        if unit in self.volume_to_ml:
            converted_qty = qty_value * self.volume_to_ml[unit]
            qty_str = str(int(converted_qty)) if converted_qty.is_integer() else str(round(converted_qty, 1))
            return {'unit': f"{qty_str} ml"}
        
        if unit in ['củ', 'cây', 'quả', 'trái']:
            for key, (est_unit, est_gram, est_target) in self.count_estimation.items():
                if key in name and unit == est_unit:
                    converted_qty = qty_value * est_gram
                    qty_str = str(int(converted_qty))
                    return {'unit': f"{qty_str} {est_target}"}
            return {'unit': f"{quantity_str} {unit}"}
        
        if unit in ['củ', 'cây', 'quả', 'trái', 'miếng', 'lát', 'lá', 'nhánh', 'bó', 'gói']:
            return {'unit': f"{quantity_str} {unit}"}
        
        if is_liquid:
            return {'unit': f"{quantity_str} ml"}
        else:
            return {'unit': f"{quantity_str} g"}