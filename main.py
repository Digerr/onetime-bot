import os
import subprocess
import threading
import sqlite3
import json
import time
import requests
from bottle import route, run, static_file, response, request
from dotenv import load_dotenv

load_dotenv()

DB_NAME = "bot_v25.db"
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "c7c58272f8b84c73b73483d15a3a8b03")
API_CACHE = {}

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posted_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            description TEXT,
            source TEXT,
            tag TEXT,
            image_url TEXT,
            published TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reactions (
            news_id TEXT PRIMARY KEY, likes INTEGER DEFAULT 0, dislikes INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

@route('/')
def index():
    init_db()
    return static_file('index.html', root='.')

@route('/api/news')
def get_news():
    response.content_type = 'application/json; charset=utf-8'
    init_db()
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT url, title, description, source, tag, image_url, published FROM posted_news ORDER BY id DESC LIMIT 40")
        rows = cursor.fetchall()
        conn.close()
        news = [{"id": str(abs(hash(r[0]))), "title": r[1], "desc": r[2] or "", "source": r[3], "tag": r[4] or "#Футбол", "image": r[5] or "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500", "time": r[6].split()[1][:5] if r[6] else "Свежая"} for r in rows]
        return json.dumps(news, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})

# === ТВОИ ОСТАЛЬНЫЕ API (оставил как у тебя было) ===
@route('/api/matches')
def api_matches():
    # (вставь сюда весь свой код api_matches из предыдущего main.py)
    response.content_type = 'application/json; charset=UTF-8'
    # ... твой код api_matches ...
    return json.dumps([], ensure_ascii=False)  # временно, замени на свой

@route('/api/tables/<league_code>')
def api_table(league_code):
    # твой код
    return json.dumps([], ensure_ascii=False)

@route('/api/scorers/<league_code>')
def api_scorers(league_code):
    # твой код
    return json.dumps([], ensure_ascii=False)

@route('/api/reaction', method='POST')
def handle_reaction():
    # твой код реакции (оставь как был)
    return {"status": "success"}

@route('/<filename:path>')
def server_static(filename):
    return static_file(filename, root='.')

if __name__ == "__main__":
    init_db()
    # Запускаем бота в фоне
    threading.Thread(target=lambda: subprocess.Popen(["python", "football_final.py"]), daemon=True).start()
    run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
