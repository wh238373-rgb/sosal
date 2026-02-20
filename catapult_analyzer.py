import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import logging
import re
from datetime import datetime
from collections import defaultdict
import time
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CatapultAnalyzer:
    def __init__(self, headless=True, use_virtual_display=True):
        self.driver = None
        self.all_tokens = []
        self.pattern_frequency = defaultdict(int)
        self.base_url = "https://catapult.trade"
        self.headless = headless
        self.use_virtual_display = use_virtual_display
        self.display = None

    def init_virtual_display(self):
        """🖥️ Ініціалізує Virtual Display для VPS"""
        if not self.use_virtual_display:
            return True
            
        if os.name != 'posix':  # Тільки для Linux/Unix
            logger.info("ℹ️ Virtual Display не потрібен на цій системі")
            return True

        try:
            from pyvirtualdisplay import Display
            self.display = Display(visible=0, size=(1920, 1080))
            self.display.start()
            logger.info("✅ Virtual Display запущений (1920x1080)")
            return True
        except ImportError:
            logger.warning("⚠️ pyvirtualdisplay не встановлений, продовжую без нього")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Помилка Virtual Display: {e}")
            return True

    def init_driver(self):
        """🌐 Ініціалізує браузер з оптимізацією для VPS"""
        try:
            logger.info("🌐 Запускаю браузер...")

            options = uc.ChromeOptions()
            
            # 🔧 Базові параметри
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            
            # 🔧 Для VPS (headless mode)
            if self.headless:
                options.add_argument('--headless')
                options.add_argument('--disable-extensions')
                options.add_argument('--disable-plugins')
                options.add_argument('--disable-images')  # 📉 Швидше
                options.add_argument('--blink-settings=imagesEnabled=false')
                logger.info("   💡 Headless mode активований")
            else:
                options.add_argument('--start-maximized')

            # 🔧 Оптимізація для VPS
            options.add_argument('--disable-web-resources')
            options.add_argument('--disable-default-apps')
            options.add_argument('--disable-translate')
            
            # 🔧 User-Agent щоб уникнути блокування
            options.add_argument(
                'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )

            logger.info("   ⚙️ Запускаю Chrome...")
            self.driver = uc.Chrome(
                options=options,
                version_main=None,
                use_subprocess=False  # 🔧 Краще для VPS
            )
            
            # 🔧 Timeout для завантаження сторінок
            self.driver.set_page_load_timeout(30)
            
            logger.info("✅ Браузер запущений успішно")
            return True

        except Exception as e:
            logger.error(f"❌ Помилка браузера: {e}")
            return False

    def fetch_page(self):
        """📍 Завантажує сторінку з обробкою помилок"""
        try:
            logger.info("📍 Завантажаю catapult.trade/turbo/home...")

            self.driver.get(f"{self.base_url}/turbo/home?sort=deployed_at_desc")
            logger.info("   ⏳ Сторінка завантажена, чекаю контенту...")

            wait = WebDriverWait(self.driver, 20)  # 🔄 Збільшив до 20 сек
            
            try:
                wait.until(
                    EC.presence_of_all_elements_located(
                        (By.XPATH, "//a[contains(@href, '/turbo/tokens/')]")
                    )
                )
                logger.info("   ✅ Токени загрузились")
            except:
                logger.warning("   ⚠️ Чекання скінчилось, але намагаюсь далі...")
                # Чекаємо ще 5 сек для JS рендеру
                time.sleep(5)

            # 🔧 Скроллинг для завантаження більше токенів
            logger.info("   📜 Скроллю для завантаження додаткових токенів...")
            
            for i in range(4):  # 🔄 4 замість 5
                try:
                    self.driver.execute_script("window.scrollBy(0, 300)")
                    time.sleep(0.8)  # 🔄 Менше часу чекання
                except:
                    break

            logger.info("✅ Сторінка завантажена")
            return self.driver.page_source

        except Exception as e:
            logger.error(f"❌ Помилка завантаження: {e}")
            return None

    def extract_tokens(self, html: str):
        """🔍 Витягує токени з перевіркою якості"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            tokens_found = []
            links = soup.find_all('a', href=re.compile(r'/turbo/tokens/\d+'))

            logger.info(f"📊 Знайдено {len(links)} посилань на токени")

            seen_urls = set()

            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)

                if href and href not in seen_urls:
                    if re.search(r'/turbo/tokens/\d+', href):
                        seen_urls.add(href)

                        full_url = href if href.startswith('http') else f"{self.base_url}{href}"
                        
                        # 🔧 Безпечне видобування ID
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
                logger.debug(f"   HTML розмір: {len(html)} символів")

            return tokens_found[:30]  # Перші 30

        except Exception as e:
            logger.error(f"❌ Помилка парсингу: {e}")
            return []

    def analyze_token(self, token_url: str, token_id: str):
        """🔬 Аналізує окремий токен"""
        token_data = {
            'url': token_url,
            'token_id': token_id,
            'name': '',
            'patterns': []
        }

        try:
            logger.info(f"   🔗 Аналізую Token #{token_id}")

            self.driver.get(token_url)
            time.sleep(2)  # 🔄 Було 3, тепер 2

            html = self.driver.page_source

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            
            # 📝 Витягуємо назву
            title = soup.find('h1') or soup.find('title')
            if title:
                token_data['name'] = title.get_text(strip=True)[:50]

            # 🔍 ПАТТЕРНИ

            # ⏰ NEW
            if re.search(r'\bnew\b|\brecent\b|\blaunch\b', html, re.I):
                token_data['patterns'].append('⏰NEW')
                self.pattern_frequency['⏰NEW'] += 1

            # 🚀 PUMP
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

            # 📈 VOLUME
            if re.search(r'24h|volume|trading', html, re.I):
                token_data['patterns'].append('📈VOLUME')
                self.pattern_frequency['📈VOLUME'] += 1

            # 🔒 LOCK
            if re.search(r'lock|locked|freeze|frozen', html, re.I):
                token_data['patterns'].append('🔒LOCK')
                self.pattern_frequency['🔒LOCK'] += 1

            # 📱 SOCIAL
            if re.search(r'telegram|twitter|discord|instagram', html, re.I):
                token_data['patterns'].append('📱SOCIAL')
                self.pattern_frequency['📱SOCIAL'] += 1

            # 👥 HOLDERS
            holders_match = re.search(r'(\d+(?:,\d+)*)\s+holders?', html, re.I)
            if holders_match:
                token_data['patterns'].append('👥HOLDERS')
                self.pattern_frequency['👥HOLDERS'] += 1

            # 🚨 RUG
            if re.search(r'\brug\b|\bscam\b|\bhoneypot\b|\bdanger\b|\brisk\b', html, re.I):
                token_data['patterns'].append('🚨RUG')
                self.pattern_frequency['🚨RUG'] += 1

            # 📉 DIP
            if re.search(r'\bdown\b|\bdip\b|\bcrash\b|\b-\d+%', html, re.I):
                token_data['patterns'].append('📉DIP')
                self.pattern_frequency['📉DIP'] += 1

            # 💰 MCAP
            if re.search(r'market\s+cap|mcap|m\$', html, re.I):
                token_data['patterns'].append('💰MCAP')
                self.pattern_frequency['💰MCAP'] += 1

            # 💎 HIGH_PRICE
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

            # ✅ Логування результатів
            if token_data['patterns']:
                logger.info(f"      ✅ {', '.join(token_data['patterns'][:3])}")
            else:
                logger.debug(f"      ℹ️ Паттернів не знайдено")

        except Exception as e:
            logger.debug(f"      ⚠️ Помилка: {str(e)[:50]}")

        return token_data

    async def scan(self):
        """🔄 Основне сканування"""
        logger.info("\n" + "=" * 70)
        logger.info(f"🔄 СКАНУВАННЯ CATAPULT - {datetime.now().strftime('%H:%M:%S')}")
        logger.info(f"   Режим: {'VPS (Headless)' if self.headless else 'Desktop'}")
        logger.info("=" * 70)

        # 1️⃣ Virtual Display
        if not self.init_virtual_display():
            logger.error("❌ Не вдалося ініціалізувати Virtual Display")

        # 2️⃣ Браузер
        if not self.init_driver():
            return self._empty_report()

        try:
            # 3️⃣ Завантаження ст��рінки
            html = self.fetch_page()
            if not html:
                return self._empty_report()

            # 4️⃣ Витягнення токенів
            tokens = self.extract_tokens(html)
            if not tokens:
                logger.warning("⚠️ Реальних токенів не знайдено")
                return self._empty_report()

            # 5️⃣ Аналіз токенів
            logger.info(f"📊 Аналізую {min(len(tokens), 12)} токенів...")
            
            for idx, token in enumerate(tokens[:12], 1):  # 🔄 12 замість 15
                logger.info(f"   [{idx}/{min(len(tokens), 12)}]")
                token_data = self.analyze_token(token['url'], token['token_id'])
                if token_data['patterns']:
                    self.all_tokens.append(token_data)
                time.sleep(0.5)  # 🔄 Менше часу чекання

            # 6️⃣ Генерація звіту
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
            logger.info(f"✅ Знайдено паттернів: {report['total_patterns_found']}")
            logger.info(f"📊 Проаналізовано токенів: {report['total_tokens']}")
            logger.info("=" * 70 + "\n")

            return report

        except Exception as e:
            logger.error(f"❌ Помилка під час сканування: {e}")
            return self._empty_report()

        finally:
            # 🔌 Закриття
            self._cleanup()

    def _empty_report(self):
        """Порожній звіт при помилці"""
        return {
            'timestamp': datetime.now().isoformat(),
            'total_tokens': 0,
            'total_patterns_found': 0,
            'top_patterns': [],
            'tokens': []
        }

    def _cleanup(self):
        """🔌 Очищення ресурсів"""
        try:
            if self.driver:
                self.driver.quit()
                logger.info("🔌 Браузер закритий")
        except:
            pass

        try:
            if self.display:
                self.display.stop()
                logger.info("🔌 Virtual Display зупинений")
        except:
            pass


async def scan_catapult(headless=True, use_virtual_display=True):
    """📡 Публічна функція для запуску"""
    analyzer = CatapultAnalyzer(headless=headless, use_virtual_display=use_virtual_display)
    return await analyzer.scan()
