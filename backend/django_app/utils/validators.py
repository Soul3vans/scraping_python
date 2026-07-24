"""Validadores de datos extraídos"""
from pydantic import BaseModel, ValidationError
from typing import Any, Dict, List

class ScrapedDataValidator:
    """Validador de datos scrapeados"""
    
    @staticmethod
    def validate_basic_data(data: Dict[str, Any]) -> bool:
        """Validación básica de datos"""
        if not data:
            return False
        
        required_fields = ['url', 'timestamp']
        for field in required_fields:
            if field not in data:
                return False
        
        return True
    
    @staticmethod
    def validate_with_schema(data: Dict[str, Any], schema: BaseModel) -> bool:
        """Validar datos contra un esquema Pydantic"""
        try:
            schema(**data)
            return True
        except ValidationError:
            return False
    
    @staticmethod
    def sanitize_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitizar datos extraídos"""
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = value.strip()
            else:
                sanitized[key] = value
        return sanitized
