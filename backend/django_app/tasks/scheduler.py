
"""Scheduler para tareas programadas"""
from django.utils import timezone
from django_app.scrapers.models import ScheduledTask, ScraperTask
from .scraper_tasks import queue_scraper_task
import logging


logger = logging.getLogger(__name__)


def check_scheduled_tasks():
    """Verificar y ejecutar tareas programadas"""
    
    now = timezone.now()
    
    # Buscar tareas que deben ejecutarse
    scheduled_tasks = ScheduledTask.objects.filter(
        is_active=True,
        next_run__lte=now
    )
    
    for scheduled_task in scheduled_tasks:
        try:
            # Crear nueva tarea de ejecución
            task = ScraperTask.objects.create(
                config=scheduled_task.config,
                trigger_type='scheduled',
                created_by=scheduled_task.created_by
            )
            
            # Encolar tarea
            queue_scraper_task(task.id)
            
            # Actualizar última ejecución y próxima ejecución
            scheduled_task.last_run = now
            scheduled_task.next_run = calculate_next_run(scheduled_task)
            scheduled_task.save()
            
            logger.info(f"Tarea programada ejecutada: {scheduled_task.config.name}")
            
        except Exception as e:
            logger.error(f"Error ejecutando tarea programada {scheduled_task.id}: {str(e)}")


def calculate_next_run(scheduled_task: ScheduledTask):
    """Calcular próxima ejecución basada en frecuencia"""
    
    from datetime import timedelta
    
    now = timezone.now()
    
    if scheduled_task.frequency == 'hourly':
        return now + timedelta(hours=1)
    
    elif scheduled_task.frequency == 'daily':
        next_run = now.replace(
            hour=scheduled_task.hour,
            minute=scheduled_task.minute,
            second=0,
            microsecond=0
        )
        if next_run <= now:
            next_run += timedelta(days=1)
        return next_run
    
    elif scheduled_task.frequency == 'weekly':
        next_run = now.replace(
            hour=scheduled_task.hour,
            minute=scheduled_task.minute,
            second=0,
            microsecond=0
        )
        
        # Calcular próximo día de la semana
        if scheduled_task.day_of_week:
            target_day = int(scheduled_task.day_of_week)
            current_day = now.weekday()
            days_ahead = target_day - current_day
            if days_ahead < 0:
                days_ahead += 7
            next_run += timedelta(days=days_ahead)
        else:
            next_run += timedelta(days=7)
        
        if next_run <= now:
            next_run += timedelta(weeks=1)
        
        return next_run
    
    else:
        return None


def schedule_task(config_id: int, frequency: str, hour: int = 0, minute: int = 0, 
                  day_of_week: str = '', user=None):
    """Crear nueva tarea programada"""
    
    from django_app.scrapers.models import ScraperConfig
    
    config = ScraperConfig.objects.get(id=config_id)
    
    scheduled_task = ScheduledTask.objects.create(
        config=config,
        frequency=frequency,
        hour=hour,
        minute=minute,
        day_of_week=day_of_week,
        created_by=user
    )
    
    # Calcular próxima ejecución
    scheduled_task.next_run = calculate_next_run(scheduled_task)
    scheduled_task.save()
    
    return scheduled_task