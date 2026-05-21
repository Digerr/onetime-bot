# -*- coding: utf-8 -*-
"""
🤖 Футбольный RSS-бот для Telegram и VK
Версия: 2.3 (Исправлен капкан дубликатов и интервал)
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
from datetime import datetime, timedelta

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

# Интервалы публикации (Ставим 5 минут вместо сонных 15)
TG_INTERVAL = 300  
VK_DAILY_LIMIT = int(os.getenv("VK_DAILY_LIMIT", "50"))  # Максимум постов в день

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
                    published TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    posted_to_vk INTEGER DEFAULT 0
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
            
            # Таблица статистики VK (для лимита 50 постов/день)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vk_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_date DATE,
                    posts_count INTEGER DEFAULT 0
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
# VK СТАТИСТИКА И ЛИМИТЫ
# ============================================
def get_vk_posts_today():
    """Возвращает количество постов в VK за сегодня"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            today = datetime.now().date()
            cursor.execute("SELECT posts_count FROM vk_stats WHERE post_date = ?", (today,))
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else 0
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики VK: {e}")
        return 0

def increment_vk_counter():
    """Увеличивает счётчик постов VK на 1"""
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            today = datetime.now().date()
            cursor.execute("SELECT posts_count FROM vk_stats WHERE post_date = ?", (today,))
            result = cursor.fetchone()
            
            if result:
                cursor.execute(
                    "UPDATE vk_stats SET posts_count = posts_count + 1 WHERE post_date = ?",
                    (today,)
                )
            else:
                cursor.execute(
                    "INSERT INTO vk_stats (post_date, posts_count) VALUES (?, 1)",
                    (today,)
                )
            
            conn.commit()
            conn.close()
    except Exception as e:
        logger.error(f"❌ Ошибка обновления счётчика VK: {e}")

def can_post_to_vk():
    """Проверяет, можно ли публиковать в VK (только лимит)"""
    posts_today = get_vk_posts_today()
    if posts_today >= VK_DAILY_LIMIT:
        logger.warning(f"⚠️ Достигнут лимит VK на сегодня: {posts_today}/{VK_DAILY_LIMIT}")
        return False
    
    return True

# ============================================
# ОПРЕДЕЛЕНИЕ ХЕШТЕГОВ
# ============================================
def get_hashtag(title, summary):
    """Определяет хештег по содержимому новости"""
    text = (title + " " + summary).lower()
    
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
    
    url = re.sub(r'/(merchant|crop|resize|reize|preview)/.+?/', '/', url)
    url = re.sub(r'/\d+x\d+/', '/', url)
    
    url = url.replace("_reize/", "").replace("_preview/", "")
    
    if "%" in url:
        url = url.split("%")[0]
    
    return url

def extract_image_from_entry(entry):
    """Извлекает URL изображения из RSS-записи"""
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image/'):
                return clean_image_url(enc.get('href'))
    
    if hasattr(entry, 'media_content') and entry.media_content:
        return clean_image_url(entry.media_content[0].get('url'))
    
    if hasattr(entry, 'links'):
        for link in entry.links:
            if link.get('type', '').startswith('image/'):
                return clean_image_url(link.get('href'))
    
    if hasattr(entry, 'summary') and "<img" in entry.summary:
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', entry.summary)
        if match:
            return clean_image_url(match.group(1))
    
    return None

# ============================================
# ЗАГРУЗКА ФОТО В VK
# ============================================
def upload_photo_to_vk(image_url):
    """Загружает фото на server VK и возвращает attachment"""
    try:
        upload_url_response = requests.get(
            "https://api.vk.com/method/photos.getWallUploadServer",
            params={
                "group_id": VK_GROUP_ID,
                "access_token": VK_TOKEN,
                "v": "5.131"
            },
            timeout=10
        ).json()
        
        if "error" in upload_url_response:
            logger.error(f"❌ VK getWallUploadServer: {upload_url_response['error']}")
            return None
        
        upload_url = upload_url_response['response']['upload_url']
        
        img_response = requests.get(image_url, timeout=10)
        if img_response.status_code != 200:
            logger.error(f"❌ Не удалось скачать фото: {image_url}")
            return None
        
        upload_response = requests.post(
            upload_url,
            files={'photo': ('image.jpg', img_response.content, 'image/jpeg')}
        ).json()
        
        if 'photo' not in upload_response:
            logger.error(f"❌ VK upload ошибка: {upload_response}")
            return None
        
        save_response = requests.get(
            "https://api.vk.com/method/photos.saveWallPhoto",
            params={
                "group_id": VK_GROUP_ID,
                "photo": upload_response['photo'],
                "server": upload_response['server'],
                "hash": upload_response['hash'],
                "access_token": VK_TOKEN,
                "v": "5.131"
            },
            timeout=10
        ).json()
        
        if "error" in save_response:
            logger.error(f"❌ VK saveWallPhoto: {save_response['error']}")
            return None
        
        photo = save_response['response'][0]
        attachment = f"photo{photo['owner_id']}_{photo['id']}"
        
        logger.info(f"✅ Фото загружено в VK: {attachment}")
        return attachment
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки фото в VK: {e}")
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
            
            cursor.execute("SELECT title FROM posted_news ORDER BY id DESC LIMIT 30")
            posted_titles = cursor.fetchall()
            conn.close()
        
        new_words = set([w.lower() for w in new_title.split() if len(w) > 3])
        if not new_words:
            return False
        
        for (old_title,) in posted_titles:
            old_words = set([w.lower() for w in old_title.split() if len(w) > 3])
            if not old_words:
                continue
            
            common_words = new_words.intersection(old_words)
            similarity = len(common_words) / min(len(new_words), len(old_words))
            
            if similarity > 0.55:  
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки дубликатов: {e}")
        return False

# ============================================
# ПУБЛИКАЦИЯ В VK
# ============================================
def post_to_vk(source, title, summary, link, image_url, tag):
    """Публикует новость в группу VK с картинкой"""
    if not VK_TOKEN:
        return False
    
    if source.lower() not in VK_ALLOWED_SOURCES:
        logger.debug(f"⏭️ Источник {source} не публикуется в VK")
        return False
    
    if not can_post_to_vk():
        return False
    
    try:
        vk_text = (
            f"⚽️ {title}\n\n"
            f"⚡️ {summary}\n\n"
            f"Читать полностью: {link}\n\n"
            f"{tag}"
        )
        
        params = {
            "owner_id": f"-{VK_GROUP_ID}",
            "from_group": 1,
            "message": vk_text,
            "access_token": VK_TOKEN,
            "v": "5.131"
        }
        
        if image_url:
            attachment = upload_photo_to_vk(image_url)
            if attachment:
                params["attachments"] = attachment
            else:
                params["attachments"] = link
        else:
            params["attachments"] = link
        
        response = requests.post(
            "https://api.vk.com/method/wall.post",
            data=params,
            timeout=10
        )
        
        result = response.json()
        
        if "error" in result:
            logger.error(f"❌ VK API ошибка: {result['error']['error_msg']}")
            return False
        else:
            post_id = result.get('response', {}).get('post_id')
            logger.info(f"✅ Опубликовано в VK: post_{VK_GROUP_ID}_{post_id}")
            increment_vk_counter()
            return True
            
    except Exception as e:
        logger.error(f"❌ Ошибка публикации в VK: {e}")
        return False

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
                feed = feedparser.parse(url)
                
                for entry in reversed(feed.entries[:4]):
                    link = entry.get('link', '')
                    if not link:
                        continue
                    
                    cursor.execute("SELECT 1 FROM posted_news WHERE url = ?", (link,))
                    if cursor.fetchone():
                        continue
                    
                    cursor.execute("SELECT 1 FROM queue WHERE link = ?", (link,))
                    if cursor.fetchone():
                        continue
                    
                    title = entry.get('title', 'Без заголовка')
                    summary = entry.get('summary', entry.get('description', ''))
                    
                    if "<" in summary:
                        summary = re.sub('<[^<]+?>', '', summary)
                    
                    summary = summary.replace("Читать дальше →", "").replace("Читать дальше", "").strip()
                    
                    if len(summary) > 250:
                        summary = summary[:250].rsplit(' ', 1)[0] + "..."
                    
                    image_url = extract_image_from_entry(entry)
                    tag = get_hashtag(title, summary)
                    
                    try:
                        cursor.execute("""
                            INSERT INTO queue (source, title, summary, link, tag, image_url)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (source_name, title, summary, link, tag, image_url))
                        conn.commit()
                        new_count += 1
                        logger.info(f"➕ Добавлено в очередь: {title[:50]}... ({source_name})")
                    except sqlite3.IntegrityError:
                        pass
                        
            except Exception as e:
                logger.error(f"❌ Ошибка парсинга {source_name}: {e}")
        
        conn.close()
    logger.info(f"📊 Добавлено новых записей: {new_count}")

# ============================================
# ПУБЛИКАЦИЯ ИЗ ОЧЕРЕДИ
# ============================================
def publish_from_queue():
    """Публикует одну уникальную новость из очереди (с исправленным циклом перебора)"""
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        while True:
            cursor.execute("""
                SELECT id, source, title, summary, link, tag, image_url 
                FROM queue 
                ORDER BY RANDOM() 
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if not row:
                logger.info("💤 Очередь пуста, нечего публиковать")
                break
            
            q_id, source, title, summary, link, tag, image_url = row
            
            # Проверка на дубликаты
            if is_duplicate(title):
                logger.warning(f"🗑️ Удалён дубликат: {title[:50]}...")
                cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
                conn.commit()
                continue  # Мгновенно переходим к следующему посту в очереди!
            
            clean_title = title.replace("<", "&lt;").replace(">", "&gt;")
            clean_summary = summary.replace("<", "&lt;").replace(">", "&gt;")
            
            post_text = (
                f"⚽️ <b>{clean_title}</b>\n\n"
                f"⚡️ {clean_summary} — <i><a href='{link}'>{source}</a></i>\n\n"
                f"⚡️ Подписывайся на <a href='https://t.me/onetime_foot'>Ван-Тайм</a> — главный футбольный в один клик!\n\n"
                f"{tag}"
            )
            
            try:
                if image_url:
                    bot.send_photo(CHANNEL_ID, image_url, caption=post_text, parse_mode="HTML")
                else:
                    bot.send_message(CHANNEL_ID, post_text, parse_mode="HTML", disable_web_page_preview=False)
                
                logger.info(f"📢 Опубликовано в Telegram: {title[:50]}... ({source})")
                
                # Дублируем в ВК
                posted_to_vk = post_to_vk(source, title, summary, link, image_url, tag)
                
                cursor.execute(
                    "INSERT INTO posted_news (url, title, posted_to_vk) VALUES (?, ?, ?)",
                    (link, title, 1 if posted_to_vk else 0)
                )
                cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
                conn.commit()
                break  # Пост успешно отправлен, выходим
                
            except telebot.apihelper.ApiTelegramException as e:
                logger.error(f"❌ Telegram API ошибка: {e}")
                cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
                conn.commit()
                break
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка при публикации: {e}")
                cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
                conn.commit()
                break
        
        conn.close()

# ============================================
# GRACEFUL SHUTDOWN
# ======
