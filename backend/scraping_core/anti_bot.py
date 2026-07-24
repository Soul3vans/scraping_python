"""Sistema de defensa anti-bot"""
from fake_useragent import UserAgent
import random
import time

class AntiBotSystem:
    """Sistema de evasión de detección de bots"""
    
    def __init__(self):
        self.ua = UserAgent()
        self.last_request_time = 0
    
    def get_random_headers(self) -> dict:
        """Obtener headers aleatorios"""
        return {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
    
    def apply_delay(self, min_delay: float = 1.0, max_delay: float = 3.0):
        """Aplicar delay aleatorio entre requests"""
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)
        self.last_request_time = time.time()
    
    def get_random_proxy(self, proxy_list: list) -> str:
        """Obtener proxy aleatorio de la lista"""
        if not proxy_list:
            return None
        return random.choice(proxy_list)
