import os
import subprocess
import threading
from bottle import route, run, template

DB_NAME = "football.db"

@route('/')
def index():
    import sqlite3
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # Достаем последние 30 сохраненных новостей
        cursor.execute("SELECT title, description, source FROM news ORDER BY id DESC LIMIT 30")
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        # Если бот еще не создал таблицу news или она пустая
        rows = []
    conn.close()
    
    news_data = [{"title": r[0], "desc": r[1], "source": r[2]} for r in rows]
    
    if not news_data:
        news_data = [{
            "title": "Лента обновляется", 
            "desc": "Бот собирает свежие футбольные инсайды. Загляните через пару минут!", 
            "source": "Система"
        }]

    html_page = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SYNTHESIS FOOTBALL</title>
        <style>
            body { background-color: #121212; color: #ffffff; font-family: Arial, sans-serif; margin: 0; padding: 20px; }
            .header { text-align: center; color: #2ecc71; font-size: 24px; font-weight: bold; margin-bottom: 25px; text-transform: uppercase; letter-spacing: 2px; }
            .card { background-color: #1e1e1e; padding: 15px; border-radius: 8px; margin-bottom: 15px; border-left: 5px solid #2ecc71; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
            .card-title { color: #2ecc71; font-size: 18px; font-weight: bold; margin-bottom: 8px; }
            .card-desc { color: #b3b3b3; font-size: 14px; line-height: 1.4; margin-bottom: 8px; }
            .card-source { color: #555; font-size: 11px; text-align: right; font-style: italic; }
            .footer { text-align: center; color: #444; font-size: 12px; margin-top: 30px; }
        </style>
    </head>
    <body>
        <div class="header">⚽ SYNTHESIS FOOTBALL</div>
        
        % for item in news:
            <div class="card">
                <div class="card-title">{{item['title']}}</div>
                <div class="card-desc">{{item['desc']}}</div>
                <div class="card-source">Источник: {{item['source']}}</div>
            </div>
        % end
        
        <div class="footer">Автоматический новостной агрегатор 2026</div>
    </body>
    </html>
    """
    return template(html_page, news=news_data)

def start_bot():
    # Запуск твоего основного бота в фоне параллельно с сайтом
    subprocess.Popen(["python", "football_final.py"])

if __name__ == "__main__":
    # 1. Запускаем бота
    threading.Thread(target=start_bot, daemon=True).start()
    
    # 2. Запускаем сайт наружу для Railway
    port = int(os.environ.get("PORT", 8080))
    run(host='0.0.0.0', port=port)
  
