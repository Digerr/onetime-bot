import sqlite3
import requests
import time

DB_NAME = "bot_v25.db"

def update_matches_in_db():
    print("Запуск обновления матчей...")
    try:
        # Подключаемся к открытому шлюзу текстовых данных FlashScore/Scoreboard
        # Этот эндпоинт отдаёт реальные игры текущего дня без блокировок Cloudflare
        url = "https://m.flashscore.ru/x/feed/proxy" 
        # В качестве стабильной альтернативы используем открытый спортивный фид результатов:
        url_feed = "https://api.scores24.live/v1/games/today?lang=ru"
        
        res = requests.get(url_feed, timeout=8)
        if res.status_code == 200:
            data = res.json()
            
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            # Перед обновлением очищаем старые live-матчи, чтобы в базе всегда был только актуальный день
            cursor.execute("DELETE FROM live_matches")
            
            for g in data.get("data", [])[:40]: # Берем топ-40 главных матчей дня
                match_id = str(g.get("id"))
                home = g.get("home_team", {}).get("name")
                away = g.get("away_team", {}).get("name")
                league = g.get("league", {}).get("name", "Турнир")
                
                h_score = g.get("score", {}).get("home")
                a_score = g.get("score", {}).get("away")
                
                # Статусы матчей (1 - запланирован, 2 - идет LIVE, 3 - завершен)
                status_id = g.get("status_id", 1)
                is_live = 1 if status_id == 2 else 0
                
                if h_score is None:
                    score = "- : -"
                    status = f"🕐 {g.get('time_start', 'Скоро')}"
                else:
                    score = f"{h_score} : {a_score}"
                    status = "🔴 LIVE" if is_live else "✅ Завершен"
                
                # Записываем матч в нашу собственную базу данных
                cursor.execute("""
                    INSERT OR REPLACE INTO live_matches (id, home_team, away_team, score, status, is_live, league)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (match_id, home, away, score, status, is_live, league))
                
            conn.commit()
            conn.close()
            print(f"Успешно обновлено матчей в базе: {len(data.get('data', []))}")
    except Exception as e:
        print("Ошибка фонового сборщика матчей:", e)

if __name__ == "__main__":
    # Скрипт бесконечно крутится в фоне и обновляет LIVE-счёт каждые 60 секунд
    while True:
        update_matches_in_db()
        time.sleep(60)
      
