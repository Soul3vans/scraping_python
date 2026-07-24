"""Clase base abstracta para scrapers"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import logging

class BaseScraper(ABC):
    """Clase base para todos los scrapers"""
    
    def __init__(self, config_path: str, logger: Optional[logging.Logger] = None):
        self.config_path = config_path
        self.logger = logger or logging.getLogger(__name__)
        self.session = None
        
    @abstractmethod
    def authenticate(self) -> bool:
        """Método de autenticación"""
        pass
    
    @abstractmethod
    def scrape(self) -> Dict[str, Any]:
        """Método principal de scraping"""
        pass
    
    @abstractmethod
    def validate_data(self, data: Dict[str, Any]) -> bool:
        """Validar datos extraídos"""
        pass
    
    def cleanup(self):
        """Limpieza de recursos"""
        if self.session:
            self.session.close()
