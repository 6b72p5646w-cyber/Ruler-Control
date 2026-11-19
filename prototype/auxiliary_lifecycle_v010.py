"""Finite charge/child-effect reference, not an auxiliary game client.

A final charge must create the same bounded grant as an earlier charge. The
source's ability to trigger again is independent of an already committed grant.
Continuous powered fields and effect-specific geometry are outside this model.
"""
from dataclasses import dataclass, field
import math


@dataclass
class ChildEffect:
    target_id: str
    starts_at: float
    ends_at: float
    ended: bool = False

    def active(self, now):
        return not self.ended and self.starts_at <= now < self.ends_at


@dataclass
class ChargedSource:
    remaining: int
    retired: bool = False
    grants: dict = field(default_factory=dict)

    def commit(self, receipt, target_id, now, duration, *, valid=True):
        # A replay must not refresh the original grant even if its source was
        # subsequently repaired, refilled or has a new available charge.
        if receipt in self.grants:
            return False
        if not valid or self.retired or self.remaining < 1:
            return False
        if not target_id or not all(math.isfinite(v) for v in (now, duration)) or duration <= 0:
            return False
        self.remaining -= 1
        self.grants[receipt] = ChildEffect(target_id, now, now + duration)
        return True

    def active(self, receipt, now):
        effect = self.grants.get(receipt)
        # Do not recheck remaining charges or retired status here.
        return effect is not None and effect.active(now)

    def retire(self):
        self.retired = True

    def end_target(self, target_id):
        for effect in self.grants.values():
            if effect.target_id == target_id:
                effect.ended = True


def snapshot_next_action(permit, action_id, now):
    """Consume one armed work permit after copying it to its real action.

    The caller owns actual action admission/progress. Once snapshotted, ending
    or consuming the originating item does not reset this action's multiplier.
    """
    if permit['consumed'] or not action_id or not permit['starts_at'] <= now < permit['ends_at']:
        return None
    action = {'action_id': action_id, 'duration_multiplier': permit['duration_multiplier']}
    permit['consumed'] = True
    return action
