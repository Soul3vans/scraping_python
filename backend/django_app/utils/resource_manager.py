"""Gestor de recursos del sistema"""
import os
import resource
from django.conf import settings

class ResourceManager:
    """Control de recursos del sistema"""
    
    @staticmethod
    def set_limits():
        """Establecer límites de recursos"""
        max_ram = settings.MAX_RAM_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (max_ram, max_ram))
        
        max_cpu = settings.MAX_CPU_CORES
        os.sched_setaffinity(0, range(max_cpu))
    
    @staticmethod
    def get_usage() -> dict:
        """Obtener uso actual de recursos"""
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {
            'user_time': usage.ru_utime,
            'system_time': usage.ru_stime,
            'max_rss': usage.ru_maxrss
        }
