"""Vistas para gestión de scrapers"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.conf import settings
from .models import ScraperConfig, ScraperTask, ScheduledTask, ScrapedData, ScraperLog
from .forms import ScraperConfigForm, SearchParamsForm, ScheduleForm
from ..tasks.scraper_tasks import queue_scraper_task, cancel_scraper_task
import json
from datetime import datetime
import os


@login_required
def dashboard(request):
    """Dashboard principal"""
    # Estadísticas
    total_configs = ScraperConfig.objects.count()
    active_configs = ScraperConfig.objects.filter(status='active').count()
    total_tasks = ScraperTask.objects.count()
    completed_tasks = ScraperTask.objects.filter(status='completed').count()
    failed_tasks = ScraperTask.objects.filter(status='failed').count()
    pending_tasks = ScraperTask.objects.filter(status='pending').count()
    
    # Tareas recientes
    recent_tasks = ScraperTask.objects.select_related('config').order_by('-created_at')[:10]
    
    # Scrapers disponibles
    configs = ScraperConfig.objects.filter(status='active')
    
    context = {
        'total_configs': total_configs,
        'active_configs': active_configs,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'failed_tasks': failed_tasks,
        'pending_tasks': pending_tasks,
        'recent_tasks': recent_tasks,
        'configs': configs,
        'resource_limits': {
            'max_cpu_cores': settings.MAX_CPU_CORES,
            'max_ram_mb': settings.MAX_RAM_MB
        }
    }
    
    return render(request, 'scrapers/dashboard.html', context)


@login_required
def config_list(request):
    """Lista de configuraciones de scrapers"""
    configs = ScraperConfig.objects.all().order_by('-created_at')
    
    # Filtros
    status_filter = request.GET.get('status')
    if status_filter:
        configs = configs.filter(status=status_filter)
    
    # Paginación
    paginator = Paginator(configs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'configs': page_obj,
        'status_filter': status_filter
    }
    
    return render(request, 'scrapers/config_list.html', context)


@login_required
def config_create(request):
    """Crear nueva configuración de scraper"""
    if request.method == 'POST':
        form = ScraperConfigForm(request.POST)
        if form.is_valid():
            config = form.save(commit=False)
            config.created_by = request.user
            config.save()
            messages.success(request, f'Configuración "{config.name}" creada exitosamente')
            return redirect('scrapers:config_detail', pk=config.pk)
    else:
        form = ScraperConfigForm()
    
    return render(request, 'scrapers/config_form.html', {'form': form, 'action': 'create'})


@login_required
def config_detail(request, pk):
    """Detalle de configuración"""
    config = get_object_or_404(ScraperConfig, pk=pk)
    tasks = ScraperTask.objects.filter(config=config).order_by('-created_at')[:20]
    
    # Cargar datos del archivo JSON si existe
    config_data = config.get_config_data()
    
    context = {
        'config': config,
        'tasks': tasks,
        'config_data': config_data
    }
    
    return render(request, 'scrapers/config_detail.html', context)


@login_required
def scraper_execute(request, config_id):
    """Ejecutar scraper manualmente"""
    config = get_object_or_404(ScraperConfig, pk=config_id)
    
    if request.method == 'POST':
        # Obtener parámetros de búsqueda del formulario
        form = SearchParamsForm(request.POST)
        if form.is_valid():
            # Crear tarea
            task = ScraperTask.objects.create(
                config=config,
                trigger_type='manual',
                created_by=request.user
            )
            
            # Encolar tarea en RQ
            try:
                job_id = queue_scraper_task(task.id)
                task.rq_job_id = job_id
                task.save()
                
                messages.success(
                    request, 
                    f'Tarea de scraping encolada exitosamente. ID: {task.id}'
                )
                return redirect('scrapers:task_detail', pk=task.pk)
            except Exception as e:
                task.status = 'failed'
                task.save()
                messages.error(request, f'Error al encolar tarea: {str(e)}')
        else:
            messages.error(request, 'Parámetros de búsqueda inválidos')
    
    else:
        form = SearchParamsForm()
    
    context = {
        'config': config,
        'form': form
    }
    
    return render(request, 'scrapers/execute_scraper.html', context)


@login_required
def task_list(request):
    """Lista de tareas"""
    tasks = ScraperTask.objects.select_related('config').order_by('-created_at')
    
    # Filtros
    status_filter = request.GET.get('status')
    config_filter = request.GET.get('config')
    
    if status_filter:
        tasks = tasks.filter(status=status_filter)
    if config_filter:
        tasks = tasks.filter(config_id=config_filter)
    
    # Paginación
    paginator = Paginator(tasks, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    configs = ScraperConfig.objects.all()
    
    context = {
        'page_obj': page_obj,
        'tasks': page_obj,
        'configs': configs,
        'status_filter': status_filter,
        'config_filter': config_filter
    }
    
    return render(request, 'scrapers/task_list.html', context)


@login_required
def task_detail(request, pk):
    """Detalle de tarea"""
    task = get_object_or_404(ScraperTask, pk=pk)
    logs = ScraperLog.objects.filter(task=task).order_by('created_at')
    data = ScrapedData.objects.filter(task=task)
    
    context = {
        'task': task,
        'logs': logs,
        'data': data
    }
    
    return render(request, 'scrapers/task_detail.html', context)


@login_required
def task_cancel(request, pk):
    """Cancelar tarea"""
    task = get_object_or_404(ScraperTask, pk=pk)
    
    if task.status in ['pending', 'running']:
        try:
            cancel_scraper_task(task.id)
            messages.success(request, f'Tarea {task.id} cancelada exitosamente')
        except Exception as e:
            messages.error(request, f'Error al cancelar tarea: {str(e)}')
    else:
        messages.warning(request, 'La tarea no puede ser cancelada en su estado actual')
    
    return redirect('scrapers:task_detail', pk=pk)


@login_required
def schedule_create(request, config_id):
    """Crear tarea programada"""
    config = get_object_or_404(ScraperConfig, pk=config_id)
    
    if request.method == 'POST':
        form = ScheduleForm(request.POST)
        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.config = config
            schedule.created_by = request.user
            schedule.save()
            
            messages.success(request, 'Tarea programada creada exitosamente')
            return redirect('scrapers:config_detail', pk=config_id)
    else:
        form = ScheduleForm()
    
    context = {
        'config': config,
        'form': form
    }
    
    return render(request, 'scrapers/schedule_form.html', context)


@login_required
def data_list(request):
    """Lista de datos extraídos"""
    data = ScrapedData.objects.select_related('config', 'task').order_by('-scraped_at')
    
    # Filtros
    config_filter = request.GET.get('config')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if config_filter:
        data = data.filter(config_id=config_filter)
    if date_from:
        data = data.filter(scraped_at__date__gte=date_from)
    if date_to:
        data = data.filter(scraped_at__date__lte=date_to)
    
    # Paginación
    paginator = Paginator(data, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    configs = ScraperConfig.objects.all()
    
    context = {
        'page_obj': page_obj,
        'data': page_obj,
        'configs': configs,
        'config_filter': config_filter,
        'date_from': date_from,
        'date_to': date_to
    }
    
    return render(request, 'scrapers/data_list.html', context)


@login_required
def data_detail(request, pk):
    """Detalle de dato extraído"""
    data_item = get_object_or_404(ScrapedData, pk=pk)
    
    context = {
        'data_item': data_item
    }
    
    return render(request, 'scrapers/data_detail.html', context)


@login_required
def data_export(request, pk):
    """Exportar dato a JSON"""
    data_item = get_object_or_404(ScrapedData, pk=pk)
    
    response = HttpResponse(
        json.dumps(data_item.data, indent=2, default=str),
        content_type='application/json'
    )
    response['Content-Disposition'] = f'attachment; filename="scraped_data_{pk}.json"'
    
    return response


@login_required
@require_http_methods(["GET", "POST"])
def ajax_search_params(request):
    """Endpoint AJAX para obtener parámetros de búsqueda dinámicos"""
    if request.method == 'POST':
        config_id = request.POST.get('config_id')
        config = get_object_or_404(ScraperConfig, pk=config_id)
        
        # Obtener configuración del archivo JSON
        config_data = config.get_config_data()
        
        # Retornar parámetros requeridos
        search_params = config_data.get('search_params', {})
        
        return JsonResponse({
            'success': True,
            'params': search_params,
            'example': search_params.get('example', {})
        })
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})


@login_required
def system_status(request):
    """Estado del sistema"""
    import psutil
    
    # Uso de recursos
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # Estado de colas RQ
    import django_rq
    queue = django_rq.get_queue('default')
    
    context = {
        'cpu_percent': cpu_percent,
        'memory_percent': memory.percent,
        'memory_available_mb': memory.available / 1024 / 1024,
        'disk_percent': (disk.used / disk.total) * 100,
        'queue_jobs_count': queue.count,
        'max_cpu_cores': settings.MAX_CPU_CORES,
        'max_ram_mb': settings.MAX_RAM_MB
    }
    
    return render(request, 'scrapers/system_status.html', context)
