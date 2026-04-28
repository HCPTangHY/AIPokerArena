from app.models.tournament import TournamentConfig, BlindLevel


def generate_blind_levels(config: TournamentConfig) -> list[BlindLevel]:
    """Generate blind levels if not manually specified. Doubles every level."""
    if config.blind_levels:
        return [
            BlindLevel(
                level=level.level,
                small_blind=level.small_blind,
                big_blind=level.big_blind,
                ante=level.ante if config.ante_enabled else 0,
            )
            for level in config.blind_levels
        ]

    levels: list[BlindLevel] = []
    sb = config.small_blind_initial
    bb = config.big_blind_initial

    # Generate enough levels for a typical tournament (20 levels)
    for i in range(1, 21):
        level = BlindLevel(
            level=i,
            small_blind=sb,
            big_blind=bb,
            ante=0,
        )
        if config.ante_enabled and i >= config.ante_start_level:
            level.ante = max(1, bb // 4)

        levels.append(level)

        # Double blinds each level (standard progression)
        sb = sb * 2
        bb = bb * 2

    return levels
