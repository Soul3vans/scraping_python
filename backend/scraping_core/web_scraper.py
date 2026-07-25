"""Scraper para Poder Judicial - Oficina Judicial Virtual"""
import json
import random
import time
import os
from typing import Any, Dict, Optional, List
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from playwright_stealth import Stealth
from .base_scraper import BaseScraper
from .anti_bot import AntiBotSystem
from .proxy_rotator import ProxyRotator
import logging

logger = logging.getLogger(__name__)


class PoderJudicialScraper(BaseScraper):
    """
    Scraper especializado para oficinajudicialvirtual.pjud.cl
    """
    
    BASE_URL = "https://oficinajudicialvirtual.pjud.cl"
    HOME_URL = f"{BASE_URL}/home/index.php"
    INDEX_URL = f"{BASE_URL}/indexN.php"
    
    def __init__(self, config_path: str, headless: bool = False, **kwargs):
        super().__init__(config_path, logger)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.headless = headless
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_authenticated = False
        self.is_processing = False
        
        self.anti_bot = AntiBotSystem()
        self.proxy_rotator: Optional[ProxyRotator] = None
        
        self.max_memory_mb = self.config.get('resource_limits', {}).get('max_memory_mb', 512)
        self.timeout_seconds = self.config.get('resource_limits', {}).get('timeout_seconds', 60)
    
    def _get_chrome_path(self) -> str:
        """Obtener ruta del ejecutable de Chrome"""
        import subprocess
        
        try:
            result = subprocess.run(['which', 'google-chrome'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except:
            pass
        
        chrome_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium"
        ]
        
        for path in chrome_paths:
            if os.path.exists(path):
                return path
        
        return "/usr/bin/google-chrome"
    
    def authenticate(self, rut: Optional[str] = None, password: Optional[str] = None) -> bool:
        """Autenticación"""
        try:
            if rut and password:
                logger.info("🔐 Iniciando autenticación con Clave Única...")
                return self._login_clave_unica(rut, password)
            else:
                logger.info("🔓 Accediendo como invitado...")
                return self._login_invitado()
        except Exception as e:
            logger.error(f"❌ Error en autenticación: {e}")
            return False
    
    def _login_invitado(self) -> bool:
        """Acceso como invitado (Traducción exacta de puppeteer.plugin.js)"""
        try:
            logger.info("🌐 Cargando home/index.php para generar sesión base...")
            self.page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=60000)
            self._human_delay(4000, 6000)
            
            # 1. Inyectar tokens de sesión (OBLIGATORIO según el JS original)
            self._inject_guest_tokens()
            self._human_delay(2000)
            
            # 2. Ejecutar Priming Sequence (Clic en Clave Única y volver)
            self._priming_sequence()
            
            logger.info("✅ Acceso como invitado completado y tokens activos")
            return True
        except Exception as e:
            logger.error(f"Error en login invitado: {e}")
            return False
    
    def scrape(self, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecutar scraping"""
        try:
            self.is_processing = True
            
            # Navegar a indexN.php si no estamos ahí
            current_url = self.page.url  # ✅ CORREGIDO: sin paréntesis
            if not current_url.endswith('indexN.php'):
                self._navigate_to_search_page()
            
            self.page.wait_for_selector('select#competencia', timeout=30000)
            
            self._ensure_recaptcha_tokens()
            self._apply_search_filters(search_params)
            
            self.page.wait_for_selector('tbody#verDetalle', timeout=30000)
            
            if self._no_results():
                logger.warning("📭 No se encontraron resultados")
                return {'error': 'No results found', 'rol': search_params['rol']}
            
            anchors = self._extract_anchors()
            
            if not anchors:
                return {'error': 'No anchors found', 'rol': search_params['rol']}
            
            result = self._extract_cause_details(anchors[0])
            
            self.is_processing = False
            
            return result
            
        except Exception as e:
            logger.error(f"Error en scraping: {e}")
            self.is_processing = False
            raise
    
    def validate_data(self, data: Dict[str, Any]) -> bool:
        """Validar datos extraídos"""
        required_fields = ['rol', 'admission', 'process', 'court']
        
        for field in required_fields:
            if field not in data or not data[field]:
                logger.warning(f"Campo requerido faltante: {field}")
                return False
        
        logger.info("✅ Datos validados correctamente")
        return True
    
    def cleanup(self):
        """Limpiar recursos"""
        if self.browser:
            logger.info(" Cerrando navegador...")
            self.browser.close()
            self.browser = None
        
        if self.playwright:
            self.playwright.stop()
    
    def _init_browser(self):
        """Inicializar navegador con stealth usando Chrome"""
        self.playwright = sync_playwright().start()
        
        chrome_path = self._get_chrome_path()
        logger.info(f"🔧 Usando Chrome en: {chrome_path}")
        
        launch_args = {
            'headless': self.headless,
            'executable_path': chrome_path,
            'args': [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=BlockInsecurePrivateNetworkRequests',
                '--disable-sync',
                '--mute-audio',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-extensions',
                '--window-size=1920,1080'
            ]
        }
        
        self.browser = self.playwright.chromium.launch(**launch_args)
        
        self.context = self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent=self.anti_bot.get_random_headers()['User-Agent']
        )
        
        self.page = self.context.new_page()
        
        # ✅ CORREGIDO: Aplicar stealth correctamente
        # En lugar de: stealth_sync(page)
        stealth = Stealth()
        stealth.apply_stealth_sync(self.page)
        
        self.page.set_extra_http_headers(self.anti_bot.get_random_headers())
        
        logger.info(" Navegador Chrome inicializado con stealth")
    
    def _inject_guest_tokens(self):
        """Inyectar tokens de sesión de invitado"""
        self.page.evaluate("""
            localStorage.setItem('InitSitioOld', '0');
            localStorage.setItem('InitSitioNew', '1');
            localStorage.setItem('logged-in', 'true');
            sessionStorage.setItem('logged-in', 'true');
            localStorage.setItem('acceso-invitado', 'true');
            sessionStorage.setItem('acceso-invitado', 'true');
        """)
        logger.info("✅ Tokens de invitado inyectados")
    
    def _priming_sequence(self):
        """Workaround para desbloquear botones"""
        logger.info("🔑 Ejecutando priming sequence...")
        
        self.page.evaluate("""
            const link = document.querySelector('a[onclick*="AutenticaCUnica"]');
            if (link) link.click();
        """)
        
        self._human_delay(3000)
        
        self.page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=60000)
        self._human_delay(2000)
        
        self._inject_guest_tokens()
        
        logger.info("✅ Priming completado")
    
    def _navigate_to_search_page(self):
        """Navegar a indexN.php (Traducción exacta de goUnifiedQuery en unified-query.js)"""
        logger.info("🧭 Navegando a página de búsqueda (Flujo Unificado)...")
        
        current_url = self.page.url
        
        # 1. Si estamos en indexN.php pero sin formulario, limpiar o volver al home
        if 'indexN.php' in current_url:
            if self._verify_search_fields():
                logger.info("🧹 Formulario ya disponible, limpiando...")
                try: self.page.click('#btnConLimpiar', timeout=3000)
                except: pass
                return
            else:
                logger.warning("⚠️ indexN.php sin formulario. Volviendo a home...")
                self.page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=60000)
                self._human_delay(3000)

        # 2. Asegurar que estamos en home/index.php
        if 'home/index.php' not in self.page.url:
            self.page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=60000)
            self._human_delay(3000)
            self._inject_guest_tokens()

        # 3. Cerrar modales (Traducción exacta del JS)
        self._close_warning_modals()
        self._human_delay(1500)

        # 4. Hacer clic en "Consulta de Causas"
        logger.info("🖱️ Clickeando 'Consulta de Causas'...")
        try:
            # Usar el selector exacto del JS original
            self.page.evaluate("""
                () => {
                    const btn = document.querySelector('button.dropbtn[onclick*="accesoConsultaCausas"]');
                    if (btn) {
                        btn.click();
                    } else {
                        const buttons = Array.from(document.querySelectorAll('button.dropbtn'));
                        const consultaBtn = buttons.find(b => b.textContent.includes('Consulta causas'));
                        if (consultaBtn) consultaBtn.click();
                    }
                }
            """)
        except Exception as e:
            logger.warning(f"⚠️ Error haciendo clic: {e}")

        # 5. Esperar la redirección a indexN.php
        logger.info("⏳ Esperando redirección a indexN.php...")
        try:
            self.page.wait_for_url("**/indexN.php*", timeout=20000)
        except Exception:
            logger.warning("⚠️ Timeout esperando indexN.php. URL actual: " + self.page.url)
            # Fallback: navegar directo si el clic no funcionó
            self.page.goto(self.INDEX_URL, wait_until="domcontentloaded", timeout=30000)

        self._human_delay(2000)
        
        # 6. Validar que llegamos
        if 'indexN.php' not in self.page.url:
            raise Exception(f"No se pudo navegar a indexN.php. URL final: {self.page.url}")

        # 7. Manejo de reCAPTCHA (Si el sitio lo muestra)
        if self._has_recaptcha():
            logger.warning("🔐 reCAPTCHA detectado. Resuélvelo en el navegador visible...")
            self._wait_for_recaptcha_resolution(timeout_seconds=300)
            
        # 8. Esperar a que el formulario esté listo
        logger.info("⏳ Esperando selector select#competencia...")
        self.page.wait_for_selector('select#competencia', timeout=30000, state='visible')
        logger.info("✅ En página de búsqueda (indexN.php) listo para scrapear")
    
    def _close_warning_modals(self):
        """Cerrar modales de aviso de forma agresiva"""
        try:
            # Intentar clicar "Aceptar" o "Cerrar" si existe el botón
            self.page.locator('button:has-text("Aceptar"), button:has-text("Cerrar"), .close').first.click(timeout=3000, force=True)
        except:
            pass
        
        # Fallback: forzar ocultamiento por JS si el botón no funciona
        try:
            self.page.evaluate("""
                const modals = document.querySelectorAll('.modal');
                modals.forEach(m => {
                    m.classList.remove('in', 'show');
                    m.style.display = 'none';
                });
                document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
            """)
        except:
            pass
    
    def _has_recaptcha(self) -> bool:
        """Detectar si hay reCAPTCHA real (buscando el iframe de Google)"""
        try:
            # Contar si existe el iframe de Google reCAPTCHA en la página
            count = self.page.locator('iframe[src*="google.com/recaptcha"]').count()
            return count > 0
        except Exception:
            return False
        
    def _verify_search_fields(self) -> bool:
        """Verificar que los campos de búsqueda están disponibles en indexN.php"""
        try:
            # Verificar los selectores principales del formulario de búsqueda
            selectors_to_check = [
                'select#competencia',
                'select#conCorte',
                'select#conTribunal',
                'input#conRolCausa'
            ]
            
            for selector in selectors_to_check:
                try:
                    self.page.wait_for_selector(selector, timeout=3000)
                except:
                    logger.warning(f"⚠️ Campo no encontrado: {selector}")
                    return False
            
            logger.info("✅ Todos los campos de búsqueda están presentes")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error verificando campos: {e}")
            return False
    
    def _wait_for_recaptcha_resolution(self, timeout_seconds: int = 600):
        """Esperar a que el usuario resuelva el reCAPTCHA con detección inteligente"""
        logger.info(f"⏳ Esperando resolución de reCAPTCHA (máximo {timeout_seconds}s)...")
        logger.info("=" * 70)
        logger.info("📋 INSTRUCCIONES:")
        logger.info("   1. Ve al navegador VISIBLE")
        logger.info("   2. Resuelve el reCAPTCHA haciendo clic en 'No soy un robot'")
        logger.info("   3. Espera a que la página cargue completamente")
        logger.info("   4. El scraper detectará automáticamente cuando los campos aparezcan")
        logger.info("=" * 70)
        
        start_time = time.time()
        last_status_time = start_time
        
        while time.time() - start_time < timeout_seconds:
            # Verificar si los campos de búsqueda aparecieron (reCAPTCHA resuelto)
            try:
                # Intentar encontrar el select de competencia (indicador de éxito)
                self.page.wait_for_selector('select#competencia', timeout=3000)
                logger.info("✅ ¡reCAPTCHA resuelto! Campos de búsqueda detectados")
                self._human_delay(2000)  # Esperar un poco más para que todo cargue
                return  # ¡ÉXITO!
            except:
                pass  # Los campos aún no están, continuar esperando
            
            # Mostrar estado cada 10 segundos
            current_time = time.time()
            if current_time - last_status_time >= 10:
                elapsed = int(current_time - start_time)
                logger.info(f"⏳ Aún esperando... ({elapsed}s) - URL: {self.page.url[:80]}...")
                last_status_time = current_time
            
            self._human_delay(1000, 2000)
        
        # Timeout alcanzado
        raise Exception(f"⏱️ Timeout esperando reCAPTCHA ({timeout_seconds}s). No se detectaron campos de búsqueda.")
    
    def _ensure_recaptcha_tokens(self):
        """Asegurar que los tokens de reCAPTCHA estén presentes (Traducción de refreshRecaptchaTokens)"""
        logger.info("🔐 Verificando y generando tokens de reCAPTCHA v3...")
        
        for attempt in range(3):
            # 1. Obtener tokens actuales
            tokens = self.page.evaluate("""
                () => {
                    return {
                        rit: document.getElementById('g-recaptcha-response-rit')?.value || '',
                        nombre: document.getElementById('g-recaptcha-response-nombre')?.value || '',
                        fecha: document.getElementById('g-recaptcha-response-fecha')?.value || '',
                        jur: document.getElementById('g-recaptcha-response-jur')?.value || ''
                    };
                }
            """)
            
            # 2. Verificar si ya son válidos
            if all(len(tokens.get(k, '')) > 10 for k in ['rit', 'nombre', 'fecha', 'jur']):
                logger.info("✅ Tokens de reCAPTCHA válidos y presentes")
                return True
            
            # 3. Si no lo son, ¡EJECUTAR LOS CALLBACKS MANUALMENTE (El secreto del JS)!
            logger.warning(f"⚠️ Intento {attempt + 1}: Tokens incompletos. Ejecutando callbacks de reCAPTCHA v3...")
            self.page.evaluate("""
                () => {
                    if (typeof recaptchacallbackritv3 === 'function') recaptchacallbackritv3();
                    if (typeof recaptchacallbacknombrev3 === 'function') recaptchacallbacknombrev3();
                    if (typeof recaptchacallbackfechav3 === 'function') recaptchacallbackfechav3();
                    if (typeof recaptchacallbackjurv3 === 'function') recaptchacallbackjurv3();
                }
            """)
            
            # 4. Esperar a que Google genere los tokens
            self._human_delay(3000, 5000)
            
        logger.warning("⚠️ No se pudieron generar tokens óptimos, pero continuando...")
        return False
    
    def _apply_search_filters(self, params: Dict[str, Any]):
        """Aplicar filtros de búsqueda"""
        logger.info("🔍 Aplicando filtros de búsqueda...")
        
        self.page.select_option('select#competencia', params.get('competencia', '3'))
        self._human_delay(1000)
        
        self.page.select_option('select#conCorte', str(params.get('corteId', '90')))
        self._human_delay(1000)
        
        self.page.select_option('select#conTribunal', str(params.get('tribune')))
        self._human_delay(1000)
        
        rol_parts = params['rol'].split('-')
        tipo = rol_parts[0]
        numero = rol_parts[1]
        year = rol_parts[2]
        
        self.page.select_option('select#conTipoCausa', tipo)
        self._human_delay(1000)
        
        self.page.fill('input#conRolCausa', numero)
        self.page.fill('input#conEraCausa', year)
        
        self._human_delay(1000)
        
        self.page.click('button#btnConConsulta')
        
        logger.info("✅ Filtros aplicados")
    
    def _no_results(self) -> bool:
        """Verificar si no hay resultados"""
        try:
            content = self.page.inner_text('tbody#verDetalle')
            return 'No se han encontrado resultados' in content
        except:
            return False
    
    def _extract_anchors(self) -> List[str]:
        """Extraer scripts onclick"""
        anchors = self.page.evaluate("""
            Array.from(document.querySelectorAll("tbody#verDetalle > tr"))
                .map(row => row.querySelector('a[href="#modalDetalleCivil"]')?.getAttribute("onclick"))
                .filter(onclick => onclick)
        """)
        
        logger.info(f"📋 Encontrados {len(anchors)} resultados")
        return anchors
    
    def _extract_cause_details(self, anchor_script: str) -> Dict[str, Any]:
        """Extraer detalles de la causa"""
        logger.info("📖 Extrayendo detalles de la causa...")
        
        self.page.evaluate(anchor_script)
        
        self.page.wait_for_selector('#modalDetalleCivil', timeout=10000, state='visible')
        self._human_delay(1000)
        
        cause_data = self.page.evaluate("""
            () => {
                const cells = Array.from(document.querySelectorAll(
                    "div.modal-body > div.with-nav-tabs > div.panel-default > table:nth-child(1) td"
                )).map(td => td.textContent?.trim() || "");
                
                return {
                    rol: cells[0]?.replace("ROL:", "").trim(),
                    admission: cells[1]?.replace("F. Ing.:", "").trim(),
                    cover: cells[2]?.trim(),
                    estAdmin: cells[3]?.replace("Est. Adm.:", "").trim(),
                    process: cells[4]?.replace("Proc.:", "").trim(),
                    location: cells[5]?.replace("Ubicación:", "").trim(),
                    processState: cells[6]?.replace("Estado Proc.:", "").trim(),
                    stage: cells[7]?.replace("Etapa:", "").trim(),
                    court: cells[8]?.replace("Tribunal:", "").trim()
                };
            }
        """)
        
        movements = self._extract_movements()
        litigants = self._extract_litigants()
        document_links = self._extract_document_links()
        
        self._close_modal()
        
        return {
            **cause_data,
            'movementsHistory': movements,
            'litigants': litigants,
            'documentLinks': document_links,
            'extractedAt': datetime.now().isoformat(),
            'source': 'poder-judicial-scraper'
        }
    
    def _extract_movements(self) -> List[Dict]:
        """Extraer movimientos"""
        try:
            self.page.click('a[href="#loadHistCuadernoCiv"]')
            self._human_delay(1000)
            return []
        except Exception as e:
            logger.error(f"Error extrayendo movimientos: {e}")
            return []
    
    def _extract_litigants(self) -> List[Dict]:
        """Extraer litigantes"""
        try:
            self.page.click('a[href="#litigantesCiv"]')
            self._human_delay(1000)
            
            litigants = self.page.evaluate("""
                () => {
                    const rows = Array.from(document.querySelectorAll(
                        "div#litigantesCiv table > tbody > tr"
                    ));
                    
                    return rows.map(row => {
                        const cells = Array.from(row.querySelectorAll("td"));
                        return {
                            participant: cells[0]?.textContent?.trim(),
                            rut: cells[1]?.textContent?.trim(),
                            person: cells[2]?.textContent?.trim(),
                            name: cells[3]?.textContent?.trim()
                        };
                    });
                }
            """)
            
            logger.info(f"👥 Extraídos {len(litigants)} litigantes")
            return litigants
            
        except Exception as e:
            logger.error(f"Error extrayendo litigantes: {e}")
            return []
    
    def _extract_document_links(self) -> List[Dict]:
        """Extraer enlaces"""
        try:
            links = self.page.evaluate("""
                () => {
                    const modal = document.querySelector("#modalDetalleCivil");
                    if (!modal) return [];
                    
                    const anchors = modal.querySelectorAll(`
                        a[onclick*="anexo"], 
                        a[onclick*="detalle"],
                        a[onclick*="geoReferencia"]
                    `);
                    
                    return Array.from(anchors).map((a, idx) => ({
                        id: idx,
                        onclick: a.getAttribute('onclick'),
                        title: a.getAttribute('title'),
                        text: a.textContent?.trim()
                    }));
                }
            """)
            
            logger.info(f"🔗 Extraídos {len(links)} enlaces")
            return links
            
        except Exception as e:
            logger.error(f"Error extrayendo enlaces: {e}")
            return []
    
    def _close_modal(self):
        """Cerrar modal"""
        try:
            self.page.evaluate("""
                const closeBtn = document.querySelector('#modalDetalleCivil .close');
                if (closeBtn) closeBtn.click();
            """)
            self._human_delay(1000)
            logger.info("🔒 Modal cerrado")
        except Exception as e:
            logger.warning(f"Error cerrando modal: {e}")
    
    def _human_delay(self, min_ms: int = 600, max_ms: int = 2000):
        """Delay aleatorio"""
        delay = random.uniform(min_ms, max_ms) / 1000
        time.sleep(delay)


def create_scraper(config_path: str, headless: bool = False) -> PoderJudicialScraper:
    """Crear instancia del scraper"""
    scraper = PoderJudicialScraper(config_path, headless=headless)
    scraper._init_browser()
    return scraper
