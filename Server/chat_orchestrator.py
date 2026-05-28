"""Per-user chat orchestrator for the SecMate Orchestrator runtime.

ChatOrchestrator is the runtime object owned by the API wrapper for one
user/session. It keeps conversation state between turns, calls MessageHandler
for the LangGraph Orchestrator workflow, receives ClueCollector status/data
from the wrapper, and resets state when a conversation is cleared.
"""

import json
import logging
import os
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import AzureChatOpenAI

from agent_state import AgentState
from message_handler import MessageHandler


load_dotenv()

logger = logging.getLogger(__name__)


def build_service_url(service_name: str) -> Optional[str]:
    """Build a service URL from direct or composed environment variables."""
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


LOGGER_URL = build_service_url("LOGGER")


class ChatOrchestrator:
    """Owns conversation state and delegates each turn to MessageHandler."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.llm = AzureChatOpenAI(
            model=os.getenv("MODEL_NAME", "gpt-4o"),
            deployment_name=os.getenv("DEPLOYMENT_NAME", "gpt4o"),
            temperature=float(os.getenv("TEMPERATURE", "0.5")),
            openai_api_type=os.getenv("OPENAI_API_TYPE", "azure"),
        )
        self.msg_handler = MessageHandler(self.llm)
        self._reset_conversation_state()
        logger.info("ChatOrchestrator initialized for user %s", self.user_id)

    def set_uid(self, new_id: str) -> None:
        """Update the user id associated with this orchestrator."""
        self.user_id = new_id

    def generate_cid(self) -> str:
        """Generate a new conversation id."""
        return str(uuid.uuid4())

    async def send_message_to_chat(self, user_message: str, mid: str, session_id: str) -> Dict[str, Any]:
        """Process one user turn through MessageHandler and update local state."""
        try:
            logger.info("Processing message %s for user %s", mid, self.user_id)
            await self._log_message(user_message, "user", mid, session_id)

            handler_response_state: AgentState = self.msg_handler(
                user_message,
                self.conversation,
                self.sys_info,
                self.system_info_pull_count,
                self.user_id,
                self.conversation_id,
                mid,
                session_id,
                self.router_decision,
                self.diagnosis_confidence,
                self.performed_steps,
                self.connection_status,
                self.recommendation_timing,
                self.recommendation,
                self.recommendation_shown,
            )

            self._update_state_from_handler_state(handler_response_state)
            final_response_content = self._extract_response_text(handler_response_state)

            self.conversation.append(HumanMessage(content=user_message))
            self.conversation.append(AIMessage(content=final_response_content))

            await self._log_message(final_response_content, "assistant", mid, session_id)

            return {
                "response": final_response_content,
                "recommendation_shown": self.recommendation_shown,
            }
        except Exception:
            logger.exception("Error processing message %s for user %s", mid, self.user_id)
            return {
                "response": "I apologize, but I encountered an error processing your message. Please try again.",
                "recommendation_shown": False,
            }

    def _extract_response_text(self, handler_state: AgentState) -> str:
        """Choose the final response field returned by MessageHandler."""
        if handler_state.get("augmented_solution"):
            return self.msg_handler.format_solution_for_display(handler_state["augmented_solution"])
        if handler_state.get("augmented_question"):
            return handler_state["augmented_question"]
        if handler_state.get("response"):
            return handler_state["response"]
        return "I'm sorry, I encountered an issue processing that."

    def _update_state_from_handler_state(self, handler_state: AgentState) -> None:
        """Copy persistent workflow state back from the handler result."""
        self.sys_info = handler_state.get("system_info", self.sys_info)
        self.system_info_pull_count = handler_state.get("system_info_pull_count", self.system_info_pull_count)
        self.diagnosis_confidence = handler_state.get("diagnosis_confidence", self.diagnosis_confidence)
        self.performed_steps = handler_state.get("performed_steps", self.performed_steps)
        self.router_decision = handler_state.get("router_decision", self.router_decision)
        self.recommendation = handler_state.get("recommendation", self.recommendation)
        self.recommendation_shown = handler_state.get("recommendation_shown", self.recommendation_shown)

    async def _log_message(self, content: Any, role: str, mid: str, session_id: str) -> bool:
        """Send a message-level log to the optional logging service."""
        if not LOGGER_URL:
            return False

        if not isinstance(content, str):
            content = json.dumps(content, default=str) if isinstance(content, (dict, list)) else str(content)

        message = {
            "message_id": f"{mid}_{role}",
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "diagnosis_confidence": self.diagnosis_confidence,
                "performed_steps": self.performed_steps,
                "connection_status": self.connection_status,
                "system_info_pulls": self.system_info_pull_count,
                "recommendation_timing": self.recommendation_timing,
                "recommendation_shown": self.recommendation_shown,
            },
        }

        try:
            async with aiohttp.ClientSession() as http_session:
                async with http_session.post(f"{LOGGER_URL}/message", json=message) as response:
                    if response.status != 200:
                        logger.warning("Failed to save message log: %s", await response.text())
                        return False
                    return True
        except Exception as exc:
            logger.warning("Error saving message log: %s", exc)
            return False

    async def sys_info_accept(self) -> None:
        """Mark the ClueCollector connection as available."""
        self.connection_status = "Connected"

    async def cancel_sys_info(self) -> None:
        """Mark the ClueCollector connection as unavailable."""
        self.connection_status = "Disconnected"

    async def write_system_info(self, data: Dict[str, Any]) -> None:
        """Store ClueCollector data received by the API wrapper."""
        if "str_info" in data:
            self.sys_info = data["str_info"]
            self.json_sys_info = data.get("json_info", {})
        else:
            self.sys_info = data
            self.json_sys_info = data

        self.system_info_pull_count += 1

    async def wait_for_sys_info(self, timeout: float = 10):
        """Wait for system-info data if an external caller uses the event hook."""
        try:
            await asyncio.wait_for(self.sys_info_event.wait(), timeout)
            return self.sys_info
        except asyncio.TimeoutError:
            return None

    async def clear_history(self, save: bool = True) -> None:
        """Reset local conversation state for a new conversation."""
        if save:
            logger.info(
                "clear_history(save=True) called for user %s. Conversation persistence is handled by the API wrapper.",
                self.user_id,
            )

        connection_status = self.connection_status
        self._reset_conversation_state()
        self.connection_status = connection_status
        logger.info("Chat history cleared for user %s", self.user_id)

    def _reset_conversation_state(self) -> None:
        """Initialize or reset all state that belongs to one conversation."""
        self.conversation_id = self.generate_cid()
        self.conversation: List[BaseMessage] = []
        self.sys_info: Dict[str, Any] = {}
        self.json_sys_info: Dict[str, Any] = {}
        self.system_info_pull_count = 0
        self.diagnosis_confidence = 0.0
        self.performed_steps: List[str] = []
        self.connection_status = "Disconnected"
        self.router_decision = ""
        self.recommendation_timing = os.getenv("RECOMMENDATION_TIMING", "late").lower()
        if self.recommendation_timing not in {"early", "late"}:
            self.recommendation_timing = "late"
        self.recommendation: Optional[Dict[str, Any]] = None
        self.recommendation_shown = False
        self.sys_info_event = asyncio.Event()

    def _get_conv_id(self) -> str:
        """Return the current conversation id for wrapper-level logging."""
        return self.conversation_id
