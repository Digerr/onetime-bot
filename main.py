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

# Твой рабочий API-ключ
API_KEY = "c7c58272f8b84c73b73483d15a3a8b03" 
DB_NAME = "bot_v25.db"

# Умный кэш для защиты от блокировки API (сохраняет данные на 60 секунд)
API_CACHE = {}

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
    if not text or len(text) > 30: return text
    try: return translator.translate(text)
    except: return text

def get_live_matches_365():
    now = time.time()
    if 'matches' in API_CACHE and now - API_CACHE['matches']['time'] < 60:
        return API_CACHE['matches']['data']

    headers = {'X-Auth-Token': API_KEY}
    live_matches = []
    translator = GoogleTranslator(source='auto', target='ru')
    date_from = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    date_to = (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')
    
    try:
        res = requests.get(f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}", headers=headers, timeout=6)
        if res.status_code == 200:
            for m in res.json().get('matches', [])[:25]:
                h_name = translate_safe(m['homeTeam']['name'], translator)
                a_name = translate_safe(m['awayTeam']['name'], translator)
                h_crest = m['homeTeam'].get('crest', '')
                a_crest = m['awayTeam'].get('crest', '')
                league_name = translate_safe(m['competition']['name'], translator)
                league_flag = m['competition'].get('emblem', '')
                
                h_score = m['score']['fullTime']['home'] if m['score']['fullTime']['home'] is not None else '-'
                a_score = m['score']['fullTime']['away'] if m['score']['fullTime']['away'] is not None else '-'
                
                scorers_text = ""
                if m.get('goals'):
                    scorers_list = [f"{translate_safe(g.get('scorer', {}).get('name', ''), translator)} {g.get('minute', '')}'" for g in m['goals']]
                    scorers_text = "⚽ " + ", ".join(scorers_list)
                
                raw_status = m.get('status', '')
                if raw_status == 'IN_PLAY': status = "LIVE 🔥"
                elif raw_status == 'FINISHED': status = "Завершен"
                else:
                    try: status = f"{m['utcDate'].split('T')[0].split('-')[2]} мая, {m['utcDate'].split('T')[1][:5]}"
                    except: status = "Скоро"

                live_matches.append({
                    "home": h_name, "home_img": h_crest, "away": a_name, "away_img": a_crest,
                    "score": f"{h_score} : {a_score}", "status": status,
                    "league": league_name, "league_img": league_flag, "scorers": scorers_text
                })
    except Exception: pass
    
    if not live_matches: live_matches = [{"home": "Матчей", "home_img": "", "away": "Нет", "away_img": "", "score": "-", "status": "Ожидание", "league": "Центр LIVE", "league_img": "", "scorers": ""}]
    
    API_CACHE['matches'] = {'data': live_matches, 'time': now}
    return live_matches

def get_real_table(league_code):
    now = time.time()
    cache_key = f'table_{league_code}'
    if cache_key in API_CACHE and now - API_CACHE[cache_key]['time'] < 300:
        return API_CACHE[cache_key]['data']

    headers = {'X-Auth-Token': API_KEY}
    table_data = []
    translator = GoogleTranslator(source='auto', target='ru')
    try:
        res = requests.get(f"https://api.football-data.org/v4/competitions/{league_code}/standings", headers=headers, timeout=5)
        if res.status_code == 200:
            standings = res.json().get('standings', [])
            if standings:
                for team in standings[0].get('table', [])[:10]:
                    table_data.append({
                        "pos": team['position'],
                        "name": translate_safe(team['team']['name'], translator),
                        "crest": team['team'].get('crest', ''),
                        "games": team['playedGames'],
                        "won": team['won'], "draw": team['draw'], "lost": team['lost'],
                        "goals": f"{team['goalsFor']}-{team['goalsAgainst']}",
                        "points": team['points']
                    })
    except Exception: pass
    
    API_CACHE[cache_key] = {'data': table_data, 'time': now}
    return table_data

def get_top_scorers(league_code):
    now = time.time()
    cache_key = f'scorers_{league_code}'
    if cache_key in API_CACHE and now - API_CACHE[cache_key]['time'] < 300:
        return API_CACHE[cache_key]['data']

    headers = {'X-Auth-Token': API_KEY}
    scorers_data = []
    translator = GoogleTranslator(source='auto', target='ru')
    try:
        res = requests.get(f"https://api.football-data.org/v4/competitions/{league_code}/scorers", headers=headers, timeout=5)
        if res.status_code == 200:
            for s in res.json().get('scorers', [])[:10]:
                scorers_data.append({
                    "name": translate_safe(s['player']['name'], translator),
                    "team": translate_safe(s['team']['name'], translator),
                    "goals": s['goals'],
                    "assists": s.get('assists') or 0
                })
    except Exception: pass
    
    API_CACHE[cache_key] = {'data': scorers_data, 'time': now}
    return scorers_data

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
            news_id = str(abs(hash(r[0])))
            news_data.append({
                "id": news_id, "title": r[1], "desc": r[2], "source": r[3], 
                "tag": r[4] if r[4] else "#Футбол", "image": r[5] if r[5] else "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500", 
                "time": r[6].split()[1][:5] if r[6] else "Свежая", "likes": r[7], "dislikes": r[8]
            })
    return news_data

@route('/api/reaction', method='POST')
def handle_reaction():
    news_id = request.forms.get('news_id')
    t_react = request.forms.get('type')
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

@route('/api/comments/add', method='POST')
def add_comment():
    news_id, username, text = request.forms.get('news_id'), request.forms.get('username') or "Аноним", request.forms.get('text')
    if news_id and text:
        conn = sqlite3.connect(DB_NAME)
        conn.cursor().execute("INSERT INTO comments (news_id, username, text) VALUES (?, ?, ?)", (news_id, username, text))
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
    res = [{"username": r[0], "text": r[1], "time": r[2].split()[1][:5] if r[2] else ""} for r in cursor.fetchall()]
    conn.close()
    return json.dumps(res, ensure_ascii=False)

@route('/')
def index():
    news_data = fetch_news_from_db()
    matches_today = get_live_matches_365()
    
    # Берем ТОП-5 самых популярных лиг для таблиц и бомбардиров, чтобы сайт загружался мгновенно
    tables = {
        "apl": get_real_table("PL"), "la": get_real_table("PD"), 
        "seria_a": get_real_table("SA"), "bunde": get_real_table("BL1"), "liga_1": get_real_table("FL1")
    }
    scorers = {
        "apl": get_top_scorers("PL"), "la": get_top_scorers("PD"), 
        "seria_a": get_top_scorers("SA"), "bunde": get_top_scorers("BL1"), "liga_1": get_top_scorers("FL1")
    }
    
    return template('index.html', news=news_data, matches=matches_today, t=tables, s=scorers)

def start_bot(): subprocess.Popen(["python", "football_final.py"])

if __name__ == "__main__":
    init_extended_db()
    threading.Thread(target=start_bot, daemon=True).start()
    run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
    
