import os
import subprocess
import threading
import sqlite3
import json
import requests
import time
from bottle import route, run, static_file, response, request
from bs4 import BeautifulSoup

DB_NAME = "bot_v25.db"
CACHE = {}

# Железобетонные таблицы (РПЛ, АПЛ, Ла Лига)
MOCK_TABLES = {
    "RPL": [
        {"pos": 1, "name": "Зенит", "games": 24, "won": 15, "draw": 5, "lost": 4, "points": 50},
        {"pos": 2, "name": "Краснодар", "games": 24, "won": 14, "draw": 7, "lost": 3, "points": 49},
        {"pos": 3, "name": "Динамо Москва", "games": 24, "won": 12, "draw": 8, "lost": 4, "points": 44},
        {"pos": 4, "name": "Локомотив", "games": 24, "won": 10, "draw": 11, "lost": 3, "points": 41},
        {"pos": 5, "name": "Спартак Москва", "games": 24, "won": 11, "draw": 5, "lost": 8, "points": 38},
        {"pos": 6, "name": "ЦСКА Москва", "games": 24, "won": 9, "draw": 10, "lost": 5, "points": 37}
    ],
    "PL": [
        {"pos": 1, "name": "Арсенал", "games": 35, "won": 25, "draw": 5, "lost": 5, "points": 80},
        {"pos": 2, "name": "Манчестер Сити", "games": 34, "won": 24, "draw": 7, "lost": 3, "points": 79},
        {"pos": 3, "name": "Ливерпуль", "games": 35, "won": 22, "draw": 9, "lost": 4, "points": 75},
        {"pos": 4, "name": "Астон Вилла", "games": 35, "won": 20, "draw": 7, "lost": 8, "points": 67}
    ],
    "PD": [
        {"pos": 1, "name": "Реал Мадрид", "games": 33, "won": 26, "draw": 6, "lost": 1, "points": 84},
        {"pos": 2, "name": "Барселона", "games": 33, "won": 22, "draw": 7, "lost": 4, "points": 73},
        {"pos": 3, "name": "Жирона", "games": 33, "won": 22, "draw": 5, "lost": 6, "points": 71}
    ]
}

MOCK_SCORERS = {
    "RPL": [
        {"name": "Кассьерра", "team": "Зенит", "goals": 16, "assists": 3},
        {"name": "Тюкавин", "team": "Динамо М", "goals": 13, "assists": 4},
        {"name": "Кордоба", "team": "Краснодар", "goals": 12, "assists": 2}
    ],
    "PL": [
        {"name": "Erling Haaland", "team": "Manchester City", "goals": 27, "assists": 8},
        {"name": "Cole Palmer", "team": "Chelsea", "goals": 22, "assists": 11},
        {"name": "Ollie Watkins", "team": "Aston Villa", "goals": 19, "assists": 12}
    ]
}

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS posted_news (
        id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE, title TEXT, 
        description TEXT, source TEXT, tag TEXT, image_url TEXT, published TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS reactions (
        news_id TEXT PRIMARY KEY, likes INTEGER DEFAULT 0, dislikes INTEGER DEFAULT 0)""")
    conn.commit()
    conn.close()

@route('/')
def index():
    init_db()
    return static_file('index.html', root='.')

@route('/api/news')
def get_news():
    response.content_type = 'application/json; charset=utf-8'
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT url, title, description, source, tag, image_url, published FROM posted_news ORDER BY id DESC LIMIT 40")
        rows = cursor.fetchall()
        conn.close()
        
        news = []
        for r in rows:
            news_id = str(abs(hash(r[0])))
            conn_r = sqlite3.connect(DB_NAME)
            cur_r = conn_r.cursor()
            cur_r.execute("SELECT likes, dislikes FROM reactions WHERE news_id = ?", (news_id,))
            react = cur_r.fetchone()
            conn_r.close()
            
            news.append({
                "id": news_id, "title": r[1], "desc": r[2] or "", "source": r[3] or "ВАН-ТАЙМ",
                "tag": r[4] or "#Футбол", "image": r[5] or "https://images.unsplash.com/photo-1508098682722-e99c43a406b2",
                "time": r[6].split()[1][:5] if r[6] and " " in r[6] else "Свежая",
                "likes": react[0] if react else 0, "dislikes": react[1] if react else 0
            })
        return json.dumps(news, ensure_ascii=False)
    except:
        return json.dumps([])

# --- ЖЕЛЕЗОБЕТОННЫЙ ПАРСЕР ТЕКУЩИХ МАТЧЕЙ С LIVERESULT ---
def parse_liveresult_matches():
    now = time.time()
    if 'matches' in CACHE and now - CACHE['matches']['time'] < 30:
        return CACHE['matches']['data']

    matches = []
    try:
        url = "https://www.liveresult.ru/football/matches/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(url, headers=headers, timeout=6)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            # Находим контейнеры матчей на сегодня
            match_rows = soup.find_all('div', class_='match-row')
            
            for row in match_rows:
                try:
                    # Извлекаем названия команд
                    teams = row.find_all('div', class_='team-name')
                    if len(teams) < 2: continue
                    home = teams[0].text.strip()
                    away = teams[1].text.strip()
                    
                    # Извлекаем счет
                    score_text = row.find('div', class_='match-score').text.strip().replace(' ', '')
                    if not score_text or '—' in score_text:
                        score = "- : -"
                    else:
                        score = score_text.replace(':', ' : ')
                    
                    # Извлекаем статус / время матча
                    status_box = row.find('div', class_='match-status')
                    status_text = status_box.text.strip().lower() if status_box else ""
                    
                    is_live = False
                    if "идёт" in status_text or "live" in status_text or "перерыв" in status_text or "'" in status_text or "мин" in status_text:
                        status = "🔴 LIVE"
                        is_live = True
                    elif "завершен" in status_text or "фт" in status_text or "матч окончен" in status_text:
                        status = "✅ Завершен"
                    else:
                        # Если там просто время (например 18:30)
                        status = f"🕐 {status_text.upper() if status_text else 'СКОРО'}"
                        
                    # Извлекаем название лиги/турнира
                    try:
                        league = row.find_previous('div', class_='category-header').text.strip()
                    except:
                        league = "Топ-Турнир"

                    matches.append({
                        "home": home, "away": away, "home_img": "", "away_img": "",
                        "score": score, "status": status, "is_live": is_live, "league": league
                    })
                except:
                    continue
    except Exception as e:
        print("Ошибка парсинга матчей:", e)

    # Если в текущую минуту на сайте пусто или идет пересчет туров, выдаем чистый пустой список,
    # чтобы фронтенд красиво вывел плашку "Активных матчей нет" без архивного мусора
    CACHE['matches'] = {'data': matches, 'time': now}
    return matches

@route('/api/matches')
def get_all_matches():
    response.content_type = 'application/json; charset=utf-8'
    return json.dumps(parse_liveresult_matches(), ensure_ascii=False)

@route('/api/matches/live')
def get_only_live_matches():
    response.content_type = 'application/json; charset=utf-8'
    all_m = parse_liveresult_matches()
    live_m = [m for m in all_m if m["is_live"]]
    return json.dumps(live_m, ensure_ascii=False)

@route('/api/tables/<code>')
def get_table(code):
    response.content_type = 'application/json; charset=utf-8'
    res = MOCK_TABLES.get(code, MOCK_TABLES["PL"])
    return json.dumps(res, ensure_ascii=False)

@route('/api/scorers/<code>')
def get_scorers(code):
    response.content_type = 'application/json; charset=utf-8'
    res = MOCK_SCORERS.get(code, MOCK_SCORERS["PL"])
    return json.dumps(res, ensure_ascii=False)

@route('/api/reaction', method='POST')
def handle_reaction():
    news_id = request.forms.get('news_id')
    t = request.forms.get('type')
    if news_id and t in ['like','dislike']:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO reactions (news_id) VALUES (?)", (news_id,))
        cursor.execute(f"UPDATE reactions SET {t}s = {t}s + 1 WHERE news_id = ?", (news_id,))
        conn.commit()
        cursor.execute("SELECT likes, dislikes FROM reactions WHERE news_id = ?", (news_id,))
        res = cursor.fetchone()
        conn.close()
        return {"status":"success", "likes":res[0], "dislikes":res[1]}
    return {"status":"error"}

@route('/<filename:path>')
def server_static(filename):
    return static_file(filename, root='.')

if __name__ == "__main__":
    init_db()
    threading.Thread(target=lambda: subprocess.Popen(["python", "football_final.py"]), daemon=True).start()
    run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
    
