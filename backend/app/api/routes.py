import json
import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.security import create_access_token, decode_access_token, encrypt_api_key, hash_password, key_hint, verify_password
from app.core.config import settings
from app.core.time import utcnow
from app.database.session import async_session_maker, get_db
from app.models.tables import ApiKey, Event, Investigation, User
from app.orchestration.jobs import job_service
from app.providers.base import ProviderError
from app.providers.registry import _classify_provider_error, provider_model_ids, provider_registry, public_model_registry
from app.schemas.api import AuthResponse, InvestigationCreate, LoginRequest, RegisterRequest, ValidateKeyRequest
from app.websocket.manager import manager

logger = logging.getLogger(__name__)


router = APIRouter()


def _event_envelope(event: Event, investigation_id: str) -> dict:
    return {
        "id": event.id,
        "type": event.type,
        "investigation_id": investigation_id,
        "payload": json.loads(event.payload_json),
        "created_at": event.created_at.isoformat(),
    }


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
    provider = providers[payload.provider]
    provider.api_key = payload.api_key
    try:
        valid = await provider.validate_key()
    except ProviderError as exc:
        logger.warning("provider_key_validation_failed provider=%s reason=%s", payload.provider, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Provider key validation failed for %s", payload.provider)
        classified = _classify_provider_error(provider.display_name, exc)
        raise HTTPException(status_code=400, detail=str(classified)) from exc
    if not valid:
        raise HTTPException(status_code=400, detail="Key failed basic validation")

    encrypted_key = encrypt_api_key(payload.api_key)
    hint = key_hint(payload.api_key)
    existing = await db.scalar(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.provider == payload.provider))
    if existing:
        existing.encrypted_key = encrypted_key
        existing.key_hint = hint
        existing.last_validated_at = utcnow()
    else:
        db.add(
            ApiKey(
                user_id=user.id,
                provider=payload.provider,
                encrypted_key=encrypted_key,
                key_hint=hint,
                last_validated_at=utcnow(),
            )
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.provider == payload.provider))
        if not existing:
            raise
        existing.encrypted_key = encrypted_key
        existing.key_hint = hint
        existing.last_validated_at = utcnow()
        await db.commit()
    return {"ok": True, "provider": payload.provider, "key_hint": hint}


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
            _event_envelope(event, investigation_id)
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

    async with async_session_maker() as db:
        investigation = await db.get(Investigation, investigation_id)
        if not investigation or investigation.user_id != user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await websocket.accept()
    await manager.register(investigation_id, websocket, buffering=True)
    sent_ids: set[str] = set()
    try:
        cutoff = utcnow()
        async with async_session_maker() as db:
            events = await db.scalars(
                select(Event)
                .where(Event.investigation_id == investigation_id, Event.created_at <= cutoff)
                .order_by(Event.created_at.asc(), Event.id.asc())
            )
            for event in events:
                await websocket.send_json(_event_envelope(event, investigation_id))
                sent_ids.add(event.id)

        await manager.flush_buffered(investigation_id, websocket, already_sent_ids=sent_ids)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(investigation_id, websocket)
    except Exception:
        await manager.disconnect(investigation_id, websocket)
        raise
