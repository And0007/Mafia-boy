import asyncio
import logging
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    MessageHandler,
    Filters
)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from game_manager import GameManager
from models import GameStatus, GamePhase, Role
from messages import MESSAGES
from config import TOKEN, MIN_PLAYERS
from database import Base, engine

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Changed to DEBUG for more detailed logs
)
logger = logging.getLogger(__name__)

# Create database tables
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
except Exception as e:
    logger.error(f"Error creating database tables: {e}")
    raise

game_manager = GameManager()

def error_handler(update: Update, context: CallbackContext) -> None:
    """Log Errors caused by Updates."""
    logger.error(f'Update "{update}" caused error "{context.error}"', exc_info=True)
    if update and update.effective_chat:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Произошла ошибка. Пожалуйста, попробуйте еще раз."
        )

def start_command(update: Update, context: CallbackContext) -> None:
    """Starts a new game"""
    try:
        chat_id = update.effective_chat.id
        user = update.effective_user
        logger.info(f"Start command received from user {user.id} in chat {chat_id}")

        if not update.message.chat.type in ['group', 'supergroup']:
            context.bot.send_message(
                chat_id=chat_id,
                text="Бот работает только в групповых чатах!"
            )
            return

        if chat_id in game_manager.active_games:
            logger.info(f"Game already exists in chat {chat_id}")
            context.bot.send_message(
                chat_id=chat_id,
                text=MESSAGES['game_already_started']
            )
            return

        game = game_manager.create_game(chat_id)
        logger.info(f"Created new game with ID {game.id}")

        keyboard = [[InlineKeyboardButton("Միանալ", callback_data="join")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        context.bot.send_message(
            chat_id=chat_id,
            text=MESSAGES['waiting_for_players'].format(0, MIN_PLAYERS),
            reply_markup=reply_markup
        )
        logger.info(f"Game started successfully in chat {chat_id}")
    except Exception as e:
        logger.error(f"Error in start_command: {e}", exc_info=True)
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Произошла ошибка при создании игры. Попробуйте позже."
        )

def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    try:
        logger.info(f"Help command received from user {update.effective_user.id}")
        update.message.reply_text(
            "Доступные команды:\n"
            "/start - Начать новую игру\n"
            "/help - Показать это сообщение\n"
            "\nПравила игры:\n"
            "1. Минимум 4 игрока для начала\n"
            "2. Каждому игроку назначается роль\n"
            "3. Игра проходит в циклах день/ночь\n"
            "4. Используйте кнопки для действий"
        )
    except Exception as e:
        logger.error(f"Error in help_command: {e}", exc_info=True)

def join_callback(update: Update, context: CallbackContext) -> None:
    """Handles player joining the game"""
    try:
        query = update.callback_query
        chat_id = query.message.chat_id
        user_id = query.from_user.id
        username = query.from_user.username or query.from_user.first_name

        logger.info(f"User {username} ({user_id}) trying to join game in chat {chat_id}")

        game = game_manager.active_games.get(chat_id)
        if not game or game.status != GameStatus.WAITING:
            query.answer(MESSAGES['game_already_started'])
            return

        player = game_manager.add_player(game.id, user_id, username)
        query.answer(MESSAGES['player_joined'].format(username))

        players_count = len(game.players)
        if players_count >= MIN_PLAYERS:
            game_manager.start_game(chat_id, context)
        else:
            keyboard = [[InlineKeyboardButton("Միանալ", callback_data="join")]]
            query.message.edit_text(
                MESSAGES['waiting_for_players'].format(players_count, MIN_PLAYERS),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        logger.info(f"Player {username} successfully joined the game")
    except Exception as e:
        logger.error(f"Error in join_callback: {e}", exc_info=True)
        if 'query' in locals():
            query.answer(MESSAGES['error_joining'])

def main() -> None:
    """Starts the bot"""
    try:
        logger.info("Starting bot with token: %s...", TOKEN[:10] if TOKEN else "Not set")

        if not TOKEN:
            raise ValueError("Bot token is not set!")

        # Initialize updater with increased timeout
        updater = Updater(TOKEN, use_context=True, request_kwargs={
            'read_timeout': 30,
            'connect_timeout': 30
        })

        # Explicitly remove webhook before polling
        updater.bot.delete_webhook()

        dp = updater.dispatcher

        # Add command handlers
        dp.add_handler(CommandHandler("start", start_command))
        dp.add_handler(CommandHandler("help", help_command))
        dp.add_handler(CallbackQueryHandler(join_callback, pattern="^join$"))
        dp.add_handler(CallbackQueryHandler(
            game_manager.handle_night_action,
            pattern="^night_action_"
        ))
        dp.add_handler(CallbackQueryHandler(
            game_manager.handle_vote,
            pattern="^vote_"
        ))

        # Add error handler
        dp.add_error_handler(error_handler)

        # Start bot with advanced polling settings
        logger.info("Starting polling...")
        updater.start_polling(
            drop_pending_updates=True,
            timeout=30,
            read_latency=2.0
        )
        logger.info("Bot started successfully!")
        updater.idle()
    except Exception as e:
        logger.error(f"Critical error in main: {e}", exc_info=True)
        raise

if __name__ == '__main__':
    main()