import time
import sqlite3
import feedparser
import telebot
import requests
from bs4 import BeautifulSoup

# Настройки
BOT_TOKEN = "8970612151:AAHU6nSkOYjnpW0uLaOEdhZfunh0mrsOmkU"
CHANNEL_ID = "@onetime_foot"
CHECK_INTERVAL = 600  # 10 минут

# Список RSS-лент (8 футбольных источников)
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
    conn = sqlite3.connect("bot_v4.db")
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
            tag TEXT
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
    elif "ювентус" in text or "милан" in text or "интер" in text or "серия а" in text:
        return "#СерияА"
    elif "бавария" in text or "боруссия" in text or "бундеслига" in text:
        return "#Бундеслига"
    elif "псж" in text or "лига 1" in text:
        return "#Лига1"
    elif "лига чемпионов" in text or "лч" in text:
        return "#ЛЧ"
    elif "сборная" in text or "чм-" in text or "евро-" in text:
        return "#Сборные"
    return "#Интер"

def get_image_url(url):
    """Улучшенный парсер картинок, заточенный под спортивные сайты"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=7)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. Ищем og:image
            meta_img = soup.find("meta", property="og:image")
            if meta_img and meta_img.get("content"):
                return meta_img["content"]
                
            # 2. Ищем twitter:image
            tw_img = soup.find("meta", name="twitter:image")
            if tw_img and tw_img.get("content"):
                return tw_img["content"]

            # 3. Специфический поиск для Спорт-Экспресса и Чемпионата
            for img in soup.find_all("img"):
                src = img.get("src", "")
                # Обычно главные фотки содержать слова 'preview', 'main', 'origin' или большие размеры
                if "media" in src or "materials" in src or "origin" in src:
                    if src.startswith("//"): return "https:" + src
                    if src.startswith("/"): return url.split("/")[0] + "//" + url.split("/")[2] + src
                    return src
    except Exception as e:
        print(f"⚠️ Ошибка поиска картинки: {e}")
    return None

def parse_and_queue():
    print("🔄 Сканирую источники...")
    conn = sqlite3.connect("bot_v4.db")
    cursor = conn.cursor()
    
    for source_name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in reversed(feed.entries[:5]):
                link = entry.link
                
                cursor.execute("SELECT 1 FROM posted_news WHERE url = ?", (link,))
                if cursor.fetchone():
                    continue
                    
                cursor.execute("SELECT 1 FROM queue WHERE link = ?", (link,))
                if cursor.fetchone():
                    continue
                
                title = entry.title
                summary = entry.get("summary", "")
                if len(summary) > 250:
                    summary = summary[:250] + "..."
                
                tag = get_hashtag(title, summary)
                
                cursor.execute("""
                    INSERT INTO queue (source, title, summary, link, tag)
                    VALUES (?, ?, ?, ?, ?)
                """, (source_name, title, summary, link, tag))
                conn.commit()
                print(f"➕ Очередь: {title}")
                
        except Exception as e:
            print(f"⚠️ Ошибка RSS {source_name}: {e}")
            
    conn.close()

def publish_from_queue():
    conn = sqlite3.connect("bot_v4.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, source, title, summary, link, tag FROM queue ORDER BY id ASC LIMIT 1")
    row = cursor.fetchone()
    
    if row:
        q_id, source, title, summary, link, tag = row
        
        # Очищаем текст от возможных символов < и >, чтобы HTML не ругался
        clean_title = title.replace("<", "&lt;").replace(">", "&gt;")
        clean_summary = summary.replace("<", "&lt;").replace(">", "&gt;")
        
        # Шаблон на чистом HTML
        post_text = (
            f"📌 <b>{clean_title}</b>\n\n"
            f"📝 {clean_summary} — <i><a href='{link}'>{source}</a></i>\n\n"
            f"⚡️ Подписывайся на <a href='https://t.me/onetime_foot'>Ван-Тайм</a> — главный футбольный в один клик!\n\n"
            f"📌 {tag}"
        )
        
        image_url = get_image_url(link)
        
        try:
            if image_url:
                bot.send_photo(CHANNEL_ID, image_url, caption=post_text, parse_mode="HTML")
            else:
                bot.send_message(CHANNEL_ID, post_text, parse_mode="HTML")
                
            print(f"📢 Опубликовано: {title}")
            cursor.execute("INSERT INTO posted_news (url, title) VALUES (?, ?)", (link, title))
            cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
            conn.commit()
            
        except Exception as e:
            print(f"❌ Ошибка отправки: {e}")
    else:
        print("💤 Очередь пуста.")
        
    conn.close()

def main():
    init_db()
    while True:
        parse_and_queue()
        publish_from_queue()
        print(f"😴 Засыпаю...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
    
