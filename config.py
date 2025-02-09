import os
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_CONFIG = {
    'host': os.getenv('PGHOST', 'localhost'),
    'port': os.getenv('PGPORT', '5432'),
    'database': os.getenv('PGDATABASE', 'mafia_bot'),
    'user': os.getenv('PGUSER', 'postgres'),
    'password': os.getenv('PGPASSWORD', '')
}

# Bot configuration
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("Telegram bot token not found in environment variables!")

# Game configuration
MIN_PLAYERS = 4
MAX_PLAYERS = 15
NIGHT_DURATION = 120  # seconds
DAY_DURATION = 180    # seconds
VOTING_DURATION = 60  # seconds

# Role settings
MAFIA_RATIO = 3      # 1 mafia per 3 players
LAWYER_MIN_PLAYERS = 8  # Lawyer appears with 8+ players