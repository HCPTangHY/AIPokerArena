from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Discord OAuth
    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = "http://localhost:8000/poker/api/auth/callback"
    required_guild_id: str = ""
    required_role_id: str = ""
    discord_bot_token: str = ""

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # Frontend URL for OAuth redirect (empty = same origin, production mode)
    frontend_url: str = ""

    # Admin Discord user IDs (comma-separated)
    admin_user_ids: str = ""

    # Tournament defaults
    config_dir: str = str(Path(__file__).parent.parent / "configs")
    tournament_config_file: str = "tournament.yaml"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
