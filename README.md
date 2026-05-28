# SecMate Clean Release

This repository contains the clean research release of SecMate: the
Confidence-Guided Orchestrator, the ClueCollector host-context module, the
bridge that connects ClueCollector to the Orchestrator, and the experiment web
UI.

The release keeps the implementation surfaces needed to understand and recreate
the paper system while removing private deployment details, experiment-specific
cloud infrastructure, and extensive internal logging wrappers.

## Repository Layout

- `Server/`: Confidence-Guided Orchestrator and API wrapper.
- `ClueCollector/`: host-context collection module.
- `agent_service/`: WebSocket/HTTP bridge between the Orchestrator and
  ClueCollector.
- `web_ui/`: cleaned React UI used for the experiment workflow.
- `.env.example`: combined configuration reference for the Python services and UI.

## Paper Component Mapping

The paper describes SecMate as a per-iteration workflow coordinated by the
Orchestrator. In this release:

- The **Confidence-Guided Orchestrator** lives in `Server/`.
- Conversation guardrails, diagnosis confidence calculation, follow-up question
  generation, ClueCollector selection, and profile-aware troubleshooting are
  implemented in `Server/message_handler.py`.
- Prompt definitions for those internal agents are in `Server/prompts.py`.
- The **Profiler**, **Recommender**, and experiment **Logger** are represented
  as replaceable clients in `Server/service_clients.py`.
- The **Clue Collector** is included in `ClueCollector/`, and the bridge used to
  connect it to the Orchestrator is in `agent_service/`.

## Runtime Pipeline

The end-to-end flow is:

```text
web_ui
  -> Server/server.py
    -> Server/orchestrator_manager.py
      -> Server/chat_orchestrator.py
        -> Server/message_handler.py
          -> Server/prompts.py
          -> Server/service_clients.py
              -> profiler/logger/recommender service clients
              -> agent_service bridge
                  -> ClueCollector runner
```

`Server/message_handler.py` contains the Orchestrator's decision graph. It
computes diagnosis confidence, decides whether to ask a follow-up question,
request device evidence, or produce a solution, and adapts generated content
using the configured user profile mode. The profiler, logger, and recommender
are represented through replaceable service clients. ClueCollector is included
as code, with `agent_service` showing how the Orchestrator connects to a locally
running collector.

## Configuration

Copy `.env.example` to `.env` and fill in the values relevant to the modules you
run.

Important values:

- Azure OpenAI: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`,
  `DEPLOYMENT_NAME`, `MODEL_NAME`.
- Agent bridge: `AGENT_URL`, usually `http://localhost:8765`.
- Optional external services: `PROFILER_URL`, `LOGGER_URL`, `RECOMMENDER_URL`.
- ClueCollector local mode: `USE_LOCAL_CONFIG=true`,
  `LOCAL_CONFIG_PATH=machineConfig.example.json`.
- UI preview mode: `REACT_APP_UI_TEST_MODE=true`,
  `REACT_APP_ENABLE_AUTH=false`.

## Run Order

For a local run with ClueCollector:

1. Start the bridge:

```bash
cd agent_service
pip install -r requirements.txt
python src/sia_server.py
```

2. Start ClueCollector:

```bash
cd ClueCollector
pip install -r requirements.txt
cd src
python runner.py
```

3. Start the agent API wrapper:

```bash
cd Server
pip install -r requirements.txt
python -m uvicorn server:app --reload --port 5000
```

4. Start the UI:

```bash
cd web_ui
npm install
npm start
```

See each module README for details and replacement points.
