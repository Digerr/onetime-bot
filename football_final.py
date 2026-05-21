import telebot
import requests
import xml.etree.ElementTree as ET
import time
import sqlite3
import re

# ================= НАСТРОЙКИ КООРДИНАТ =================
TOKEN = "8970612151:AAHU6nSkOYjnpW0uLaOEdhZfunh0mrsOmkU"  # Твой токен футбольного бота
CHANNEL_ID = "@onetime_foot"                            # Твой канал Ван-Тайм
# =======================================================

# Расширенный список из 8 источников
SOURCES = {
    "Спорт-Экспресс": "https://www.sport-express.ru/services/materials/news/football/se/",
    "Sports.ru": "https://www.sports.ru/rss/rubric.xml?s=208",
    "Евро-Футбол": "https://www.euro-football.ru/rss.xml",
    "Бомбардир": "https://bombardir.ru/rss/news",
    "Чемпионат": "https://www.championat.com/rss/news/football/",
    "РБ Спорт": "https://bookmaker-ratings.ru/news/feed/football/",
    "Soccer.ru": "https://soccer.ru/news.rss",
    "FootballHD": "https://footballhd.ru/rss.xml"
}

HASHTAGS = {
    "зенит": "#Зенит", "спартак": "#Спартак", "цска": "#ЦСКА", "динамо": "#Динамо",
    "краснодар": "#Краснодар", "локомотив": "#Локомотив", "реал": "#РеалМадрид",
    "барселона": "#Барселона", "сити": "#МанСити", "ливерпуль": "#Ливерпуль",
    "ювентус": "#Ювентус", "псж": "#ПСЖ", "бавария": "#Бавария", "челси": "#Челси",
    "арсенал": "#Арсенал", "мю": "#МЮ", "атлетико": "#Атлетико", "интер": "#Интер",
    "милан": "#Милан", "трансфер": "#трансферы", "инсайд": "#инсайды", "сборная": "#Сборная"
}

bot = telebot.TeleBot(TOKEN)
DB_FILE = "football_history.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Таблица для истории (чтобы не было дублей)
    cursor.execute('''CREATE TABLE IF NOT EXISTS posts 
                      (link TEXT PRIMARY KEY, title TEXT)''')
    # Новая таблица для очереди публикаций
    cursor.execute('''CREATE TABLE IF NOT EXISTS queue 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       title TEXT, link TEXT, description TEXT, source_name TEXT)''')
    conn.commit()
    conn.close()

def is_already_known(link, title):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Проверяем и в истории, и в текущей очереди, чтобы не добавить дважды
    cursor.execute('SELECT 1 FROM posts WHERE link = ? OR title = ?', (link, title))
    res1 = cursor.fetchone()
    cursor.execute('SELECT 1 FROM queue WHERE link = ? OR title = ?', (link, title))
    res2 = cursor.fetchone()
    conn.close()
    return (res1 is not None) or (res2 is not None)

def add_to_queue(title, link, description, source_name):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO queue (title, link, description, source_name) VALUES (?, ?, ?, ?)',
                   (title, link, description, source_name))
    conn.commit()
    conn.close()

def pop_from_queue():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Берем самую старую из добавленных новостей (FIFO очередь)
    cursor.execute('SELECT id, title, link, description, source_name FROM queue ORDER BY id ASC LIMIT 1')
    row = cursor.fetchone()
    if row:
        # Сразу удаляем её из очереди
        cursor.execute('DELETE FROM queue WHERE id = ?', (row[0],))
        conn.commit()
    conn.close()
    return row  # Возвращает данные новости или None

def save_to_history(link, title):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO posts (link, title) VALUES (?, ?)', (link, title))
    conn.commit()
    conn.close()

def clean_and_format(text):
    if not text: return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'Читать далее.*', '', text)
    text = re.sub(r'Читать дальше.*', '', text)
    text = re.sub(r'Подробнее на.*', '', text)
    return text.strip()

def generate_hashtags(title, description):
    full_text = f"{title} {description}".lower()
    found_tags = []
    for keyword, tag in HASHTAGS.items():
        if keyword in full_text:
            found_tags.append(tag)
    return " ".join(found_tags) if found_tags else ""

def scan_rss_sources():
    print("🔄 Сканирую 8 футбольных источников на наличие новинок...")
    new_count = 0
    for source_name, url in SOURCES.items():
        try:
            response = requests.get(url, timeout=10)
            response.encoding = 'utf-8'
            if response.status_code != 200: continue
                
            root = ET.fromstring(response.text)
            items = root.findall('.//item')[:3] # Проверяем топ-3 свежих новости с каждого сайта
            
            for item in items:
                title = clean_and_format(item.find('title').text)
                link = item.find('link').text.strip()
                desc_node = item.find('description')
                description = clean_and_format(desc_node.text) if desc_node is not None else ""
                
                if not is_already_known(link, title):
                    add_to_queue(title, link, description, source_name)
                    new_count += 1
        except Exception as e:
            print(f"⚠️ Ошибка сканирования {source_name}: {e}")
    if new_count > 0:
        print(f"📥 Найдено и добавлено в очередь новых новостей: {new_count}")

def publish_next_post():
    # Достаем новость из очереди
    news = pop_from_queue()
    if not news:
        print("📭 Очередь пуста. Публиковать нечего.")
        return False
        
    _, title, link, description, source_name = news
    
    try:
        if len(description) > 450:
            description = description[:450] + "..."
            
        tags = generate_hashtags(title, description)
        tags_str = f"\n\n📌 {tags}" if tags else ""
        safe_title = title.replace("*", "").replace("_", "")
        
        # Красивый шаблон с призывом
        post_text = (
            f"📰 *{safe_title}*\n\n"
            f"📝 {description}\n\n"
            f"⚡️ Подписывайся на [Ван-Тайм](https://t.me/onetime_foot) — главный футбольный в один клик!{tags_str}"
        )
        
        # Инлайн кнопка
        keyboard = telebot.types.InlineKeyboardMarkup()
        url_button = telebot.types.InlineKeyboardButton(text="Читать подробнее на источнике ➔", url=link)
        keyboard.add(url_button)
        
        # Отправка
        bot.send_message(CHANNEL_ID, post_text, parse_mode="Markdown", disable_web_page_preview=False, reply_markup=keyboard)
        save_to_history(link, title)
        print(f"🚀 [Очередь] Опубликована новость от {source_name}: {title}")
        return True
    except Exception as e:
        print(f"🚨 Ошибка при отправке поста: {e}")
        return False

# Главный цикл управления каналом
init_db()
print("🤖 Футбольный медиа-комбайн 'Ван-Тайм' запущен!")

while True:
    # 1. Собираем свежие новости со всех сайтов в очередь
    scan_rss_sources()
    
    # 2. Пытаемся опубликовать одну верхнюю новость
    posted = publish_next_post()
    
    # 3. Режим ожидания
    if posted:
        # Если новость успешно ушла, строго спим 10 минут (600 секунд) до следующей
        print("⏳ Новость опубликована. Следующая выйдет ровно через 10 минут...")
        time.sleep(600)
    else:
        # Если очередь была пуста, делаем паузу полегче (например, 3 минуты) и проверяем сайты снова
        print("⏳ Ждем 3 минуты до следующей проверки сайтов...")
        time.sleep(180)
