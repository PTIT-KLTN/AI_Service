import re

class UnitConverterService:
    def __init__(self):
        # Conversion rules
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
            'muỗng': 15,  # Mặc định = muỗng canh
            'muong': 15,
            'ly': 200,
            'cốc': 240,
            'coc': 240
        }
        
        # Ước lượng đơn vị đếm
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
        
        # Liquid ingredients (chuyển sang ml)
        self.liquid_keywords = [
            'nước', 'dầu', 'mắm', 'tương', 'sữa', 'giấm', 
            'rượu', 'nước cốt', 'nước dừa', 'nước mía'
        ]

        self.count_units = {
            'cái','chiếc','quả','trái','nhánh','cọng','nắm','miếng','tép','lá','con',
            'ổ','ổ bánh','ổ mì','bó','gói','lát'
        }

    
    def normalize_ingredients(self, ingredients: list) -> list:
        """
        Chuyển đổi nhanh không cần LLM
        """
        if not ingredients:
            return []
        
        result = []
        for item in ingredients:
            converted = self._convert_single(item)
            result.append({
                **item,
                'converted_quantity': converted['quantity'],
                'converted_unit': converted['unit']
            })
        
        return result
    
    def _convert_single(self, item: dict) -> dict:
        """
        Chuyển đổi 1 nguyên liệu
        """
        quantity = str(item.get('quantity', '')).strip()
        unit = str(item.get('unit', '')).strip().lower()
        name = str(item.get('name_vi') or item.get('name') or '').strip().lower()
        
        # Không có số lượng
        if not quantity or quantity == '':
            return {'quantity': '', 'unit': unit or 'tùy thích'}
        
        # Parse quantity (có thể là số hoặc phân số)
        try:
            qty_value = self._parse_quantity(quantity)
        except:
            return {'quantity': quantity, 'unit': unit}
        
        # Giữ nguyên nếu là đơn vị đếm hoặc unit rỗng
        if (not unit) or (unit in self.count_units):
            return {'quantity': quantity, 'unit': unit or 'tùy thích'}

        
        # Kiểm tra liquid
        is_liquid = any(keyword in name for keyword in self.liquid_keywords)
        
        # Chuyển đổi weight
        if unit in self.weight_to_gram:
            converted_qty = qty_value * self.weight_to_gram[unit]
            return {
                'quantity': str(int(converted_qty)) if converted_qty.is_integer() else str(round(converted_qty, 1)),
                'unit': 'g'
            }
        
        # Chuyển đổi volume
        if unit in self.volume_to_ml:
            converted_qty = qty_value * self.volume_to_ml[unit]
            return {
                'quantity': str(int(converted_qty)) if converted_qty.is_integer() else str(round(converted_qty, 1)),
                'unit': 'ml'
            }
        
        # Ước lượng đơn vị đếm (nếu muốn)
        if unit in ['củ', 'cây', 'quả', 'trái']:
            # Tìm estimation
            for key, (est_unit, est_gram, est_target) in self.count_estimation.items():
                if key in name and unit == est_unit:
                    converted_qty = qty_value * est_gram
                    return {
                        'quantity': str(int(converted_qty)),
                        'unit': est_target
                    }
            # Không tìm thấy → giữ nguyên
            return {'quantity': quantity, 'unit': unit}
        
        # Đơn vị đặc biệt - giữ nguyên
        if unit in ['củ', 'cây', 'quả', 'trái', 'miếng', 'lát', 'lá', 'nhánh', 'bó', 'gói']:
            return {'quantity': quantity, 'unit': unit}
        
        # Default: nếu liquid → ml, solid → g
        if is_liquid:
            return {'quantity': quantity, 'unit': 'ml'}
        else:
            return {'quantity': quantity, 'unit': 'g'}
    
    def _parse_quantity(self, quantity_str: str) -> float:
        """
        Parse số lượng: "1", "1.5", "1/2", "2 1/2"
        """
        quantity_str = quantity_str.strip()
        
        # Phân số: 1/2, 3/4
        if '/' in quantity_str:
            parts = quantity_str.split()
            if len(parts) == 2:  # 2 1/2
                whole = float(parts[0])
                frac = parts[1].split('/')
                return whole + float(frac[0]) / float(frac[1])
            else:  # 1/2
                frac = quantity_str.split('/')
                return float(frac[0]) / float(frac[1])
        
        # Số thập phân: 1.5, 2.0
        return float(quantity_str)