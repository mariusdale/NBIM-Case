from nbim_digest.actions import ACTIONS, ActionCode, get_action


def test_action_taxonomy_has_exactly_five_hierarchical_levels():
    assert [action.code for action in ACTIONS] == [
        ActionCode.NO_ACTION,
        ActionCode.MONITOR,
        ActionCode.ALERT_COMMUNICATIONS,
        ActionCode.ALERT_OWNERSHIP_AND_COMPLIANCE,
        ActionCode.ESCALATE_TO_LEADERSHIP,
    ]
    assert [action.severity for action in ACTIONS] == [0, 1, 2, 3, 4]


def test_action_metadata_is_user_facing_and_professional():
    ownership = get_action(ActionCode.ALERT_OWNERSHIP_AND_COMPLIANCE)

    assert ownership.label == "Alert ownership & compliance"
    assert ownership.color == "#c05621"
    assert "portfolio company" in ownership.when.lower()
    assert "Forward to Ownership & Compliance" in ownership.default_next_step
