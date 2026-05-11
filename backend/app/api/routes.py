import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.security import create_access_token, decode_access_token, encrypt_api_key, hash_password, key_hint, verify_password
from app.core.config import settings
from app.database.session import get_db
from app.models.tables import ApiKey, Event, Investigation, User
from app.orchestration.jobs import job_service
from app.providers.registry import provider_model_ids, provider_registry, public_model_registry
from app.schemas.api import AuthResponse, InvestigationCreate, LoginRequest, RegisterRequest, ValidateKeyRequest
from app.websocket.manager import manager

logger = logging.getLogger(__name__)


router = APIRouter()


@router.post("/auth/register", response_model=AuthResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"access_token": create_access_token(user.id), "user": {"id": user.id, "email": user.email}}


@router.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_access_token(user.id), "user": {"id": user.id, "email": user.email}}


@router.get("/auth/me")
async def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email}


@router.get("/models")
async def models(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    configured = set(
        await db.scalars(select(ApiKey.provider).where(ApiKey.user_id == user.id))
    )
    return {"providers": public_model_registry(configured)}


@router.post("/validate-key")
async def validate_key(payload: ValidateKeyRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    providers = provider_registry()
    if payload.provider not in providers:
        raise HTTPException(status_code=400, detail="Unsupported provider")
    print("Received key validation request for provider:", payload.provider)
    provider = providers[payload.provider]
    print("Instantiated provider:", provider.name)
    provider.api_key = payload.api_key
    print("Set API key on provider. Now validating...", provider.api_key)
    try:
        valid = await provider.validate_key()
        print("Validation result:", valid)
    except Exception as exc:
        logger.exception("Provider key validation failed for %s", payload.provider)
        raise HTTPException(status_code=400, detail=f"Provider validation failed: {exc}") from exc
    if not valid:
        raise HTTPException(status_code=400, detail="Key failed basic validation")

    existing = await db.scalar(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.provider == payload.provider))
    if existing:
        existing.encrypted_key = encrypt_api_key(payload.api_key)
        existing.key_hint = key_hint(payload.api_key)
        existing.last_validated_at = datetime.utcnow()
    else:
        db.add(
            ApiKey(
                user_id=user.id,
                provider=payload.provider,
                encrypted_key=encrypt_api_key(payload.api_key),
                key_hint=key_hint(payload.api_key),
                last_validated_at=datetime.utcnow(),
            )
        )
    await db.commit()
    return {"ok": True, "provider": payload.provider, "key_hint": key_hint(payload.api_key)}


@router.post("/investigate")
async def investigate(
    payload: InvestigationCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    env_key_name = f"{payload.provider}_api_key"
    if payload.provider not in provider_registry():
        raise HTTPException(status_code=400, detail="Unsupported provider")
    if payload.model not in provider_model_ids(payload.provider):
        raise HTTPException(status_code=400, detail="Unsupported model for provider")
    has_env_key = bool(getattr(settings, env_key_name, None))
    has_user_key = await db.scalar(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.provider == payload.provider))
    if not has_env_key and not has_user_key:
        raise HTTPException(
            status_code=400,
            detail=f"Add a {payload.provider} API key in the BYOK vault before starting an AI investigation.",
        )
    investigation = Investigation(
        user_id=user.id,
        claim=payload.claim,
        selected_provider=payload.provider,
        selected_model=payload.model,
        agent_count=payload.agent_count,
        search_depth=payload.search_depth,
        speed_accuracy=payload.speed_accuracy,
        status="queued",
    )
    db.add(investigation)
    await db.commit()
    await db.refresh(investigation)
    await job_service.enqueue(investigation.id)
    return {"id": investigation.id, "status": investigation.status, "claim": investigation.claim}


@router.get("/investigations")
async def investigations(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(
        select(Investigation).where(Investigation.user_id == user.id).order_by(Investigation.created_at.desc())
    )
    return [
        {
            "id": row.id,
            "claim": row.claim,
            "status": row.status,
            "verdict": row.verdict,
            "confidence": row.confidence,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/investigations/{investigation_id}")
async def investigation_detail(investigation_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    investigation = await db.get(Investigation, investigation_id)
    if not investigation or investigation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Investigation not found")
    events = await db.scalars(select(Event).where(Event.investigation_id == investigation_id).order_by(Event.created_at.asc()))
    return {
        "id": investigation.id,
        "claim": investigation.claim,
        "status": investigation.status,
        "verdict": investigation.verdict,
        "confidence": investigation.confidence,
        "events": [
            {"type": event.type, "payload": json.loads(event.payload_json), "created_at": event.created_at.isoformat()}
            for event in events
        ],
    }


@router.websocket("/ws/investigation/{investigation_id}")
async def investigation_ws(websocket: WebSocket, investigation_id: str):
    token = websocket.query_params.get("token")
    authorization = websocket.headers.get("authorization")
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        user_id = decode_access_token(token)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async for db in get_db():
        investigation = await db.get(Investigation, investigation_id)
        if not investigation or investigation.user_id != user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        break

    await manager.connect(investigation_id, websocket)
    async for db in get_db():
        events = await db.scalars(select(Event).where(Event.investigation_id == investigation_id).order_by(Event.created_at.asc()))
        for event in events:
            await websocket.send_json(
                {
                    "type": event.type,
                    "investigation_id": investigation_id,
                    "payload": json.loads(event.payload_json),
                    "created_at": event.created_at.isoformat(),
                }
            )
        break
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(investigation_id, websocket)
