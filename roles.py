from dataclasses import dataclass
from typing import List, Optional
from models import Role, Player, Action, ActionType

@dataclass
class RoleHandler:
    def __init__(self, role: Role):
        self.role = role
        self.night_action: Optional[ActionType] = None
        self.can_vote: bool = True

class MafiaRole(RoleHandler):
    def __init__(self):
        super().__init__(Role.MAFIA)
        self.night_action = ActionType.KILL

    def night_action_handler(self, player: Player, target: Player, game_id: int) -> bool:
        return True

class DonRole(RoleHandler):
    def __init__(self):
        super().__init__(Role.DON)
        self.night_action = ActionType.CHECK

    def night_action_handler(self, player: Player, target: Player, game_id: int) -> bool:
        return target.current_role == Role.COMMISSIONER

class DoctorRole(RoleHandler):
    def __init__(self):
        super().__init__(Role.DOCTOR)
        self.night_action = ActionType.HEAL
        self.last_target = None

    def night_action_handler(self, player: Player, target: Player, game_id: int) -> bool:
        if self.last_target == target.id:
            return False
        self.last_target = target.id
        return True

class CommissionerRole(RoleHandler):
    def __init__(self):
        super().__init__(Role.COMMISSIONER)
        self.night_action = ActionType.CHECK
        self.night_count = 0

    def night_action_handler(self, player: Player, target: Player, game_id: int) -> bool:
        self.night_count += 1
        return True

    def can_kill(self) -> bool:
        return self.night_count >= 3

class LawyerRole(RoleHandler):
    def __init__(self):
        super().__init__(Role.LAWYER)
        self.night_action = ActionType.PROTECT
        self.protected_player = None

    def night_action_handler(self, player: Player, target: Player, game_id: int) -> bool:
        if target.current_role not in [Role.MAFIA, Role.DON]:
            return False
        self.protected_player = target.id
        return True

ROLE_HANDLERS = {
    Role.MAFIA: MafiaRole(),
    Role.DON: DonRole(),
    Role.DOCTOR: DoctorRole(),
    Role.COMMISSIONER: CommissionerRole(),
    Role.LAWYER: LawyerRole(),
}