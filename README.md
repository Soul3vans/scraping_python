# Sistema de Scraping Modular

Sistema de scraping con Python y Django, diseñado para ser modular, seguro y eficiente en recursos.

## Características

- Scraping de sitios web HTML y APIs
- Sistema de configuración por archivo para cada sitio
- Rotación de proxies y IPs
- Defensas anti-bot
- Colas de tareas con RQ
- Base de datos PostgreSQL
- Interfaz web con Django
- Contenedor Podman para despliegue
- Validación de datos y calidad de código con Ruff

## Requisitos

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Podman (opcional)

## Instalación

1. Clonar repositorio
2. Crear entorno virtual: `python -m venv venv`
3. Activar entorno: `source venv/bin/activate`
4. Instalar dependencias: `pip install -r backend/requirements.txt`
5. Configurar `.env`
6. Migrar base de datos: `python backend/manage.py migrate`
7. Crear superusuario: `python backend/manage.py createsuperuser`
8. Ejecutar: `python backend/manage.py runserver`

## Uso con Podman

```bash
podman-compose up -d