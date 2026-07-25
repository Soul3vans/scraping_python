"""Tareas RQ para ejecución de scrapers"""
import django_rq
from django.utils import timezone
from django.conf import settings
from django_app.scrapers.models import ScraperTask, ScrapedData, ScraperLog
from scraping_core.web_scraper import WebScraper
from scraping_core.api_scraper import APIScraper
import logging
import traceback


logger = logging.getLogger(__name__)


@django_rq.job('default', timeout=3600)
def execute_scraper_task(task_id: int):
    """Ejecutar tarea de scraper de forma asíncrona"""
    
    try:
        # Obtener tarea
        task = ScraperTask.objects.get(id=task_id)
        task.status = 'running'
        task.started_at = timezone.now()
        task.save()
        
        # Log de inicio
        ScraperLog.objects.create(
            task=task,
            level='INFO',
            message=f'Iniciando ejecución de {task.config.name}'
        )
        
        # Cargar configuración
        config_data = task.config.get_config_data()
        if 'error' in config_data:
            raise Exception(f"Error cargando configuración: {config_data['error']}")
        
        # Instanciar scraper según tipo
        config_path = f"scraping_core/configs/{task.config.config_file}"
        
        if task.config.scraper_type == 'web':
            scraper = WebScraper(config_path=config_path)
        elif task.config.scraper_type == 'api':
            scraper = APIScraper(config_path=config_path)
        else:
            raise Exception(f"Tipo de scraper no soportado: {task.config.scraper_type}")
        
        # Autenticar si es necesario
        if task.config.requires_auth:
            ScraperLog.objects.create(
                task=task,
                level='INFO',
                message='Autenticando...'
            )
            if not scraper.authenticate():
                raise Exception("Error en autenticación")
        
        # Ejecutar scraping
        ScraperLog.objects.create(
            task=task,
            level='INFO',
            message='Ejecutando scraping...'
        )
        
        scraped_data = scraper.scrape()
        
        # Validar datos
        if not scraper.validate_data(scraped_data):
            raise Exception("Datos extraídos no pasan validación")
        
        # Guardar datos en base de datos
        items_count = 0
        if isinstance(scraped_data, list):
            for item in scraped_data:
                ScrapedData.objects.create(
                    task=task,
                    config=task.config,
                    url=item.get('url', task.config.get_config_data().get('url', '')),
                    data=item
                )
                items_count += 1
        else:
            ScrapedData.objects.create(
                task=task,
                config=task.config,
                url=config_data.get('url', ''),
                data=scraped_data
            )
            items_count = 1
        
        # Actualizar tarea
        task.status = 'completed'
        task.completed_at = timezone.now()
        task.items_scraped = items_count
        task.save()
        
        # Log de éxito
        ScraperLog.objects.create(
            task=task,
            level='INFO',
            message=f'Scraping completado exitosamente. {items_count} elementos extraídos.'
        )
        
        # Limpiar recursos
        scraper.cleanup()
        
        return {'success': True, 'items': items_count}
        
    except Exception as e:
        # Manejo de errores
        error_msg = f"Error en tarea {task_id}: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        
        try:
            task = ScraperTask.objects.get(id=task_id)
            task.status = 'failed'
            task.completed_at = timezone.now()
            task.errors_count += 1
            task.save()
            
            ScraperLog.objects.create(
                task=task,
                level='ERROR',
                message=error_msg
            )
        except:
            pass
        
        return {'success': False, 'error': str(e)}


def queue_scraper_task(task_id: int):
    """Encolar tarea de scraper en RQ"""
    queue = django_rq.get_queue('default')
    job = queue.enqueue(execute_scraper_task, task_id)
    
    # Guardar job_id en la tarea
    task = ScraperTask.objects.get(id=task_id)
    task.rq_job_id = job.id
    task.save()
    
    return job.id


def cancel_scraper_task(task_id: int):
    """Cancelar tarea de scraper"""
    try:
        task = ScraperTask.objects.get(id=task_id)
        
        if task.rq_job_id:
            queue = django_rq.get_queue('default')
            job = queue.fetch_job(task.rq_job_id)
            if job:
                job.cancel()
        
        task.status = 'cancelled'
        task.completed_at = timezone.now()
        task.save()
        
        ScraperLog.objects.create(
            task=task,
            level='WARNING',
            message='Tarea cancelada por el usuario'
        )
        
        return True
    except Exception as e:
        logger.error(f"Error cancelando tarea {task_id}: {str(e)}")
        return False
