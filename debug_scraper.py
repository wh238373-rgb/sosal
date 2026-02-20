import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_scraper():
    """Дебаг версія скрейпера"""
    logger.info("🔧 ДЕБАГ: Запускаю браузер...")
    
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--headless')
    options.add_argument('--disable-images')
    
    driver = uc.Chrome(options=options, version_main=None, use_subprocess=False)
    
    try:
        logger.info("📍 Завантажаю сторінку...")
        driver.get("https://catapult.trade/turbo/home?sort=deployed_at_desc")
        
        logger.info("⏳ Чекаю 10 сек для JS рендеру...")
        time.sleep(10)
        
        # 📝 Зберігаємо HTML для аналізу
        html = driver.page_source
        
        with open('debug_page.html', 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"💾 HTML збережений у debug_page.html ({len(html)} символів)")
        
        # 🔍 Шукаємо токени
        logger.info("🔍 Шукаю токени на сторінці...")
        
        # Метод 1: XPath
        try:
            links = driver.find_elements(By.XPATH, "//a[contains(@href, '/turbo/tokens/')]")
            logger.info(f"✅ XPath метод: Знайдено {len(links)} токенів")
        except:
            logger.warning("❌ XPath не знайшов нічого")
        
        # Метод 2: CSS селектор
        try:
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/turbo/tokens/']")
            logger.info(f"✅ CSS метод: Знайдено {len(links)} токенів")
        except:
            logger.warning("❌ CSS не знайшов нічого")
        
        # Метод 3: Всі посилання
        all_links = driver.find_elements(By.TAG_NAME, "a")
        logger.info(f"📊 Всього посилань на сторінці: {len(all_links)}")
        logger.info("   Перші 15 посилань:")
        for i, link in enumerate(all_links[:15]):
            href = link.get_attribute('href')
            text = link.text
            logger.info(f"      {i+1}. href='{href}' text='{text}'")
        
        # Метод 4: BeautifulSoup аналіз
        logger.info("\n🔍 BeautifulSoup аналіз...")
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
        
        # Шукаємо всі посилання з /turbo/tokens/
        import re
        token_links = soup.find_all('a', href=re.compile(r'/turbo/tokens/\d+'))
        logger.info(f"✅ BeautifulSoup: Знайдено {len(token_links)} токенів")
        
        if token_links:
            logger.info("   Перші 5 токенів:")
            for i, link in enumerate(token_links[:5]):
                logger.info(f"      {i+1}. {link.get('href')} - {link.text}")
        
        # Метод 5: Перевіримо чи сайт блокує
        logger.info("\n🛡️ Перевіряю наявність Cloudflare/блокування...")
        if "Cloudflare" in html or "Just a moment" in html:
            logger.warning("⚠️ CLOUDFLARE ВИЯВЛЕНА!")
        else:
            logger.info("✅ Cloudflare не виявлена")
        
        # Метод 6: Дивимось на <title>
        title = soup.find('title')
        logger.info(f"📄 Title: {title.text if title else 'Не знайден'}")
        
        # Метод 7: Пошук даних JSON
        logger.info("\n🔍 Шукаю JSON дані...")
        script_tags = soup.find_all('script')
        logger.info(f"📊 Script тегів знайдено: {len(script_tags)}")
        
        for i, script in enumerate(script_tags[:5]):
            content = script.string
            if content and 'token' in content.lower():
                logger.info(f"   Script #{i}: {content[:100]}...")
        
    finally:
        driver.quit()
        logger.info("\n🔌 Браузер закритий")

if __name__ == "__main__":
    test_scraper()
