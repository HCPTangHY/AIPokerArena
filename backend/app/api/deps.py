from fastapi import HTTPException, Request, Depends
from app.services.auth_service import AuthService


auth_service = AuthService()


def get_auth_service() -> AuthService:
    return auth_service


def require_auth(request: Request) -> dict:
    """FastAPI dependency: validates JWT and returns user info."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    token = auth_header[len("Bearer "):]
    try:
        user = auth_service.verify_jwt(token)
        return user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_admin(request: Request) -> dict:
    """Validate JWT + check if user is admin."""
    user = require_auth(request)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
