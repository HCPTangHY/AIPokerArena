import random
from treys import Evaluator as TreysEvaluator, Card as TreysCard, Deck as TreysDeck

_treys = TreysEvaluator()


def parse_card(card_str: str) -> int:
    """Convert 'Ah' 'Kd' etc. to treys integer representation."""
    return TreysCard.new(card_str)


def evaluate_hand(hole_cards: list[str], community_cards: list[str]) -> int:
    """Return treys score (1=best/royal flush, 7462=worst/7-high)."""
    hole_ints = [parse_card(c) for c in hole_cards]
    comm_ints = [parse_card(c) for c in community_cards]
    return _treys.evaluate(comm_ints, hole_ints)


def get_hand_name(score: int) -> str:
    return _treys.class_to_string(_treys.get_rank_class(score))


def determine_winners(
    hole_cards_map: dict[str, list[str]],  # player_id -> hole cards
    community_cards: list[str],
    eligible_player_ids: set[str],
) -> list[str]:
    """Return list of winning player IDs (handles ties)."""
    best_score = 9999
    winners: list[str] = []

    for pid in eligible_player_ids:
        if pid not in hole_cards_map:
            continue
        score = evaluate_hand(hole_cards_map[pid], community_cards)
        if score < best_score:
            best_score = score
            winners = [pid]
        elif score == best_score:
            winners.append(pid)

    return winners


def calculate_equity(
    hole_cards_map: dict[str, list[str]],  # player_id -> hole cards
    community_cards: list[str],
    active_player_ids: set[str],
    iterations: int = 500,
) -> dict[str, float]:
    """
    Monte Carlo equity calculation.
    Returns {player_id: win_percentage} for each active player.
    """
    if len(active_player_ids) <= 1:
        pid = next(iter(active_player_ids)) if active_player_ids else ""
        return {pid: 1.0} if pid else {}

    # Build known cards (exclude from deck)
    known_ints: set[int] = set()
    for cards in hole_cards_map.values():
        for c in cards:
            known_ints.add(parse_card(c))
    for c in community_cards:
        known_ints.add(parse_card(c))

    # Build a fresh deck minus known cards
    full_deck = TreysDeck.GetFullDeck()
    deck = [c for c in full_deck if c not in known_ints]
    # Shuffle once — we'll deal sequentially from different positions
    random.shuffle(deck)

    needed = 5 - len(community_cards)
    wins: dict[str, int] = {pid: 0 for pid in active_player_ids}
    ties: dict[str, int] = {pid: 0 for pid in active_player_ids}

    comm_ints = [parse_card(c) for c in community_cards]
    hole_ints_map = {pid: [parse_card(c) for c in cards] for pid, cards in hole_cards_map.items()}

    for i in range(iterations):
        # Deal remaining community cards
        start = (i * needed) % (len(deck) - needed + 1) if len(deck) > needed else 0
        if start + needed > len(deck):
            # Re-shuffle and start over
            random.shuffle(deck)
            start = 0

        full_comm = comm_ints + deck[start:start + needed]
        best_score = 9999
        best_pids: list[str] = []

        for pid in active_player_ids:
            if pid not in hole_ints_map:
                continue
            score = _treys.evaluate(full_comm, hole_ints_map[pid])
            if score < best_score:
                best_score = score
                best_pids = [pid]
            elif score == best_score:
                best_pids.append(pid)

        if len(best_pids) == 1:
            wins[best_pids[0]] += 1
        else:
            for pid in best_pids:
                ties[pid] += 1

    result: dict[str, float] = {}
    for pid in active_player_ids:
        w = wins.get(pid, 0)
        t = ties.get(pid, 0)
        result[pid] = round((w + t / len(active_player_ids)) / iterations * 100, 1)

    return result
