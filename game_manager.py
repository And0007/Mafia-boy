import asyncio
from typing import List, Dict
from datetime import datetime, timedelta
from models import Game, Player, Action, GameStatus, GamePhase, Role, ActionType
from database import get_db
from messages import MESSAGES
from roles import ROLE_HANDLERS
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import logging

logger = logging.getLogger(__name__)

class GameManager:
    def __init__(self):
        self.active_games: Dict[int, Game] = {}
        self.player_votes: Dict[int, Dict[int, int]] = {}  # game_id -> {voter_id: target_id}
        self.role_handlers = ROLE_HANDLERS

    def create_game(self, chat_id: int) -> Game:
        db = next(get_db())
        game = Game(
            chat_id=chat_id,
            status=GameStatus.WAITING,
            current_phase=None
        )
        db.add(game)
        db.commit()
        self.active_games[chat_id] = game
        return game

    def add_player(self, game_id: int, telegram_id: int, username: str) -> Player:
        db = next(get_db())
        # Проверяем существующего игрока
        player = db.query(Player).filter(Player.telegram_id == telegram_id).first()
        if player:
            if player.game_id != game_id:
                # Обновляем существующего игрока для новой игры
                player.game_id = game_id
                player.username = username
                player.is_alive = True
                player.current_role = None
                player.is_revealed = False
        else:
            # Создаем нового игрока
            player = Player(
                telegram_id=telegram_id,
                username=username,
                game_id=game_id,
                is_alive=True,
                is_revealed=False
            )
            db.add(player)

        db.commit()
        db.refresh(player)
        return player

    def assign_roles(self, game_id: int) -> Dict[int, Role]:
        db = next(get_db())
        game = db.query(Game).filter(Game.id == game_id).first()
        players = db.query(Player).filter(Player.game_id == game_id).all()

        num_players = len(players)
        num_mafia = max(1, num_players // 3)

        roles = [Role.CIVILIAN] * num_players
        roles[:num_mafia] = [Role.MAFIA] * (num_mafia - 1) + [Role.DON]
        roles[num_mafia:num_mafia + 2] = [Role.DOCTOR, Role.COMMISSIONER]

        if num_players >= 8:
            roles[num_mafia + 2] = Role.LAWYER

        random.shuffle(roles)

        roles_dict = {}
        for player, role in zip(players, roles):
            player.current_role = role
            player.is_alive = True
            player.is_revealed = False
            roles_dict[player.telegram_id] = role

            # Добавляем мафию в специальный чат
            if role in [Role.MAFIA, Role.DON]:
                if player not in game.mafia_chat_players:
                    game.mafia_chat_players.append(player)

        db.commit()
        return roles_dict

    def process_night_actions(self, game_id: int) -> List[str]:
        db = next(get_db())
        game = db.query(Game).filter(Game.id == game_id).first()
        actions = db.query(Action).filter(
            Action.game_id == game_id,
            Action.night_number == game.night_count
        ).all()

        messages = []
        killed_players = set()
        protected_players = set()

        # Process protection actions first
        for action in actions:
            if action.action_type in [ActionType.HEAL, ActionType.PROTECT]:
                target = db.query(Player).filter(Player.id == action.target_id).first()
                if target:
                    protected_players.add(target.id)

        # Process kill actions
        for action in actions:
            if action.action_type == ActionType.KILL:
                target = db.query(Player).filter(Player.id == action.target_id).first()
                if target and target.id not in protected_players:
                    killed_players.add(target.id)
                    target.is_alive = False
                    messages.append(MESSAGES['player_killed'].format(target.username))

        db.commit()
        return messages

    def check_game_end(self, game_id: int) -> tuple[bool, str]:
        db = next(get_db())
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

    def handle_night_action(self, update: Update, context: CallbackContext) -> None:
        query = update.callback_query
        _, action_type, target_telegram_id = query.data.split('_')

        chat_id = query.message.chat_id
        player_telegram_id = query.from_user.id

        game = self.active_games.get(chat_id)
        if not game or game.current_phase != GamePhase.NIGHT:
            query.answer(MESSAGES['not_night_phase'])
            return

        db = next(get_db())
        player = db.query(Player).filter(
            Player.game_id == game.id,
            Player.telegram_id == player_telegram_id,
            Player.is_alive == True
        ).first()

        target = db.query(Player).filter(
            Player.game_id == game.id,
            Player.telegram_id == int(target_telegram_id),
            Player.is_alive == True
        ).first()

        if not player or not target:
            query.answer(MESSAGES['player_not_found'])
            return

        role_handler = self.role_handlers.get(player.current_role)
        if not role_handler or not role_handler.night_action:
            query.answer(MESSAGES['no_night_action'])
            return

        action_result = role_handler.night_action_handler(player, target, game.id)
        if not action_result:
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
        query.answer(MESSAGES['action_successful'])

    def handle_vote(self, update: Update, context: CallbackContext) -> None:
        query = update.callback_query
        _, target_telegram_id = query.data.split('_')

        chat_id = query.message.chat_id
        voter_telegram_id = query.from_user.id

        game = self.active_games.get(chat_id)
        if not game or game.current_phase != GamePhase.VOTING:
            query.answer(MESSAGES['not_night_phase'])
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

    def process_votes(self, game_id: int) -> List[str]:
        if game_id not in self.player_votes:
            return ["Нет голосов"]

        db = next(get_db())
        votes = self.player_votes[game_id]

        # Count votes
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

        # Find player with most votes
        max_votes = max(vote_counts.values())
        voted_player_id = max(vote_counts.items(), key=lambda x: x[1])[0]

        # Get player and update status
        voted_player = db.query(Player).filter(
            Player.id == voted_player_id
        ).first()

        if voted_player:
            voted_player.is_alive = False
            db.commit()
            return [MESSAGES['player_killed'].format(voted_player.username)]

        return ["Ошибка при подсчете голосов"]

    def start_game(self, chat_id: int, context: CallbackContext) -> None:
        """Starts the game when enough players have joined"""
        game = self.active_games[chat_id]
        game.status = GameStatus.ACTIVE

        # Assign roles
        roles = self.assign_roles(game.id)

        # Send each player their role in private message
        for telegram_id, role in roles.items():
            try:
                role_message = MESSAGES[f'role_{role.value}']
                context.bot.send_message(telegram_id, role_message)
            except Exception as e:
                logger.error(f"Failed to send role to {telegram_id}: {e}")

        context.bot.send_message(chat_id, MESSAGES['game_start'])
        self.start_night_phase(chat_id, context)

    def start_night_phase(self, chat_id: int, context: CallbackContext):
        game = self.active_games[chat_id]
        game.current_phase = GamePhase.NIGHT
        game.night_count += 1

        context.bot.send_message(chat_id, MESSAGES['night_phase'])

        # Send night action prompts to special roles
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

        # Schedule day phase after delay
        context.job_queue.run_once(
            lambda x: self.start_day_phase(chat_id, context),
            120,  # 2 minutes for night phase
            context=chat_id
        )

    def start_day_phase(self, chat_id: int, context: CallbackContext):
        game = self.active_games[chat_id]
        game.current_phase = GamePhase.DAY

        # Process night actions
        night_results = self.process_night_actions(game.id)
        for message in night_results:
            context.bot.send_message(chat_id, message)

        # Check game end
        game_ended, end_message = self.check_game_end(game.id)
        if game_ended:
            context.bot.send_message(chat_id, end_message)
            del self.active_games[chat_id]
            return

        context.bot.send_message(chat_id, MESSAGES['day_phase'])

        # Schedule voting phase after delay
        context.job_queue.run_once(
            lambda x: self.start_voting_phase(chat_id, context),
            180,  # 3 minutes for day phase
            context=chat_id
        )

    def start_voting_phase(self, chat_id: int, context: CallbackContext):
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

        # Schedule voting processing after delay
        context.job_queue.run_once(
            lambda x: self.process_voting_phase(chat_id, context),
            60,  # 1 minute for voting
            context=chat_id
        )

    def process_voting_phase(self, chat_id: int, context: CallbackContext):
        game = self.active_games[chat_id]
        vote_results = self.process_votes(game.id)

        for message in vote_results:
            context.bot.send_message(chat_id, message)

        # Check game end after voting
        game_ended, end_message = self.check_game_end(game.id)
        if game_ended:
            context.bot.send_message(chat_id, end_message)
            del self.active_games[chat_id]
            return

        # Start next night phase
        self.start_night_phase(chat_id, context)