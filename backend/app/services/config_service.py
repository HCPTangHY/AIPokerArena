import os
import re
from pathlib import Path
import yaml
from app.models.tournament import TournamentConfig, BlindLevel
from app.models.player import AIPlayerConfig


def _substitute_env(value: str) -> str:
    """Replace ${ENV_VAR} with environment variable values."""
    if not isinstance(value, str):
        return value

    def replacer(match):
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return re.sub(r'\$\{(\w+)\}', replacer, value)


def load_tournament_config(path: str | None = None) -> TournamentConfig:
    """Load tournament config from YAML file."""
    if path is None:
        path = Path(__file__).parent.parent.parent / "configs" / "tournament.yaml"
    else:
        path = Path(path)

    if not path.exists():
        return TournamentConfig()

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        return TournamentConfig()

    tournament_data = data.get("tournament", {})
    return TournamentConfig(**tournament_data)


def load_player_configs(path: str | None = None) -> list[AIPlayerConfig]:
    """Load AI player configs from YAML file."""
    if path is None:
        path = Path(__file__).parent.parent.parent / "configs" / "tournament.yaml"
    else:
        path = Path(path)

    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        return []

    players_data = data.get("players", [])
    configs = []
    for pd in players_data:
        pd["api_key"] = _substitute_env(pd.get("api_key", ""))
        pd["api_endpoint"] = _substitute_env(pd.get("api_endpoint", ""))
        configs.append(AIPlayerConfig(**pd))

    return configs


def save_tournament_config(config: TournamentConfig, players: list[AIPlayerConfig], path: str | None = None):
    """Save tournament + player configs to YAML file."""
    if path is None:
        path = Path(__file__).parent.parent.parent / "configs" / "tournament.yaml"
    else:
        path = Path(path)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "tournament": config.model_dump(exclude_none=True),
        "players": [p.model_dump() for p in players],
    }

    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
