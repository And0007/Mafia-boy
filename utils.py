from typing import List, Dict, Tuple, Optional
from models import Player, Role

def get_alive_players(players: List[Player]) -> List[Player]:
    return [p for p in players if p.is_alive]

def get_mafia_members(players: List[Player]) -> List[Player]:
    return [p for p in players if p.current_role in [Role.MAFIA, Role.DON] and p.is_alive]

def format_player_list(players: List[Player], show_roles: bool = False) -> str:
    result = []
    for i, player in enumerate(players, 1):
        line = f"{i}. {player.username}"
        if show_roles and player.current_role:
            line += f" ({player.current_role.value})"
        result.append(line)
    return "\n".join(result)

def calculate_votes(votes: Dict[int, int], players: List[Player]) -> Tuple[Optional[Player], int]:
    vote_count = {}
    for target_id in votes.values():
        vote_count[target_id] = vote_count.get(target_id, 0) + 1

    if not vote_count:
        return None, 0

    max_votes = max(vote_count.values())
    voted_player_id = max(vote_count.items(), key=lambda x: x[1])[0]

    try:
        voted_player = next(p for p in players if p.id == voted_player_id)
        return voted_player, max_votes
    except StopIteration:
        return None, max_votes