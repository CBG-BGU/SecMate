"""Research-facing API wrapper for the SecMate Orchestrator.

This server shows how the paper pipeline is activated without carrying over the
production experiment backend. It keeps session creation, message routing,
conversation reset, profiler/logging hooks, and ClueCollector integration
points explicit so other researchers can replace each adapter with their own
implementation.
"""

import logging
import os
import time
import uuid
from typing import Dict, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from orchestrator_manager import OrchestratorManager
from service_clients import ClueCollectorClient, LoggerClient, RecommendationClient, UserProfileClient


load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def build_service_url(service_name: str) -> Optional[str]:
    """Build an optional external service URL from direct or composed env vars."""
    explicit_url = os.getenv(f"{service_name}_URL")
    if explicit_url:
        return explicit_url.rstrip("/")

    host = os.getenv("SERVICES_HOST")
    service = os.getenv(f"{service_name}_SERVICE")
    port = os.getenv(f"{service_name}_PORT")
    if not host or not service or not port:
        return None

    base_url = f"{host}{service}".rstrip("/")
    separator = "" if base_url.endswith(":") else ":"
    return f"{base_url}{separator}{port}"


AGENT_URL = build_service_url("AGENT")
LOGGER_URL = build_service_url("LOGGER")
PROFILER_URL = build_service_url("PROFILER")
RECOMMENDER_URL = build_service_url("RECOMMENDER")

app = FastAPI(
    title="SecMate Orchestrator Server",
    description="Minimal API wrapper around ChatOrchestrator and MessageHandler.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator_manager = OrchestratorManager()
sessions: Dict[str, str] = {}
profile_client = UserProfileClient(PROFILER_URL)
logger_client = LoggerClient(LOGGER_URL)
recommendation_client = RecommendationClient(RECOMMENDER_URL)
clue_collector_client = ClueCollectorClient(AGENT_URL)


class InitiateSessionRequest(BaseModel):
    """Request body for starting a conversation session."""

    user_id: str = "example-user"


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    profile_status: Optional[dict] = None


class MessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ClearHistoryRequest(BaseModel):
    session_id: Optional[str] = None


class AgentConnectionRequest(BaseModel):
    uuid: str


async def get_session_id(
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID"),
    authorization: Optional[str] = Header(default=None),
) -> str:
    """Read a session id from headers for callback-style endpoints."""
    if x_session_id:
        return x_session_id

    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    raise HTTPException(
        status_code=401,
        detail="Missing session id. Pass it in the request body, X-Session-ID, or Authorization: Bearer <session_id>.",
    )


def get_user_id_for_session(session_id: str) -> str:
    """Resolve a session id to the user id it represents."""
    user_id = sessions.get(session_id)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user_id


async def get_orchestrator_for_session(session_id: str):
    """Return the per-user ChatOrchestrator instance that owns conversation state."""
    user_id = get_user_id_for_session(session_id)
    return await orchestrator_manager.get_or_create_user_orchestrator(user_id)


async def associate_uid(user_id: str):
    """Optional ClueCollector association call used by the original runtime."""
    return await clue_collector_client.associate_uid(user_id)


@app.get("/health")
async def health_check():
    """Basic readiness endpoint for local runs and smoke tests."""
    return {
        "status": "ok",
        "active_sessions": len(sessions),
        "active_users": orchestrator_manager.get_stats()["active_users"],
        "agent_service_configured": AGENT_URL is not None,
        "profiler_configured": PROFILER_URL is not None,
        "logger_configured": LOGGER_URL is not None,
        "recommender_configured": RECOMMENDER_URL is not None,
        "timestamp": time.time(),
    }


@app.post("/initiate_session", response_model=SessionResponse)
async def initiate_session(request: InitiateSessionRequest):
    """Create a session and initialize the user profile component."""
    session_id = str(uuid.uuid4())
    sessions[session_id] = request.user_id
    await orchestrator_manager.get_or_create_user_orchestrator(request.user_id)
    profile_status = await profile_client.initialize_user(request.user_id)
    return SessionResponse(session_id=session_id, user_id=request.user_id, profile_status=profile_status)


@app.post("/send_message_to_genai")
async def send_message_to_gen(request: MessageRequest):
    """Send one user turn through ChatOrchestrator and the MessageHandler graph."""
    if not request.message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    session_id = request.session_id
    if not session_id:
        raise HTTPException(status_code=401, detail="Missing session_id in request body")

    user_id = get_user_id_for_session(session_id)
    orchestrator = await get_orchestrator_for_session(session_id)
    mid = str(uuid.uuid4())
    result = await orchestrator.send_message_to_chat(request.message, mid, session_id)
    profile_update = await profile_client.record_interaction(
        user_id=user_id,
        session_id=session_id,
        conversation_id=orchestrator._get_conv_id(),
        message_id=mid,
        user_message=request.message,
        agent_response=result,
    )
    result["profile_update"] = profile_update
    return JSONResponse(content=result, status_code=200)


@app.post("/clear_history")
async def clear_history(request: ClearHistoryRequest):
    """Save the transcript, then reset the session's conversation state."""
    if not request.session_id:
        raise HTTPException(status_code=401, detail="Missing session_id in request body")

    user_id = get_user_id_for_session(request.session_id)
    orchestrator = await get_orchestrator_for_session(request.session_id)
    save_result = await logger_client.save_conversation(
        user_id=user_id,
        session_id=request.session_id,
        conversation_id=orchestrator._get_conv_id(),
        conversation_history=orchestrator.conversation,
    )
    await orchestrator.clear_history(save=False)
    return {
        "status": "success",
        "message": "Conversation history cleared",
        "save_result": save_result,
    }


@app.post("/clear_history_gen")
async def clear_history_gen(request: ClearHistoryRequest):
    """Compatibility alias for the original backend endpoint."""
    return await clear_history(request)


@app.post("/api/system_info")
async def receive_system_info(data: dict, session_id: str = Depends(get_session_id)):
    """Receive system data collected by ClueCollector for later agent turns."""
    orchestrator = await get_orchestrator_for_session(session_id)
    await orchestrator.write_system_info(data)
    return {"status": "success"}


@app.post("/api/agent_connect")
async def receive_agent_connection(request: AgentConnectionRequest):
    """Record that a ClueCollector client connected for a user id."""
    orchestrator = await orchestrator_manager.get_or_create_user_orchestrator(request.uuid)
    await orchestrator.sys_info_accept()
    return {"status": "success"}


@app.get("/check_agent_connectivity")
async def check_agent_connectivity(session_id: str = Depends(get_session_id)):
    """Check ClueCollector connectivity, using the bridge service if configured."""
    user_id = get_user_id_for_session(session_id)
    orchestrator = await get_orchestrator_for_session(session_id)

    if not AGENT_URL:
        return {"connected": orchestrator.connection_status == "Connected", "source": "local_state"}

    try:
        connectivity = await clue_collector_client.check_connectivity(user_id)
        connected = bool(connectivity.get("connected"))
    except Exception as exc:
        logger.warning("Agent connectivity check failed: %s", exc)
        connected = False

    if connected:
        await orchestrator.sys_info_accept()
    else:
        await orchestrator.cancel_sys_info()

    return {"connected": connected, "source": "agent_service"}


@app.post("/associate_uid")
async def associate_uid_endpoint(session_id: str = Depends(get_session_id)):
    """Ask the ClueCollector bridge to associate a user id with a client id."""
    user_id = get_user_id_for_session(session_id)
    return await associate_uid(user_id)


@app.post("/recommendation")
async def recommendation(session_id: str = Depends(get_session_id)):
    """Show the clean RecommendationClient boundary for later integration work."""
    user_id = get_user_id_for_session(session_id)
    orchestrator = await get_orchestrator_for_session(session_id)
    return await recommendation_client.recommend(user_id, orchestrator.conversation)
