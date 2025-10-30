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
            
            quantity_str = converted['quantity']
            unit_str = converted['unit']
            
            if quantity_str and unit_str:
                combined = f"{quantity_str} {unit_str}"
            elif quantity_str:
                combined = quantity_str
            else:
                combined = unit_str or ''
            
            result.append({
                **item,
                'quantity': combined,
                'unit': unit_str
            })
        
        return result
    
    def _convert_single(self, item: dict) -> dict:
        quantity = str(item.get('quantity', '')).strip()
        unit = str(item.get('unit', '')).strip().lower()
        name = str(item.get('name_vi') or item.get('name') or '').strip().lower()
        
        if not quantity or quantity == '':
            return {'quantity': '', 'unit': unit or 'tùy thích'}
        
        try:
            qty_value = parse_quantity(quantity)
        except:
            return {'quantity': quantity, 'unit': unit}
        
        if (not unit) or (unit in self.count_units):
            return {'quantity': quantity, 'unit': unit or 'tùy thích'}

        is_liquid = any(keyword in name for keyword in self.liquid_keywords)
        
        if unit in self.weight_to_gram:
            converted_qty = qty_value * self.weight_to_gram[unit]
            return {
                'quantity': str(int(converted_qty)) if converted_qty.is_integer() else str(round(converted_qty, 1)),
                'unit': 'g'
            }
        
        if unit in self.volume_to_ml:
            converted_qty = qty_value * self.volume_to_ml[unit]
            return {
                'quantity': str(int(converted_qty)) if converted_qty.is_integer() else str(round(converted_qty, 1)),
                'unit': 'ml'
            }
        
        if unit in ['củ', 'cây', 'quả', 'trái']:
            for key, (est_unit, est_gram, est_target) in self.count_estimation.items():
                if key in name and unit == est_unit:
                    converted_qty = qty_value * est_gram
                    return {
                        'quantity': str(int(converted_qty)),
                        'unit': est_target
                    }
            return {'quantity': quantity, 'unit': unit}
        
        if unit in ['củ', 'cây', 'quả', 'trái', 'miếng', 'lát', 'lá', 'nhánh', 'bó', 'gói']:
            return {'quantity': quantity, 'unit': unit}
        
        if is_liquid:
            return {'quantity': quantity, 'unit': 'ml'}
        else:
            return {'quantity': quantity, 'unit': 'g'}