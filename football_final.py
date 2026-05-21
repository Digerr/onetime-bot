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
    conn = sqlite3.connect("bot_v10.db")
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
    """Вытаскивает ссылку на картинку и улучшает её качество до оригинала"""
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

    # Превращаем сжатые миниатюры Sports.ru и Чемпионата в оригиналы высокого качества
    if img_url:
        if "sports.ru" in img_url and "%" in img_url:
            img_url = img_url.split("%")[0]
        elif "championat.com" in img_url and "reize" in img_url:
            img_url = img_url.replace("_reize/", "")
            
    return img_url

def is_duplicate(new_title):
    conn = sqlite3.connect("bot_v10.db")
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

def parse_and_queue():
    print("🔄 Сканирую источники...")
    conn = sqlite3.connect("bot_v10.db")
    cursor = conn.cursor()
    
    for source_name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in reversed(feed.entries[:4]):
                link = entry.link
                
                cursor.execute("SELECT 1 FROM posted_news WHERE url = ?", (link,))
                if cursor.fetchone():
                    continue
                    
                cursor.execute("SELECT 1 FROM queue WHERE link = ?", (link,))
                if cursor.fetchone():
                    continue
                
                title = entry.title
                summary = entry.get("summary", "")
                
                image_url = extract_image_from_entry(entry)
                
                if "<" in summary:
                    import re
                    summary = re.sub('<[^<]+?>', '', summary)
                
                if len(summary) > 250:
                    summary = summary[:250] + "..."
                
                tag = get_hashtag(title, summary)
                
                cursor.execute("""
                    INSERT INTO queue (source, title, summary, link, tag, image_url)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (source_name, title, summary, link, tag, image_url))
                conn.commit()
                
        except Exception as e:
            print(f"⚠️ Ошибка RSS {source_name}: {e}")
            
    conn.close()

def publish_from_queue():
    conn = sqlite3.connect("bot_v10.db")
    cursor = conn.cursor()
    
    while True:
        cursor.execute("SELECT id, source, title, summary, link, tag, image_url FROM queue ORDER BY RANDOM() LIMIT 1")
        row = cursor.fetchone()
        
        if not row:
            print("💤 Очередь пуста.")
            conn.close()
            return

        q_id, source, title, summary, link, tag, image_url = row

        if is_duplicate(title):
            print(f"🗑️ Удален дубликат: {title}")
            cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
            conn.commit()
            continue

        clean_title = title.replace("<", "&lt;").replace(">", "&gt;")
        clean_summary = summary.replace("<", "&lt;").replace(">", "&gt;")
        
        # Переставили эмодзи: Сверху ⚽️, у текста ⚡️
        post_text = (
            f"⚽️ <b>{clean_title}</b>\n\n"
            f"⚡️ {clean_summary} — <i><a href='{link}'>{source}</a></i>\n\n"
            f"⚡️ Подписывайся на <a href='https://t.me/onetime_foot'>Ван-Тайм</a> — главный футбольный в один клик!\n\n"
            f"📌 {tag}"
        )
        
        try:
            if image_url:
                bot.send_photo(CHANNEL_ID, image_url, caption=post_text, parse_mode="HTML")
            else:
                bot.send_message(CHANNEL_ID, post_text, parse_mode="HTML")
                
            print(f"📢 Опубликовано: {title} ({source})")
            cursor.execute("INSERT INTO posted_news (url, title) VALUES (?, ?)", (link, title))
            cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
            conn.commit()
            break
            
        except Exception as e:
            print(f"❌ Ошибка отправки (пробуем без фото): {e}")
            try:
                bot.send_message(CHANNEL_ID, post_text, parse_mode="HTML")
                cursor.execute("INSERT INTO posted_news (url, title) VALUES (?, ?)", (link, title))
            except:
                pass
            cursor.execute("DELETE FROM queue WHERE id = ?", (q_id,))
            conn.commit()
            break

    conn.close()

def main():
    init_db()
    while True:
        parse_and_queue()
        publish_from_queue()
        print(f"😴 Засыпаю на 5 минут...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
    
