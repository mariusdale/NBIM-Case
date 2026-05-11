import re
from dataclasses import dataclass
from enum import Enum


class ActionCode(str, Enum):
    NO_ACTION = "NO_ACTION"
    MONITOR = "MONITOR"
    ALERT_COMMUNICATIONS = "ALERT_COMMUNICATIONS"
    ALERT_OWNERSHIP_AND_COMPLIANCE = "ALERT_OWNERSHIP_AND_COMPLIANCE"
    ESCALATE_TO_LEADERSHIP = "ESCALATE_TO_LEADERSHIP"


@dataclass(frozen=True)
class ActionDefinition:
    code: ActionCode
    severity: int
    label: str
    when: str
    color: str
    default_next_step: str


ACTIONS = [
    ActionDefinition(
        code=ActionCode.NO_ACTION,
        severity=0,
        label="No action",
        when="Irrelevant; dropped from final digest, kept in audit trail.",
        color="#737373",
        default_next_step="No action. Keep the decision in the audit trail.",
    ),
    ActionDefinition(
        code=ActionCode.MONITOR,
        severity=1,
        label="Monitor",
        when="Relevant background; no immediate action.",
        color="#3b6ea8",
        default_next_step="Monitor only. No immediate communications action required.",
    ),
    ActionDefinition(
        code=ActionCode.ALERT_COMMUNICATIONS,
        severity=2,
        label="Alert communications",
        when="Direct NBIM mention or stakeholder-question risk; comms team reviews today.",
        color="#b7791f",
        default_next_step="Comms should review today and prepare a short internal Q&A if needed.",
    ),
    ActionDefinition(
        code=ActionCode.ALERT_OWNERSHIP_AND_COMPLIANCE,
        severity=3,
        label="Alert ownership & compliance",
        when=(
            "Portfolio company controversy, ethics, sanctions, human rights, climate, "
            "weapons, or governance issue that needs ownership/compliance input before "
            "any external response."
        ),
        color="#c05621",
        default_next_step="Forward to Ownership & Compliance before considering any external response.",
    ),
    ActionDefinition(
        code=ActionCode.ESCALATE_TO_LEADERSHIP,
        severity=4,
        label="Escalate to leadership",
        when="Direct allegations against NBIM/leadership, mandate risk, litigation, or major reputational crisis.",
        color="#b91c1c",
        default_next_step="Escalate to leadership with a one-paragraph briefing and suggested response options.",
    ),
]

_ACTION_BY_CODE = {action.code: action for action in ACTIONS}


def get_action(code: ActionCode | str) -> ActionDefinition:
    return _ACTION_BY_CODE[ActionCode(code)]


def clamp_action(code: str | None) -> ActionCode:
    if not code:
        return ActionCode.NO_ACTION
    normalized = re.sub(r"^\d+_", "", str(code).strip()).upper()
    try:
        return ActionCode(normalized)
    except ValueError:
        return ActionCode.NO_ACTION


def higher_action(left: ActionCode, right: ActionCode) -> ActionCode:
    left_action = get_action(left)
    right_action = get_action(right)
    return left if left_action.severity >= right_action.severity else right
