from dotenv import load_dotenv
import os

# Загружаем переменные из .env
load_dotenv()

# Берём токен
API_TOKEN = os.getenv("API_TOKEN")

# Берём список админов и превращаем строки в числа
ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(",") if x.strip()]

# Девелопер
DEV_ID = int(os.getenv("DEV_ID", "0"))

# Путь к базе
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")
