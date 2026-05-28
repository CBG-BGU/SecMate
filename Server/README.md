# Server / Orchestrator

## Overview

`Server/` contains the SecMate Confidence-Guided Orchestrator described in the
paper, plus the API wrapper used by the release. The wrapper is intentionally
smaller than the original experiment backend: it keeps session creation,
message routing, conversation reset, ClueCollector connection points, and
replaceable profiler/logger/recommender boundaries.

The Orchestrator coordinates the per-turn troubleshooting workflow. It checks
whether the user turn is troubleshooting-related, estimates diagnosis
confidence, decides whether to ask a follow-up question, request ClueCollector
evidence, or produce a solution, and adapts generated text to the user's
profile.

## Files

- `server.py`: FastAPI wrapper used by the UI and local runs.
- `orchestrator_manager.py`: per-user registry of chat orchestrators.
- `chat_orchestrator.py`: owns one user's conversation state and delegates each
  turn to `MessageHandler`.
- `message_handler.py`: main LangGraph workflow for the paper's Orchestrator.
- `agent_state.py`: typed state shared across graph nodes.
- `prompts.py`: prompt definitions used directly by the message handler.
- `service_clients.py`: ClueCollector bridge services, and replaceable adapters 
  for profiler, logger, and recommender.
- `requirements.txt`: Python dependencies for this module.

## Paper Component Mapping

The paper architecture names several logical agents inside the SecMate
workflow. In the release code, they map to the following files:

- Conversation guardrails: `MessageHandler.intent_router`.
- Diagnosis confidence calculator (`Dconf`): `MessageHandler.calculate_diagnosis_confidence`.
- Follow-up question generator: `MessageHandler.gen_question`.
- Profile-aware troubleshooter: the `MessageHandler.gen_solution_*` methods.
- Clue Collector retrieval decision: `MessageHandler.route_query`,
  `MessageHandler.select_system_info`, and `MessageHandler.execute_tools`.
- Profiler and Recommender calls: replaceable clients in `service_clients.py`.

## External Services

The clean release treats these components as replaceable services:

- `UserProfileClient`: initializes/updates user profiles for personalization.
- `LoggerClient`: saves conversations and turn-level logs.
- `RecommendationClient`: calls a recommender service.
- `ClueCollectorClient`: talks to `agent_service`, which then communicates with
  the local ClueCollector process.

If a URL is not configured, the profiler/logger/recommender clients return
`not_configured` placeholder responses so the wrapper can still run. The
ClueCollector client returns a clear `not_configured` message telling the user
to set `AGENT_URL`.

## Run

From this directory:

```bash
pip install -r requirements.txt
python -m uvicorn server:app --reload --port 5000
```

The UI expects the following routes:

- `POST /initiate_session`
- `POST /send_message_to_genai`
- `POST /clear_history_gen`
- `GET /get_associated_cid`
- `GET /check_agent_connectivity`
- `GET /health`

The wrapper also exposes:

- `POST /api/system_info`
- `POST /api/agent_connect`
- `POST /associate_uid`
- `POST /recommendation`

## Configuration

The module reads `.env` through `python-dotenv`. Key values:

- `AGENT_URL`: URL of the ClueCollector bridge, for example
  `http://localhost:8765`.
- `PROFILER_URL`, `LOGGER_URL`, `RECOMMENDER_URL`: optional external service
  URLs.
- Azure OpenAI variables: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`,
  `OPENAI_API_VERSION`, `DEPLOYMENT_NAME`, `MODEL_NAME`.
- Runtime flags: `CC_ENABLED`, `ADAPTATION_ENABLED`, `PROFILE_MODE`,
  `RECOMMENDATION_TIMING`.

The original S3/Cognito/session-manager backend was removed. Researchers can
replace the adapter classes in `service_clients.py` with their own storage or
service implementations.
