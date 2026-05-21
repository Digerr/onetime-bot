import time
import sqlite3
import feedparser
import telebot
import requests
import re

# Настройки TELEGRAM
BOT_TOKEN = "8970612151:AAHU6nSkOYjnpW0uLaOEdhZfunh0mrsOmkU"
CHANNEL_ID = "@onetime_foot"
CHECK_INTERVAL = 300  # 5 минут

# Настройки ВКОНТАКТЕ
VK_TOKEN = "vk1.a.loMELO9me0A1TfCHqzeWTPx9WgPMJzduEHk2GS4YiLUNYhkqe5ZItXLYU4-wQby-JZdHr8TGPV9hraOF6h-cDZKBB4nLPBqzPWR5YdKJKQh_GBF-qTEvBIqLFCZFbO4K6h0EM7Y3ABCMQZO89B9IQM0igZiHvQxAkbbAiopRfkFPP2CX8aLWFffa053JpoSCsPuUB0CDafLpwlVNG0_Ptw"
VK_GROUP_ID = "238937915"

# Список RSS-лент
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

bot = telebot.TeleBot(BOT_TOKEN)

def init_db():
    conn = sqlite3.connect("bot_v20.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posted_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            published TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            title TEXT,
            summary TEXT,
            link TEXT,
            tag TEXT,
            image_url TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_hashtag(title, summary):
    text = (title + " " + summary).lower()
    if "россия" in text or "рпл" in text or "зенит" in text or "спартак" in text or "цска" in text:
        return "#РПЛ"
    elif "реал" in text or "барселона" in text or "ла лига" in text or "испания" in text:
        return "#ЛаЛига"
    elif "сити" in text or "ливерпуль" in text or "арсенал" in text or "апл" in text or "англия" in text:
        return "#АПЛ"
    elif "ювентус" in text or "милан" in text or " интер " in text or "серия а" in text:
        return "#СерияА"
    elif "бавария" in text or "боруссия" in text or "бундеслига" in text:
        return "#Бундеслига"
    elif "псж" in text or "лига 1" in text:
        return "#Лига1"
    elif "лига чемпионов" in text or "лч" in text:
        return "#ЛЧ"
    elif "сборная" in text or "чм-" in text or "евро-" in text:
        return "#Сборные"
    return "#Футбол"

def extract_image_from_entry(entry):
    img_url = None
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image/') or enc.get('href', ''):
                img_url = enc.get('href')
                break
    if not img_url and hasattr(entry, 'media_content') and entry.media_content:
        img_url = entry.media_content[0].get('url')
    if not img_url and hasattr(entry, 'links'):
        for l in entry.links:
            if l.get('rel') == 'enclosure' or l.get('type', '').startswith('image/'):
                img_url = l.get('href')
                break
    if not img_url and hasattr(entry, 'summary') and "<img" in entry.summary:
        try:
            start = entry.summary.find('src="') + 5
            end = entry.summary.find('"', start)
            tmp = entry.summary[start:end]
            if tmp.startswith("http"):
                img_url = tmp
        except:
            pass

    if img_url:
        if "sports.ru" in img_url:
            img_url = re.sub(r'/(merchant|crop|resize|reize|preview)/.+?/', '/', img_url)
            img_url = re.sub(r'/(\d+)x(\d+)/', '/', img_url)
            if "%" in img_url:
                img_url = img_url.split("%")[0]
        elif "championat.com" in img_url:
            img_url = img_url.replace("_reize/", "").replace("_preview/", "")
            
    return img_url

def is_duplicate(new_title):
    conn = sqlite3.connect("bot_v20.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM posted_news ORDER BY id DESC LIMIT 30")
    posted_titles = cursor.fetchall()
    conn.close()

    new_words = set([w.lower() for w in new_title.split() if len(w) > 3])
    if not new_words:
        return False

    for (old_title,) in posted_titles:
        old_words = set([w.lower() for w in old_title.split() if len(w) > 3])
        common_words = new_words.intersection(old_words)
        if len(common_words) / min(len(new_words), len(old_words)) > 0.55:
            return True
    return False

def post_to_vk(source, title, summary, link, image_url, tag):
    """Тестовая отправка ВСЕХ постов в ВК без каких-либо ограничений"""
    if not VK_TOKEN or VK_TOKEN == "ТВОЙ_ТОКЕН_ВК_СЮДА":
        return

    try:
        vk_text = (
            f"⚽️ {title}\n\n"
            f"⚡️ {summary}\n\n"
            f"Читать на {source}: {link}\n\n"
            f"{tag}"
        )
        
        params = {
            "owner_id": f"-{VK_GROUP_ID}",
            "from_group": 1,
            "message": vk_text,
            "access_token": VK_TOKEN,
            "v": "5.131"
        }
        
        # Прикрепляем картинку, если она есть, иначе просто ссылку на источник
        if image_url:
            params["attachments"] = f"{link},{image_url}"
        else:
            params["attachments"] = link
            
        response = requests.post("https://api.vk.com/method/wall.post", data=params, timeout=10)
        result = response.json()
        
        if "response" in result:
            print(f"✅ Тестовый дубль в ВК прошёл! ID поста: {result['response']['post_id']}")
        else:
            print(f"⚠️ ВК
            
