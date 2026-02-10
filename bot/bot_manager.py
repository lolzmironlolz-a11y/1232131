import subprocess
import sys
import os
import threading
import time

# путь к mine.py (лежит рядом)
mine_path = os.path.join(os.path.dirname(__file__), "mine.py")

proc = None
running = True

def start_bot():
    global proc
    proc = subprocess.Popen([sys.executable, mine_path],
                            stdout=sys.stdout,
                            stderr=sys.stderr)
    print("✅ Бот запущен.")

def stop_bot():
    global proc
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("🛑 Бот остановлен.")

def input_thread():
    global running
    while running:
        cmd = input("Введите команду (restart/stop/exit): ").strip().lower()
        if cmd == "restart":
            stop_bot()
            start_bot()
        elif cmd == "stop":
            stop_bot()
        elif cmd == "exit":
            stop_bot()
            running = False
            break

start_bot()
t = threading.Thread(target=input_thread)
t.start()

while running:
    if proc.poll() is not None:
        print("⚠️ Бот завершился. Перезапуск через 5 секунд...")
        time.sleep(5)
        start_bot()
    time.sleep(1)

t.join()
print("Супервизор завершён.")
