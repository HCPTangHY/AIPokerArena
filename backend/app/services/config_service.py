import os
import re
from pathlib import Path
import yaml
from app.models.tournament import TournamentConfig, BlindLevel
from app.models.player import AIPlayerConfig
from app.models.werewolf import WerewolfConfig

CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs"

GAME_CONFIG_FILES = {
    "poker": "tournament.yaml",
    "werewolf": "werewolf.yaml",
}

GAME_CONFIG_MODELS = {
    "poker": TournamentConfig,
    "werewolf": WerewolfConfig,
}


def _substitute_env(value: str) -> str:
    """Replace ${ENV_VAR} with environment variable values."""
    if not isinstance(value, str):
        return value

    def replacer(match):
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return re.sub(r'\$\{(\w+)\}', replacer, value)


def _get_config_path(game_type: str = "poker") -> Path:
    filename = GAME_CONFIG_FILES.get(game_type, f"{game_type}.yaml")
    return CONFIGS_DIR / filename


def load_tournament_config(game_type: str = "poker", path: str | None = None):
    """Load tournament config from YAML file. Returns the appropriate config model."""
    if path is not None:
        filepath = Path(path)
    else:
        filepath = _get_config_path(game_type)

    config_model = GAME_CONFIG_MODELS.get(game_type, TournamentConfig)

    if not filepath.exists():
        return config_model(game_type=game_type)

    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        return config_model(game_type=game_type)

    tournament_data = data.get("tournament", {})
    tournament_data.setdefault("game_type", game_type)
    return config_model(**tournament_data)


def load_player_configs(game_type: str = "poker", path: str | None = None) -> list[AIPlayerConfig]:
    """Load AI player configs from YAML file."""
    if path is not None:
        filepath = Path(path)
    else:
        filepath = _get_config_path(game_type)

    if not filepath.exists():
        return []

    with open(filepath, "r", encoding="utf-8") as f:
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


def save_tournament_config(config: TournamentConfig, players: list[AIPlayerConfig], game_type: str = "poker", path: str | None = None):
    """Save tournament + player configs to YAML file."""
    if path is not None:
        filepath = Path(path)
    else:
        filepath = _get_config_path(game_type)

    filepath.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "tournament": config.model_dump(exclude_none=True),
        "players": [p.model_dump() for p in players],
    }

    with open(filepath, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

