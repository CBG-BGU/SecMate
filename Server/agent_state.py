"""Shared state schema for the Orchestrator graph.

LangGraph passes this TypedDict between MessageHandler nodes. Most fields are
updated incrementally as the workflow routes between sentiment analysis,
diagnosis confidence, ClueCollector selection, follow-up questions, and final
solution generation.
"""

from typing import TypedDict, List, Dict, Any
from langchain_core.messages import BaseMessage

from enum import Enum


class EmotionalState(Enum):
    """User emotional state estimated from the current message."""
    CALM = "0"
    LIGHTLY_FRUSTRATED = "1"
    FRUSTRATED = "2"
    VERY_FRUSTRATED = "3"
    EXTREMELY_FRUSTRATED = "4"
    OVERWHELMED = "5"
    UNKNOWN = "-1"



class AgentState(TypedDict):
    user_query: str
    user_id: str
    conversation_id: str  # Conversation id used by logs and wrapper state.
    mid: str  # Message id for the current turn.
    step_number: int  # Current workflow step count.
    session_id: str
    emotional_state: EmotionalState
    conversation_history: List[BaseMessage]
    system_info: dict
    ts_question: str
    ts_solution: str  # Raw solution from the solution-generation chain.
    augmented_solution: Any  # Final solution text, possibly with recommendation text.
    augmented_question: str
    system_info_pull_count: int
    
    performed_steps: List[str]
    router_decision: str
    diagnosis_confidence: float
    selected_endpoints: List[str]
    connection_status: str

    recommendation_timing: str  # 'early', 'late', or 'none' in the clean runtime.
    recommendation: dict  # Recommendation payload returned by the recommender, or None.
    has_recommendation: bool  # True if recommendation is populated.
    recommendation_shown: bool
    follow_up_question_count: int

    # Fields for comprehensive logging.
    node_timings: Dict[str, float]  # {node_name: duration_ms}
    node_token_counts: Dict[str, Dict[str, int]]  # {node_name: token counts}
    service_call_failures: List[Dict[str, Any]]  # External service/tool failures.

    response: str  # Response text for non-troubleshooting turns.
