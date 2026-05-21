import time
import sqlite3
import feedparser
import telebot
import requests

# Настройки
BOT_TOKEN = "8970612151:AAHU6nSkOYjnpW0uLaOEdhZfunh0mrsOmkU"
CHANNEL_ID = "@onetime_foot"
CHECK_INTERVAL = 300  # 5 минут

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
    conn = sqlite3.connect("bot_v12.db")
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
        if "sports.ru" in img_url and "%" in
        
