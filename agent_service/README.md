# ClueCollector Agent Service

## Overview

`agent_service` is the bridge between the SecMate Orchestrator and a connected
ClueCollector process. It exposes HTTP endpoints to the Orchestrator and a
WebSocket endpoint to ClueCollector.

## Flow

1. `Server/server.py` asks this service to associate an Orchestrator user id
   with a ClueCollector client id.
2. `ClueCollector/src/runner.py` starts on the target machine using that client
   id and opens a WebSocket connection to this service.
3. The Orchestrator calls `/forward_request` with a user id and an action such
   as `cpu_info`.
4. The bridge forwards the action to the connected ClueCollector client and
   returns the collected result to the Orchestrator.

The clean release uses an in-memory user-to-CID mapping by default. If
`SERVICES_HOST`, `DYNAMODB_SERVICE`, and `DYNAMODB_PORT` are set,
`src/sia_server.py` shows where an external mapping service can be attached.

## Endpoints

- `GET /ws/{client_id}`: WebSocket endpoint opened by ClueCollector.
- `POST /associate_uid`: creates or returns a user-to-ClueCollector mapping.
- `POST /forward_request`: sends a ClueCollector action to the connected client.
- `GET /connectivity_check?uid=<user_id>`: reports whether that user's
  ClueCollector client is connected.
- `PUT /ccid-mapping`: stores a known user-to-CID mapping.
- `GET /ccid/{user_id}` and `GET /userid/{cc_id}`: mapping lookup helpers.

## Run Locally

From the `agent_service` directory:

```bash
pip install -r requirements.txt
python src/sia_server.py
```

The service listens on `0.0.0.0:8765` by default. Override this with
`AGENT_SERVICE_HOST` and `AGENT_SERVICE_PORT`.

## Docker

The Dockerfile shows the deployment shape used in the experiments. Inject
environment variables through your own runtime or `.env` file:

```bash
docker build -t cluecollector-agent-service .
docker run -p 8765:8765 --env-file .env cluecollector-agent-service
```
