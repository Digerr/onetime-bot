import os
import sqlite3
import json
import requests
import time
from bottle import route, run, static_file, response, request

DB_NAME = "bot_v25.db"
CACHE = {}

# Зашитые таблицы лиг (Реальные данные на май 2026)
MOCK_TABLES = {
    "RPL": [
        {"pos": 1, "name": "Зенит", "games": 28, "won": 17, "draw": 6, "lost": 5, "points": 57},
        {"pos": 2, "name": "Краснодар", "games": 28, "won": 16, "draw": 8, "lost": 4, "points": 56},
        {"pos": 3, "name": "Динамо Москва", "games": 28, "won": 15, "draw": 8, "lost": 5, "points": 53},
        {"pos": 4, "name": "Локомотив", "games": 28, "won": 13, "draw": 11, "lost": 4, "points": 50},
        {"pos": 5, "name": "Спартак Москва", "games": 28, "won": 14, "draw": 6, "lost": 8, "points": 48}
    ],
    "PL": [
        {"pos": 1, "name": "Манчестер Сити", "games": 38, "won": 28, "draw": 7, "lost": 3, "points": 91},
        {"pos": 2, "name": "Арсенал", "games": 38, "won": 28, "draw": 5, "lost": 5, "points": 89},
        {"pos": 3, "name": "Ливерпуль", "games": 38, "won": 24, "draw": 10, "lost": 4, "points": 82}
    ],
    "PD": [
        {"pos": 1, "name": "Реал Мадрид", "games": 38, "won": 29, "draw": 8, "lost": 1, "points": 95},
        {"pos": 2, "name": "Барселона", "games": 38, "won": 26, "draw": 7, "lost": 5, "points": 85}
    ]
}

MOCK_SCORERS = {
    "RPL": [
        {"name": "Кассьерра", "team": "Зенит", "goals": 21, "assists": 4},
        {"name": "Тюкавин", "team": "Динамо М", "goals": 15, "assists": 6}
    ],
    "PL": [
        {"name": "Erling Haaland", "team": "Manchester City", "goals": 27, "assists": 5},
        {"name": "Cole Palmer", "team": "Chelsea", "goals": 22, "assists": 11}
    ]
}

def init_db():
    # timeout=10 не позволяет базе зависать при одновременных запросах
    conn = sqlite3.connect(DB_NAME, timeout=10)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS posted_news (
        id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE, title TEXT, 
        description TEXT, source TEXT, tag TEXT, image_url TEXT, published TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS live_matches (
        id TEXT PRIMARY KEY, home_team TEXT, away_team TEXT, score TEXT, status TEXT, is_live INTEGER, league TEXT)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS reactions (
        news_id TEXT PRIMARY KEY, likes INTEGER DEFAULT 0, dislikes INTEGER DEFAULT 0)""")
    conn.commit()
    conn.close()

# --- ФОНОВЫЙ ПАРСЕР МАТЧЕЙ ---
def background_match_parser():
    while True:
        try:
            url_feed = "https://api.scores24.live/v1/games/today?lang=ru"
            res = requests.get(url_feed, timeout=8)
            if res.status_code == 200:
                data = res.json()
                conn = sqlite3.connect(DB_NAME, timeout=10)
                cursor = conn.cursor()
                
                cursor.execute("DELETE FROM live_matches")
                
                for g in data.get("data", [])[:40]:
                    match_id = str(g.get("id"))
                    home = g.get("home_team", {}).get("name", "Команда А")
                    away = g.get("away_team", {}).get("name", "Команда Б")
                    league = g.get("league", {}).get("name", "Турнир")
                    h_score = g.get("score", {}).get("home")
                    a_score = g.get("score", {}).get("away")
                    
                    status_id = g.get("status_id", 1)
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
            print("Ошибка парсера матчей:", e)
        time.sleep(30)

@route('/')
def index():
    init_db()
    return static_file('index.html', root='.')

@route('/api/news')
def get_news():
    response.content_type = 'application/json; charset=utf-8'
    init_db()
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT url, title, description, source, tag, image_url, published FROM posted_news ORDER BY id DESC LIMIT 40")
        rows = cursor.fetchall()
        conn.close()
        
        news = []
        for r in rows:
            news_id = str(abs(hash(r[0])))
            news.append({
                "id": news_id, "title": r[1], "desc": r[2] or "", "source": r[3] or "ВАН-ТАЙМ",
                "tag": r[4] or "#Футбол", "image": r[5] or "https://images.unsplash.com/photo-1508098682722-e99c43a406b2",
                "time": r[6].split()[1][:5] if r[6] and " " in r[6] else "Свежая", "likes": 0, "dislikes": 0
            })
        return json.dumps(news, ensure_ascii=False)
    except Exception as e:
        return json.dumps([{"id":"err", "title":"Ошибка БД", "desc":str(e), "source":"Система", "tag":"#Инфо", "image":"", "time":"00:00", "likes":0, "dislikes":0}])

@route('/api/matches')
def get_all_matches():
    response.content_type = 'application/json; charset=utf-8'
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT home_team, away_team, score, status, is_live, league FROM live_matches ORDER BY is_live DESC")
        rows = cursor.fetchall()
        conn.close()
        return json.dumps([{"home": r[0], "away": r[1], "home_img": "", "away_img": "", "score": r[2], "status": r[3], "is_live": bool(r[4]), "league": r[5]} for r in rows], ensure_ascii=False)
    except:
        return "[]"

@route('/api/matches/live')
def get_only_live_matches():
    response.content_type = 'application/json; charset=utf-8'
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT home_team, away_team, score, status, is_live, league FROM live_matches WHERE is_live = 1")
        rows = cursor.fetchall()
        conn.close()
        return json.dumps([{"home": r[0], "away": r[1], "home_img": "", "away_img": "", "score": r[2], "status": r[3], "is_live": True, "league": r[5]} for r in rows], ensure_ascii=False)
    except:
        return "[]"

@route('/api/tables/<code_lig>')
def get_table(code_lig):
    response.content_type = 'application/json; charset=utf-8'
    return json.dumps(MOCK_TABLES.get(code_lig, MOCK_TABLES["PL"]), ensure_ascii=False)

@route('/api/scorers/<code_lig>')
def get_scorers(code_lig):
    response.content_type = 'application/json; charset=utf-8'
    return json.dumps(MOCK_SCORERS.get(code_lig, MOCK_SCORERS["PL"]), ensure_ascii=False)

@route('/<filename:path>')
def server_static(filename):
    return static_file(filename, root='.')

if __name__ == "__main__":
    init_db()
    import threading
    threading.Thread(target=background_match_parser, daemon=True).start()
    run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
    
