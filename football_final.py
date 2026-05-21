# -*- coding: utf-8 -*-
"""
🤖 Футбольный RSS-бот для Telegram и VK
Версия: 2.0 (улучшенная)
"""

import time
import sqlite3
import feedparser
import telebot
import requests
import re
import logging
import signal
import sys
import os
from threading import Lock
from datetime import datetime

# ============================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# ЗАГРУЗКА НАСТРОЕК
# ============================================
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("✅ Файл .env загружен")
except ImportError:
    logger.warning("⚠️ python-dotenv не установлен, используем переменные окружения")

# Telegram настройки
BOT_TOKEN = os.getenv("BOT_TOKEN", "8970612151:AAHU6nSkOYjnpW0uLaOEdhZfunh0mrsOmkU")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@onetime_foot")

# VK настройки
VK_TOKEN = os.getenv("VK_TOKEN", "vk1.a.loMELO9me0A1TfCHqzeWTPx9WgPMJzduEHk2GS4YiLUNYhkqe5ZItXLYU4-wQby-JZdHr8TGPV9hraOF6h-cDZKBB4nLPBqzPWR5YdKJKQh_GBF-qTEvBIqLFCZFbO4K6h0EM7Y3ABCMQZO89B9IQM0igZiHvQxAkbbAiopRfkFPP2CX8aLWFffa053JpoSCsPuUB0CDafLpwlVNG0_Ptw")
VK_GROUP_ID = os.getenv("VK_GROUP_ID", "238937915")

# Интервал проверки (в секундах)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))  # 5 минут

# ============================================
# RSS ИСТОЧНИКИ
# ============================================
RSS_FEEDS = {
    "Спорт-Экспресс": "https://www.sport-express.ru/services/materials/news/football/se/",
    "Sports.ru": "https://www.sports.ru/rss/rubric.xml?s=208",
    "Евро-Футбол": "https://www.euro-football.ru/rss.xml",
    "Бомбардир": "https://bombardir.ru/rss/news",
    "Чемпионат": "https://www.championat.com/rss/news/football/",
    "РБ Спорт": "https://bookmaker-ratings.ru/news/feed/football/",
    "FootballHD": "https://footballhd.ru/rss.xml",
    "Soccer.ru": "https://www.soccer.ru/rss/news.xml"
}

# Источники для публикации в VK (только проверенные)
VK_ALLOWED_SOURCES = ["sports.ru", "чемпионат", "спорт-экспресс"]

# ============================================
# ИНИЦИАЛИЗАЦИЯ БОТА
# ============================================
bot = telebot.TeleBot(BOT_TOKEN)
db_lock = Lock()  # Блокировка для безопасной работы с БД

# ============================================
# РАБОТА С БАЗОЙ ДАННЫХ
# ============================================
def init_db():
    """Создаёт таблицы в базе данных"""
    try:
        with db_lock:
            conn = sqlite3.connect("bot_v24.db", check_same_thread=False)
            cursor = conn.cursor()
            
            # Таблица опубликованных новостей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posted_news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    title TEXT,
                    published TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица очереди на публикацию
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT,
                    title TEXT,
                    summary TEXT,
                    link TEXT UNIQUE,
                    tag TEXT,
                    image_url TEXT,
                    added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Индексы для ускорения поиска
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posted_url ON posted_news(url)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_link ON queue(link)")
            
            conn.commit()
            conn.close()
            logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        sys.exit(1)

def get_db_connection():
    """Возвращает новое подключение к БД"""
    return sqlite3.connect("bot_v24.db", check_same_thread=False)

# ============================================
# ОПРЕДЕЛЕНИЕ ХЕШТЕГОВ
# ============================================
def get_hashtag(title, summary):
    """Определяет хештег по содержимому новости"""
    text = (title + " " + summary).lower()
    
    # Словарь ключевых слов для каждой лиги
    leagues = {
        "#РПЛ": ["россия", "рпл", "зенит", "спартак", "цска", "динамо", "краснодар", "локомотив"],
        "#ЛаЛига": ["реал мадрид", "барселона", "ла лига", "атлетико", "севилья", "испания"],
        "#АПЛ": ["манчестер", "ливерпуль", "арсенал", "челси", "апл", "тоттенхэм", "англия", "премьер-лига"],
        "#СерияА": ["ювентус", "милан", "интер", "серия а", "наполи", "рома", "италия"],
        "#Бундеслига": ["бавария", "боруссия", "бундеслига", "лейпциг", "германия"],
        "#Лига1": ["псж", "лион", "марсель", "лига 1", "франция"],
        "#ЛЧ": ["лига чемпионов", " лч ", "уефа"],
        "#Сборные": ["сборная", "чм-", "евро-", "квалификация"]
    }
    
    for tag, keywords in leagues.items():
        for keyword in keywords:
            if keyword in text:
                return tag
    
    return "#Футбол"

# ============================================
# РАБОТА С ИЗОБРАЖЕНИЯМИ
# ============================================
def clean_image_url(url):
    """Очищает URL изображения от параметров ресайза"""
    if not url or not url.startswith('http'):
        return None
    
    # Sports.ru - убираем служебные папки
    url = re.sub(r'/(merchant|crop|resize|reize|preview)/.+?/', '/', url)
    url = re.sub(r'/\d+x\d+/', '/', url)
    
    # Championat.com
    url = url.replace("_reize/", "").replace("_preview/", "")
    
    # Убираем параметры после %
    if "%" in url:
        url = url.split("%")[0]
    
    return url

def extract_image_from_entry(entry):
    """Извлекает URL изображения из RSS-записи"""
    
    # 1. Проверяем enclosures (стандартный способ)
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image/'):
                return clean_image_url(enc.get('href'))
    
    # 2. Media content (Media RSS)
    if hasattr(entry, 'media_content') and entry.media_content:
        return clean_image_url(entry.media_content[0].get('url'))
    
    # 3. Links с типом image
    if hasattr(entry, 'links'):
        for link in entry.links:
            if link.get('type', '').startswith('image/'):
                return clean_image_url(link.get('href'))
    
    # 4. Парсинг из HTML summary
    if hasattr(entry, 'summary') and "<img" in entry.summary:
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', entry.summary)
        if match:
            return clean_image_url(match.group(1))
    
    return None

# ============================================
# ПРОВЕРКА ДУБЛИКАТОВ
# ============================================
def is_duplicate(new_title):
    """Проверяет, похожа ли новость на уже опубликованные"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Берём последние 30 заголовков
            cursor.execute("SELECT title FROM posted_news ORDER BY id DESC LIMIT 30")
            posted_titles = cursor.fetchall()
            conn.close()
        
        # Разбиваем на слова (минимум 4 символа)
        new_words = set([w.lower() for w in new_title.split() if len(w) > 3])
        if not new_words:
            return False
        
        # Сравниваем с каждым заголовком
        for (old_title,) in posted_titles:
            old_words = set([w.lower() for w in old_title.split() if len(w) > 3])
            if not old_words:
                continue
            
            # Считаем процент совпадающих слов
            common_words = new_words.intersection(old_words)
            similarity = len(common_words) / min(len(new_words), len(old_words))
            
            if similarity > 0.55:  # Больше 55% совпадений = дубликат
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки дубликатов: {e}")
        return False

# ============================================
# ПУБЛИКАЦИЯ В VK
# ============================================
def post_to_vk(source, title, summary, link, tag):
    """Публикует новость в группу VK"""
    
    # Проверяем, включён ли VK
    if not VK_TOKEN:
        return
    
    # Проверяем, разрешён ли источник
    if source.lower() not in VK_ALLOWED_SOURCES:
        logger.debug(f"⏭️ Источник {source} не публикуется в VK")
        return
    
    try:
        # Формируем текст поста
        vk_text = (
            f"⚽️ {title}\n\n"
            f"⚡️ {summary}\n\n"
            f"{tag}"
        )
        
        # Параметры запроса к VK API
        params = {
            "owner_id": f"-{VK_GROUP_ID}",
            "from_group": 1,
            "message": vk_text,
            "attachments": link,  # VK сам создаст превью статьи
            "access_token": VK_TOKEN,
            "v": "5.131"
        }
        
        response = requests.post(
            "https://api.vk.com/method/wall.post",
            data=params,
            timeout=10
        )
        
        result = response.json()
        
        if "error" in result:
            logger.error(f"❌ VK API ошибка: {result['error']['error_msg']}")
        else:
            post_id = result.get('response', {}).get('post_id')
            logger.info(f"✅ Опубликовано в VK: post_{VK_GROUP_ID}_{post_id}")
            
    except requests.exceptions.Timeout:
        logger.error("⏱️ Таймаут при публикации в VK")
    except Exception as e:
        logger.error(f"❌ Ошибка публикации в VK: {e}")

# ============================================
# ПАРСИНГ RSS
# ============================================
def parse_and_queue():
    """Сканирует RSS-ленты и добавляет новости в очередь"""
    logger.info("🔄 Начинаю сканирование источников...")
    
    new_count = 0
    
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for source_name, url in RSS_FEEDS.items():
            try:
                # Парсим RSS с таймаутом
                feed = feedparser.parse(url)
                
                # Проверяем на ошибки парсинга
                if feed.bozo:
                    logger.warning(f"⚠️ Проблемы с RSS {source_name}: {feed.bozo_exception}")
                
                # Обрабатываем последние 4 записи (в обратном порядке)
                for entry in reversed(feed.entries[:4]):
                    link = entry.get('link', '')
                    
                    if not link:
                        continue
                    
                    # Проверяем, не публиковали ли уже
                    cursor.execute("SELECT 1 FROM posted_news WHERE url = ?", (link,))
                    if cursor.fetchone():
                        continue
                    
                    # Проверяем, нет ли в очереди
                    cursor.execute("SELECT 1 FROM queue WHERE link = ?", (link,))
                    if cursor.fetchone():
                        continue
                    
                    # Извлекаем данные
                    title = entry.get('title', 'Без заголовка')
                    summary = entry.get('summary', entry.get('description', ''))
                    
                    # Очищаем summary от HTML
                    if "<" in summary:
                        summary = re.sub('<[^<]+?>', '', summary)
                    
                    # Убираем лишние фразы
                    summary = summary.replace("Читать дальше →", "").replace("Читать дальше", "").strip()
                    
                    # Обрезаем длинные описания
                    if len(summary) > 250:
                        summary = summary[:250].rsplit(' ', 1)[0] + "..."
                    
                    # Извлекаем изображение
                    image_url = extract_image_from_entry(entry)
                    
                    # Определяем хештег
                    tag = get_hashtag(title, summary)
                    
                    # Добавляем в очередь
                    try:
                        cursor.execute("""
                            INSERT INTO queue (source, title, summary, link, tag, image_url)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (source_name, title, summary, link, tag, image_url))
                        conn.commit()
                        new_count += 1
                        logger.info(f"➕ Добавлено в очередь: {title[:50]}... ({source_name})")
                    except sqlite3.IntegrityError:
                        # Дубликат по link (UNIQUE constraint)
                        pass
                        
            except requests.exceptions.Timeout:
                logger.error(f"⏱️ Таймаут при загрузке {source_name}")
            except Exception as e:
                logger.error(f"❌ Ошибка парсинга {source_name}: {e}")
        
        conn.close()
    
    logger.info(f"📊 Добавлено новых записей: {new_count}")

# ============================================
# ПУБЛИКАЦИЯ ИЗ ОЧЕРЕДИ
# ============================================
def publish_from_queue():
    """Публикует одну случайную новость из очереди"""
    
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем случайную запись из очереди
        cursor.execute("""
            SELECT id, source, title, summary, link, tag, image_url 
            FROM queue 
            ORDER BY RANDOM() 
            LIMIT 1
        """)
        row = cursor.fetchone()
        
        if not row:
            logger.info("💤 Очередь пуста, нечего публиковать")
            conn.close()
            return
        
        q_id, source, title, summary, link, tag, image_url = row
        
        # Проверка на дубликаты
        if is_duplicate(title):
            logger.warning(f"🗑️ Удалён дубликат: {title[:50]}...")
            cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
            conn.commit()
            conn.close()
            return
        
        # Экранируем HTML-символы
        clean_title = title.replace("<", "&lt;").replace(">", "&gt;")
        clean_summary = summary.replace("<", "&lt;").replace(">", "&gt;")
        
        # Формируем текст поста для Telegram
        post_text = (
            f"⚽️ <b>{clean_title}</b>\n\n"
            f"⚡️ {clean_summary} — <i><a href='{link}'>{source}</a></i>\n\n"
            f"⚡️ Подписывайся на <a href='https://t.me/onetime_foot'>Ван-Тайм</a> — главный футбольный в один клик!\n\n"
            f"{tag}"
        )
        
        # Публикуем в Telegram
        try:
            if image_url:
                bot.send_photo(
                    CHANNEL_ID,
                    image_url,
                    caption=post_text,
                    parse_mode="HTML"
                )
            else:
                bot.send_message(
                    CHANNEL_ID,
                    post_text,
                    parse_mode="HTML",
                    disable_web_page_preview=False
                )
            
            logger.info(f"📢 Опубликовано в Telegram: {title[:50]}... ({source})")
            
            # Публикуем в VK
            post_to_vk(source, title, summary, link, tag)
            
            # Сохраняем в базу опубликованных
            cursor.execute("INSERT INTO posted_news (url, title) VALUES (?, ?)", (link, title))
            
            # Удаляем из очереди
            cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
            conn.commit()
            
        except telebot.apihelper.ApiTelegramException as e:
            logger.error(f"❌ Telegram API ошибка: {e}")
            # Удаляем проблемную запись из очереди
            cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
            conn.commit()
            
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при публикации: {e}")
            cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
            conn.commit()
        
        conn.close()

# ============================================
# GRACEFUL SHUTDOWN
# ============================================
def signal_handler(sig, frame):
    """Обработчик сигналов для корректной остановки"""
    logger.info("🛑 Получен сигнал остановки, завершаю работу...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ============================================
# ГЛАВНЫЙ ЦИКЛ
# ============================================
def main():
    """Основная функция бота"""
    
    # Инициализация
    init_db()
    logger.info("🚀 Бот запущен!")
    logger.info(f"📺 Telegram канал: {CHANNEL_ID}")
    logger.info(f"🔄 Интервал проверки: {CHECK_INTERVAL} секунд")
    
    try:
        while True:
            # Парсим RSS
            parse_and_queue()
            
            # Публикуем из очереди
            publish_from_queue()
            
            # Ждём до следующей итерации
            logger.info(f"😴 Засыпаю на {CHECK_INTERVAL} секунд...")
            time.sleep(CHECK_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.critical(f"💀 Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

# ============================================
# ТОЧКА ВХОДА
# ============================================
if __name__ == "__main__":
    main()
