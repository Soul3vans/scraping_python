"""Scraper para Poder Judicial - Oficina Judicial Virtual"""
import json
import random
import time
import os
from typing import Any, Dict, Optional, List
from datetime import datetime
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
    Traducción EXACTA de unified-query.js + puppeteer.plugin.js
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
        
        self.anti_bot = AntiBotSystem()
        self.proxy_rotator: Optional[ProxyRotator] = None
        
        self.max_memory_mb = self.config.get('resource_limits', {}).get('max_memory_mb', 512)
        self.timeout_seconds = self.config.get('resource_limits', {}).get('timeout_seconds', 60)
        
        # Configuración de espera para verificación/reCAPTCHA.
        # Se relajó bastante respecto a la versión anterior: resolver un
        # captcha a mano puede tomar varios minutos, y el sitio puede
        # encadenar varios saltos (home/initCU.php, loginN.php?noclaveu=1,
        # etc.) como parte de UN SOLO intento de verificación.
        self.recaptcha_timeout_seconds = self.config.get('resource_limits', {}).get(
            'recaptcha_timeout_seconds', 300  # 5 minutos por ciclo, no 120s
        )
        self.max_recaptcha_retries = self.config.get('resource_limits', {}).get(
            'max_recaptcha_retries', 5  # Reintentos de clic en "Consulta causas" tras volver a home
        )
        # Cuánto tiempo debe la URL permanecer estable en home/index.php
        # antes de asumir que PJUD realmente nos devolvió al inicio (y no
        # que es un salto transitorio dentro de la cadena de verificación).
        self.home_stable_seconds = self.config.get('resource_limits', {}).get(
            'home_stable_seconds', 3
        )
    
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
        """
        Acceso como invitado - Traducción EXACTA de puppeteer.plugin.js init()
        Flujo:
        1. Navegar a home/index.php
        2. Inyectar tokens
        3. Permanecer en home/index.php (NO navegar a indexN.php todavía)
        """
        try:
            logger.info("🌐 Navegando a home/index.php...")
            self.page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=60000)
            
            # Esperar 5 segundos como en JS
            logger.info("⏳ Esperando 5 segundos para carga completa...")
            time.sleep(5)
            
            # Inyectar tokens de sesión (OBLIGATORIO)
            logger.info("💉 Inyectando tokens de localStorage...")
            self._inject_guest_tokens()
            
            # Verificar que los tokens se establecieron
            tokens = self.page.evaluate("""
                () => ({
                    loggedIn: localStorage.getItem('logged-in'),
                    accesoInvitado: localStorage.getItem('acceso-invitado')
                })
            """)
            logger.info(f"✅ Tokens establecidos: {tokens}")
            
            # Esperar adicional
            time.sleep(5)
            
            logger.info("✅ Acceso como invitado completado")
            logger.info("📍 Permaneciendo en home/index.php - el scraper navegará cuando sea necesario")
            
            return True
            
        except Exception as e:
            logger.error(f"Error en login invitado: {e}")
            return False
    
    def _login_clave_unica(self, rut: str, password: str) -> bool:
        """Autenticación con Clave Única"""
        try:
            self.page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=60000)
            
            # Abrir modal de Clave Única
            self.page.evaluate("AutenticaCUnica()")
            time.sleep(4)
            
            # Esperar campos
            self.page.wait_for_selector('input#uname', timeout=30000)
            self.page.wait_for_selector('input[type="password"]', timeout=30000)
            
            # Verificar reCAPTCHA
            if self._has_recaptcha():
                logger.warning("🔐 reCAPTCHA detectado. Resuélvelo manualmente...")
                self._wait_for_recaptcha_resolution()
            
            # Escribir credenciales
            self.page.type('input#uname', rut, delay=random.uniform(100, 150))
            time.sleep(1)
            self.page.type('input[type="password"]', password, delay=random.uniform(100, 150))
            time.sleep(1.5)
            
            # Clic en login
            self.page.click('button#login-submit')
            self.page.wait_for_navigation(wait_until="domcontentloaded", timeout=60000)
            
            self.is_authenticated = True
            logger.info("✅ Autenticación completada exitosamente")
            
            return True
            
        except Exception as e:
            logger.error(f"Error en Clave Única: {e}")
            return False
    
    def scrape(self, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ejecutar scraping - Traducción EXACTA de unified-query.js factory()
        Flujo:
        1. Ir a página de búsqueda (goUnifiedQuery)
        2. Aplicar filtros
        3. Extraer anchors
        4. Extraer detalles
        """
        try:
            logger.info("🔍 Iniciando scraping...")
            
            # Navegar a indexN.php (máquina de estados)
            self._go_to_search_page()
            
            # Verificar tokens de reCAPTCHA
            self._ensure_recaptcha_tokens()
            
            # Aplicar filtros
            self._apply_search_filters(search_params)
            
            # Esperar resultados
            self.page.wait_for_selector('tbody#verDetalle', timeout=30000)
            
            if self._no_results():
                logger.warning("📭 No se encontraron resultados")
                return {'error': 'No results found', 'rol': search_params['rol']}
            
            # Extraer anchors
            anchors = self._extract_anchors()
            
            if not anchors:
                return {'error': 'No anchors found', 'rol': search_params['rol']}
            
            # Extraer detalles de la primera causa
            result = self._extract_cause_details(anchors[0])
            
            return result
            
        except Exception as e:
            logger.error(f"Error en scraping: {e}")
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
            logger.info("🔒 Cerrando navegador...")
            self.browser.close()
            self.browser = None
        
        if self.playwright:
            self.playwright.stop()
    
    def _init_browser(self):
        """Inicializar navegador con stealth"""
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
        
        # Aplicar stealth
        stealth = Stealth()
        stealth.apply_stealth_sync(self.page)
        
        self.page.set_extra_http_headers(self.anti_bot.get_random_headers())
        
        logger.info("✅ Navegador Chrome inicializado con stealth")
    
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
    
    # ========== MOTOR DE ESPERA RESILIENTE PARA VERIFICACIÓN/CAPTCHA ==========
    #
    # Un solo motor reutilizable para cualquier punto del flujo donde PJUD
    # pueda interponer una verificación (al entrar a "Consulta causas" Y
    # también al enviar la búsqueda). Reglas:
    #
    #   - Se reacciona en cada carga de página (polling fino, ~0.4s).
    #   - Cualquier URL que no sea el objetivo esperado NI home/index.php
    #     se clasifica como fase de verificación (incluye explícitamente
    #     home/initCU.php, loginN.php?noclaveu=1, o cualquier otra) y se
    #     espera PASIVAMENTE, sin navegar ni interactuar.
    #   - Un salto a home/index.php NO se toma como definitivo de inmediato:
    #     debe permanecer estable ahí por home_stable_seconds antes de
    #     asumir que el sitio realmente reinició el flujo. Esto evita
    #     interrumpir cadenas de redirección donde home/index.php aparece
    #     un instante entre varios saltos (p.ej. initCU.php -> home ->
    #     loginN.php) como parte de UNA sola verificación en curso.
    #   - Timeout largo y configurable (5 min por defecto), no rígido.

    def _classify_url(self, url: str) -> str:
        """Etiqueta la URL actual según el flujo conocido de PJUD (solo para logging)."""
        if 'initCU.php' in url or 'loginN.php' in url or 'noclaveu' in url:
            return 'VERIFICATION_PJUD'
        if 'indexN.php' in url:
            return 'INDEX'
        if 'home/index.php' in url:
            return 'HOME'
        return 'VERIFICATION_OTRA'

    def _wait_through_verification(self, success_check, timeout_seconds: int) -> str:
        """
        Espera pacientemente a que success_check() devuelva True,
        tolerando cualquier cantidad de saltos por páginas de
        verificación/captcha en el camino. Devuelve 'SUCCESS', 'HOME'
        (PJUD confirmó reinicio a home, hay que reintentar el clic que
        originó este flujo) o 'TIMEOUT'.
        """
        start = time.time()
        last_status_log = start
        last_url_logged = None
        home_since: Optional[float] = None

        while time.time() - start < timeout_seconds:
            try:
                if success_check():
                    return 'SUCCESS'
            except Exception:
                pass

            current_url = self._safe_url()
            category = self._classify_url(current_url)

            if category == 'HOME':
                if home_since is None:
                    home_since = time.time()
                elif time.time() - home_since >= self.home_stable_seconds:
                    logger.info(
                        f"↩️ URL estable en home/index.php por {self.home_stable_seconds}s: "
                        f"se asume reinicio real del flujo."
                    )
                    return 'HOME'
            else:
                home_since = None  # cualquier URL que no sea home reinicia el debounce

            if current_url != last_url_logged:
                if category == 'VERIFICATION_PJUD':
                    logger.info(f"🔐 Verificación/captcha PJUD detectada: {current_url}")
                elif category == 'VERIFICATION_OTRA':
                    logger.info(f"📄 Página intermedia no reconocida (tratada como verificación): {current_url}")
                elif category == 'HOME':
                    logger.info(f"📍 Paso transitorio por home/index.php (esperando estabilidad)...")
                else:
                    logger.info(f"📍 Página cargada: {current_url}")
                last_url_logged = current_url

            now = time.time()
            if now - last_status_log >= 15:
                elapsed = int(now - start)
                logger.info(
                    f"⏳ Esperando resolución... ({elapsed}s/{timeout_seconds}s) "
                    f"URL actual: {current_url[:90]}"
                )
                last_status_log = now

            time.sleep(0.4)

        return 'TIMEOUT'

    def _safe_url(self) -> str:
        try:
            return self.page.url
        except Exception:
            return "desconocida"

    def _click_consulta_causas_js(self):
        """
        Clic en 'Consulta causas' vía JS (page.evaluate), NO un click()
        accionable de Playwright. El botón vive en un menú desplegable
        visible solo con :hover, así que Playwright nunca lo considera
        'visible/accionable' y el click() real revienta por timeout. El
        evaluate replica el comportamiento del JS original y evita esto.
        """
        try:
            clicked = self.page.evaluate("""
                () => {
                    const btn = document.querySelector('button.dropbtn[onclick*="accesoConsultaCausas"]');
                    if (btn) { btn.click(); return true; }
                    const buttons = Array.from(document.querySelectorAll('button.dropbtn'));
                    const consultaBtn = buttons.find(b => b.textContent.includes('Consulta causas'));
                    if (consultaBtn) { consultaBtn.click(); return true; }
                    return false;
                }
            """)
            if not clicked:
                logger.warning("⚠️ No se encontró el botón 'Consulta causas' en el DOM")
        except Exception as e:
            logger.warning(f"⚠️ Error al clickear 'Consulta causas' vía JS: {e}")

    def _go_to_search_page(self):
        """
        Navega a indexN.php:
          1. Ya estamos en home/index.php (hecho en _login_invitado)
          2. Clic en "Consulta causas" (vía JS, ver _click_consulta_causas_js)
          3. Esperar pacientemente (_wait_through_verification), tolerando
             cualquier cadena de páginas de verificación
          4. Si termina en home/index.php de forma estable -> volver al
             paso 2. Si llega a indexN.php con formulario -> éxito.
        """
        logger.info("🧭 Navegando a página de búsqueda...")

        if 'indexN.php' in self.page.url and self._search_form_visible():
            logger.info("✅ Ya en indexN.php con formulario visible, limpiando...")
            self._clear_search_form()
            return

        def form_ready():
            return 'indexN.php' in self.page.url and self._search_form_visible()

        for cycle in range(1, self.max_recaptcha_retries + 1):
            if 'home/index.php' not in self.page.url:
                logger.info("↩️ Volviendo a home/index.php antes de clickear...")
                self.page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(1.5 + random.uniform(0, 1))
                self._inject_guest_tokens()
                time.sleep(1)

            self._close_warning_modals()

            logger.info(f"🖱️ [Ciclo {cycle}/{self.max_recaptcha_retries}] Clic en 'Consulta causas'...")
            self._click_consulta_causas_js()
            time.sleep(1 + random.uniform(0, 1))

            outcome = self._wait_through_verification(
                success_check=form_ready,
                timeout_seconds=self.recaptcha_timeout_seconds
            )

            if outcome == 'SUCCESS':
                logger.info("✅ Navegación completada, formulario de búsqueda listo")
                return

            if outcome == 'HOME':
                logger.info("↩️ PJUD reinició a home/index.php. Reintentando clic (paso 2)...")
                continue

            raise Exception(
                f"No se resolvió la verificación dentro de {self.recaptcha_timeout_seconds}s "
                f"(ciclo {cycle}/{self.max_recaptcha_retries}). URL actual: {self.page.url}"
            )

        raise Exception(
            f"No se logró llegar a indexN.php tras {self.max_recaptcha_retries} ciclos de reintento."
        )

    def _search_form_visible(self) -> bool:
        """Verificación rápida (no bloqueante) de si el formulario está presente"""
        try:
            return self.page.query_selector('select#competencia') is not None
        except Exception:
            return False
    
    def _close_warning_modals(self):
        """Cerrar modales de aviso"""
        try:
            modal_closed = self.page.evaluate("""
                () => {
                    const modal = document.querySelector('.modal.in') || document.querySelector('.modal.show');
                    if (!modal) return false;
                    
                    modal.classList.remove('in', 'show');
                    modal.style.display = 'none';
                    modal.setAttribute('aria-hidden', 'true');
                    document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
                    document.body.classList.remove('modal-open');
                    document.body.style.overflow = '';
                    
                    return true;
                }
            """)
            
            if modal_closed:
                logger.info("✅ Modal cerrado manualmente")
                time.sleep(0.5)
            else:
                logger.info("ℹ️ No se detectó modal de aviso")
                
        except Exception as e:
            logger.warning(f"⚠️ Error al cerrar modal: {e}")
    
    def _has_recaptcha(self) -> bool:
        """Detectar si hay reCAPTCHA"""
        try:
            content = self.page.content().lower()
            return any(x in content for x in ['recaptcha', 'captcha', 'verification', 'verifica'])
        except:
            return False
    
    def _wait_for_recaptcha_resolution(self, timeout_seconds: Optional[int] = None):
        """
        Espera genérica a que el reCAPTCHA visible desaparezca. Se usa en
        el flujo de Clave Única (_login_clave_unica), donde no hay ciclos
        de home/indexN — solo se espera a que el propio widget de
        verificación deje de estar presente en la página actual.

        La lógica específica de "si PJUD redirige a home mientras se
        resuelve, reintentar el clic en Consulta causas" vive en
        _wait_until_home_or_index(), usada por el flujo de invitado
        (_go_to_search_page), que es un caso distinto.
        """
        timeout_seconds = timeout_seconds or self.recaptcha_timeout_seconds
        start_time = time.time()
        last_log = start_time

        while time.time() - start_time < timeout_seconds:
            if not self._has_recaptcha():
                logger.info(f"✅ reCAPTCHA resuelto después de {int(time.time() - start_time)}s")
                time.sleep(1 + random.uniform(0, 1))
                return True

            now = time.time()
            if now - last_log >= 10:
                elapsed = int(now - start_time)
                logger.info(f"⏳ Esperando resolución de reCAPTCHA... ({elapsed}s/{timeout_seconds}s)")
                last_log = now

            time.sleep(1)

        raise Exception(
            f"reCAPTCHA no resuelto después de {timeout_seconds}s de espera "
            f"(flujo Clave Única)."
        )
    
    def _ensure_recaptcha_tokens(self):
        """Asegurar tokens de reCAPTCHA v3"""
        logger.info("🔐 Verificando tokens de reCAPTCHA v3...")
        
        for attempt in range(3):
            tokens = self.page.evaluate("""
                () => ({
                    rit: document.getElementById('g-recaptcha-response-rit')?.value || '',
                    nombre: document.getElementById('g-recaptcha-response-nombre')?.value || '',
                    fecha: document.getElementById('g-recaptcha-response-fecha')?.value || '',
                    jur: document.getElementById('g-recaptcha-response-jur')?.value || ''
                })
            """)
            
            if all(len(tokens.get(k, '')) > 10 for k in ['rit', 'nombre', 'fecha', 'jur']):
                logger.info("✅ Tokens de reCAPTCHA válidos")
                return True
            
            logger.warning(f"️ Intento {attempt + 1}: Tokens incompletos. Ejecutando callbacks...")
            
            self.page.evaluate("""
                () => {
                    if (typeof recaptchacallbackritv3 === 'function') recaptchacallbackritv3();
                    if (typeof recaptchacallbacknombrev3 === 'function') recaptchacallbacknombrev3();
                    if (typeof recaptchacallbackfechav3 === 'function') recaptchacallbackfechav3();
                    if (typeof recaptchacallbackjurv3 === 'function') recaptchacallbackjurv3();
                }
            """)
            
            time.sleep(3 + random.uniform(0, 2))
        
        logger.warning("⚠️ No se pudieron generar tokens óptimos, continuando...")
        return False
    
    def _clear_search_form(self):
        """Limpiar formulario con botón Limpiar"""
        try:
            self.page.click('#btnConLimpiar')
            time.sleep(1.5)
            logger.info("✅ Formulario limpiado")
        except Exception as e:
            logger.warning(f"⚠️ Error limpiando formulario: {e}")
    
    def _apply_search_filters(self, params: Dict[str, Any]):
        """Aplicar filtros de búsqueda"""
        logger.info(" Aplicando filtros...")
        
        competencia = params.get('competencia', '3')
        corte = params.get('corteId', '90')
        tribune = params.get('tribune')
        
        # Parsear ROL
        rol_parts = params['rol'].split('-')
        tipo = rol_parts[0]
        numero = rol_parts[1]
        year = rol_parts[2]
        
        logger.info(f"   Competencia: {competencia}, Corte: {corte}, Tribunal: {tribune}")
        logger.info(f"   ROL: {tipo}-{numero}-{year}")
        
        # Seleccionar competencia
        self.page.select_option('select#competencia', competencia)
        time.sleep(0.6 + random.uniform(0, 1))
        
        # Seleccionar corte
        self.page.select_option('select#conCorte', corte)
        time.sleep(0.6 + random.uniform(0, 1))
        
        # Seleccionar tribunal
        self.page.select_option('select#conTribunal', tribune)
        time.sleep(0.6 + random.uniform(0, 1))
        
        # Seleccionar tipo
        self.page.select_option('select#conTipoCausa', tipo)
        time.sleep(0.6 + random.uniform(0, 1))
        
        # Llenar rol y año
        self.page.fill('input#conRolCausa', numero)
        self.page.fill('input#conEraCausa', year)
        
        time.sleep(1)
        
        # Clic en buscar
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
        logger.info("📖 Extrayendo detalles...")
        
        self.page.evaluate(anchor_script)
        self.page.wait_for_selector('#modalDetalleCivil', timeout=10000, state='visible')
        time.sleep(1)
        
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
            time.sleep(1)
            return []
        except Exception as e:
            logger.error(f"Error extrayendo movimientos: {e}")
            return []
    
    def _extract_litigants(self) -> List[Dict]:
        """Extraer litigantes"""
        try:
            self.page.click('a[href="#litigantesCiv"]')
            time.sleep(1)
            
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
            time.sleep(1)
            logger.info("🔒 Modal cerrado")
        except Exception as e:
            logger.warning(f"Error cerrando modal: {e}")


def create_scraper(config_path: str, headless: bool = False) -> PoderJudicialScraper:
    """Crear instancia del scraper"""
    scraper = PoderJudicialScraper(config_path, headless=headless)
    scraper._init_browser()
    return scraper