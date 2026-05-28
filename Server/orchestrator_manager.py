from typing import Dict

from chat_orchestrator import ChatOrchestrator


class OrchestratorManager:
    """Minimal per-user orchestrator registry for the release API wrapper."""

    def __init__(self):
        self.user_orchestrators: Dict[str, ChatOrchestrator] = {}

    async def get_or_create_user_orchestrator(self, user_id: str) -> ChatOrchestrator:
        if user_id not in self.user_orchestrators:
            self.user_orchestrators[user_id] = ChatOrchestrator(user_id)
        return self.user_orchestrators[user_id]

    def remove_user_orchestrator(self, user_id: str) -> None:
        self.user_orchestrators.pop(user_id, None)

    def get_stats(self) -> dict:
        return {"active_users": len(self.user_orchestrators)}
