import os
import subprocess
import threading
import requests
from bottle import route, run, template, response

DB_NAME = "bot_v25.db"

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
    """Вспомогательная функция для чтения новостей из БД"""
    import sqlite3
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # Достаем еще и время публикации (published)
        cursor.execute("SELECT title, description, source, tag, image_url, published FROM posted_news ORDER BY id DESC LIMIT 40")
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    
    news_data = []
    for r in rows:
        if r[0] and r[1]:
            img = r[4] if (len(r) > 4 and r[4]) else "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500"
            tag = r[3] if (len(r) > 3 and r[3]) else "#Футбол"
            
            # Красиво форматируем время (берём только Часы:Минуты из таймштампа)
            time_str = "00:00"
            if len(r) > 5 and r[5]:
                try:
                    # Обычно время в БД лежит как 'YYYY-MM-DD HH:MM:SS'
                    time_str = r[5].split()[1][:5]
                except Exception:
                    time_str = "Свежая"

            news_data.append({
                "title": r[0], 
                "desc": r[1], 
                "source": r[2], 
                "tag": tag, 
                "image": img,
                "time": time_str
            })
    return news_data

@route('/api/news')
def api_news():
    """Секретный эндпоинт: отдает новости в формате JSON для автообновления сайта"""
    import json
    response.content_type = 'application/json; charset=UTF-8'
    return json.dumps(fetch_news_from_db(), ensure_ascii=False)

@route('/')
def index():
    news_data = fetch_news_from_db()
    if not news_data:
        news_data = [{
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
            
            /* Панель фильтров */
            .filter-panel { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-bottom: 25px; }
            .filter-btn { background-color: #1e1e1e; color: #b3b3b3; border: 1px solid #333; padding: 8px 14px; border-radius: 20px; cursor: pointer; font-size: 13px; font-weight: bold; transition: all 0.3s; }
            .filter-btn:hover, .filter-btn.active { background-color: #2ecc71; color: #121212; border-color: #2ecc71; }
            
            /* Сетка карточек */
            .news-container { display: flex; flex-direction: column; gap: 20px; max-width: 600px; margin: 0 auto; }
            .card { background-color: #1e1e1e; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.5); border-bottom: 4px solid #2ecc71; transition: all 0.3s ease; position: relative; }
            .card.hidden { display: none; }
            .card-img { width: 100%; height: 200px; object-fit: cover; }
            .card-body { padding: 15px; }
            .card-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
            .card-tag { display: inline-block; background-color: rgba(46, 204, 113, 0.1); color: #2ecc71; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }
            
            /* Кнопка Телеграм */
            .tg-link-btn { background-color: #2481cc; color: white; border: none; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; cursor: pointer; text-decoration: none; transition: background 0.2s; }
            .tg-link-btn:hover { background-color: #1a66a4; }
            
            .card-title { color: #ffffff; font-size: 19px; font-weight: bold; margin: 0 0 10px 0; line-height: 1.3; }
            .card-desc { color: #cccccc; font-size: 14px; line-height: 1.5; margin-bottom: 12px; }
            .card-footer { display: flex; justify-content: space-between; color: #666; font-size: 12px; font-style: italic; border-top: 1px solid #2a2a2a; padding-top: 10px; }
            .card-time { color: #2ecc71; font-weight: bold; }
            
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

            // УМНОЕ АВТООБНОВЛЕНИЕ БЕЗ ПЕРЕЗАГРУЗКИ СТРАНИЦЫ (Каждые 30 секунд)
            async function checkNewNews() {
                try {
                    let response = await fetch('/api/news');
                    let news = await response.json();
                    let container = document.querySelector('.news-container');
                    
                    // Очищаем и пересобираем ленту налету
                    let html = '';
                    news.forEach(item => {
                        let isHidden = (currentFilter === 'all' || item.tag === currentFilter) ? '' : ' hidden';
                        html += `
                            <div class="card${isHidden}" data-tag="${item.tag}">
                                <img class="card-img" src="${item.image}" alt="news-img" onerror="this.src='https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500'">
                                <div class="card-body">
                                    <div class="card-header-row">
                                        <span class="card-tag">${item.tag}</span>
                                        <a href="https://t.me/onetime_foot" target="_blank" class="tg-link-btn">Читать в TG ⚡</a>
                                    </div>
                                    <h2 class="card-title">${item.title}</h2>
                                    <div class="card-desc">${item.desc}</div>
                                    <div class="card-footer">
                                        <span>Источник: ${item.source}</span>
                                        <span class="card-time">🕒 ${item.time}</span>
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                    container.innerHTML = html;
                } catch (e) {
                    console.log("Ошибка обновления ленты", e);
                }
            }

            // Включаем таймер опроса базы
            setInterval(checkNewNews, 30000);
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
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    run(host='0.0.0.0', port=port)
    
