git clone <your-repository-url>
cd telegram-mafia-bot
```

2. Создайте и активируйте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
```

3. Установите зависимости:
```bash
pip install python-telegram-bot==13.7
pip install SQLAlchemy
pip install psycopg2-binary
pip install python-dotenv
```

4. Настройте базу данных PostgreSQL:
   - Создайте новую базу данных с именем 'mafia_bot'
   - Убедитесь, что PostgreSQL сервер запущен
   - Таблицы будут созданы автоматически при запуске бота

5. Создайте файл .env со следующими переменными:
```ini
PGHOST=localhost
PGPORT=5432
PGDATABASE=mafia_bot
PGUSER=your_database_user
PGPASSWORD=your_database_password
TELEGRAM_BOT_TOKEN=7577686873:AAGVCVaAjJZFB-6H4ji-bSwPCSwwzMcmt_Q
```

6. Запустите бота:
```bash
python bot.py
```

## Команды игры

- `/start` - Начать новую игру
- Используйте кнопки для взаимодействия с игрой

## Структура проекта

- `bot.py` - Основной файл бота
- `game_manager.py` - Управление игровым процессом
- `models.py` - Модели базы данных
- `messages.py` - Сообщения на армянском языке
- `roles.py` - Определение ролей и их действий
- `utils.py` - Вспомогательные функции
- `config.py` - Конфигурация приложения
- `database.py` - Настройки базы данных

## Развертывание на GitHub

1. Инициализация Git репозитория:
```bash
git init
```

2. Добавление файлов:
```bash
git add .
git commit -m "Initial commit"
```

3. Подключение к GitHub:
```bash
git remote add origin <your-repository-url>
git branch -M main
git push -u origin main
```

## Необходимые файлы для архива

```
telegram-mafia-bot/
├── .env.example
├── .gitignore
├── README.md
├── bot.py
├── config.py
├── database.py
├── game_manager.py
├── messages.py
├── models.py
├── roles.py
└── utils.py