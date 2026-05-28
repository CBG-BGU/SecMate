# ClueCollector

## Overview

ClueCollector collects host-level system information requested by the SecMate
Orchestrator. In the paper pipeline, it runs on the user's machine, opens a
WebSocket connection to `agent_service`, and waits for action requests from the
Orchestrator.

This module is included because it is part of the published pipeline, not a
placeholder.

## Files

- `src/DataCollector.py`: collects and caches system information.
- `src/DataAnalyzer.py`: formats selected low-level results for agent use.
- `src/DataStructures.py`: shared data structures used by the collector and
  analyzer.
- `src/WebSocketClient.py`: connects ClueCollector to the agent-service
  WebSocket bridge.
- `src/runner.py`: terminal/container entry point that activates
  ClueCollector.
- `src/machineConfig.example.json`: local example of bridge endpoints.
- `requirements.txt`: Python dependencies for this module.

## How It Connects

```text
Server/server.py
  -> Server/service_clients.py:ClueCollectorClient
    -> agent_service/src/sia_server.py
      -> WebSocket
        -> ClueCollector/src/runner.py
```

The UI displays a customer ID (CID) to the user. The same CID is used when running
ClueCollector so the bridge can associate the local collector with the active
user/session.

## Local Example

Start `agent_service` first, then run ClueCollector with a local config:

```powershell
pip install -r requirements.txt
cd src
$env:USE_LOCAL_CONFIG = "true"
$env:LOCAL_CONFIG_PATH = "machineConfig.example.json"
$env:LOCAL_CC_CLIENT_ID = "test_cc"
python runner.py
```

For a deployed experiment, provide `CC_CLIENT_ID` and either a local server
config or the optional S3 config variables used by `ServerConfigManager`.

## Exposed Actions

The available action names are defined in `DataCollector.py`. The Orchestrator
selects the relevant actions and forwards them through `agent_service`.
