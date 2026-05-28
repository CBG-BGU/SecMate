"""Agent-service bridge used to connect the main agent to ClueCollector.

The service has two responsibilities:
1. Keep WebSocket connections from ClueCollector clients.
2. Expose HTTP endpoints the main agent can call to associate a user with a
   ClueCollector id, check connectivity, and forward system-info actions.

The original experiment deployment stored user-to-CC mappings in an external
service. This release version uses an in-memory mapping store by default and
keeps the external store as an optional adapter point.
"""

import asyncio
import json
import logging
import os
import uuid

from aiohttp import ClientSession, WSMsgType, web
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)


class CCIDService:
    """Stores the user id to ClueCollector client id mapping."""

    def __init__(self):
        self.user_to_ccid = {}
        self.ccid_to_user = {}
        self.external_base_url = self._build_external_url()

    def _build_external_url(self):
        services_host = os.getenv("SERVICES_HOST")
        service_name = os.getenv("DYNAMODB_SERVICE")
        service_port = os.getenv("DYNAMODB_PORT")
        if services_host and service_name and service_port:
            return f"{services_host}{service_name}:{service_port}"
        return None

    async def put_ccid_mapping(self, user_id: str, cc_id: str):
        """Create or update a mapping in the configured mapping store."""
        self.user_to_ccid[user_id] = cc_id
        self.ccid_to_user[cc_id] = user_id

        if self.external_base_url:
            await self._put_external_mapping(user_id, cc_id)

        return {"user_id": user_id, "cc_id": cc_id}

    async def get_ccid_by_userid(self, user_id: str):
        """Return the CC id for a user, if one has been associated."""
        if user_id in self.user_to_ccid:
            return self.user_to_ccid[user_id]

        if self.external_base_url:
            cc_id = await self._get_external_ccid(user_id)
            if cc_id:
                self.user_to_ccid[user_id] = cc_id
                self.ccid_to_user[cc_id] = user_id
            return cc_id

        return None

    async def get_userid_by_ccid(self, cc_id: str):
        """Return the user id associated with a CC id, if known."""
        if cc_id in self.ccid_to_user:
            return self.ccid_to_user[cc_id]

        if self.external_base_url:
            user_id = await self._get_external_userid(cc_id)
            if user_id:
                self.user_to_ccid[user_id] = cc_id
                self.ccid_to_user[cc_id] = user_id
            return user_id

        return None

    async def _put_external_mapping(self, user_id: str, cc_id: str):
        url = f"{self.external_base_url}/ccid-mapping"
        async with ClientSession() as session:
            async with session.put(url, json={"user_id": user_id, "cc_id": cc_id}) as response:
                if response.status != 200:
                    raise web.HTTPInternalServerError(reason="Error adding CCID mapping")

    async def _get_external_ccid(self, user_id: str):
        url = f"{self.external_base_url}/ccid/{user_id}"
        async with ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("cc_id")
                if response.status == 404:
                    return None
                raise web.HTTPInternalServerError(reason="Error retrieving CCID")

    async def _get_external_userid(self, cc_id: str):
        url = f"{self.external_base_url}/userid/{cc_id}"
        async with ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("user_id")
                if response.status == 404:
                    return None
                raise web.HTTPInternalServerError(reason="Error retrieving user ID")


class ConnectionManager:
    """Tracks active ClueCollector WebSocket connections and pending replies."""

    def __init__(self):
        self.active_connections = {}
        self.responses = {}

    async def connect(self, client_id: str, websocket: web.WebSocketResponse):
        self.active_connections[client_id] = websocket
        logging.info("ClueCollector client connected: %s", client_id)

    def disconnect(self, client_id: str):
        self.active_connections.pop(client_id, None)
        logging.info("ClueCollector client disconnected: %s", client_id)

    async def send_personal_message(self, message: str, client_id: str):
        if client_id not in self.active_connections:
            raise web.HTTPNotFound(reason="No active WebSocket connection for the specified CC id")
        await self.active_connections[client_id].send_str(message)

    async def get_response(self, client_id: str, timeout: float = 30.0):
        future = asyncio.Future()
        self.responses[client_id] = future
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            self.responses.pop(client_id, None)


ccid_service = CCIDService()
manager = ConnectionManager()


async def handle_root(request):
    """Health endpoint for local checks and container probes."""
    return web.json_response({"service": "cluecollector-agent-service", "status": "ok"})


async def websocket_handler(request):
    """Accept the outbound WebSocket connection opened by ClueCollector."""
    websocket = web.WebSocketResponse()
    await websocket.prepare(request)

    client_id = request.match_info["client_id"]
    await manager.connect(client_id, websocket)

    try:
        async for msg in websocket:
            if msg.type == WSMsgType.TEXT:
                if client_id in manager.responses:
                    manager.responses[client_id].set_result(msg.data)
                else:
                    logging.info("Received unsolicited message from %s", client_id)
            elif msg.type == WSMsgType.ERROR:
                logging.error("WebSocket connection error: %s", websocket.exception())
    finally:
        manager.disconnect(client_id)

    return websocket


async def forward_request(request):
    """Forward one agent-requested CC action to the associated CC client."""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.HTTPBadRequest(reason="Invalid JSON")

    uid = data.get("uid")
    action = data.get("action")
    if not uid or not action:
        return web.HTTPBadRequest(reason="Missing uid or action")

    cc_id = await ccid_service.get_ccid_by_userid(uid)
    if not cc_id:
        return web.HTTPNotFound(reason="No ClueCollector id is associated with this user")

    if cc_id not in manager.active_connections:
        return web.HTTPNotFound(reason="No active WebSocket connection for the specified user")

    try:
        await manager.send_personal_message(json.dumps({"action": action}), cc_id)
        response = await manager.get_response(cc_id)
        if response.startswith("PENDING:"):
            return web.json_response({"status": "pending", "action": response.split(":", 1)[1]})

        response_data = json.loads(response)
        if action == "running_processes":
            return web.json_response(format_running_processes(response_data))

        return web.json_response(response_data)
    except asyncio.TimeoutError:
        return web.HTTPGatewayTimeout(reason="Timeout waiting for ClueCollector response")
    except json.JSONDecodeError:
        return web.HTTPInternalServerError(reason="Invalid JSON response from ClueCollector")
    except web.HTTPException:
        raise
    except Exception:
        logging.exception("Error forwarding request to ClueCollector client %s", cc_id)
        return web.HTTPInternalServerError(reason="Error forwarding request to ClueCollector")


def format_running_processes(response_data):
    """Keep the process endpoint compact for agent consumption."""
    processes = response_data.get("running_processes", {}).get("processes", [])
    top_processes = sorted(processes, key=lambda item: item.get("memory_percent", 0), reverse=True)[:20]
    return {
        "action": "running_processes",
        "top_processes": [
            {
                "name": process.get("name", "Unknown"),
                "pid": process.get("pid", "N/A"),
                "memory_percent": round(process.get("memory_percent", 0), 4),
            }
            for process in top_processes
        ],
    }


async def connectivity_check(request):
    """Report whether a user's associated CC client is connected."""
    uid = request.query.get("uid")
    if not uid:
        return web.HTTPBadRequest(reason="Missing uid parameter")

    cc_id = await ccid_service.get_ccid_by_userid(uid)
    return web.json_response({"connected": bool(cc_id and cc_id in manager.active_connections)})


async def associate_uid(request):
    """Create or return the CC id assigned to a backend user id."""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.HTTPBadRequest(reason="Invalid JSON")

    user_id = data.get("user_id")
    if not user_id:
        return web.HTTPBadRequest(reason="Missing user_id")

    existing_cc_id = await ccid_service.get_ccid_by_userid(user_id)
    if existing_cc_id:
        return web.json_response({"cc_id": existing_cc_id, "message": "Existing mapping found"})

    cc_id = str(uuid.uuid4())
    await ccid_service.put_ccid_mapping(user_id, cc_id)
    return web.json_response({"cc_id": cc_id, "message": "New mapping created"})


async def put_ccid_mapping(request):
    """Manually store a known user-to-CC mapping."""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.HTTPBadRequest(reason="Invalid JSON")

    user_id = data.get("user_id")
    cc_id = data.get("cc_id")
    if not user_id or not cc_id:
        return web.HTTPBadRequest(reason="Missing user_id or cc_id")

    result = await ccid_service.put_ccid_mapping(user_id, cc_id)
    return web.json_response(result)


async def get_ccid(request):
    """Return the CC id currently associated with a user id."""
    user_id = request.match_info["user_id"]
    cc_id = await ccid_service.get_ccid_by_userid(user_id)
    if cc_id is None:
        return web.HTTPNotFound(reason="CCID not found for this user ID")
    return web.json_response({"cc_id": cc_id})


async def get_userid(request):
    """Return the user id currently associated with a CC id."""
    cc_id = request.match_info["cc_id"]
    user_id = await ccid_service.get_userid_by_ccid(cc_id)
    if user_id is None:
        return web.HTTPNotFound(reason="User ID not found for this CCID")
    return web.json_response({"user_id": user_id})


async def main():
    """Configure and run the aiohttp bridge server."""
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/ws/{client_id}", websocket_handler)
    app.router.add_post("/forward_request", forward_request)
    app.router.add_post("/associate_uid", associate_uid)
    app.router.add_put("/ccid-mapping", put_ccid_mapping)
    app.router.add_get("/ccid/{user_id}", get_ccid)
    app.router.add_get("/userid/{cc_id}", get_userid)
    app.router.add_get("/connectivity_check", connectivity_check)

    runner = web.AppRunner(app)
    await runner.setup()

    host = os.getenv("AGENT_SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("AGENT_SERVICE_PORT", "8765"))
    site = web.TCPSite(runner, host, port)
    await site.start()

    logging.info("ClueCollector agent service started at http://%s:%s", host, port)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
