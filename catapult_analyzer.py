import asyncio
import logging
import re
from datetime import datetime
from collections import defaultdict
import time
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CatapultAnalyzer:
    def __init__(self):
        self.all_tokens = []
        self.pattern_frequency = defaultdict(int)
        self.base_url = "https://catapult.trade"

    async def fetch_page(self):
        """Завантажує сторінку з Playwright (обходить Cloudflare)"""
        try:
            logger.info("📍 Завантажаю catapult.trade...")
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                    ]
                )
                
                page = await browser.new_page(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                
                logger.info("⏳ Завантажаю сторінку (з очіканням JS)...")
                await page.goto(f"{self.base_url}/turbo/home?sort=deployed_at_desc", wait_until='networkidle')
                
                logger.info("⏳ Чекаю 15 сек для повного рендеру...")
                await asyncio.sleep(15)
                
                # Скроллимо
                logger.info("📜 Скроллю токени...")
                for i in range(8):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1.5)
                
                html = await page.content()
                await browser.close()
                
                logger.info(f"✅ HTML завантажений ({len(html)} байт)")
                return html
                
        except Exception as e:
            logger.error(f"❌ Помилка завантаження: {e}")
            return None

    def extract_tokens(self, html: str):
        """Витягує токени"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            tokens_found = []
            
            # Перевіримо чи Cloudflare не блокує
            if "Just a moment" in html or "Cloudflare" in html:
                logger.warning("⚠️ CLOUDFLARE - спробую все одно...")
            
            # Шукаємо токени
            links = soup.find_all('a', href=re.compile(r'/turbo/tokens/'))
            logger.info(f"📊 Знайдено {len(links)} токенів")
            
            seen_urls = set()
            for link in links:
                href = link.get('href', '')
                if href and href not in seen_urls and '/turbo/tokens/' in href:
                    seen_urls.add(href)
                    full_url = href if href.startswith('http') else f"{self.base_url}{href}"
                    token_id_match = re.search(r'/tokens/(\d+)', href)
                    token_id = token_id_match.group(1) if token_id_match else 'unknown'
                    token_name = link.get_text(strip=True) or f"Token {token_id}"
                    
                    tokens_found.append({
                        'url': full_url,
                        'name': token_name,
                        'token_id': token_id
                    })

            logger.info(f"✅ Витягнуто {len(tokens_found)} токенів")
            return tokens_found[:20]

        except Exception as e:
            logger.error(f"❌ Помилка парсингу: {e}")
            return []

    async def analyze_token(self, token_url: str, token_id: str):
        """Аналізує окремий токен"""
        token_data = {
            'url': token_url,
            'token_id': token_id,
            'name': '',
            'patterns': []
        }

        try:
            logger.info(f"   🔗 Token #{token_id}")
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
                page = await browser.new_page()
                await page.goto(token_url, wait_until='load')
                await asyncio.sleep(2)
                
                html = await page.content()
                await browser.close()

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

        html = await self.fetch_page()

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
            logger.warning("⚠️ Токенів не знайдено")
            return {
                'timestamp': datetime.now().isoformat(),
                'total_tokens': 0,
                'total_patterns_found': 0,
                'top_patterns': [],
                'tokens': []
            }

        logger.info(f"📊 Аналізую {len(tokens)} токенів...")

        for token in tokens:
            token_data = await self.analyze_token(token['url'], token['token_id'])
            if token_data['patterns']:
                self.all_tokens.append(token_data)
            await asyncio.sleep(0.5)

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


async def scan_catapult():
    """Публічна функція"""
    analyzer = CatapultAnalyzer()
    return await analyzer.scan()
