import hashlib
import random
from itertools import combinations
from math import comb

from treys import Card as TreysCard
from treys import Deck as TreysDeck
from treys import Evaluator as TreysEvaluator

_treys = TreysEvaluator()
_FULL_DECK = tuple(TreysDeck.GetFullDeck())


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
    iterations: int = 2000,
    max_exact_combinations: int = 30_000,
) -> dict[str, float]:
    """
    Calculate showdown equity with treys hand evaluation.

    Exact enumeration is used whenever the remaining board runouts are small
    enough. Pre-flop can have more than a million possible runouts, so it uses
    deterministic random sampling to avoid UI jitter while staying fast.
    Returns {player_id: win_percentage} for each active player.
    """
    player_ids = [
        pid for pid in sorted(active_player_ids)
        if pid in hole_cards_map and len(hole_cards_map[pid]) == 2
    ]
    if not player_ids:
        return {}
    if len(player_ids) == 1:
        return {player_ids[0]: 100.0}

    needed = 5 - len(community_cards)
    if needed < 0:
        raise ValueError("community_cards cannot contain more than 5 cards")

    known_ints: set[int] = set()
    for pid in player_ids:
        for card in hole_cards_map[pid]:
            card_int = parse_card(card)
            if card_int in known_ints:
                raise ValueError(f"duplicate known card: {card}")
            known_ints.add(card_int)
    for card in community_cards:
        card_int = parse_card(card)
        if card_int in known_ints:
            raise ValueError(f"duplicate known card: {card}")
        known_ints.add(card_int)

    deck = [card for card in _FULL_DECK if card not in known_ints]
    comm_ints = [parse_card(card) for card in community_cards]
    hole_ints_map = {
        pid: [parse_card(card) for card in hole_cards_map[pid]]
        for pid in player_ids
    }
    shares: dict[str, float] = {pid: 0.0 for pid in player_ids}

    def tally(full_comm: list[int]) -> None:
        best_score = 9999
        best_pids: list[str] = []
        for pid in player_ids:
            score = _treys.evaluate(full_comm, hole_ints_map[pid])
            if score < best_score:
                best_score = score
                best_pids = [pid]
            elif score == best_score:
                best_pids.append(pid)

        split = 1.0 / len(best_pids)
        for pid in best_pids:
            shares[pid] += split

    total_boards = comb(len(deck), needed) if needed else 1
    board_count = 0

    if needed == 0:
        tally(comm_ints)
        board_count = 1
    elif total_boards <= max_exact_combinations:
        for draw in combinations(deck, needed):
            tally(comm_ints + list(draw))
            board_count += 1
    else:
        target = min(max(1, iterations), total_boards)
        rng = random.Random(_equity_seed(hole_cards_map, community_cards, player_ids, target))
        seen_draws: set[tuple[int, ...]] = set()
        attempts = 0
        max_attempts = target * 8

        while board_count < target and attempts < max_attempts:
            attempts += 1
            draw = tuple(sorted(rng.sample(deck, needed)))
            if draw in seen_draws:
                continue
            seen_draws.add(draw)
            tally(comm_ints + list(draw))
            board_count += 1

        while board_count < target:
            tally(comm_ints + rng.sample(deck, needed))
            board_count += 1

    return {
        pid: round(shares[pid] / board_count * 100, 1)
        for pid in player_ids
    }


def _equity_seed(
    hole_cards_map: dict[str, list[str]],
    community_cards: list[str],
    player_ids: list[str],
    iterations: int,
) -> int:
    parts: list[str] = [str(iterations), "board", *community_cards]
    for pid in player_ids:
        parts.append(pid)
        parts.extend(sorted(hole_cards_map[pid]))
    payload = "|".join(parts).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")
