#!/usr/bin/env python3
"""
SCRIPT DE PRUEBA - Poder Judicial Scraper
Este script prueba el scraper de forma standalone antes de integrar con Django.
"""
import sys
import json
import os
from pathlib import Path

# Agregar backend al path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from scraping_core.web_scraper import create_scraper


def test_scraper():
    """Probar scraper con una causa de ejemplo"""
    print("=" * 70)
    print("🧪 PRUEBA DE SCRAPER - PODER JUDICIAL")
    print("=" * 70)
    
    # Configuración
    config_path = "backend/scraping_core/configs/poder_judicial.json"
    
    # Parámetros de búsqueda (CAUSA DE EJEMPLO - modificar según necesites)
    search_params = {
        'rol': 'C-21503-2024',  # ROL de la causa
        'tribune': '273',        # ID del tribunal
        'competencia': '3',      # 3 = Civil
        'corteId': '90'          # ID de la corte (90 = Corte Suprema)
    }
    
    print(f"\n📋 Configuración:")
    print(f"   - Config: {config_path}")
    print(f"   - ROL: {search_params['rol']}")
    print(f"   - Tribunal: {search_params['tribune']}")
    print(f"   - Competencia: {search_params['competencia']}")
    print(f"   - Corte: {search_params['corteId']}")
    print(f"   - Headless: False (visible para debug)")
    print("\n" + "=" * 70)
    
    scraper = None
    
    try:
        # 1. Crear instancia del scraper (inicializa Chrome)
        print("\n🚀 Inicializando navegador Chrome...")
        scraper = create_scraper(config_path, headless=False)
        
        # 2. Autenticar (modo invitado por defecto)
        print("\n🔐 Autenticando (modo invitado)...")
        if not scraper.authenticate():
            raise Exception("Error en autenticación")
        
        # 3. Ejecutar scraping
        print("\n🔍 Ejecutando búsqueda...")
        result = scraper.scrape(search_params)
        
        # 4. Validar resultados
        print("\n✅ Scraping completado!")
        print("\n" + "=" * 70)
        print("📊 RESULTADOS:")
        print("=" * 70)
        
        # Datos generales
        print("\n DATOS GENERALES:")
        for key, value in result.items():
            if key not in ['movementsHistory', 'litigants', 'documentLinks', 'extractedAt', 'source']:
                print(f"   {key}: {value}")
        
        # Litigantes
        if result.get('litigants'):
            print(f"\n👥 LITIGANTES ({len(result['litigants'])}):")
            for lit in result['litigants'][:5]:  # Mostrar primeros 5
                print(f"   - {lit.get('name', 'N/A')} ({lit.get('participant', 'N/A')})")
        
        # Movimientos
        if result.get('movementsHistory'):
            print(f"\n📜 MOVIMIENTOS ({len(result['movementsHistory'])}):")
            for mov in result['movementsHistory'][:5]:  # Mostrar primeros 5
                print(f"   - {mov.get('dateProcedure', 'N/A')}: {mov.get('descProcedure', 'N/A')}")
        
        # Enlaces
        if result.get('documentLinks'):
            print(f"\n🔗 ENLACES ({len(result['documentLinks'])}):")
            for link in result['documentLinks'][:5]:  # Mostrar primeros 5
                print(f"   - {link.get('text', 'N/A')} ({link.get('type', 'N/A')})")
        
        # Guardar resultado en JSON
        output_file = "test_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n💾 Resultados guardados en: {output_file}")
        
        print("\n" + "=" * 70)
        print("✅ PRUEBA EXITOSA")
        print("=" * 70)
        
        return True
        
    except Exception as e:
        print("\n" + "=" * 70)
        print(" ERROR EN LA PRUEBA")
        print("=" * 70)
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Limpiar recursos
        if scraper:
            print("\n📍 Cerrando navegador...")
            scraper.cleanup()


if __name__ == "__main__":
    success = test_scraper()
    sys.exit(0 if success else 1)
