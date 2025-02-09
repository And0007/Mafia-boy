from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Boolean, ForeignKey, Enum, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()

# Чат для общения мафии
mafia_chat_members = Table(
    'mafia_chat_members',
    Base.metadata,
    Column('game_id', Integer, ForeignKey('games.id')),
    Column('player_id', Integer, ForeignKey('players.id'))
)

class GameStatus(enum.Enum):
    WAITING = "waiting"
    ACTIVE = "active"
    FINISHED = "finished"

class GamePhase(enum.Enum):
    NIGHT = "night"
    DAY = "day"
    VOTING = "voting"

class Role(enum.Enum):
    CIVILIAN = "civilian"    # Мирный житель
    MAFIA = "mafia"         # Мафия
    DON = "don"             # Дон мафии
    DOCTOR = "doctor"       # Доктор
    COMMISSIONER = "commissioner"  # Комиссар
    LAWYER = "lawyer"       # Адвокат

class ActionType(enum.Enum):
    KILL = "kill"           # Убийство от мафии
    HEAL = "heal"           # Лечение от доктора
    CHECK = "check"         # Проверка от комиссара
    PROTECT = "protect"     # Защита от адвоката
    VOTE = "vote"           # Голосование днем

class Player(Base):
    __tablename__ = 'players'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True)
    username = Column(String)
    game_id = Column(Integer, ForeignKey('games.id'))
    current_role = Column(Enum(Role), nullable=True)
    is_alive = Column(Boolean, default=True)
    is_revealed = Column(Boolean, default=False)  # Для адвоката, когда его находит дон

    # Отношения
    game = relationship("Game", back_populates="players")
    actions_made = relationship("Action", back_populates="player", foreign_keys="Action.player_id")
    actions_received = relationship("Action", foreign_keys="Action.target_id")
    mafia_chats = relationship("Game", secondary=mafia_chat_members, back_populates="mafia_chat_players")

class Game(Base):
    __tablename__ = 'games'

    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, unique=True)  # ID чата Telegram, где идет игра
    status = Column(Enum(GameStatus), default=GameStatus.WAITING)
    current_phase = Column(Enum(GamePhase), nullable=True)
    night_count = Column(Integer, default=0)

    # Отношения
    players = relationship("Player", back_populates="game")
    actions = relationship("Action", back_populates="game")
    mafia_chat_players = relationship("Player", secondary=mafia_chat_members, back_populates="mafia_chats")

class Action(Base):
    __tablename__ = 'actions'

    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey('games.id'))
    player_id = Column(Integer, ForeignKey('players.id'))
    target_id = Column(Integer, ForeignKey('players.id'))
    action_type = Column(Enum(ActionType))
    night_number = Column(Integer)  # Номер ночи
    result = Column(Boolean, nullable=True)  # Результат действия (успех/неудача)

    # Отношения
    game = relationship("Game", back_populates="actions")
    player = relationship("Player", back_populates="actions_made", foreign_keys=[player_id])