# Experiment Web UI

## Overview

`web_ui/` contains the cleaned React UI used to run the experiment workflow.
Deployment-specific Amplify backend files and real machine configuration were
removed. The UI keeps the participant flow, chat interface, experiment
condition switching, ClueCollector CID display, feedback controls, and
recommendation display.

## Files

- `src/App.js`: main UI composition and experiment controls.
- `src/hooks/useExperiment.js`: condition selection and machine endpoint
  switching.
- `src/hooks/useSession.js`: frontend session initialization.
- `src/hooks/useChat.js`: chat request/response handling.
- `src/hooks/useAuth.js`: authentication boundary, with local preview support.
- `src/config/machineConfig.example.json`: placeholder agent-service endpoints.
- `src/aws-exports.js`: placeholder Cognito/Amplify config.

## Local Preview

Install Node.js first. Then run:

```bash
npm install
npm start
```

For a local UI preview, copy `.env.example` to `.env` and keep:

```env
REACT_APP_UI_TEST_MODE=true
REACT_APP_ENABLE_AUTH=false
```

This lets researchers inspect the UI without Cognito or live backend services.

## Connecting To Services

To connect to the Python backend:

1. Set `REACT_APP_UI_TEST_MODE=false`.
2. Replace the placeholder `api_base_url` values in
   `src/config/machineConfig.example.json`.
3. Configure authentication in `src/aws-exports.js`, or replace the auth hook
   with another provider.

Each configured Orchestrator endpoint is expected to expose:

- `POST /initiate_session`
- `POST /send_message_to_genai`
- `POST /clear_history_gen`
- `GET /get_associated_cid`
- `POST /submit_feedback`
- `GET /get_recommendation`
- `GET /check_agent_connectivity`
- `GET /health`

## ClueCollector CID

The UI displays the associated CID in the user menu. The user can copy that CID
and use it when running ClueCollector locally so the bridge can associate the
local collector with the active session.
