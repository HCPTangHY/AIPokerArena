from dataclasses import dataclass, field
from app.models.tournament import TournamentConfig, BlindLevel


@dataclass
class Pot:
    amount: int
    eligible_players: set[str]  # player IDs who can win this pot


def calculate_side_pots(
    player_bets: dict[str, int],  # player_id -> total bet this hand
    active_player_ids: set[str],  # players who haven't folded
) -> list[Pot]:
    """
    Calculate main and side pots. Returns list[Pot], main pot first.

    Algorithm:
    1. Collect all unique bet amounts (from all players) as thresholds.
    2. Sort thresholds ascending.
    3. For each threshold level, compute how much each player contributes at this level.
    4. Only active players who bet at least the threshold are eligible for that pot.

    Example: A all-in 500, B all-in 300, C called 500.
    -> Pot 1 (main): 900 (300 from each) - all eligible
    -> Pot 2 (side): 400 (200 from A + 200 from C) - A,C eligible
    """
    if not active_player_ids:
        return []

    # Collect unique bet amounts from ALL players as thresholds
    thresholds = sorted(set(player_bets.values()))
    if not thresholds or thresholds == [0]:
        return []

    active_bets = {
        pid: player_bets.get(pid, 0)
        for pid in active_player_ids
    }

    pots: list[Pot] = []
    prev_level = 0

    for level in thresholds:
        if level <= prev_level:
            continue

        # Total contribution at this level: each player contributes (min(bet, level) - prev_level)
        total_contrib = 0
        for p_bet in player_bets.values():
            if p_bet > prev_level:
                total_contrib += min(p_bet, level) - prev_level

        # Eligible: active players whose bet >= this level
        eligible = {
            pid for pid, bet in active_bets.items()
            if bet >= level
        }

        if total_contrib > 0 and eligible:
            pots.append(Pot(amount=total_contrib, eligible_players=eligible))

        prev_level = level

    return pots
