import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
import re
from datetime import datetime
from collections import defaultdict
import time
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CatapultAnalyzer:
    def __init__(self, headless=False):  # 🔧 ЗМІНИВ НА False!
        self.driver = None
        self.all_tokens = []
        self.pattern_frequency = defaultdict(int)
        self.base_url = "https://catapult.trade"
        self.headless = headless
        self.display = None

    def init_virtual_display(self):
        """Запускає Virtual Display для VPS"""
        if not self.headless or os.name != 'posix':
            return True
        
        try:
            from pyvirtualdisplay import Display
            self.display = Display(visible=0, size=(1920, 1080))
            self.display.start()
            logger.info("✅ Virtual Display запущений")
            return True
        except:
            logger.warning("⚠️ Virtual Display не доступний")
            return True

    def init_driver(self):
        """Ініціалізує браузер БЕЗ headless для JS рендеру"""
        try:
            logger.info("🌐 Запускаю браузер...")

            options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-blink-features=AutomationControlled')
            
            # 🔧 БЕЗ --headless!
            if self.headless:
                options.add_argument('--virtual-display-size=1920x1080')
                logger.info("   💡 Virtual режим")
            
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-plugins')
            options.add_argument('--disable-background-networking')
            options.add_argument('--disable-breakpad')
            options.add_argument('--disable-client-side-phishing-detection')
            options.add_argument('--disable-default-apps')
            options.add_argument('--disable-hang-monitor')
            options.add_argument('--disable-popup-blocking')
            options.add_argument('--disable-prompt-on-repost')
            options.add_argument('--disable-sync')
            
            options.add_argument('user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

            self.driver = uc.Chrome(options=options, version_main=None, use_subprocess=False)
            self.driver.set_page_load_timeout(50)
            
            logger.info("✅ Браузер запущений")
            return True

        except Exception as e:
            logger.error(f"❌ Помилка браузера: {e}")
            return False

    def fetch_page(self):
        """Завантажує сторінку та чекає на JS рендер"""
        try:
            logger.info("📍 Завантажаю catapult.trade...")

            self.driver.get(f"{self.base_url}/turbo/home?sort=deployed_at_desc")

            logger.info("⏳ Чекаю JS рендер (20 сек)...")
            time.sleep(20)  # 🔧 ДОВШЕ ЧЕКАЄМО!

            # Чекаємо елементи
            wait = WebDriverWait(self.driver, 25)
            try:
                wait.until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "a[href*='/turbo/tokens/']")
                    )
                )
                logger.info("✅ Елементи знайдені")
            except:
                logger.warning("⚠️ XPath timeout, але продовжую...")

            # Агресивний скроллинг
            logger.info("📜 Скроллю токени...")
            for i in range(10):  # 🔧 БІЛЬШЕ СКРОЛЛІВ!
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)

            # Чекаємо ще
            time.sleep(5)

            logger.info("✅ Готово для парсингу")
            return self.driver.page_source

        except Exception as e:
            logger.error(f"❌ Помилка завантаження: {e}")
            return None

    def extract_tokens(self, html: str):
        """Витягує токени - спробуємо ВСІ методи"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            tokens_found = []
            
            # Метод 1: CSS селектор
            logger.info("   🔍 Метод 1: CSS селектор...")
            links = soup.find_all('a', href=re.compile(r'/turbo/tokens/'))
            logger.info(f"      → Знайдено: {len(links)}")
            
            # Метод 2: Просто фільтр
            if len(links) == 0:
                logger.info("   🔍 Метод 2: Прямий фільтр...")
                all_a = soup.find_all('a')
                links = [a for a in all_a if a.get('href') and '/turbo/tokens/' in a.get('href', '')]
                logger.info(f"      → Знайдено: {len(links)}")

            # Метод 3: По data атрибутам
            if len(links) == 0:
                logger.info("   🔍 Метод 3: Data атрибути...")
                links = soup.select('a[href*="turbo/tokens"]')
                logger.info(f"      → Знайдено: {len(links)}")

            logger.info(f"📊 ИТОГО: {len(links)} посилань на токени")

            seen_urls = set()
            for link in links:
                href = link.get('href', '')
                if not href or href in seen_urls:
                    continue
                    
                if '/turbo/tokens/' not in href:
                    continue

                seen_urls.add(href)

                full_url = href if href.startswith('http') else f"{self.base_url}{href}"
                
                # Витягуємо ID
                token_id_match = re.search(r'/tokens/(\d+)', href)
                token_id = token_id_match.group(1) if token_id_match else 'unknown'
                token_name = link.get_text(strip=True) or f"Token {token_id}"

                tokens_found.append({
                    'url': full_url,
                    'name': token_name,
                    'token_id': token_id
                })

            if tokens_found:
                logger.info(f"✅ Витягнуто {len(tokens_found)} токенів")
            else:
                logger.warning("⚠️ ТОКЕНІВ НЕ ЗНАЙДЕНО!")
                logger.warning(f"   HTML розмір: {len(html)} символів")
                
                # Дебаг
                if "Cloudflare" in html:
                    logger.warning("   ⚠️ CLOUDFLARE ВИЯВЛЕНА!")
                
                all_links = soup.find_all('a', limit=30)
                logger.warning(f"   Всього <a> тегів: {len(all_links)}")
                if all_links:
                    logger.warning("   Перші 5 href:")
                    for i, l in enumerate(all_links[:5]):
                        logger.warning(f"      {i+1}. {l.get('href')}")

            return tokens_found[:25]

        except Exception as e:
            logger.error(f"❌ Помилка парсингу: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def analyze_token(self, token_url: str, token_id: str):
        """Аналізує окремий токен"""
        token_data = {
            'url': token_url,
            'token_id': token_id,
            'name': '',
            'patterns': []
        }

        try:
            logger.info(f"   🔗 Token #{token_id}")

            self.driver.get(token_url)
            time.sleep(3)

            html = self.driver.page_source

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            title = soup.find('h1') or soup.find('title')
            if title:
                token_data['name'] = title.get_text(strip=True)[:50]

            # Паттерни
            patterns = [
                ('⏰NEW', r'\bnew\b|\brecent\b|\blaunch\b'),
                ('📈VOLUME', r'24h|volume|trading'),
                ('🔒LOCK', r'lock|locked|freeze|frozen'),
                ('📱SOCIAL', r'telegram|twitter|discord|instagram'),
                ('👥HOLDERS', r'(\d+(?:,\d+)*)\s+holders?'),
                ('🚨RUG', r'\brug\b|\bscam\b|\bhoneypot\b'),
                ('📉DIP', r'\bdown\b|\bdip\b|\bcrash\b'),
                ('💰MCAP', r'market\s+cap|mcap'),
            ]

            for pattern_name, pattern_regex in patterns:
                if re.search(pattern_regex, html, re.I):
                    token_data['patterns'].append(pattern_name)
                    self.pattern_frequency[pattern_name] += 1

            pump_match = re.search(r'\+(\d+(?:\.\d+)?)\s*%', html)
            if pump_match:
                change = float(pump_match.group(1))
                if change >= 50:
                    token_data['patterns'].append('🚀MEGA_PUMP')
                    self.pattern_frequency['🚀MEGA_PUMP'] += 1
                elif change >= 20:
                    token_data['patterns'].append('🚀PUMP')
                    self.pattern_frequency['🚀PUMP'] += 1

            if token_data['patterns']:
                logger.info(f"      ✅ {', '.join(token_data['patterns'][:3])}")

        except Exception as e:
            logger.debug(f"      ⚠️ {str(e)[:50]}")

        return token_data

    async def scan(self):
        """Основне сканування"""
        logger.info("\n" + "=" * 70)
        logger.info(f"🔄 СКАНУВАННЯ CATAPULT - {datetime.now().strftime('%H:%M:%S')}")
        logger.info("=" * 70)

        # Virtual Display
        if not self.init_virtual_display():
            logger.error("❌ Virtual Display помилка")

        if not self.init_driver():
            return {
                'timestamp': datetime.now().isoformat(),
                'total_tokens': 0,
                'total_patterns_found': 0,
                'top_patterns': [],
                'tokens': []
            }

        try:
            html = self.fetch_page()

            if not html:
                logger.error("❌ HTML пуст")
                return {
                    'timestamp': datetime.now().isoformat(),
                    'total_tokens': 0,
                    'total_patterns_found': 0,
                    'top_patterns': [],
                    'tokens': []
                }

            tokens = self.extract_tokens(html)

            if not tokens:
                logger.warning("⚠️ Токенів не знайдено - повертаю пустий звіт")
                return {
                    'timestamp': datetime.now().isoformat(),
                    'total_tokens': 0,
                    'total_patterns_found': 0,
                    'top_patterns': [],
                    'tokens': []
                }

            logger.info(f"📊 Аналізую {len(tokens)} токенів...")

            for token in tokens:
                token_data = self.analyze_token(token['url'], token['token_id'])
                if token_data['patterns']:
                    self.all_tokens.append(token_data)
                time.sleep(1)

            top_patterns = sorted(
                self.pattern_frequency.items(),
                key=lambda x: x[1],
                reverse=True
            )

            report = {
                'timestamp': datetime.now().isoformat(),
                'total_tokens': len(self.all_tokens),
                'total_patterns_found': sum(self.pattern_frequency.values()),
                'top_patterns': top_patterns,
                'tokens': self.all_tokens
            }

            logger.info("\n" + "=" * 70)
            logger.info(f"✅ Паттернів: {report['total_patterns_found']}")
            logger.info(f"📊 Токенів: {report['total_tokens']}")
            logger.info("=" * 70 + "\n")

            return report

        finally:
            if self.driver:
                self.driver.quit()
                logger.info("🔌 Браузер закритий")
            
            if self.display:
                self.display.stop()
                logger.info("🔌 Virtual Display закритий")


async def scan_catapult():
    """Публічна функція"""
    analyzer = CatapultAnalyzer(headless=False)  # 🔧 False!
    return await analyzer.scan()
