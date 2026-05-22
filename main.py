import os
import subprocess
import threading
import requests
import sqlite3
import json
from bottle import route, run, template, response, request

DB_NAME = "bot_v25.db"

def init_extended_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            news_id TEXT,
            username TEXT,
            text TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reactions (
            news_id TEXT PRIMARY KEY,
            likes INTEGER DEFAULT 0,
            dislikes INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def get_today_matches():
    matches = []
    try:
        url = "https://www.scorebat.com/video-api/v3/"
        res = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if res.status_code == 200:
            data = res.json()
            for item in data.get('response', [])[:10]:
                title = item.get('title', '')
                video_url = item.get('matchviewUrl', '')
                status = "Завершен" if video_url else "LIVE / Скоро"
                if " - " in title:
                    matches.append({"teams": title, "status": status, "video": video_url})
    except Exception:
        pass
    if not matches:
        matches = [
            {"teams": "Матчи лиг появятся перед началом туров", "status": "Ожидание", "video": ""},
            {"teams": "Следите за обновлениями ВАН-ТАЙМ", "status": "Инфо", "video": ""}
        ]
    return matches

def fetch_news_from_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT p.url, p.title, p.description, p.source, p.tag, p.image_url, p.published, 
                   IFNULL(r.likes, 0), IFNULL(r.dislikes, 0)
            FROM posted_news p
            LEFT JOIN reactions r ON abs(hash(p.url)) = r.news_id
            ORDER BY p.id DESC LIMIT 40
        """)
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    
    news_data = []
    for r in rows:
        if r[1] and r[2]:
            img = r[5] if r[5] else "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500"
            tag = r[4] if r[4] else "#Футбол"
            time_str = "00:00"
            if r[6]:
                try: time_str = r[6].split()[1][:5]
                except Exception: time_str = "Свежая"
            news_id = str(abs(hash(r[0])))
            news_data.append({
                "id": news_id, "title": r[1], "desc": r[2], "source": r[3], 
                "tag": tag, "image": img, "time": time_str, "likes": r[7], "dislikes": r[8]
            })
    return news_data

@route('/api/reaction', method='POST')
def handle_reaction():
    news_id = request.forms.get('news_id')
    type_reaction = request.forms.get('type')
    if news_id and type_reaction:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM reactions WHERE news_id = ?", (news_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO reactions (news_id, likes, dislikes) VALUES (?, 0, 0)", (news_id,))
        if type_reaction == 'like':
            cursor.execute("UPDATE reactions SET likes = likes + 1 WHERE news_id = ?", (news_id,))
        elif type_reaction == 'dislike':
            cursor.execute("UPDATE reactions SET dislikes = dislikes + 1 WHERE news_id = ?", (news_id,))
        conn.commit()
        cursor.execute("SELECT likes, dislikes FROM reactions WHERE news_id = ?", (news_id,))
        res = cursor.fetchone()
        conn.close()
        return {"status": "success", "likes": res[0], "dislikes": res[1]}
    return {"status": "error"}

@route('/api/comments/add', method='POST')
def add_comment():
    news_id = request.forms.get('news_id')
    username = request.forms.get('username') or "Аноним"
    text = request.forms.get('text')
    if news_id and text:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO comments (news_id, username, text) VALUES (?, ?, ?)", (news_id, username, text))
        conn.commit()
        conn.close()
        return {"status": "success"}
    return {"status": "error"}

@route('/api/comments/<news_id>')
def get_comments(news_id):
    response.content_type = 'application/json; charset=UTF-8'
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT username, text, timestamp FROM comments WHERE news_id = ? ORDER BY id DESC", (news_id,))
    rows = cursor.fetchall()
    conn.close()
    comments = [{"username": r[0], "text": r[1], "time": r[2].split()[1][:5] if r[2] else ""} for r in rows]
    return json.dumps(comments, ensure_ascii=False)

@route('/')
def index():
    news_data = fetch_news_from_db()
    if not news_data:
        news_data = [{
            "id": "0", "title": "Лента «ВАН-ТАЙМ» обновляется", "desc": "Бот собирает свежие футбольные инсайды...", 
            "source": "Система", "tag": "#Футбол", "image": "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500", 
            "time": "Сейчас", "likes": 0, "dislikes": 0
        }]
    matches_today = get_today_matches()
    # Читаем шаблон интерфейса напрямую из отдельного файла html
    return template('index.html', news=news_data, matches=matches_today)

def start_bot():
    subprocess.Popen(["python", "football_final.py"])

if __name__ == "__main__":
    init_extended_db()
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    run(host='0.0.0.0', port=port)
    
