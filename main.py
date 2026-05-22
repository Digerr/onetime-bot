import os
import sqlite3
import json
import requests
from bottle import route, run, static_file, response
from dotenv import load_dotenv

load_dotenv()

DB_NAME = "bot_v25.db"
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "c7c58272f8b84c73b73483d15a3a8b03")

@route('/')
def index():
    return static_file('index.html', root='.')

@route('/api/news')
def get_news():
    response.content_type = 'application/json; charset=utf-8'
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT url, title, description, source, tag, image_url, published FROM posted_news ORDER BY id DESC LIMIT 20")
        rows = cursor.fetchall()
        conn.close()
        news = [{"id": str(abs(hash(r[0]))), "title": r[1], "desc": r[2], "source": r[3], "tag": r[4] or "#Футбол", "image": r[5] or "https://images.unsplash.com/photo-1508098682722-e99c43a406b2", "time": r[6].split()[1][:5] if r[6] else "Свежая"} for r in rows]
        return json.dumps(news, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})

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
            score = f"{m['score']['fullTime']['home'] if m['score']['fullTime']['home'] is not None else '-'} : {m['score']['fullTime']['away'] if m['score']['fullTime']['away'] is not None else '-'}"
            status = m["status"]
            if status in ("IN_PLAY", "PAUSED"): status = "🔴 LIVE"
            elif status == "FINISHED": status = "✅ Завершён"
            else: status = "🕐 Скоро"
            league = m["competition"]["name"]
            league_img = m["competition"].get("emblem", "")
            matches.append({"home": home, "away": away, "home_img": home_img, "away_img": away_img, "score": score, "status": status, "league": league, "league_img": league_img, "scorers": ""})
        return json.dumps(matches, ensure_ascii=False)
    except:
        return json.dumps([])

@route('/api/tables/<code>')
def get_table(code):
    response.content_type = 'application/json; charset=utf-8'
    try:
        league_ids = {"PL": 2021, "PD": 2014, "SA": 2019, "BL1": 2002, "FL1": 2015}
        lid = league_ids.get(code, 2021)
        headers = {"X-Auth-Token": FOOTBALL_API_KEY}
        res = requests.get(f"https://api.football-data.org/v4/competitions/{lid}/standings", headers=headers, timeout=8)
        data = res.json()
        table = []
        for t in data["standings"][0]["table"]:
            table.append({"pos": t["position"], "name": t["team"]["name"], "crest": t["team"].get("crest",""), "games": t["playedGames"], "won": t["won"], "draw": t["draw"], "lost": t["lost"], "points": t["points"]})
        return json.dumps(table, ensure_ascii=False)
    except:
        return json.dumps([])

@route('/api/scorers/<code>')
def get_scorers(code):
    response.content_type = 'application/json; charset=utf-8'
    try:
        league_ids = {"PL": 2021, "PD": 2014, "SA": 2019, "BL1": 2002, "FL1": 2015}
        lid = league_ids.get(code, 2021)
        headers = {"X-Auth-Token": FOOTBALL_API_KEY}
        res = requests.get(f"https://api.football-data.org/v4/competitions/{lid}/scorers?limit=10", headers=headers, timeout=8)
        data = res.json()
        result = []
        for s in data.get("scorers", []):
            result.append({"name": s["player"]["name"], "team": s["team"]["name"], "goals": s.get("goals", 0), "assists": s.get("assists", 0) or 0})
        return json.dumps(result, ensure_ascii=False)
    except:
        return json.dumps([])

@route('/<filename:path>')
def server_static(filename):
    return static_file(filename, root='.')

if __name__ == "__main__":
    run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
