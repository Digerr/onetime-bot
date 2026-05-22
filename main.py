import os
import subprocess
import threading
import requests
import sqlite3
import json
from bottle import route, run, template, response, request

DB_NAME = "bot_v25.db"

def init_extended_db():
    """Создаем таблицы для комментариев и реакций, если их еще нет"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Таблица комментариев
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            news_id TEXT,
            username TEXT,
            text TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Таблица лайков/дизлайков
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reactions (
            news_id TEXT PRIMARY KEY,
            likes INTEGER DEFAULT 0,
            dislikes INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def get_today_matches():
    """Продвинутый сборщик матчей: вытаскивает счет, статусы и ссылки на видеообзоры"""
    matches = []
    try:
        url = "https://www.scorebat.com/video-api/v3/"
        res = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if res.status_code == 200:
            data = res.json()
            for item in data.get('response', [])[:10]:
                title = item.get('title', '')
                video_url = item.get('matchviewUrl', '') # Ссылка на хайлайты/обзор
                
                # Проверяем, идет ли матч прямо сейчас или завершен
                # В данном API наличие видео часто означает, что матч завершен или забит гол
                status = "Завершен" if video_url else "LIVE / Скоро"
                
                if " - " in title:
                    matches.append({
                        "teams": title,
                        "status": status,
                        "video": video_url
                    })
    except Exception:
        pass
    
    if not matches:
        matches = [
            {"teams": "Матчи лиг появятся перед началом туров", "status": "Ожидание", "video": ""},
            {"teams": "Следите за обновлениями ВАН-ТАЙМ", "status": "Инфо", "video": ""}
        ]
    return matches

def fetch_news_from_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT p.url, p.title, p.description, p.source, p.tag, p.image_url, p.published, 
                   IFNULL(r.likes, 0), IFNULL(r.dislikes, 0)
            FROM posted_news p
            LEFT JOIN reactions r ON abs(hash(p.url)) = r.news_id
            ORDER BY p.id DESC LIMIT 40
        """)
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    
    news_data = []
    for r in rows:
        if r[1] and r[2]:
            img = r[5] if r[5] else "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500"
            tag = r[4] if r[4] else "#Футбол"
            
            time_str = "00:00"
            if r[6]:
                try:
                    time_str = r[6].split()[1][:5]
                except Exception:
                    time_str = "Свежая"

            news_id = str(abs(hash(r[0])))
            news_data.append({
                "id": news_id,
                "title": r[1], 
                "desc": r[2], 
                "source": r[3], 
                "tag": tag, 
                "image": img,
                "time": time_str,
                "likes": r[7] if len(r) > 7 else 0,
                "dislikes": r[8] if len(r) > 8 else 0
            })
    return news_data

@route('/api/news')
def api_news():
    response.content_type = 'application/json; charset=UTF-8'
    return json.dumps(fetch_news_from_db(), ensure_ascii=False)

@route('/api/reaction', method='POST')
def handle_reaction():
    """Обработка кликов по лайкам и дизлайкам"""
    news_id = request.forms.get('news_id')
    type_reaction = request.forms.get('type') # 'like' или 'dislike'
    
    if news_id and type_reaction:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Проверяем, есть ли уже запись для этой новости в таблице реакций
        cursor.execute("SELECT 1 FROM reactions WHERE news_id = ?", (news_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO reactions (news_id, likes, dislikes) VALUES (?, 0, 0)", (news_id,))
            
        if type_reaction == 'like':
            cursor.execute("UPDATE reactions SET likes = likes + 1 WHERE news_id = ?", (news_id,))
        elif type_reaction == 'dislike':
            cursor.execute("UPDATE reactions SET dislikes = dislikes + 1 WHERE news_id = ?", (news_id,))
            
        conn.commit()
        # Достаем обновленные значения, чтобы вернуть их на сайт
        cursor.execute("SELECT likes, dislikes FROM reactions WHERE news_id = ?", (news_id,))
        res = cursor.fetchone()
        conn.close()
        return {"status": "success", "likes": res[0], "dislikes": res[1]}
    return {"status": "error"}

@route('/api/comments/add', method='POST')
def add_comment():
    news_id = request.forms.get('news_id')
    username = request.forms.get('username') or "Аноним"
    text = request.forms.get('text')
    if news_id and text:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO comments (news_id, username, text) VALUES (?, ?, ?)", (news_id, username, text))
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
    rows = cursor.fetchall()
    conn.close()
    comments = [{"username": r[0], "text": r[1], "time": r[2].split()[1][:5] if r[2] else ""} for r in rows]
    return json.dumps(comments, ensure_ascii=False)

@route('/')
def index():
    news_data = fetch_news_from_db()
    if not news_data:
        news_data = [{
            "id": "0", "title": "Лента «ВАН-ТАЙМ» обновляется", "desc": "Бот собирает свежие футбольные инсайды...", 
            "source": "Система", "tag": "#Футбол", "image": "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500", 
            "time": "Сейчас", "likes": 0, "dislikes": 0
        }]
    matches_today = get_today_matches()

    html_page = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ВАН-ТАЙМ | Футбольный портал</title>
    <style>
        body { background-color: #121212; color: #ffffff; font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 15px; }
        .header { text-align: center; color: #2ecc71; font-size: 26px; font-weight: bold; margin: 15px 0; text-transform: uppercase; letter-spacing: 2px; }
        .main-nav { display: flex; justify-content: center; gap: 10px; margin-bottom: 20px; border-bottom: 1px solid #222; padding-bottom: 10px; }
        .nav-tab-btn { background: none; border: none; color: #888; font-size: 16px; font-weight: bold; padding: 8px 16px; cursor: pointer; transition: color 0.3s; position: relative; }
        .nav-tab-btn.active { color: #2ecc71; }
        .nav-tab-btn.active::after { content: ''; position: absolute; bottom: -11px; left: 0; width: 100%; height: 3px; background-color: #2ecc71; }
        .tab-content { display: none; max-width: 600px; margin: 0 auto; }
        .tab-content.active { display: block; }
        
        /* Виджет матчей */
        .matches-section { background-color: #1e1e1e; border-radius: 12px; padding: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.4); }
        .matches-title { font-size: 15px; font-weight: bold; color: #2ecc71; margin-bottom: 15px; text-transform: uppercase; }
        .matches-vertical-list { display: flex; flex-direction: column; gap: 10px; }
        .match-ticker { background-color: #2a2a2a; padding: 12px 15px; border-radius: 8px; font-size: 14px; font-weight: bold; border: 1px solid #333; display: flex; flex-direction: column; gap: 8px; }
        .match-meta { display: flex; justify-content: space-between; align-items: center; width: 100%; }
        .match-status { font-size: 11px; background-color: #333; padding: 2px 6px; border-radius: 4px; color: #aaa; }
        .match-status.live { background-color: rgba(231, 76, 60, 0.2); color: #e74c3c; border: 1px solid #e74c3c; }
        .video-btn { background-color: #2ecc71; color: #121212; text-decoration: none; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: bold; text-align: center; }
        
        /* Таблицы лиг */
        .table-container-box { background-color: #1e1e1e; border-radius: 12px; padding: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.4); }
        .league-select-panel { display: flex; gap: 8px; margin-bottom: 15px; justify-content: center; }
        .league-sub-btn { background-color: #2a2a2a; color: #aaa; border: 1px solid #333; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: bold; cursor: pointer; }
        .league-sub-btn.active { background-color: #2ecc71; color: #121212; border-color: #2ecc71; }
        .league-table-wrapper { display: none; }
        .league-table-wrapper.active { display: block; }
        .league-table { width: 100%; border-collapse: collapse; font-size: 14px; text-align: left; }
        .league-table th { color: #666; padding: 8px 6px; border-bottom: 1px solid #333; font-size: 12px; }
        .league-table td { padding: 10px 6px; border-bottom: 1px solid #222; }
        .league-table tr:nth-child(-n+4) td:first-child { color: #2ecc71; font-weight: bold; }
        
        /* Фильтры и карточки */
        .filter-panel { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-bottom: 20px; }
        .filter-btn { background-color: #1e1e1e; color: #b3b3b3; border: 1px solid #333; padding: 8px 14px; border-radius: 20px; cursor: pointer; font-size: 13px; font-weight: bold; }
        .filter-btn:hover, .filter-btn.active { background-color: #2ecc71; color: #121212; border-color: #2ecc71; }
        .news-container { display: flex; flex-direction: column; gap: 20px; }
        .card { background-color: #1e1e1e; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.5); border-bottom: 4px solid #2ecc71; }
        .card.hidden { display: none; }
        .card-img { width: 100%; height: 200px; object-fit: cover; }
        .card-body { padding: 15px; }
        .card-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .card-tag { display: inline-block; background-color: rgba(46, 204, 113, 0.1); color: #2ecc71; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }
        .tg-link-btn { background-color: #2481cc; color: white; border: none; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; text-decoration: none; }
        .card-title { color: #ffffff; font-size: 19px; font-weight: bold; margin: 0 0 10px 0; line-height: 1.3; }
        .card-desc { color: #cccccc; font-size: 14px; line-height: 1.5; margin-bottom: 12px; }
        .card-footer { display: flex; justify-content: space-between; color: #666; font-size: 12px; font-style: italic; border-top: 1px solid #2a2a2a; padding-top: 10px; margin-bottom: 12px; }
        .card-time { color: #2ecc71; font-weight: bold; }
        
        /* Интерактивная панель (Лайки + Комменты) */
        .interactive-panel { display: flex; justify-content: space-between; align-items: center; }
        .reactions-group { display: flex; gap: 10px; }
        .react-btn { background-color: #252525; border: 1px solid #333; color: #aaa; padding: 5px 12px; border-radius: 6px; font-size: 13px; cursor: pointer; font-weight: bold; display: flex; align-items: center; gap: 5px; }
        .react-btn:hover { border-color: #2ecc71; color: white; }
        .comment-toggle-btn { background-color: transparent; border: 1px solid #444; color: #aaa; padding: 5px 12px; border-radius: 6px; font-size: 13px; cursor: pointer; font-weight: bold; }
        
        /* Шторка комментариев */
        .comments-box { background-color: #171717; padding: 12px; border-top: 1px solid #252525; display: none; }
        .comments-list { max-height: 150px; overflow-y: auto; margin-bottom: 10px; font-size: 13px; }
        .comment-item { margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px dashed #222; }
        .comment-user { color: #2ecc71; font-weight: bold; margin-right: 5px; }
        .comment-text { color: #bbb; }
        .comment-input-row { display: flex; gap: 6px; }
        .comment-input { flex: 1; background-color: #252525; border: 1px solid #333; color: white; padding: 6px 10px; border-radius: 6px; font-size: 13px; }
        .comment-btn { background-color: #2ecc71; color: #121212; border: none; padding: 6px 12px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 13px; }
        
        .footer { text-align: center; color: #444; font-size: 12px; margin-top: 40px; padding-bottom: 20px; }
    </style>
    <script>
        function switchTab(tabId, button) {
            let tabs = document.querySelectorAll('.tab-content');
            tabs.forEach(tab => tab.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            let buttons = document.querySelectorAll('.nav-tab-btn');
            buttons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
        }
        function switchLeague(leagueId, button) {
            let wrappers = document.querySelectorAll('.league-table-wrapper');
            wrappers.forEach(w => w.classList.remove('active'));
            document.getElementById(leagueId).classList.add('active');
            let buttons = document.querySelectorAll('.league-sub-btn');
            buttons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
        }
        function filterNews(tag, button) {
            let buttons = document.querySelectorAll('.filter-btn');
            buttons.forEach(btn => btn.classList.remove('active'));
            if(button) button.classList.add('active');
            let cards = document.querySelectorAll('.card');
            cards.forEach(card => {
                if (tag === 'all' || card.getAttribute('data-tag') === tag) {
                    card.classList.remove('hidden');
                } else {
                    card.classList.add('hidden');
                }
            });
        }
        async function sendReaction(newsId, typeReaction) {
            let formData = new FormData();
            formData.append('news_id', newsId);
            formData.append('type', typeReaction);
            try {
                let res = await fetch('/api/reaction', { method: 'POST', body: formData });
                let data = await res.json();
                if(data.status === 'success') {
                    document.getElementById('l-cnt-' + newsId).innerText = data.likes;
                    document.getElementById('dl-cnt-' + newsId).innerText = data.dislikes;
                }
            } catch(e) {}
        }
        async function toggleComments(newsId) {
            let box = document.getElementById("box-" + newsId);
            if (box.style.display === 'block') {
                box.style.display = 'none';
            } else {
                box.style.display = 'block';
                loadComments(newsId);
            }
        }
        async function loadComments(newsId) {
            let list = document.getElementById("list-" + newsId);
            list.innerHTML = '<span style="color:#666;font-size:12px;">Загрузка...</span>';
            try {
                let res = await fetch('/api/comments/' + newsId);
                let comments = await res.json();
                if(comments.length === 0) {
                    list.innerHTML = '<span style="color:#666;font-size:12px;">Комментариев пока нет.</span>';
                    return;
                }
                list.innerHTML = comments.map(c => '<div class="comment-item"><span class="comment-user">' + c.username + ':</span><span class="comment-text">' + c.text + '</span><span style="color:#444; font-size:10px; float:right;">' + c.time + '</span></div>').join('');
            } catch(e) { list.innerHTML = 'Ошибка загрузки'; }
        }
        async function sendComment(newsId) {
            let nameInput = document.getElementById("name-" + newsId);
            let textInput = document.getElementById("text-" + newsId);
            if(!textInput.value.trim()) return;
            let formData = new FormData();
            formData.append('news_id', newsId);
            formData.append('username', nameInput.value.trim());
            formData.append('text', textInput.value.trim());
            await fetch('/api/comments/add', { method: 'POST', body: formData });
            textInput.value = '';
            loadComments(newsId);
        }
        setInterval(function() {
            window.location.reload();
        }, 90000); // Мягкое автообновление раз в 1.5 минуты
    </script>
</head>
<body>
    <div class="header">⚽ ВАН-ТАЙМ</div>
    
    <div class="main-nav">
        <button class="nav-tab-btn active" onclick="switchTab('tab-news', this)">Лента</button>
        <button class="nav-tab-btn" onclick="switchTab('tab-matches', this)">Матчи</button>
        <button class="nav-tab-btn" onclick="switchTab('tab-tables', this)">Таблицы</button>
    </div>
    
    <div id="tab-news" class="tab-content active">
        <div class="filter-panel">
            <button class="filter-btn active" onclick="filterNews('all', this)">Все</button>
            <button class="filter-btn" onclick="filterNews('#Трансферы', this)">Трансферы</button>
            <button class="filter-btn" onclick="filterNews('#РПЛ', this)">РПЛ</button>
            <button class="filter-btn" onclick="filterNews('#АПЛ', this)">АПЛ</button>
            <button class="filter-btn" onclick="filterNews('#ЛаЛига', this)">Ла Лига</button>
            <button class="filter-btn" onclick="filterNews('#ЛЧ', this)">ЛЧ</button>
        </div>
        <div class="news-container">
            % for item in news:
                <div class="card" data-tag="{{item['tag']}}">
                    <img class="card-img" src="{{item['image']}}" onerror="this.src='https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500'">
                    <div class="card-body">
                        <div class="card-header-row">
                            <span class="card-tag">{{item['tag']}}</span>
                            <a href="https://t.me/onetime_foot" target="_blank" class="tg-link-btn">Читать в TG ⚡</a>
                        </div>
                        <h2 class="card-title">{{item['title']}}</h2>
                        <div class="card-desc">{{item['desc']}}</div>
                        <div class="card-footer">
                            <span>Источник: {{item['source']}}</span>
                            <span class="card-time">🕒 {{item['time']}}</span>
                        </div>
                        
                        <div class="interactive-panel">
                            <div class="reactions-group">
                                <button class="react-btn" onclick="sendReaction('{{item['id']}}', 'like')">👍 <span id="l-cnt-{{item['id']}}">{{item['likes']}}</span></button>
                                <button class="react-btn" onclick="sendReaction('{{item['id']}}', 'dislike')">👎 <span id="dl-cnt-{{item['id']}}">{{item['dislikes']}}</span></button>
                            </div>
                           
