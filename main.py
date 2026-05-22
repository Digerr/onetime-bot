import os
import subprocess
import threading
import sqlite3
import json
import requests
from bottle import route, run, static_file, response

DB_NAME = "bot_v25.db"
FOOTBALL_API_KEY = "c7c58272f8b84c73b73483d15a3a8b03"

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
        cursor.execute("SELECT url, title, description, source, tag, image_url, published FROM posted_news ORDER BY id DESC LIMIT 30")
        rows = cursor.fetchall()
        conn.close()
        news = [{"id": str(abs(hash(r[0]))), "title": r[1], "desc": r[2] or "", "source": r[3], "tag": r[4] or "#Футбол", "image": r[5] or "https://images.unsplash.com/photo-1508098682722-e99c43a406b2", "time": r[6].split()[1][:5] if r[6] else "Свежая"} for r in rows]
        return json.dumps(news, ensure_ascii=False)
    except:
        return json.dumps([])

@route('/api/matches')
def get_matches():
    response.content_type = 'application/json; charset=utf-8'
    try:
        headers = {"X-Auth-Token": FOOTBALL_API_KEY}
        res = requests.get("https://api.football-data.org/v4/matches?status=LIVE,IN_PLAY,PAUSED,FINISHED&limit=20", headers=headers, timeout=8)
        data = res.json()
        matches = []
        for m in data.get("matches", []):
            home = m["homeTeam"]["name"]
            away = m["awayTeam"]["name"]
            home_img = m["homeTeam"].get("crest", "")
            away_img = m["awayTeam"].get("crest", "")
            score = f"{m['score']['fullTime']['home'] or '-'} : {m['score']['fullTime']['away'] or '-'}"
            status = "🔴 LIVE" if m["status"] in ("IN_PLAY", "PAUSED") else "✅ Завершён" if m["status"] == "FINISHED" else "🕐 Скоро"
            matches.append({"home": home, "away": away, "home_img": home_img, "away_img": away_img, "score": score, "status": status, "league": m["competition"]["name"]})
        return json.dumps(matches, ensure_ascii=False)
    except:
        return json.dumps([])

@route('/api/tables/<code>')
def get_table(code):
    response.content_type = 'application/json; charset=utf-8'
    try:
        league_ids = {"PL": 2021, "PD": 2014, "SA": 2019, "BL1": 2002, "FL1": 2015}
        res = requests.get(f"https://api.football-data.org/v4/competitions/{league_ids.get(code, 2021)}/standings", headers={"X-Auth-Token": FOOTBALL_API_KEY}, timeout=8)
        data = res.json()
        return json.dumps([{"pos": t["position"], "name": t["team"]["name"], "points": t["points"]} for t in data["standings"][0]["table"][:10]], ensure_ascii=False)
    except:
        return json.dumps([])

@route('/<filename:path>')
def server_static(filename):
    return static_file(filename, root='.')

if __name__ == "__main__":
    init_db()
    threading.Thread(target=lambda: subprocess.Popen(["python", "football_final.py"]), daemon=True).start()
    run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
