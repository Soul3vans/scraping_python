"""Sistema de rotación de proxies"""
import random
from typing import List, Optional
import requests

class ProxyRotator:
    """Rotador de proxies"""
    
    def __init__(self, proxy_list: List[str]):
        self.proxies = proxy_list
        self.current_index = 0
        self.failed_proxies = set()
    
    def get_next_proxy(self) -> Optional[dict]:
        """Obtener siguiente proxy disponible"""
        available_proxies = [p for p in self.proxies if p not in self.failed_proxies]
        
        if not available_proxies:
            self.failed_proxies.clear()
            available_proxies = self.proxies
        
        if not available_proxies:
            return None
        
        proxy = random.choice(available_proxies)
        return {
            'http': f'http://{proxy}',
            'https': f'http://{proxy}'
        }
    
    def mark_proxy_failed(self, proxy: str):
        """Marcar proxy como fallido"""
        self.failed_proxies.add(proxy)
    
    def test_proxy(self, proxy: dict, test_url: str = 'https://httpbin.org/ip') -> bool:
        """Probar si un proxy funciona"""
        try:
            response = requests.get(test_url, proxies=proxy, timeout=5)
            return response.status_code == 200
        except:
            return False
