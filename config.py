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
MAX_PLAYERS = 20
NIGHT_DURATION = 120  # seconds
DAY_DURATION = 180    # seconds
VOTING_DURATION = 60  # seconds

# Role distribution settings
MAFIA_RATIO = 4      # 1 mafia per 4 players
DON_MIN_PLAYERS = 7  # Don appears with 7+ players
LAWYER_MIN_PLAYERS = 8  # Lawyer appears with 8+ players
SECOND_DOCTOR_MIN_PLAYERS = 12  # Second doctor with 12+ players
SECOND_COMMISSIONER_MIN_PLAYERS = 15  # Second commissioner with 15+ players