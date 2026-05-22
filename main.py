import os
import subprocess
import threading
from bottle import route, run

@route('/')
def index():
    return "<h1 style='color:green; text-align:center; padding:100px;'>✅ ВАН-ТАЙМ ЗАПУСТИЛСЯ!<br>Если видишь этот текст — сайт живой</h1>"

@route('/<filename:path>')
def static(filename):
    return "OK"

if __name__ == "__main__":
    # запускаем бота в фоне
    threading.Thread(target=lambda: subprocess.Popen(["python", "football_final.py"]), daemon=True).start()
    run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
