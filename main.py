import os
import subprocess
import threading
import sqlite3
import json
import time
from bottle import route, run, static_file

DB_NAME = "bot_v25.db"

@route('/')
def index():
    return static_file('index.html', root='.')

# НОВЫЙ ЭНДПОИНТ ДЛЯ НОВОСТЕЙ
@route('/api/news')
def get_news():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT url, title, description, source, tag, image_url, published FROM posted_news ORDER BY id DESC LIMIT 20")
    rows = cursor.fetchall()
    conn.close()
    news = [{"id": str(abs(hash(r[0]))), "title": r[1], "desc": r[2], "source": r[3], "tag": r[4] or "#Футбол", "image": r[5] or "https://images.unsplash.com/photo-1508098682722-e99c43a406b2", "time": r[6].split()[1][:5] if r[6] else "Свежая"} for r in rows]
    return json.dumps(news, ensure_ascii=False)

@route('/<filename:path>')
def server_static(filename):
    return static_file(filename, root='.')

if __name__ == "__main__":
    run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
    
