from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from app.services.auth_service import AuthService
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# In-memory state store (simple dict for MVP)
_states: dict[str, str] = {}  # state -> stored value


def get_auth_service() -> AuthService:
    return AuthService()


@router.get("/login")
async def login(auth: AuthService = Depends(get_auth_service)):
    state = auth.generate_state()
    _states[state] = "pending"
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

        if state:
            _states.pop(state)

        # Redirect to frontend with token
        base = settings.frontend_url.rstrip("/") if settings.frontend_url else "/poker"
        return RedirectResponse(f"{base}/auth/callback?token={jwt_token}")
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
