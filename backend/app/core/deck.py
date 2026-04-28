from treys import Deck as TreysDeck, Card as TreysCard


def card_int_to_str(card_int: int) -> str:
    """Convert treys card int to 'Ah', 'Kd', etc. format."""
    return TreysCard.int_to_str(card_int)


class Deck:
    """Wrapper around treys.Deck for card management."""

    def __init__(self):
        self._deck = TreysDeck()

    def draw(self, count: int = 1) -> list[str]:
        card_ints = self._deck.draw(count)
        return [card_int_to_str(c) for c in card_ints]

    def shuffle(self):
        self._deck.shuffle()

    def reset(self):
        self._deck = TreysDeck()

    def __len__(self) -> int:
        return len(self._deck)
