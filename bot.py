import asyncio
import logging
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext
)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from game_manager import GameManager
from models import GameStatus, GamePhase, Role
from messages import MESSAGES
from config import TOKEN
from database import Base, engine

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

game_manager = GameManager()

def start_command(update: Update, context: CallbackContext) -> None:
    """Starts a new game"""
    chat_id = update.effective_chat.id
    game = game_manager.create_game(chat_id)

    keyboard = [[InlineKeyboardButton("Միանալ", callback_data="join")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    context.bot.send_message(
        chat_id=chat_id,
        text=MESSAGES['waiting_for_players'].format(0, 4),
        reply_markup=reply_markup
    )

def join_callback(update: Update, context: CallbackContext) -> None:
    """Handles player joining the game"""
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name

    game = game_manager.active_games.get(chat_id)
    if not game or game.status != GameStatus.WAITING:
        query.answer(MESSAGES['game_already_started'])
        return

    try:
        player = game_manager.add_player(game.id, user_id, username)
        query.answer(MESSAGES['player_joined'].format(username))

        players_count = len(game.players)
        if players_count >= 4:  # Минимальное количество игроков
            game_manager.start_game(chat_id, context)
        else:
            keyboard = [[InlineKeyboardButton("Միանալ", callback_data="join")]]
            query.message.edit_text(
                MESSAGES['waiting_for_players'].format(players_count, 4),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        logger.error(f"Error adding player: {e}")
        query.answer(MESSAGES['error_joining'])

def main() -> None:
    """Starts the bot"""
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    # Add command handlers
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CallbackQueryHandler(join_callback, pattern="^join$"))
    dp.add_handler(CallbackQueryHandler(
        game_manager.handle_night_action,
        pattern="^night_action_"
    ))
    dp.add_handler(CallbackQueryHandler(
        game_manager.handle_vote,
        pattern="^vote_"
    ))

    # Start the bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()