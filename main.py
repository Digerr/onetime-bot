import os
import subprocess
import threading
from bottle import route, run, static_file

# Теперь Python не трогает HTML, он просто отдает его браузеру
@route('/')
def index():
    return static_file('index.html', root='.')

# Чтобы картинки, стили и скрипты работали, если ты их вынесешь
@route('/<filename:path>')
def server_static(filename):
    return static_file(filename, root='.')

def start_bot():
    subprocess.Popen(["python", "football_final.py"])

if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
    
