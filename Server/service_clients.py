"""Replaceable adapters for external services used by the release pipeline.

The paper system calls several components through the Orchestrator boundary:
the Profiler, experiment logger, Recommender, and ClueCollector bridge service.
The Profiler, logger, and Recommender implementations are intentionally not
bundled with this clean release; ClueCollector and its bridge are included.
This module keeps those boundaries explicit while making the repository
runnable without private infrastructure.

Each client follows the same pattern:

1. If a service URL is configured, call that HTTP service.
2. If no URL is configured, return a small local placeholder response that
   documents the expected payload shape.

Researchers can replace these classes with their own local files, databases,
cloud services, Docker services, or REST clients without changing the main
agent logic.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx


logger = logging.getLogger(__name__)


class UserProfileClient:
    """Adapter for the user profiler described in the paper.

    Researchers can replace this client with their own profile source, such as
    a database, S3/Cognito, a survey service, or a local file. A replacement
    should support session initialization, turn-level profile updates, and
    optional profile lookup for personalization.

    When no service URL is configured, the client behaves as a placeholder and
    returns status objects for write-like calls and None for profile lookups.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url

    async def initialize_user(self, user_id: str) -> Dict[str, Any]:
        """Start or load the user's profile at session creation time."""
        if not self.base_url:
            return {"status": "not_configured", "event": "profile_initialized", "user_id": user_id}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{self.base_url}/init_user", params={"uid": user_id})
            response.raise_for_status()
            return response.json()

    async def record_interaction(
        self,
        user_id: str,
        session_id: str,
        conversation_id: str,
        message_id: str,
        user_message: str,
        agent_response: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send a completed turn to the profiler for profile updates."""
        payload = {
            "question": user_message,
            "result": agent_response,
            "id": {
                "uid": user_id,
                "conversation_id": conversation_id,
                "mid": message_id,
                "session_id": session_id,
            },
        }
        if not self.base_url:
            return {
                "status": "not_configured",
                "event": "profile_interaction_recorded",
                "user_id": user_id,
                "session_id": session_id,
                "message_id": message_id,
            }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{self.base_url}/examine", json=payload)
            response.raise_for_status()
            return response.json()

    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Return a user proficiency profile from an external service if configured."""
        if not self.base_url:
            return None

        try:
            response = httpx.get(f"{self.base_url}/profile/{user_id}", timeout=10.0)
            response.raise_for_status()
            data = response.json()
            return data.get("profile", data)
        except Exception as exc:
            logger.warning("Profile lookup failed for user %s: %s", user_id, exc)
            return None


class LoggerClient:
    """Adapter for conversation and turn-level logging.

    Researchers can replace this with a database logger, local file logger,
    S3-backed exporter, Cognito-aware logger, or any other experiment logging
    implementation. A replacement should persist enough information to
    reconstruct the conversation, message ids, user id, session id, and any
    MessageHandler log entries needed for analysis.

    The placeholder stores payloads in memory for local inspection only.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url
        self.saved_conversations: List[Dict[str, Any]] = []

    async def save_conversation(
        self,
        user_id: str,
        session_id: str,
        conversation_id: str,
        conversation_history: List[Any],
    ) -> Dict[str, Any]:
        """Persist a conversation transcript before clearing local state."""
        payload = {
            "user_id": user_id,
            "session_id": session_id,
            "conversation_id": conversation_id,
            "conversation_history": [
                {
                    "role": message.__class__.__name__,
                    "content": getattr(message, "content", str(message)),
                }
                for message in conversation_history
            ],
        }

        if not self.base_url:
            self.saved_conversations.append(payload)
            return {"status": "not_configured", "event": "conversation_saved", "message_count": len(payload["conversation_history"])}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{self.base_url}/conversation", json=payload)
            response.raise_for_status()
            return response.json()

    def save_log_entry(
        self,
        user_id: str,
        conversation_id: str,
        log_entry: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Persist one comprehensive MessageHandler log entry."""
        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "log_entry": log_entry,
        }
        if not self.base_url:
            self.saved_conversations.append(payload)
            return {"status": "not_configured", "event": "log_entry_saved"}

        try:
            response = httpx.post(f"{self.base_url}/log_entry", json=payload, timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("Log entry save failed for user %s: %s", user_id, exc)
            return {"status": "error", "event": "log_entry_save_failed", "error": str(exc)}


class RecommendationClient:
    """Adapter boundary for the recommendation component.

    A replacement should receive a user id plus the current conversation and
    return the recommendation payload expected by the UI or agent. The
    recommendation endpoint in server.py uses this client to show the
    integration point.

    MessageHandler may also call a recommender URL directly for the full agent
    workflow; this class documents the cleaner wrapper boundary for researchers
    who want to swap in their own recommender service.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url

    async def recommend(self, user_id: str, conversation_history: List[Any]) -> Optional[Dict[str, Any]]:
        payload = {
            "user_id": user_id,
            "conversation_history": [
                getattr(message, "content", str(message)) for message in conversation_history
            ],
        }
        if not self.base_url:
            return {"status": "not_configured", "event": "recommendation_requested", "payload": payload}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{self.base_url}/recommend", json=payload)
            response.raise_for_status()
            return response.json()


class ClueCollectorClient:
    """Adapter for the ClueCollector/agent-service bridge.

    This is not a replacement for ClueCollector. It is the HTTP client used by
    server.py to talk to the bundled bridge in agent_service/src/sia_server.py.
    The bridge then communicates with ClueCollector/src/runner.py over
    WebSocket.

    A compatible bridge should associate the current user/session with a
    ClueCollector client id and report whether the local ClueCollector process
    is connected. The included agent_service implementation shows one
    WebSocket-based bridge, but this client can point to any equivalent local
    or remote service.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url

    async def associate_uid(self, user_id: str) -> Dict[str, Any]:
        if not self.base_url:
            return {
                "status": "not_configured",
                "event": "cluecollector_bridge_not_configured",
                "user_id": user_id,
                "message": "Set AGENT_URL to the agent_service bridge to enable ClueCollector CID association.",
            }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{self.base_url}/associate_uid", json={"user_id": user_id})
            response.raise_for_status()
            return response.json()

    async def check_connectivity(self, user_id: str) -> Dict[str, Any]:
        if not self.base_url:
            return {
                "connected": False,
                "source": "not_configured",
                "user_id": user_id,
                "message": "Set AGENT_URL to the agent_service bridge to check ClueCollector connectivity.",
            }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/connectivity_check", params={"uid": user_id})
            response.raise_for_status()
            return response.json()
