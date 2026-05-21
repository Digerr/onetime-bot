# -*- coding: utf-8 -*-
"""
🤖 Футбольный RSS-бот для Telegram и VK
Версия: 2.16 (Инсайдеры, автоперевод и раздельные тайминги)
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
from threading import RLock
from datetime import datetime, timedelta
from deep_translator import GoogleTranslator

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

BOT_TOKEN = os.getenv("BOT_TOKEN", "8970612151:AAHU6nSkOYjnpW0uLaOEdhZfunh0mrsOmkU")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@onetime_foot")
VK_TOKEN = os.getenv("VK_TOKEN", "vk1.a.loMELO9me0A1TfCHqzeWTPx9WgPMJzduEHk2GS4YiLUNYhkqe5ZItXLYU4-wQby-JZdHr8TGPV9hraOF6h-cDZKBB4nLPBqzPWR5YdKJKQh_GBF-qTEvBIqLFCZFbO4K6h0EM7Y3ABCMQZO89B9IQM0igZiHvQxAkbbAiopRfkFPP2CX8aLWFffa053JpoSCsPuUB0CDafLpwlVNG0_Ptw")
VK_GROUP_ID = os.getenv("VK_GROUP_ID", "238937915")

TG_INTERVAL = 900
VK_DAILY_LIMIT = int(os.getenv("VK_DAILY_LIMIT", "50"))
telebot.apihelper.READ_TIMEOUT = 10
telebot.apihelper.CONNECT_TIMEOUT = 10
LAST_VK_POST_TIME = 0  

# ============================================
# RSS ИСТОЧНИКИ
# ============================================
RSS_FEEDS = {
    "Спорт-Экспресс": "https://www.sport-express.ru/services/materials/news/football/se/",
    "Sports.ru": "https://www.sports.ru/rss/rubric.xml?s=208",
    "Чемпионат": "https://www.championat.com/rss/news/football/",
    "Sky Sports": "https://www.skysports.com/rss/12040",
    "BBC Sport": "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "Goal.com (Трансферы)": "https://www.goal.com/feeds/en/news"
}

FOREIGN_SOURCES = ["Sky Sports", "BBC Sport", "Goal.com (Трансферы)"]

bot = telebot.TeleBot(BOT_TOKEN)
db_lock = RLock()

def init_db():
    try:
        with db_lock:
            conn = sqlite3.connect("bot_v25.db", check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posted_news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    title TEXT,
                    published TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    posted_to_vk INTEGER DEFAULT 0
                )
            """)
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vk_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_date DATE,
                    posts_count INTEGER DEFAULT 0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posted_url ON posted_news(url)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_link ON queue(link)")
            conn.commit()
            conn.close()
    except Exception as e:
        sys.exit(1)

def get_db_connection():
    return sqlite3.connect("bot_v25.db", check_same_thread=False)

def get_vk_posts_today():
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            today = datetime.now().date()
            cursor.execute("SELECT posts_count FROM vk_stats WHERE post_date = ?", (today,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0
    except:
        return 0

def increment_vk_counter():
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            today = datetime.now().date()
            cursor.execute("SELECT posts_count FROM vk_stats WHERE post_date = ?", (today,))
            result = cursor.fetchone()
            if result:
                cursor.execute("UPDATE vk_stats SET posts_count = posts_count + 1 WHERE post_date = ?", (today,))
            else:
                cursor.execute("INSERT INTO vk_stats (post_date, posts_count) VALUES (?, 1)", (today,))
            conn.commit()
            conn.close()
    except:
        pass

def can_post_to_vk():
    global LAST_VK_POST_TIME
    posts_today = get_vk_posts_today()
    if posts_today >= VK_DAILY_LIMIT:
        return False
    vk_interval = 86400 // VK_DAILY_LIMIT
    current_time = time.time()
    if current_time - LAST_VK_POST_TIME < vk_interval:
        return False
    return True

def get_hashtag(title, summary):
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

def clean_image_url(url):
    if not url or not url.startswith('http'):
        return None
    url = re.sub(r'/(merchant|crop|resize|reize|preview)/.+?/', '/', url)
    url = re.sub(r'/\d+x\d+/', '/', url)
    url = url.replace("_reize/", "").replace("_preview/", "")
    if "%" in url:
        url = url.split("%")[0]
    return url

def extract_image_from_entry(entry):
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

def check_image_accessible(url):
    try:
        res = requests.head(url, timeout=4, headers={"User-Agent": "Mozilla/5.0"})
        return res.status_code == 200
    except:
        return False

def upload_photo_to_vk(image_url):
    try:
        upload_url_response = requests.get(
            "https://api.vk.com/method/photos.getWallUploadServer",
            params={"group_id": VK_GROUP_ID, "access_token": VK_TOKEN, "v": "5.131"},
            timeout=5
        ).json()
        if "error" in upload_url_response: return None
        upload_url = upload_url_response['response']['upload_url']
        img_response = requests.get(image_url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if img_response.status_code != 200: return None
        upload_response = requests.post(upload_url, files={'photo': ('image.jpg', img_response.content, 'image/jpeg')}, timeout=5).json()
        if 'photo' not in upload_response: return None
        save_response = requests.get(
            "https://api.vk.com/method/photos.saveWallPhoto",
            params={"group_id": VK_GROUP_ID, "photo": upload_response['photo'], "server": upload_response['server'], "hash": upload_response['hash'], "access_token": VK_TOKEN, "v": "5.131"},
            timeout=5
        ).json()
        if "error" in save_response: return None
        photo = save_response['response'][0]
        return f"photo{photo['owner_id']}_{photo['id']}"
    except:
        return None

def is_duplicate(new_title):
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT title FROM posted_news ORDER BY id DESC LIMIT 30")
            posted_titles = cursor.fetchall()
            conn.close()
        new_words = set([w.lower() for w in new_title.split() if len(w) > 3])
        if not new_words: return False
        for (old_title,) in posted_titles:
            old_words = set([w.lower() for w in old_title.split() if len(w) > 3])
            if not old_words: continue
            common_words = new_words.intersection(old_words)
            similarity = len(common_words) / min(len(new_words), len(old_words))
            if similarity > 0.55: return True
        return False
    except:
        return False

def post_to_vk(source, title, summary, link, image_url, tag):
    global LAST_VK_POST_TIME
    if not VK_TOKEN or not can_post_to_vk():
        return False
    try:
        vk_text = f"⚽️ {title}\n\n⚡️ {summary}\n\nЧитать полностью: {link}\n\n{tag}"
        params = {"owner_id": f"-{VK_GROUP_ID}", "from_group": 1, "message": vk_text, "access_token": VK_TOKEN, "v": "5.131"}
        if image_url and check_image_accessible(image_url):
            attachment = upload_photo_to_vk(image_url)
            params["attachments"] = attachment if attachment else link
        else:
            params["attachments"] = link
        response = requests.post("https://api.vk.com/method/wall.post", data=params, timeout=5)
        if "error" in response.json(): return False
        increment_vk_counter()
        LAST_VK_POST_TIME = time.time()
        return True
    except:
        return False

def parse_and_queue():
    logger.info("🔄 Сканирование источников...")
    translator = GoogleTranslator(source='auto', target='ru')
    new_count = 0
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        for source_name, url in RSS_FEEDS.items():
            try:
                response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                if response.status_code != 200: continue
                feed = feedparser.parse(response.content)
                for entry in reversed(feed.entries[:4]):
                    link = entry.get('link', '')
                    if not link: continue
                    parsed_date = entry.get('published_parsed') or entry.get('updated_parsed')
                    if parsed_date:
                        try:
                            entry_dt = datetime.fromtimestamp(time.mktime(parsed_date))
                            if datetime.now() - entry_dt > timedelta(days=1): continue
                        except: pass
                    cursor.execute("SELECT 1 FROM posted_news WHERE url = ?", (link,))
                    if cursor.fetchone(): continue
                    cursor.execute("SELECT 1 FROM queue WHERE link = ?", (link,))
                    if cursor.fetchone(): continue
                    title = entry.get('title', 'Без заголовка')
                    summary = entry.get('summary', entry.get('description', ''))
                    if "<" in summary: summary = re.sub('<[^<]+?>', '', summary)
                    summary = summary.replace("Читать дальше →", "").replace("Читать дальше", "").strip()
                    
                    if source_name in FOREIGN_SOURCES:
                        try:
                            title = translator.translate(title)
                            if summary: summary = translator.translate(summary)
                        except:
                            continue
                    
                    if len(summary) > 250: summary = summary[:250].rsplit(' ', 1)[0] + "..."
                    image_url = extract_image_from_entry(entry)
                    tag = get_hashtag(title, summary)
                    try:
                        cursor.execute("INSERT INTO queue (source, title, summary, link, tag, image_url) VALUES (?, ?, ?, ?, ?, ?)", (source_name, title, summary, link, tag, image_url))
                        conn.commit()
                        new_count += 1
                    except: pass
            except: pass
        conn.close()

def publish_from_queue():
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        while True:
            cursor.execute("SELECT id, source, title, summary, link, tag, image_url FROM queue ORDER BY RANDOM() LIMIT 1")
            row = cursor.fetchone()
            if not row: break
            q_id, source, title, summary, link, tag, image_url = row
            if is_duplicate(title) or not image_url or not check_image_accessible(image_url):
                cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
                conn.commit()
                continue
            clean_title = title.replace("<", "&lt;").replace(">", "&gt;")
            clean_summary = summary.replace("<", "&lt;").replace(">", "&gt;")
            post_text = f"⚽️ <b>{clean_title}</b>\n\n⚡️ {clean_summary} — <i><a href='{link}'>{source}</a></i>\n\n⚡️ Подписывайся на <a href='https://t.me/onetime_foot'>Ван-Тайм</a>!\n\n{tag}"
            try:
                bot.send_photo(CHANNEL_ID, image_url, caption=post_text, parse_mode="HTML")
                post_to_vk(source, title, summary, link, image_url, tag)
                cursor.execute("INSERT INTO posted_news (url, title, posted_to_vk) VALUES (?, ?, ?)", (link, title, 1))
                cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
                conn.commit()
                break
            except:
                cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
                conn.commit()
                continue
        conn.close()

def main():
    init_db()
    while True:
        try:
            parse_and_queue()
            publish_from_queue()
            time.sleep(TG_INTERVAL)
        except:
            time.sleep(10)

if __name__ == "__main__":
    main()
    
