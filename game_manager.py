import asyncio
from typing import List, Dict
from datetime import datetime, timedelta
from models import Game, Player, Action, GameStatus, GamePhase, Role, ActionType
from database import get_db
from messages import MESSAGES
from roles import ROLE_HANDLERS
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import CallbackContext
import logging

logger = logging.getLogger(__name__)

# Assume these constants are defined elsewhere in the project
MAX_PLAYERS = 8
MIN_PLAYERS = 4
MAFIA_RATIO = 3
DON_MIN_PLAYERS = 5
LAWYER_MIN_PLAYERS = 8
SECOND_DOCTOR_MIN_PLAYERS = 10
SECOND_COMMISSIONER_MIN_PLAYERS = 10


class GameManager:
    def __init__(self):
        self.active_games: Dict[int, Game] = {}
        self.player_votes: Dict[int, Dict[int, int]] = {}
        self.role_handlers = ROLE_HANDLERS
        logger.info("GameManager initialized")

    def create_game(self, chat_id: int) -> Game:
        try:
            db = next(get_db())
            logger.info(f"Creating new game for chat_id: {chat_id}")

            # Check if game already exists
            existing_game = db.query(Game).filter(Game.chat_id == chat_id).first()
            if existing_game:
                logger.info(f"Found existing game for chat_id {chat_id}, cleaning up...")
                db.delete(existing_game)
                db.commit()

            game = Game(
                chat_id=chat_id,
                status=GameStatus.WAITING,
                current_phase=None,
                night_count=0
            )
            db.add(game)
            db.commit()
            db.refresh(game)

            self.active_games[chat_id] = game
            logger.info(f"Game created successfully with ID: {game.id}")
            return game

        except Exception as e:
            logger.error(f"Error creating game: {e}", exc_info=True)
            raise

    def add_player(self, game_id: int, telegram_id: int, username: str) -> Player:
        try:
            db = next(get_db())
            logger.info(f"Adding player {username} (ID: {telegram_id}) to game {game_id}")

            # Check current number of players
            current_players = db.query(Player).filter(Player.game_id == game_id).count()
            if current_players >= MAX_PLAYERS:
                logger.warning(f"Maximum player limit reached for game {game_id}")
                raise ValueError(MESSAGES['too_many_players'])

            player = db.query(Player).filter(Player.telegram_id == telegram_id).first()
            if player:
                if player.game_id != game_id:
                    player.game_id = game_id
                    player.username = username
                    player.is_alive = True
                    player.current_role = None
                    player.is_revealed = False
                    logger.info(f"Updated existing player: {username}")
            else:
                player = Player(
                    telegram_id=telegram_id,
                    username=username,
                    game_id=game_id,
                    is_alive=True,
                    is_revealed=False
                )
                db.add(player)
                logger.info(f"Created new player: {username}")

            db.commit()
            db.refresh(player)
            return player

        except Exception as e:
            logger.error(f"Error adding player: {e}", exc_info=True)
            raise

    def assign_roles(self, game_id: int) -> Dict[int, Role]:
        try:
            db = next(get_db())
            logger.info(f"Assigning roles for game {game_id}")
            game = db.query(Game).filter(Game.id == game_id).first()
            players = db.query(Player).filter(Player.game_id == game_id).all()

            num_players = len(players)
            # Calculate number of mafia based on player count and ratio
            num_mafia = max(1, num_players // MAFIA_RATIO)

            # Initialize roles list with civilians
            roles = [Role.CIVILIAN] * num_players

            # Add basic mafia members
            roles[:num_mafia - 1] = [Role.MAFIA] * (num_mafia - 1)

            # Add special roles based on player count
            special_role_idx = num_mafia - 1

            # Always add one doctor and one commissioner
            roles[special_role_idx:special_role_idx + 2] = [Role.DOCTOR, Role.COMMISSIONER]
            special_role_idx += 2

            # Add Don if enough players
            if num_players >= DON_MIN_PLAYERS:
                roles[special_role_idx] = Role.DON
                special_role_idx += 1

            # Add Lawyer if enough players
            if num_players >= LAWYER_MIN_PLAYERS:
                roles[special_role_idx] = Role.LAWYER
                special_role_idx += 1

            # Add second doctor if enough players
            if num_players >= SECOND_DOCTOR_MIN_PLAYERS:
                roles[special_role_idx] = Role.DOCTOR
                special_role_idx += 1

            # Add second commissioner if enough players
            if num_players >= SECOND_COMMISSIONER_MIN_PLAYERS:
                roles[special_role_idx] = Role.COMMISSIONER
                special_role_idx += 1

            # Shuffle roles
            random.shuffle(roles)

            # Assign roles to players
            roles_dict = {}
            for player, role in zip(players, roles):
                player.current_role = role
                player.is_alive = True
                player.is_revealed = False
                roles_dict[player.telegram_id] = role

                if role in [Role.MAFIA, Role.DON]:
                    if player not in game.mafia_chat_players:
                        game.mafia_chat_players.append(player)

            db.commit()
            logger.info(f"Roles assigned successfully for game {game_id}")
            return roles_dict
        except Exception as e:
            logger.error(f"Error assigning roles: {e}", exc_info=True)
            raise

    def process_night_actions(self, game_id: int) -> List[str]:
        try:
            db = next(get_db())
            logger.info(f"Processing night actions for game {game_id}")
            game = db.query(Game).filter(Game.id == game_id).first()
            actions = db.query(Action).filter(
                Action.game_id == game_id,
                Action.night_number == game.night_count
            ).all()

            messages = []
            killed_players = set()
            protected_players = set()

            for action in actions:
                if action.action_type in [ActionType.HEAL, ActionType.PROTECT]:
                    target = db.query(Player).filter(Player.id == action.target_id).first()
                    if target:
                        protected_players.add(target.id)

            for action in actions:
                if action.action_type == ActionType.KILL:
                    target = db.query(Player).filter(Player.id == action.target_id).first()
                    if target and target.id not in protected_players:
                        killed_players.add(target.id)
                        target.is_alive = False
                        messages.append(MESSAGES['player_killed'].format(target.username))

            db.commit()
            logger.info(f"Night actions processed for game {game_id}")
            return messages
        except Exception as e:
            logger.error(f"Error processing night actions: {e}", exc_info=True)
            return ["Ошибка при обработке ночных действий"]

    def check_game_end(self, game_id: int) -> tuple[bool, str]:
        try:
            db = next(get_db())
            logger.info(f"Checking game end for game {game_id}")
            players = db.query(Player).filter(
                Player.game_id == game_id,
                Player.is_alive == True
            ).all()

            mafia_count = sum(1 for p in players if p.current_role in [Role.MAFIA, Role.DON])
            civilian_count = len(players) - mafia_count

            if mafia_count == 0:
                return True, "Խաղաղ բնակիչները հաղթեցին!"
            if mafia_count >= civilian_count:
                return True, "Մաֆիան հաղթեց!"

            return False, ""
        except Exception as e:
            logger.error(f"Error checking game end: {e}", exc_info=True)
            return False, "Ошибка при проверке окончания игры"

    # Add more detailed logging to night_action_handler
    def handle_night_action(self, update: Update, context: CallbackContext) -> None:
        try:
            query = update.callback_query
            logger.info(f"Handling night action from user {query.from_user.id}")

            _, action_type, target_telegram_id = query.data.split('_')
            logger.info(f"Action type: {action_type}, target: {target_telegram_id}")

            chat_id = query.message.chat_id
            player_telegram_id = query.from_user.id

            game = self.active_games.get(chat_id)
            if not game or game.current_phase != GamePhase.NIGHT:
                logger.warning(f"Invalid game state for night action: game={game}, phase={game.current_phase if game else None}")
                query.answer(MESSAGES['not_night_phase'])
                return

            db = next(get_db())
            player = db.query(Player).filter(
                Player.game_id == game.id,
                Player.telegram_id == player_telegram_id,
                Player.is_alive == True
            ).first()

            if not player:
                logger.warning(f"Player not found: telegram_id={player_telegram_id}")
                query.answer(MESSAGES['player_not_found'])
                return

            target = db.query(Player).filter(
                Player.game_id == game.id,
                Player.telegram_id == int(target_telegram_id),
                Player.is_alive == True
            ).first()

            if not target:
                logger.warning(f"Target player not found: telegram_id={target_telegram_id}")
                query.answer(MESSAGES['player_not_found'])
                return

            role_handler = self.role_handlers.get(player.current_role)
            if not role_handler or not role_handler.night_action:
                logger.warning(f"Invalid role handler: role={player.current_role}")
                query.answer(MESSAGES['no_night_action'])
                return

            action_result = role_handler.night_action_handler(player, target, game.id)
            if not action_result:
                logger.warning(f"Night action failed: player={player.id}, target={target.id}")
                query.answer(MESSAGES['action_failed'])
                return

            action = Action(
                game_id=game.id,
                player_id=player.id,
                target_id=target.id,
                action_type=ActionType(action_type),
                night_number=game.night_count,
                result=action_result
            )

            db.add(action)
            db.commit()
            logger.info(f"Night action successful: action_id={action.id}")
            query.answer(MESSAGES['action_successful'])

        except ValueError as e:
            logger.error(f"Value error in handle_night_action: {e}", exc_info=True)
            if 'query' in locals():
                query.answer(MESSAGES['action_failed'])
        except Exception as e:
            logger.error(f"Error in handle_night_action: {e}", exc_info=True)
            if 'query' in locals():
                query.answer(MESSAGES['action_failed'])

    def handle_vote(self, update: Update, context: CallbackContext) -> None:
        try:
            query = update.callback_query
            _, target_telegram_id = query.data.split('_')

            chat_id = query.message.chat_id
            voter_telegram_id = query.from_user.id

            game = self.active_games.get(chat_id)
            if not game or game.current_phase != GamePhase.VOTING:
                query.answer(MESSAGES['not_voting_phase'])
                return

            db = next(get_db())
            voter = db.query(Player).filter(
                Player.game_id == game.id,
                Player.telegram_id == voter_telegram_id,
                Player.is_alive == True
            ).first()

            if not voter:
                query.answer(MESSAGES['player_not_found'])
                return

            if game.id not in self.player_votes:
                self.player_votes[game.id] = {}

            self.player_votes[game.id][voter.id] = int(target_telegram_id)
            query.answer(MESSAGES['action_successful'])
            logger.info(f"Vote registered from player {voter_telegram_id}")
        except Exception as e:
            logger.error(f"Error handling vote: {e}", exc_info=True)
            query.answer(MESSAGES['action_failed'])

    def process_votes(self, game_id: int) -> List[str]:
        try:
            if game_id not in self.player_votes:
                return ["Нет голосов"]

            db = next(get_db())
            votes = self.player_votes[game_id]

            vote_counts = {}
            for target_telegram_id in votes.values():
                target = db.query(Player).filter(
                    Player.game_id == game_id,
                    Player.telegram_id == target_telegram_id,
                    Player.is_alive == True
                ).first()
                if target:
                    vote_counts[target.id] = vote_counts.get(target.id, 0) + 1

            if not vote_counts:
                return ["Нет голосов"]

            max_votes = max(vote_counts.values())
            voted_player_id = max(vote_counts.items(), key=lambda x: x[1])[0]

            voted_player = db.query(Player).filter(
                Player.id == voted_player_id
            ).first()

            if voted_player:
                voted_player.is_alive = False
                db.commit()
                logger.info(f"Player {voted_player.username} eliminated by vote in game {game_id}")
                return [MESSAGES['player_killed'].format(voted_player.username)]

            return ["Ошибка при подсчете голосов"]
        except Exception as e:
            logger.error(f"Error processing votes: {e}", exc_info=True)
            return ["Ошибка при обработке голосов"]

    def start_game(self, chat_id: int, context: CallbackContext) -> None:
        try:
            logger.info(f"Starting game in chat_id: {chat_id}")
            game = self.active_games[chat_id]
            game.status = GameStatus.ACTIVE

            roles = self.assign_roles(game.id)

            for telegram_id, role in roles.items():
                try:
                    role_message = MESSAGES[f'role_{role.value}']
                    context.bot.send_message(telegram_id, role_message)
                except Exception as e:
                    logger.error(f"Failed to send role to {telegram_id}: {e}")

            context.bot.send_message(chat_id, MESSAGES['game_start'])
            self.start_night_phase(chat_id, context)
            logger.info(f"Game started successfully in chat_id: {chat_id}")
        except Exception as e:
            logger.error(f"Error starting game: {e}", exc_info=True)
            context.bot.send_message(chat_id, MESSAGES['game_start_failed'])

    def start_night_phase(self, chat_id: int, context: CallbackContext):
        try:
            logger.info(f"Starting night phase in chat_id: {chat_id}")
            game = self.active_games[chat_id]
            game.current_phase = GamePhase.NIGHT
            game.night_count += 1

            context.bot.send_message(chat_id, MESSAGES['night_phase'])

            for player in game.players:
                if not player.is_alive:
                    continue

                role_handler = self.role_handlers.get(player.current_role)
                if role_handler and role_handler.night_action:
                    targets = [p for p in game.players if p.is_alive and p.telegram_id != player.telegram_id]
                    markup = InlineKeyboardMarkup([
                        [InlineKeyboardButton(
                            target.username,
                            callback_data=f"night_action_{role_handler.night_action.value}_{target.telegram_id}"
                        )]
                        for target in targets
                    ])

                    try:
                        context.bot.send_message(
                            player.telegram_id,
                            MESSAGES[f'{player.current_role.value}_action'],
                            reply_markup=markup
                        )
                    except Exception as e:
                        logger.error(f"Failed to send night action to {player.telegram_id}: {e}")

            context.job_queue.run_once(
                lambda x: self.start_day_phase(chat_id, context),
                120,  # 2 minutes for night phase
                context=chat_id
            )
            logger.info(f"Night phase started successfully in chat_id: {chat_id}")
        except Exception as e:
            logger.error(f"Error starting night phase: {e}", exc_info=True)

    def start_day_phase(self, chat_id: int, context: CallbackContext):
        try:
            logger.info(f"Starting day phase in chat_id: {chat_id}")
            game = self.active_games[chat_id]
            game.current_phase = GamePhase.DAY

            night_results = self.process_night_actions(game.id)
            for message in night_results:
                context.bot.send_message(chat_id, message)

            game_ended, end_message = self.check_game_end(game.id)
            if game_ended:
                context.bot.send_message(chat_id, end_message)
                del self.active_games[chat_id]
                logger.info(f"Game ended in chat_id: {chat_id}")
                return

            context.bot.send_message(chat_id, MESSAGES['day_phase'])

            context.job_queue.run_once(
                lambda x: self.start_voting_phase(chat_id, context),
                180,  # 3 minutes for day phase
                context=chat_id
            )
            logger.info(f"Day phase started successfully in chat_id: {chat_id}")
        except Exception as e:
            logger.error(f"Error starting day phase: {e}", exc_info=True)

    def start_voting_phase(self, chat_id: int, context: CallbackContext):
        try:
            logger.info(f"Starting voting phase in chat_id: {chat_id}")
            game = self.active_games[chat_id]
            game.current_phase = GamePhase.VOTING

            alive_players = [p for p in game.players if p.is_alive]
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    player.username,
                    callback_data=f"vote_{player.telegram_id}"
                )]
                for player in alive_players
            ])

            context.bot.send_message(
                chat_id,
                MESSAGES['voting_phase'],
                reply_markup=markup
            )

            context.job_queue.run_once(
                lambda x: self.process_voting_phase(chat_id, context),
                60,  # 1 minute for voting
                context=chat_id
            )
            logger.info(f"Voting phase started successfully in chat_id: {chat_id}")
        except Exception as e:
            logger.error(f"Error starting voting phase: {e}", exc_info=True)

    def process_voting_phase(self, chat_id: int, context: CallbackContext):
        try:
            logger.info(f"Processing voting phase in chat_id: {chat_id}")
            game = self.active_games[chat_id]
            vote_results = self.process_votes(game.id)

            for message in vote_results:
                context.bot.send_message(chat_id, message)

            game_ended, end_message = self.check_game_end(game.id)
            if game_ended:
                context.bot.send_message(chat_id, end_message)
                del self.active_games[chat_id]
                logger.info(f"Game ended in chat_id: {chat_id}")
                return

            self.start_night_phase(chat_id, context)
            logger.info(f"Voting phase processed successfully in chat_id: {chat_id}")
        except Exception as e:
            logger.error(f"Error processing voting phase: {e}", exc_info=True)

    def format_player_list(self, players: List[Player]) -> str:
        return "\n".join([f"{i + 1}. {player.username}" for i, player in enumerate(players)])

    def join_callback(self, update: Update, context: CallbackContext) -> None:
        try:
            query = update.callback_query
            chat_id = query.message.chat_id
            user_id = query.from_user.id
            username = query.from_user.username or query.from_user.first_name

            logger.info(f"User {username} ({user_id}) trying to join game in chat {chat_id}")

            game = self.active_games.get(chat_id)
            if not game or game.status != GameStatus.WAITING:
                query.answer(MESSAGES['game_already_started'])
                return

            try:
                player = self.add_player(game.id, user_id, username)
                query.answer(MESSAGES['player_joined'].format(username))
            except ValueError as e:
                query.answer(str(e))
                return

            players = game.players
            players_count = len(players)

            if players_count >= MIN_PLAYERS:
                self.start_game(chat_id, context)
            else:
                keyboard = [[InlineKeyboardButton("Միանալ", callback_data="join")]]
                player_list = self.format_player_list(players)
                query.message.edit_text(
                    MESSAGES['waiting_for_players'].format(
                        players_count,
                        MIN_PLAYERS,
                        player_list
                    ),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.HTML
                )

            logger.info(f"Player {username} successfully joined the game")
        except Exception as e:
            logger.error(f"Error in join_callback: {e}", exc_info=True)
            if 'query' in locals():
                query.answer(MESSAGES['error_joining'])