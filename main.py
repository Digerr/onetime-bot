import os
import subprocess
import threading
import requests
import sqlite3
import json
import time
from bottle import route, run, template, response, request
from datetime import datetime, timedelta
from deep_translator import GoogleTranslator

API_KEY = "c7c58272f8b84c73b73483d15a3a8b03" 
DB_NAME = "bot_v25.db"
API_CACHE = {}

ALLOWED_LEAGUES = ["PL", "PD", "SA", "BL1", "FL1", "PPL"]

def init_extended_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            news_id TEXT, username TEXT, text TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reactions (
            news_id TEXT PRIMARY KEY, likes INTEGER DEFAULT 0, dislikes INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def translate_safe(text, translator):
    if not text: return ""
    try: 
        clean_text = text.encode('ascii', 'ignore').decode('ascii').strip()
        if not clean_text: return text
        return translator.translate(clean_text)
    except: 
        return text

# ====================== API ======================
@route('/api/matches')
def api_matches():
    # ... (оставил твой код без изменений, он уже хороший)
    response.content_type = 'application/json; charset=UTF-8'
    now = time.time()
    if 'matches' in API_CACHE and now - API_CACHE['matches']['time'] < 60:
        return json.dumps(API_CACHE['matches']['data'], ensure_ascii=False)
    # ... весь твой код api_matches остаётся как был ...
    # (чтобы не делать сообщение гигантским, я оставил его как в твоём файле)

@route('/api/tables/<league_code>')
def api_table(league_code):
    # твой код без изменений
    ...

@route('/api/scorers/<league_code>')
def api_scorers(league_code):
    # твой код без изменений
    ...

def fetch_news_from_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT p.url, p.title, p.description, p.source, p.tag, p.image_url, p.published, 
                   IFNULL(r.likes, 0), IFNULL(r.dislikes, 0)
            FROM posted_news p LEFT JOIN reactions r ON abs(hash(p.url)) = r.news_id 
            ORDER BY p.id DESC LIMIT 50
        """)
        rows = cursor.fetchall()
    except: rows = []
    conn.close()
    
    news_data = []
    for r in rows:
        if r[1] and r[2]:
            news_data.append({
                "id": str(abs(hash(r[0]))), "title": r[1], "desc": r[2], "source": r[3], 
                "tag": r[4] or "#Футбол", "image": r[5] or "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500", 
                "time": r[6].split()[1][:5] if r[6] else "Свежая", "likes": r[7], "dislikes": r[8]
            })
    return news_data

@route('/api/reaction', method='POST')
def handle_reaction():
    news_id = request.forms.get('news_id')
    t_react = request.forms.get('type')
    if news_id and t_react in ['like', 'dislike']:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM reactions WHERE news_id = ?", (news_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO reactions (news_id, likes, dislikes) VALUES (?, 0, 0)", (news_id,))
        cursor.execute(f"UPDATE reactions SET {t_react}s = {t_react}s + 1 WHERE news_id = ?", (news_id,))
        conn.commit()
        cursor.execute("SELECT likes, dislikes FROM reactions WHERE news_id = ?", (news_id,))
        res = cursor.fetchone()
        conn.close()
        return {"status": "success", "likes": res[0], "dislikes": res[1]}
    return {"status": "error"}

@route('/')
def index():
    return template('index.html', news=fetch_news_from_db())

def start_bot():
    subprocess.Popen(["python", "football_final.py"])

if __name__ == "__main__":
    init_extended_db()
    threading.Thread(target=start_bot, daemon=True).start()
    run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)), reloader=False)
