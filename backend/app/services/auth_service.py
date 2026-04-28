import secrets
import time
import httpx
from urllib.parse import urlencode
from jose import jwt, JWTError
from app.config import settings


class AuthService:
    """Discord OAuth2 + JWT authentication."""

    DISCORD_AUTH_URL = "https://discord.com/api/oauth2/authorize"
    DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
    DISCORD_API_URL = "https://discord.com/api/v10"

    def __init__(self):
        self.client_id = settings.discord_client_id
        self.client_secret = settings.discord_client_secret
        self.redirect_uri = settings.discord_redirect_uri
        self.required_guild_id = settings.required_guild_id
        self.required_role_id = settings.required_role_id
        self.bot_token = settings.discord_bot_token
        self.jwt_secret = settings.jwt_secret
        self.jwt_algorithm = settings.jwt_algorithm
        self.jwt_expire_minutes = settings.jwt_expire_minutes

    def get_login_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "identify guilds",
        }
        if not self.bot_token:
            # Need guilds.members.read if no bot token for role check
            params["scope"] += " guilds.members.read"

        qs = urlencode(params)
        return f"{self.DISCORD_AUTH_URL}?{qs}&state={state}"

    async def exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.DISCORD_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            return resp.json()

    async def verify_user(self, access_token: str) -> dict:
        """Verify Discord user identity, guild membership, and role."""
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {access_token}"}

            # Get user identity
            user_resp = await client.get(f"{self.DISCORD_API_URL}/users/@me", headers=headers)
            user_resp.raise_for_status()
            user = user_resp.json()

            # Check guild membership
            guilds_resp = await client.get(
                f"{self.DISCORD_API_URL}/users/@me/guilds", headers=headers
            )
            guilds_resp.raise_for_status()
            guilds = guilds_resp.json()

            in_guild = any(g["id"] == self.required_guild_id for g in guilds)
            if not in_guild:
                raise PermissionError("Not a member of the required server")

            # Check role
            if self.bot_token:
                # Use bot token to check member roles
                bot_headers = {"Authorization": f"Bot {self.bot_token}"}
                member_resp = await client.get(
                    f"{self.DISCORD_API_URL}/guilds/{self.required_guild_id}/members/{user['id']}",
                    headers=bot_headers,
                )
                if member_resp.status_code != 200:
                    raise PermissionError("Could not verify server membership")
                member = member_resp.json()
                has_role = self.required_role_id in member.get("roles", [])
            else:
                # Use user token with guilds.members.read scope
                member_resp = await client.get(
                    f"{self.DISCORD_API_URL}/users/@me/guilds/{self.required_guild_id}/member",
                    headers=headers,
                )
                if member_resp.status_code != 200:
                    raise PermissionError("Could not verify server membership")
                member = member_resp.json()
                has_role = self.required_role_id in member.get("roles", [])

            if not has_role:
                raise PermissionError("Missing required role")

            admin_ids = [x.strip() for x in settings.admin_user_ids.split(",") if x.strip()]
            is_admin = user["id"] in admin_ids

            return {
                "id": user["id"],
                "username": user["username"],
                "discriminator": user.get("discriminator", "0"),
                "avatar": user.get("avatar"),
                "global_name": user.get("global_name", user["username"]),
                "is_admin": is_admin,
            }

    def create_jwt(self, user: dict) -> str:
        payload = {
            "sub": user["id"],
            "username": user["username"],
            "global_name": user.get("global_name", user["username"]),
            "avatar": user.get("avatar"),
            "is_admin": user.get("is_admin", False),
            "iat": int(time.time()),
            "exp": int(time.time()) + self.jwt_expire_minutes * 60,
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

    def verify_jwt(self, token: str) -> dict:
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except JWTError:
            raise PermissionError("Invalid or expired token")

    @staticmethod
    def generate_state() -> str:
        return secrets.token_hex(16)
