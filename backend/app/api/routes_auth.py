from urllib.parse import urlencode
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.responses import RedirectResponse, JSONResponse
from app.services.auth_service import AuthService
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# In-memory state store (simple dict for MVP)
_states: dict[str, str] = {}  # state -> post-login frontend path


def get_auth_service() -> AuthService:
    return AuthService()


def _frontend_callback_path(next_path: str) -> str:
    first_segment = next_path.strip("/").split("/", 1)[0]
    if first_segment in {"poker", "werewolf"}:
        return f"/{first_segment}/auth/callback"
    return "/auth/callback"


@router.get("/login")
async def login(
    next: str = Query("/", alias="next"),
    auth: AuthService = Depends(get_auth_service),
):
    state = auth.generate_state()
    if not next.startswith("/") or next.startswith("//"):
        next = "/"
    _states[state] = next
    url = auth.get_login_url(state)
    return {"url": url}


@router.get("/callback")
async def callback(code: str, state: str = "", auth: AuthService = Depends(get_auth_service)):
    if state and state not in _states:
        raise HTTPException(status_code=400, detail="Invalid state")

    try:
        token_data = await auth.exchange_code(code)
        access_token = token_data["access_token"]
        user = await auth.verify_user(access_token)
        jwt_token = auth.create_jwt(user)

        next_path = _states.get(state, "/")
        if state:
            _states.pop(state)

        # Redirect to frontend with token
        base = settings.frontend_url.rstrip("/") if settings.frontend_url else ""
        qs = urlencode({"token": jwt_token, "next": next_path})
        return RedirectResponse(f"{base}{_frontend_callback_path(next_path)}?{qs}")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/me")
async def me(request: Request, auth: AuthService = Depends(get_auth_service)):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    token = auth_header[len("Bearer "):]
    try:
        user = auth.verify_jwt(token)
        return {"user": user}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
