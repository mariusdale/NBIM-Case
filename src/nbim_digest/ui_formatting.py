from .actions import ActionCode, get_action


def action_badge_html(code: ActionCode) -> str:
    action = get_action(code)
    return (
        f"<span style='background:{action.color}; color:white; padding:0.25rem 0.55rem; "
        f"border-radius:6px; font-size:0.82rem; font-weight:600;'>{action.label}</span>"
    )


def human_rule_decision(value: str) -> str:
    return {"pass": "Pass", "review": "Review", "skip": "Skip"}.get(value, value.title())


def human_source(source: str) -> str:
    return source.replace("Demo article: ", "")
