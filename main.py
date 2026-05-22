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

# Маппинг лиг для Sports.ru
SPORTS_LEAGUE_MAP = {
    "RPL": "rpl",
    "PL": "epl",
    "PD": "la-liga",
    "SA": "seria-a",
    "BL1": "bundesliga",
    "FL1": "ligue-1"
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

# --- ПАРСЕР ЦЕНТРА МАТЧЕЙ С SPORTS.RU ---
def parse_sports_matches():
    now = time.time()
    if 'matches' in CACHE and now - CACHE['matches']['time'] < 40:
        return CACHE['matches']['data']

    matches = []
    try:
        url = "https://m.sports.ru/stat/football/center/"
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15"}
        res = requests.get(url, headers=headers, timeout=7)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            # Находим блоки матчей в мобильной версии
            match_items = soup.find_all('div', class_='match-item')
            
            for item in match_items:
                try:
                    league = item.find_previous('div', class_='title-block').text.strip()
                except:
                    league = "Турнир"
                    
                teams = item.find_all('div', class_='team-name')
                if len(teams) < 2: continue
                home = teams[0].text.strip()
                away = teams[1].text.strip()
                
                try:
                    score_box = item.find('div', class_='score').text.strip().replace('\n', '').replace(' ', '')
                except:
                    score_box = "- : -"
                
                status_box = item.find('div', class_='status')
                status_text = status_box.text.strip().lower() if status_box else ""
                
                is_live = False
                if "идёт" in status_text or "live" in status_text or "тайм" in status_text or "'" in status_text:
                    status = "🔴 LIVE"
                    is_live = True
                elif "завершен" in status_text or "финал" in status_text:
                    status = "✅ Завершен"
                else:
                    status = f"🕐 {status_text.upper() or 'Скоро'}"

                matches.append({
                    "home": home, "away": away, "home_img": "", "away_img": "",
                    "score": score_box if ":" in score_box else f"{score_box[0]} : {score_box[1]}" if len(score_box)==2 else "0 : 0",
                    "status": status, "is_live": is_live, "league": league
                })
    except Exception as e:
        print("Ошибка матчей:", e)

    CACHE['matches'] = {'data': matches, 'time': now}
    return matches

@route('/api/matches')
def get_all_matches():
    response.content_type = 'application/json; charset=utf-8'
    return json.dumps(parse_sports_matches(), ensure_ascii=False)

@route('/api/matches/live')
def get_only_live_matches():
    response.content_type = 'application/json; charset=utf-8'
    all_m = parse_sports_matches()
    live_m = [m for m in all_m if m["is_live"]]
    return json.dumps(live_m, ensure_ascii=False)

# --- ПАРСЕР ТАБЛИЦ С SPORTS.RU ---
@route('/api/tables/<code>')
def get_table(code):
    response.content_type = 'application/json; charset=utf-8'
    now = time.time()
    cache_key = f"table_{code}"
    if cache_key in CACHE and now - CACHE[cache_key]['time'] < 300:
        return json.dumps(CACHE[cache_key]['data'], ensure_ascii=False)

    table_data = []
    try:
        league_slug = SPORTS_LEAGUE_MAP.get(code, "rpl")
        url = f"https://m.sports.ru/{league_slug}/table/"
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X)"}
        res = requests.get(url, headers=headers, timeout=6)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            table = soup.find('table', class_='stat-table') or soup.find('table')
            rows = table.find_all('tr')[1[:16]] if table else [] # берем топ-15 команд
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 4: continue
                
                pos = cols[0].text.strip().replace('.', '')
                name = cols[1].text.strip()
                games = cols[2].text.strip()
                won = cols[3].text.strip()
                draw = cols[4].text.strip()
                lost = cols[5].text.strip()
                points = cols[-1].text.strip()
                
                table_data.append({
                    "pos": pos, "name": name, "crest": "",
                    "games": games, "won": won, "draw": draw, "lost": lost, "points": points
                })
    except Exception as e:
        print("Ошибка таблиц:", e)
        
    CACHE[cache_key] = {'data': table_data, 'time': now}
    return json.dumps(table_data, ensure_ascii=False)

# --- ПАРСЕР БОМБАРДИРОВ С SPORTS.RU ---
@route('/api/scorers/<code>')
def get_scorers(code):
    response.content_type = 'application/json; charset=utf-8'
    now = time.time()
    cache_key = f"scorers_{code}"
    if cache_key in CACHE and now - CACHE[cache_key]['time'] < 300:
        return json.dumps(CACHE[cache_key]['data'], ensure_ascii=False)

    scorers_data = []
    try:
        league_slug = SPORTS_LEAGUE_MAP.get(code, "rpl")
        url = f"https://www.sports.ru/{league_slug}/top-scorers/"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=6)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            table = soup.find('table', class_='stat-table')
            if table:
                rows = table.find_all('tr')[1:11]
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 4: continue
                    name = cols[1].text.strip().split('\n')[0]
                    team = cols[2].text.strip()
                    goals = cols[3].text.strip()
                    assists = cols[4].text.strip() if len(cols) > 4 else "0"
                    
                    scorers_data.append({
                        "name": name, "team": team, "goals": goals, "assists": assists
                    })
    except Exception as e:
        print("Ошибка бомбардиров:", e)
        
    CACHE[cache_key] = {'data': scorers_data, 'time': now}
    return json.dumps(scorers_data, ensure_ascii=False)

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
    
