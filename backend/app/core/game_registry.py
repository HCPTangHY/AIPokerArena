from typing import Any

_registry: dict[str, dict[str, Any]] = {}


def register_game(
    game_type: str,
    engine_class: type,
    config_model: type,
):
    """注册一个游戏类型。"""
    _registry[game_type] = {
        "engine": engine_class,
        "config_model": config_model,
    }


def get_engine_class(game_type: str) -> type:
    """获取游戏引擎类。"""
    if game_type not in _registry:
        raise ValueError(f"Unknown game type: {game_type}. Registered: {list(_registry.keys())}")
    return _registry[game_type]["engine"]


def get_config_model(game_type: str) -> type:
    """获取游戏配置模型。"""
    if game_type not in _registry:
        raise ValueError(f"Unknown game type: {game_type}. Registered: {list(_registry.keys())}")
    return _registry[game_type]["config_model"]


def get_registered_games() -> list[str]:
    """获取所有已注册的游戏类型。"""
    return list(_registry.keys())
