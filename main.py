import os
import subprocess
import threading
import sqlite3
import json
import requests
import time
from bottle import route, run, static_file, response, request

DB_NAME = "bot_v25.db"
CACHE = {}

# Твои таблицы (РПЛ, АПЛ и т.д.)
MOCK_TABLES = {
    "RPL": [{"pos": 1, "name": "Зенит", "games": 28, "won": 17, "draw": 6, "lost": 5, "points": 57}, {"pos": 2, "name": "Краснодар", "games": 28, "won": 16, "draw": 8, "lost": 4, "points": 56}],
    "PL": [{"pos": 1, "name": "Манчестер Сити", "games": 38, "won": 28, "draw": 7, "lost": 3, "points": 91}]
}

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS posted_news (
        id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE, title TEXT, 
        description TEXT, source TEXT, tag TEXT, image_url TEXT, published TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS live_matches (
        id TEXT PRIMARY KEY, home_team TEXT, away_team TEXT, score TEXT, status TEXT, is_live INTEGER, league TEXT)""")
    conn.commit()
    conn.close()

# --- ФУНКЦИЯ ПАРСЕРА, КОТОРУЮ МЫ ЗАПУСТИМ В ФОНЕ НА RAILWAY ---
def background_match_parser():
    while True:
        try:
            # Свободный открытый фид FlashScore-результатов без блокировок хостинга
            url_feed = "https://api.scores24.live/v1/games/today?lang=ru"
            res = requests.get(url_feed, timeout=8)
            if res.status_code == 200:
                data = res.json()
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                
                # Очищаем таблицу перед обновлением игрового дня
                cursor.execute("DELETE FROM live_matches")
                
                for g in data.get("data", [])[:40]:
                    match_id = str(g.get("id"))
                    home = g.get("home_team", {}).get("name")
                    away = g.get("away_team", {}).get("name")
                    league = g.get("league", {}).get("name", "Турнир")
                    h_score = g.get("score", {}).get("home")
                    a_score = g.get("score", {}).get("away")
                    
                    status_id = g.get("status_id", 1) # 2 - идет LIVE
                    is_live = 1 if status_id == 2 else 0
                    
                    if h_score is None:
                        score = "- : -"
                        status = f"🕐 {g.get('time_start', 'Скоро')}"
                    else:
                        score = f"{h_score} : {a_score}"
                        status = "🔴 LIVE" if is_live else "✅ Завершен"
                    
                    cursor.execute("""INSERT OR REPLACE INTO live_matches (id, home_team, away_team, score, status, is_live, league)
                                      VALUES (?, ?, ?, ?, ?, ?, ?)""", (match_id, home, away, score, status, is_live, league))
                conn.commit()
                conn.close()
        except Exception as e:
            print("Ошибка парсера:", e)
        
        # Парсер засыпает на 60 секунд, затем снова обновляет счёт матчей
        time.sleep(60)

@route('/')
def index():
    return static_file('index.html', root='.')

@route('/api/matches')
def get_all_matches():
    response.content_type = 'application/json; charset=utf-8'
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT home_team, away_team, score, status, is_live, league FROM live_matches ORDER BY is_live DESC, id ASC")
    rows = cursor.fetchall()
    conn.close()
    return json.dumps([{"home": r[0], "away": r[1], "home_img": "", "away_img": "", "score": r[2], "status": r[3], "is_live": bool(r[4]), "league": r[5]} for r in rows], ensure_ascii=False)

@route('/api/matches/live')
def get_only_live_matches():
    response.content_type = 'application/json; charset=utf-8'
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT home_team, away_team, score, status, is_live, league FROM live_matches WHERE is_live = 1")
    rows = cursor.fetchall()
    conn.close()
    return json.dumps([{"home": r[0], "away": r[1], "home_img": "", "away_img": "", "score": r[2], "status": r[3], "is_live": True, "league": r[5]} for r in rows], ensure_ascii=False)

@route('/api/tables/<code>')
def get_table(code):
    response.content_type = 'application/json; charset=utf-8'
    return json.dumps(MOCK_TABLES.get(code, MOCK_TABLES["PL"]), ensure_ascii=False)

@route('/<filename:path>')
def server_static(filename):
    return static_file(filename, root='.')

if __name__ == "__main__":
    init_db()
    # 1. ЗАПУСКАЕМ НАШ ПАРСЕР МАТЧЕЙ В ФОНЕ СЕРВЕРА
    threading.Thread(target=background_match_parser, daemon=True).start()
    # 2. ЗАПУСКАЕМ ТВОЕГО БОТА НОВОСТЕЙ
    threading.Thread(target=lambda: subprocess.Popen(["python", "football_final.py"]), daemon=True).start()
    # 3. СТАРТУЕМ САЙТ ВАН-ТАЙМ
    run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
    
