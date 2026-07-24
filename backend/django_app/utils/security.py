"""Módulo de seguridad y encriptación"""
from cryptography.fernet import Fernet
from django.conf import settings
import os

class SecurityManager:
    """Gestor de seguridad y encriptación"""
    
    def __init__(self):
        self.cipher = Fernet(settings.ENCRYPTION_KEY.encode())
    
    def encrypt(self, data: str) -> str:
        """Encriptar datos sensibles"""
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """Desencriptar datos"""
        return self.cipher.decrypt(encrypted_data.encode()).decode()
    
    @staticmethod
    def validate_password(password: str) -> bool:
        """Validar fortaleza de contraseña"""
        if len(password) < 12:
            return False
        if not any(c.isupper() for c in password):
            return False
        if not any(c.islower() for c in password):
            return False
        if not any(c.isdigit() for c in password):
            return False
        return True
