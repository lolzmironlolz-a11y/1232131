import sqlite3, json
DB_PATH = "bot.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("SELECT id, photos_json, videos_json FROM done_tasks ORDER BY id DESC LIMIT 3")
rows = cur.fetchall()
conn.close()

for r in rows:
    print(f"ID {r[0]}:", r[1], r[2])
