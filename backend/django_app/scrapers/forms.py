"""Formularios para scrapers"""
from django import forms
from .models import ScraperConfig, ScheduledTask, ScraperTask
import json
import os


class ScraperConfigForm(forms.ModelForm):
    """Formulario para configuración de scraper"""
    
    class Meta:
        model = ScraperConfig
        fields = [
            'name', 'config_file', 'scraper_type', 'description',
            'requires_auth', 'uses_proxy', 'max_memory_mb', 'timeout_seconds'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del scraper'}),
            'config_file': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ejemplo_site.json'}),
            'scraper_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'requires_auth': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'uses_proxy': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'max_memory_mb': forms.NumberInput(attrs={'class': 'form-control'}),
            'timeout_seconds': forms.NumberInput(attrs={'class': 'form-control'})
        }


class SearchParamsForm(forms.Form):
    """Formulario dinámico para parámetros de búsqueda"""
    
    rol = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'C-21503-2024',
            'pattern': r'[A-Z]-\d+-\d{4}'
        }),
        label='ROL de la causa'
    )
    
    tribune = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '273'}),
        label='ID del Tribunal'
    )
    
    competencia = forms.ChoiceField(
        choices=[
            ('3', 'Civil'),
            ('1', 'Penal'),
            ('2', 'Laboral'),
            ('4', 'Familia'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Competencia',
        initial='3'
    )
    
    corteId = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '90', 'value': '90'}),
        label='ID de la Corte',
        initial='90'
    )


class ScheduleForm(forms.ModelForm):
    """Formulario para programar tareas"""
    
    class Meta:
        model = ScheduledTask
        fields = ['frequency', 'hour', 'minute', 'day_of_week', 'is_active']
        widgets = {
            'frequency': forms.Select(attrs={'class': 'form-control'}),
            'hour': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 23}),
            'minute': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 59}),
            'day_of_week': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '0-6 (0=Lunes, 6=Domingo) o dejar vacío'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
