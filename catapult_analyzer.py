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
    def __init__(self, headless=True):
        self.driver = None
        self.all_tokens = []
        self.pattern_frequency = defaultdict(int)
        self.base_url = "https://catapult.trade"
        self.headless = headless

    def init_driver(self):
        """Ініціалізує браузер для VPS"""
        try:
            logger.info("🌐 Запускаю браузер...")

            options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-blink-features=AutomationControlled')
            
            if self.headless:
                options.add_argument('--headless')
                options.add_argument('--disable-extensions')
                options.add_argument('--disable-plugins')
                options.add_argument('--disable-images')
                logger.info("   💡 Headless режим активований")
            else:
                options.add_argument('--start-maximized')

            options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

            self.driver = uc.Chrome(options=options, version_main=None, use_subprocess=False)
            self.driver.set_page_load_timeout(40)
            
            logger.info("✅ Браузер запущений")
            return True

        except Exception as e:
            logger.error(f"❌ Помилка браузера: {e}")
            return False

    def fetch_page(self):
        """Завантажує сторінку та чекає на елементи"""
        try:
            logger.info("📍 Завантажаю catapult.trade/turbo/home...")

            self.driver.get(f"{self.base_url}/turbo/home?sort=deployed_at_desc")

            logger.info("⏳ Чекаю завантаження контенту...")

            wait = WebDriverWait(self.driver, 30)
            try:
                wait.until(
                    EC.presence_of_all_elements_located(
                        (By.XPATH, "//a[contains(@href, '/turbo/tokens/')]")
                    )
                )
                logger.info("✅ Контент завантажився")
            except:
                logger.warning("⚠️ Timeout, продовжую...")
                time.sleep(5)

            logger.info("📜 Скроллю для завантаження додаткових токенів...")
            for i in range(6):
                self.driver.execute_script("window.scrollBy(0, 400)")
                time.sleep(1)

            logger.info("✅ Сторінка завантажена")
            return self.driver.page_source

        except Exception as e:
            logger.error(f"❌ Помилка завантаження: {e}")
            return None

    def extract_tokens(self, html: str):
        """Витягує реальні токени з ID"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            tokens_found = []
            links = soup.find_all('a', href=re.compile(r'/turbo/tokens/\d+'))

            logger.info(f"📊 Знайдено {len(links)} реальних токенів")

            seen_urls = set()

            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)

                if href and href not in seen_urls:
                    if re.search(r'/turbo/tokens/\d+', href):
                        seen_urls.add(href)

                        full_url = href if href.startswith('http') else f"{self.base_url}{href}"
                        token_id_match = re.search(r'/tokens/(\d+)', href)
                        token_id = token_id_match.group(1) if token_id_match else 'unknown'
                        token_name = text if text else f"Token {token_id}"

                        tokens_found.append({
                            'url': full_url,
                            'name': token_name,
                            'token_id': token_id
                        })

            if tokens_found:
                logger.info(f"✅ Витягнуто {len(tokens_found)} реальних токенів")
            else:
                logger.warning("⚠️ Реальних токенів не знайдено")

            return tokens_found[:20]

        except Exception as e:
            logger.error(f"❌ Помилка парсингу: {e}")
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
            time.sleep(2)

            html = self.driver.page_source

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            title = soup.find('h1') or soup.find('title')
            if title:
                token_data['name'] = title.get_text(strip=True)[:50]

            # Паттерни
            if re.search(r'\bnew\b|\brecent\b|\blaunch\b', html, re.I):
                token_data['patterns'].append('⏰NEW')
                self.pattern_frequency['⏰NEW'] += 1

            pump_match = re.search(r'\+(\d+(?:\.\d+)?)\s*%', html)
            if pump_match:
                change = float(pump_match.group(1))
                if change >= 50:
                    token_data['patterns'].append('🚀MEGA_PUMP')
                    self.pattern_frequency['🚀MEGA_PUMP'] += 1
                elif change >= 20:
                    token_data['patterns'].append('🚀PUMP')
                    self.pattern_frequency['🚀PUMP'] += 1
                else:
                    token_data['patterns'].append('⬆️UP')
                    self.pattern_frequency['⬆️UP'] += 1

            if re.search(r'24h|volume|trading', html, re.I):
                token_data['patterns'].append('📈VOLUME')
                self.pattern_frequency['📈VOLUME'] += 1

            if re.search(r'lock|locked|freeze|frozen', html, re.I):
                token_data['patterns'].append('🔒LOCK')
                self.pattern_frequency['🔒LOCK'] += 1

            if re.search(r'telegram|twitter|discord|instagram', html, re.I):
                token_data['patterns'].append('📱SOCIAL')
                self.pattern_frequency['📱SOCIAL'] += 1

            holders_match = re.search(r'(\d+(?:,\d+)*)\s+holders?', html, re.I)
            if holders_match:
                token_data['patterns'].append('👥HOLDERS')
                self.pattern_frequency['👥HOLDERS'] += 1

            if re.search(r'\brug\b|\bscam\b|\bhoneypot\b|\bdanger\b|\brisk\b', html, re.I):
                token_data['patterns'].append('🚨RUG')
                self.pattern_frequency['🚨RUG'] += 1

            if re.search(r'\bdown\b|\bdip\b|\bcrash\b|\b-\d+%', html, re.I):
                token_data['patterns'].append('📉DIP')
                self.pattern_frequency['📉DIP'] += 1

            if re.search(r'market\s+cap|mcap|market cap', html, re.I):
                token_data['patterns'].append('💰MCAP')
                self.pattern_frequency['💰MCAP'] += 1

            price_match = re.search(r'\$(\d+(?:,\d+)*(?:\.\d+)?)', html)
            if price_match:
                try:
                    price_str = price_match.group(1).replace(',', '')
                    price = float(price_str)
                    if price > 1:
                        token_data['patterns'].append('💎HIGH_PRICE')
                        self.pattern_frequency['💎HIGH_PRICE'] += 1
                except:
                    pass

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
                logger.error("❌ Не вдалося завантажити")
                return {
                    'timestamp': datetime.now().isoformat(),
                    'total_tokens': 0,
                    'total_patterns_found': 0,
                    'top_patterns': [],
                    'tokens': []
                }

            tokens = self.extract_tokens(html)

            if not tokens:
                logger.warning("⚠️ Реальних токенів не знайдено")
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
                time.sleep(0.5)

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


async def scan_catapult():
    """Публічна функція"""
    analyzer = CatapultAnalyzer(headless=True)
    return await analyzer.scan()
