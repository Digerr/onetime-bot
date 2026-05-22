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

# Список поддерживаемых лиг для валидации
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
    if len(text) > 40: return text
    try: 
        clean_text = text.encode('ascii', 'ignore').decode('ascii').strip()
        if not clean_text: return text
        return translator.translate(clean_text)
    except: 
        return text

@route('/api/matches')
def api_matches():
    response.content_type = 'application/json; charset=UTF-8'
    now = time.time()
    if 'matches' in API_CACHE and now - API_CACHE['matches']['time'] < 60:
        return json.dumps(API_CACHE['matches']['data'], ensure_ascii=False)

    headers = {'X-Auth-Token': API_KEY}
    live_matches = []
    translator = GoogleTranslator(source='auto', target='ru')
    date_from = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    date_to = (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')
    
    try:
        res = requests.get(f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}", headers=headers, timeout=6)
        if res.status_code == 200:
            for m in res.json().get('matches', [])[:30]:
                h_name = translate_safe(m['homeTeam']['name'], translator)
                a_name = translate_safe(m['awayTeam']['name'], translator)
                
                # Имена авторов голов оставляем в оригинале
                scorers_text = ""
                if m.get('goals'):
                    scorers_list = [f"{g.get('scorer', {}).get('name', 'Player')} {g.get('minute', '')}'" for g in m['goals']]
                    scorers_text = "⚽ " + ", ".join(scorers_list)
                
                raw_status = m.get('status', '')
                if raw_status == 'IN_PLAY': status = "LIVE 🔥"
                elif raw_status == 'FINISHED': status = "Завершен"
                else:
                    try: status = f"{m['utcDate'].split('T')[0].split('-')[2]} мая, {m['utcDate'].split('T')[1][:5]}"
                    except: status = "Скоро"

                live_matches.append({
                    "home": h_name, "home_img": m['homeTeam'].get('crest', ''),
                    "away": a_name, "away_img": m['awayTeam'].get('crest', ''),
                    "score": f"{m['score']['fullTime']['home'] if m['score']['fullTime']['home'] is not None else '-'} : {m['score']['fullTime']['away'] if m['score']['fullTime']['away'] is not None else '-'}",
                    "status": status, "league": translate_safe(m['competition']['name'], translator),
                    "league_img": m['competition'].get('emblem', ''), "scorers": scorers_text
                })
    except: pass
    API_CACHE['matches'] = {'data': live_matches, 'time': now}
    return json.dumps(live_matches, ensure_ascii=False)

@route('/api/tables/<league_code>')
def api_table(league_code):
    response.content_type = 'application/json; charset=UTF-8'
    if league_code not in ALLOWED_LEAGUES: return json.dumps([])
    
    now = time.time()
    cache_key = f'table_{league_code}'
    if cache_key in API_CACHE and now - API_CACHE[cache_key]['time'] < 300:
        return json.dumps(API_CACHE[cache_key]['data'], ensure_ascii=False)

    headers = {'X-Auth-Token': API_KEY}
    table_data = []
    translator = GoogleTranslator(source='auto', target='ru')
    try:
        res = requests.get(f"https://api.football-data.org/v4/competitions/{league_code}/standings", headers=headers, timeout=5)
        if res.status_code == 200:
            standings = res.json().get('standings', [])
            if standings:
                for team in standings[0].get('table', [])[:15]:
                    table_data.append({
                        "pos": team['position'], "name": translate_safe(team['team']['name'], translator),
                        "crest": team['team'].get('crest', ''), "games": team['playedGames'],
                        "won": team['won'], "draw": team['draw'], "lost": team['lost'],
                        "goals": f"{team['goalsFor']}-{team['goalsAgainst']}", "points": team['points']
                    })
    except: pass
    API_CACHE[cache_key] = {'data': table_data, 'time': now}
    return json.dumps(table_data, ensure_ascii=False)

@route('/api/scorers/<league_code>')
def api_scorers(league_code):
    response.content_type = 'application/json; charset=UTF-8'
    if league_code not in ALLOWED_LEAGUES: return json.dumps([])
    
    now = time.time()
    cache_key = f'scorers_{league_code}'
    if cache_key in API_CACHE and now - API_CACHE[cache_key]['time'] < 300:
        return json.dumps(API_CACHE[cache_key]['data'], ensure_ascii=False)

    headers = {'X-Auth-Token': API_KEY}
    scorers_data = []
    translator = GoogleTranslator(source='auto', target='ru')
    try:
        res = requests.get(f"https://api.football-data.org/v4/competitions/{league_code}/scorers", headers=headers, timeout=5)
        if res.status_code == 200:
            for s in res.json().get('scorers', [])[:10]:
                p_name = s.get('player', {}).get('name', 'Игрок') # Оставляем в оригинале (без перевода)
                t_name = s.get('team', {}).get('name', 'Клуб')
                scorers_data.append({
                    "name": p_name,
                    "team": translate_safe(t_name, translator),
                    "goals": s.get('goals', 0), 
                    "assists": s.get('assists') if s.get('assists') is not None else 0
                })
    except: pass
    API_CACHE[cache_key] = {'data': scorers_data, 'time': now}
    return json.dumps(scorers_data, ensure_ascii=False)

def fetch_news_from_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT p.url, p.title, p.description, p.source, p.tag, p.image_url, p.published, 
                   IFNULL(r.likes, 0), IFNULL(r.dislikes, 0)
            FROM posted_news p LEFT JOIN reactions r ON abs(hash(p.url)) = r.news_id ORDER BY p.id DESC LIMIT 40
        """)
        rows = cursor.fetchall()
    except: rows = []
    conn.close()
    
    news_data = []
    for r in rows:
        if r[1] and r[2]:
            news_data.append({
                "id": str(abs(hash(r[0]))), "title": r[1], "desc": r[2], "source": r[3], 
                "tag": r[4] if r[4] else "#Футбол", "image": r[5] if r[5] else "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500", 
                "time": r[6].split()[1][:5] if r[6] else "Свежая", "likes": r[7], "dislikes": r[8]
            })
    return news_data

@route('/api/reaction', method='POST')
def handle_reaction():
    news_id, t_react = request.forms.get('news_id'), request.forms.get('type')
    if news_id and t_react:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM reactions WHERE news_id = ?", (news_id,))
        if not cursor.fetchone(): cursor.execute("INSERT INTO reactions (news_id, likes, dislikes) VALUES (?, 0, 0)", (news_id,))
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

def start_bot(): subprocess.Popen(["python", "football_final.py"])

if __name__ == "__main__":
    init_extended_db()
    threading.Thread(target=start_bot, daemon=True).start()
    run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
    
