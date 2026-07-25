"""Modelos para gestión de scrapers"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.contrib.auth.models import User
import json


class ScraperConfig(models.Model):
    """Configuración de cada scraper (archivo JSON)"""
    
    STATUS_CHOICES = [
        ('active', 'Activo'),
        ('inactive', 'Inactivo'),
        ('error', 'Error'),
    ]
    
    TYPE_CHOICES = [
        ('web', 'Web HTML'),
        ('api', 'API REST'),
    ]
    
    name = models.CharField(max_length=100, unique=True, verbose_name='Nombre')
    config_file = models.CharField(max_length=255, verbose_name='Archivo de configuración')
    scraper_type = models.CharField(max_length=10, choices=TYPE_CHOICES, verbose_name='Tipo')
    description = models.TextField(blank=True, verbose_name='Descripción')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active', verbose_name='Estado')
    
    # Configuración de ejecución
    requires_auth = models.BooleanField(default=False, verbose_name='Requiere autenticación')
    uses_proxy = models.BooleanField(default=False, verbose_name='Usa proxy')
    
    # Límites de recursos
    max_memory_mb = models.IntegerField(
        default=512,
        validators=[MinValueValidator(128), MaxValueValidator(2048)],
        verbose_name='RAM máxima (MB)'
    )
    timeout_seconds = models.IntegerField(
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(300)],
        verbose_name='Timeout (segundos)'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='Creado por')
    
    class Meta:
        verbose_name = 'Configuración de Scraper'
        verbose_name_plural = 'Configuraciones de Scrapers'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.get_scraper_type_display()})"
    
    def get_config_data(self):
        """Cargar datos del archivo JSON"""
        try:
            config_path = f"scraping_core/configs/{self.config_file}"
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            return {'error': str(e)}


class ScraperTask(models.Model):
    """Tarea de ejecución de scraper"""
    
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('running', 'Ejecutando'),
        ('completed', 'Completado'),
        ('failed', 'Fallido'),
        ('cancelled', 'Cancelado'),
    ]
    
    TRIGGER_CHOICES = [
        ('manual', 'Manual'),
        ('scheduled', 'Programado'),
    ]
    
    config = models.ForeignKey(ScraperConfig, on_delete=models.CASCADE, related_name='tasks', verbose_name='Configuración')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Estado')
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default='manual', verbose_name='Tipo de ejecución')
    
    # Información de ejecución
    rq_job_id = models.CharField(max_length=100, blank=True, verbose_name='ID de trabajo RQ')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='Inicio')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Finalización')
    
    # Resultados
    items_scraped = models.IntegerField(default=0, verbose_name='Elementos extraídos')
    errors_count = models.IntegerField(default=0, verbose_name='Errores')
    log_file = models.CharField(max_length=255, blank=True, verbose_name='Archivo de log')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='Ejecutado por')
    
    class Meta:
        verbose_name = 'Tarea de Scraper'
        verbose_name_plural = 'Tareas de Scrapers'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.config.name} - {self.get_status_display()} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
    
    @property
    def duration(self):
        """Duración de la tarea en segundos"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class ScheduledTask(models.Model):
    """Programación de tareas recurrentes"""
    
    FREQUENCY_CHOICES = [
        ('hourly', 'Cada hora'),
        ('daily', 'Diario'),
        ('weekly', 'Semanal'),
        ('custom', 'Personalizado'),
    ]
    
    config = models.ForeignKey(ScraperConfig, on_delete=models.CASCADE, related_name='schedules', verbose_name='Configuración')
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, verbose_name='Frecuencia')
    
    # Horarios
    hour = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(23)], verbose_name='Hora')
    minute = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(59)], verbose_name='Minuto')
    day_of_week = models.CharField(max_length=20, blank=True, verbose_name='Día de la semana (0-6)')
    
    # Control
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    last_run = models.DateTimeField(null=True, blank=True, verbose_name='Última ejecución')
    next_run = models.DateTimeField(null=True, blank=True, verbose_name='Próxima ejecución')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='Creado por')
    
    class Meta:
        verbose_name = 'Tarea Programada'
        verbose_name_plural = 'Tareas Programadas'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.config.name} - {self.get_frequency_display()} ({self.hour:02d}:{self.minute:02d})"


class ScrapedData(models.Model):
    """Datos extraídos por los scrapers"""
    
    task = models.ForeignKey(ScraperTask, on_delete=models.CASCADE, related_name='data', verbose_name='Tarea')
    config = models.ForeignKey(ScraperConfig, on_delete=models.CASCADE, related_name='data', verbose_name='Configuración')
    
    # Datos
    url = models.URLField(max_length=500, verbose_name='URL')
    data = models.JSONField(verbose_name='Datos')
    
    # Metadata
    scraped_at = models.DateTimeField(auto_now_add=True, verbose_name='Extraído')
    
    class Meta:
        verbose_name = 'Dato Extraído'
        verbose_name_plural = 'Datos Extraídos'
        ordering = ['-scraped_at']
        indexes = [
            models.Index(fields=['config', '-scraped_at']),
            models.Index(fields=['task', '-scraped_at']),
        ]
    
    def __str__(self):
        return f"{self.config.name} - {self.url[:50]}"


class ScraperLog(models.Model):
    """Logs de ejecución de scrapers"""
    
    LEVEL_CHOICES = [
        ('DEBUG', 'Debug'),
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Critical'),
    ]
    
    task = models.ForeignKey(ScraperTask, on_delete=models.CASCADE, related_name='logs', verbose_name='Tarea')
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='INFO', verbose_name='Nivel')
    message = models.TextField(verbose_name='Mensaje')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Timestamp')
    
    class Meta:
        verbose_name = 'Log de Scraper'
        verbose_name_plural = 'Logs de Scrapers'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['task', '-created_at']),
            models.Index(fields=['level', '-created_at']),
        ]
    
    def __str__(self):
        return f"[{self.level}] {self.task.config.name} - {self.message[:50]}"
