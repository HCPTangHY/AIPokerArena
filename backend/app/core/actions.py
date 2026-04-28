from app.models.tournament import ActionType


def get_legal_actions(
    player_chips: int,
    current_bet: int,
    player_bet_this_round: int,
    min_raise: int,
    has_acted: bool,
) -> list[ActionType]:
    """Determine legal actions for a player given the current betting state."""
    to_call = current_bet - player_bet_this_round

    if player_chips == 0:
        return []  # all-in already, no actions possible

    if to_call == 0:
        # No bet to face - can check or bet/raise
        actions = [ActionType.CHECK]
        if player_chips > 0:
            actions.append(ActionType.RAISE)
            actions.append(ActionType.ALL_IN)
        return actions

    # Facing a bet
    actions = [ActionType.FOLD]
    if to_call >= player_chips:
        # Can only call all-in
        actions.append(ActionType.ALL_IN)
    else:
        actions.append(ActionType.CALL)
        if player_chips > to_call:
            actions.append(ActionType.RAISE)
            actions.append(ActionType.ALL_IN)

    return actions


def validate_and_fix_action(
    action_type: ActionType,
    amount: int,
    player_chips: int,
    current_bet: int,
    player_bet_this_round: int,
    min_raise: int,
) -> tuple[ActionType, int]:
    """Validate and correct an action. Returns corrected (action_type, amount)."""
    to_call = current_bet - player_bet_this_round

    if action_type == ActionType.FOLD:
        return ActionType.FOLD, 0

    if action_type == ActionType.CHECK:
        if to_call > 0:
            # Can't check when facing a bet - fold instead
            return ActionType.FOLD, 0
        return ActionType.CHECK, 0

    if action_type == ActionType.CALL:
        if to_call >= player_chips:
            return ActionType.ALL_IN, player_chips
        return ActionType.CALL, to_call

    if action_type == ActionType.RAISE:
        if to_call >= player_chips:
            return ActionType.ALL_IN, player_chips
        if amount < min_raise:
            amount = min_raise
        if amount >= player_chips:
            return ActionType.ALL_IN, player_chips
        total_needed = to_call + amount
        if total_needed >= player_chips:
            return ActionType.ALL_IN, player_chips
        return ActionType.RAISE, amount

    if action_type == ActionType.ALL_IN:
        return ActionType.ALL_IN, player_chips

    return ActionType.FOLD, 0  # fallback
