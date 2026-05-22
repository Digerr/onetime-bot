import os
import subprocess
import threading
import requests
import sqlite3
import json
from bottle import route, run, template, response, request

DB_NAME = "bot_v25.db"

def init_comments_db():
    """Инициализация таблицы комментариев в существующей базе данных"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            news_id TEXT,
            username TEXT,
            text TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_today_matches():
    """Сборщик реальных матчей на сегодня"""
    matches = []
    try:
        url = "https://www.scorebat.com/video-api/v3/"
        res = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if res.status_code == 200:
            data = res.json()
            for item in data.get('response', [])[:8]:
                title = item.get('title', '')
                if " - " in title:
                    matches.append({"teams": title})
    except Exception:
        pass
    
    if not matches:
        matches = [
            {"teams": "Матчи лиг появятся перед началом туров"},
            {"teams": "Следите за обновлениями ВАН-ТАЙМ"}
        ]
    return matches

def fetch_news_from_db():
    """Чтение новостей из БД с уникальным ID (используем хэш урла или сам урл)"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT url, title, description, source, tag, image_url, published FROM posted_news ORDER BY id DESC LIMIT 40")
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    
    news_data = []
    for r in rows:
        if r[1] and r[2]:
            img = r[5] if (len(r) > 5 and r[5]) else "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500"
            tag = r[4] if (len(r) > 4 and r[4]) else "#Футбол"
            
            time_str = "00:00"
            if len(r) > 6 and r[6]:
                try:
                    time_str = r[6].split()[1][:5]
                except Exception:
                    time_str = "Свежая"

            # Генерируем простой ID на основе ссылки для привязки комментариев
            news_id = str(abs(hash(r[0])))

            news_data.append({
                "id": news_id,
                "title": r[1], 
                "desc": r[2], 
                "source": r[3], 
                "tag": tag, 
                "image": img,
                "time": time_str
            })
    return news_data

@route('/api/news')
def api_news():
    response.content_type = 'application/json; charset=UTF-8'
    return json.dumps(fetch_news_from_db(), ensure_ascii=False)

@route('/api/comments/add', method='POST')
def add_comment():
    """Добавление нового комментария через AJAX"""
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
    """Получение комментариев к конкретной новости"""
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
            "id": "0",
            "title": "Лента «ВАН-ТАЙМ» обновляется", 
            "desc": "Бот собирает свежие футбольные инсайды. Загляните через пару минут!", 
            "source": "Система",
            "tag": "#Футбол",
            "image": "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500",
            "time": "Сейчас"
        }]

    matches_today = get_today_matches()

    html_page = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ВАН-ТАЙМ | Футбольный портал</title>
        <style>
            body { background-color: #121212; color: #ffffff; font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 15px; }
            .header { text-align: center; color: #2ecc71; font-size: 26px; font-weight: bold; margin: 15px 0; text-transform: uppercase; letter-spacing: 2px; }
            
            /* Виджет матчей дня */
            .matches-section { max-width: 600px; margin: 0 auto 20px auto; background-color: #1e1e1e; border-radius: 12px; padding: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.4); }
            .matches-title { font-size: 14px; font-weight: bold; color: #2ecc71; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1px; }
            .matches-scroll { display: flex; gap: 10px; overflow-x: auto; scrollbar-width: none; padding-bottom: 5px; }
            .matches-scroll::-webkit-scrollbar { display: none; }
            .match-ticker { background-color: #2a2a2a; padding: 8px 15px; border-radius: 8px; font-size: 13px; font-weight: bold; white-space: nowrap; border: 1px solid #333; }
            
            /* Блок турнирной таблицы */
            .table-section { max-width: 600px; margin: 0 auto 20px auto; background-color: #1e1e1e; border-radius: 12px; padding: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.4); }
            .table-title { font-size: 14px; font-weight: bold; color: #2ecc71; margin-bottom: 12px; text-transform: uppercase; }
            .league-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
            .league-table th { color: #888; padding: 6px; border-bottom: 1px solid #333; }
            .league-table td { padding: 8px 6px; border-bottom: 1px solid #222; }
            .league-table tr:nth-child(-n+4) td:first-child { color: #2ecc71; font-weight: bold; } /* Зона ЛЧ */

            /* Панель фильтров */
            .filter-panel { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-bottom: 25px; }
            .filter-btn { background-color: #1e1e1e; color: #b3b3b3; border: 1px solid #333; padding: 8px 14px; border-radius: 20px; cursor: pointer; font-size: 13px; font-weight: bold; transition: all 0.3s; }
            .filter-btn:hover, .filter-btn.active { background-color: #2ecc71; color: #121212; border-color: #2ecc71; }
            
            /* Сетка карточек */
            .news-container { display: flex; flex-direction: column; gap: 20px; max-width: 600px; margin: 0 auto; }
            .card { background-color: #1e1e1e; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.5); border-bottom: 4px solid #2ecc71; position: relative; }
            .card.hidden { display: none; }
            .card-img { width: 100%; height: 200px; object-fit: cover; }
            .card-body { padding: 15px; }
            .card-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
            .card-tag { display: inline-block; background-color: rgba(46, 204, 113, 0.1); color: #2ecc71; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }
            
            .tg-link-btn { background-color: #2481cc; color: white; border: none; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; cursor: pointer; text-decoration: none; }
            .card-title { color: #ffffff; font-size: 19px; font-weight: bold; margin: 0 0 10px 0; line-height: 1.3; }
            .card-desc { color: #cccccc; font-size: 14px; line-height: 1.5; margin-bottom: 12px; }
            .card-footer { display: flex; justify-content: space-between; color: #666; font-size: 12px; font-style: italic; border-top: 1px solid #2a2a2a; padding-top: 10px; margin-bottom: 10px; }
            .card-time { color: #2ecc71; font-weight: bold; }
            
            /* Секция комментариев внутри карточки */
            .comments-box { background-color: #171717; padding: 12px; border-top: 1px solid #252525; display: none; }
            .comments-list { max-height: 150px; overflow-y: auto; margin-bottom: 10px; font-size: 13px; }
            .comment-item { margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px dashed #222; }
            .comment-user { color: #2ecc71; font-weight: bold; margin-right: 5px; }
            .comment-text { color: #bbb; }
            .comment-input-row { display: flex; gap: 6px; }
            .comment-input { flex: 1; background-color: #252525; border: 1px solid #333; color: white; padding: 6px 10px; border-radius: 6px; font-size: 13px; }
            .comment-btn { background-color: #2ecc71; color: #121212; border: none; padding: 6px 12px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 13px; }
            .comment-toggle-btn { background-color: transparent; border: 1px solid #444; color: #aaa; padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; font-weight: bold; }
            
            .footer { text-align: center; color: #444; font-size: 12px; margin-top: 40px; padding-bottom: 20px; }
        </style>
        <script>
            let currentFilter = 'all';

            function filterNews(tag, button) {
                currentFilter = tag;
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

            // Переключатель видимости комментариев
            async function toggleComments(newsId) {
                let box = document.getElementById(`box-${newsId}`);
                if (box.style.display === 'block') {
                    box.style.display = 'none';
                } else {
                    box.style.display = 'block';
                    loadComments(newsId);
                }
            }

            // Загрузка комментариев через API
            async function loadComments(newsId) {
                let list = document.getElementById(`list-${newsId}`);
                list.innerHTML = '<span style="color:#666;font-size:12px;">Загрузка комментариев...</span>';
                try {
                    let res = await fetch(`/api/comments/${newsId}`);
                    let comments = await res.json();
                    if(comments.length === 0) {
                        list.innerHTML = '<span style="color:#666;font-size:12px;">Комментариев пока нет. Будьте первым!</span>';
                        return;
                    }
                    list.innerHTML = comments.map(c => `
                        <div class="comment-item">
                            <span class="comment-user">${c.username}:</span>
                            <span class="comment-text">${c.text}</span>
                            <span style="color:#444; font-size:10px; float:right;">${c.time}</span>
                        </div>
                    `).join('');
                } catch(e) { list.innerHTML = 'Ошибка загрузки'; }
            }

            // Отправка комментария
            async function sendComment(newsId) {
                let nameInput = document.getElementById(`name-${newsId}`);
                let textInput = document.getElementById(`text-${newsId}`);
                if(!textInput.value.trim()) return;

                let formData = new FormData();
                formData.append('news_id', newsId);
                formData.append('username', nameInput.value.trim());
                formData.append('text', textInput.value.trim());

                await fetch('/api/comments/add', { method: 'POST', body: formData });
                textInput.value = '';
                loadComments(newsId);
            }
        </script>
    </head>
    <body>
        <div class="header">⚽ ВАН-ТАЙМ</div>
        
        <div class="matches-section">
            <div class="matches-title">🔥 Матчи сегодня</div>
            <div class="matches-scroll">
                % for match in matches:
                    <div class="match-ticker">⚡ {{match['teams']}}</div>
                % end
            </div>
        </div>

        <div class="table-section">
            <div class="table-title">🏆 Турнирная таблица: АПЛ</div>
            <table class="league-table">
                <thead>
                    <tr><th>#</th><th>Команда</th><th>И</th><th>О</th></tr>
                </thead>
                <tbody>
                    <tr><td>1</td><td>Арсенал</td><td>38</td><td>89</td></tr>
                    <tr><td>2</td><td>Манчестер Сити</td><td>38</td><td>88</td></tr>
                    <tr><td>3</td><td>Ливерпуль</td><td>38</td><td>82</td></tr>
                    <tr><td>4</td><td>Челси</td><td>38</td><td>67</td></tr>
                    <tr><td>5</td><td>Тоттенхэм</td><td>38</td><td>66</td></tr>
                </tbody>
            </table>
        </div>
        
        <div class="filter-panel">
            <button class="filter-btn active" onclick="filterNews('all', this)">Все</button>
            <button class="filter-btn" onclick="filterNews('#Трансферы', this)">Трансферы</button>
            <button class="filter-btn" onclick="filterNews('#РПЛ', this)">РПЛ</button>
            <button class="filter-btn" onclick="filterNews('#АПЛ', this)">АПЛ</button>
            <button class="filter-btn" onclick="filterNews('#ЛаЛига', this)">Ла Лига</button>
            <button class="filter-btn" onclick="filterNews('#ЛЧ', this)">Лига Чемпионов</button>
        </div>
        
        <div class="news-container">
            % for item in news:
                <div class="card" data-tag="{{item['tag']}}">
                    <img class="card-img" src="{{item['image']}}" alt="news-img" onerror="this.src='https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500'">
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
                        <button class="comment-toggle-btn" onclick="toggleComments('{{item['id']}}')">💬 Комментарии</button>
                    </div>

                    <div class="comments-box" id="box-{{item['id']}}">
                        <div class="comments-list" id="list-{{item['id']}}"></div>
                        <div style="margin-bottom:6px;">
                            <input type="text" class="comment-input" id="name-{{item['id']}}" placeholder="Ваше имя (необязательно)" style="width: 140px; margin-bottom: 4px;">
                        </div>
                        <div class="comment-input-row">
                            <input type="text" class="comment-input" id="text-{{item['id']}}" placeholder="Напишите комментарий...">
                            <button class="comment-btn" onclick="sendComment('{{item['id']}}')">Отправить</button>
                        </div>
                    </div>
                </div>
            % end
        </div>
        
        <div class="footer">ВАН-ТАЙМ Спортивный Медиа-Хаб 2026</div>
    </body>
    </html>
    """
    return template(html_page, news=news_data, matches=matches_today)

def start_bot():
    subprocess.Popen(["python", "football_final.py"])

if __name__ == "__main__":
    init_comments_db() # Создаем таблицу комментариев при запуске
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    run(host='0.0.0.0', port=port)
    
