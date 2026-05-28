"""WebSocket connector between ClueCollector and the agent-side bridge.

In the experiment pipeline, ClueCollector runs on the user's machine and opens
an outbound WebSocket connection to one or more agent-service instances. The
agent service sends small action names such as ``cpu_info`` or ``open_ports``;
this client translates them into ``DataCollector`` actions and sends the latest
collected result back over the same socket.
"""

import asyncio
import json
import logging
import os
from typing import Dict, List

import boto3
from dotenv import load_dotenv
import websockets

from DataCollector import Actions, DataCollector

load_dotenv()


class ServerConfigManager:
    """Loads the list of agent-service WebSocket servers for ClueCollector."""

    def __init__(self):
        self.use_local_file = os.getenv("USE_LOCAL_CONFIG", "false").lower() == "true"
        self.local_config_path = os.getenv("LOCAL_CONFIG_PATH", "machineConfig.json")

        if not self.use_local_file:
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name=os.getenv("AWS_REGION"),
            )
            self.bucket_name = os.getenv("S3_BUCKET_NAME")
            self.config_file_key = os.getenv("S3_CONFIG_KEY")

    async def fetch_server_config(self) -> List[Dict]:
        """Fetch CC-enabled server definitions from local JSON or S3."""
        if self.use_local_file:
            logging.info("Loading CC server configuration from %s", self.local_config_path)
            return await self._load_from_local_file()

        logging.info("Loading CC server configuration from S3")
        return await self._load_from_s3()

    async def _load_from_local_file(self) -> List[Dict]:
        try:
            with open(self.local_config_path, "r", encoding="utf-8") as file:
                config_data = json.load(file)
        except FileNotFoundError as exc:
            raise RuntimeError(f"Local config file not found: {self.local_config_path}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in local config file: {exc}") from exc

        return self._extract_cc_servers(config_data)

    async def _load_from_s3(self) -> List[Dict]:
        response = self.s3_client.get_object(
            Bucket=self.bucket_name,
            Key=self.config_file_key,
        )
        config_data = json.loads(response["Body"].read())
        return self._extract_cc_servers(config_data)

    def _extract_cc_servers(self, config_data: dict) -> List[Dict]:
        """Return only experiment configurations that used ClueCollector."""
        cc_servers = []
        for config_key in ["a", "b"]:
            config_info = config_data.get("configs", {}).get(config_key)
            if not config_info:
                continue

            for instance in config_info.get("instances", []):
                cc_servers.append(
                    {
                        "server_id": instance["id"],
                        "host": instance["public_ip"],
                        "port": int(instance.get("port", 8765)),
                        "config_type": config_info["name"],
                    }
                )

        logging.info("Found %s CC-enabled server(s)", len(cc_servers))
        return cc_servers


class MultiServerWebSocketClient:
    """Connects one ClueCollector process to all configured agent services."""

    ACTION_MAP = {action.value.replace("get_", ""): action for action in Actions}

    def __init__(self, client_id: str):
        self.client_id = client_id
        self.config_manager = ServerConfigManager()
        self.servers_config = []
        self.websockets = {}
        self.connection_states = {}
        self.data_collector = DataCollector()
        self.should_run = True
        self.connection_retry_delay = 5
        self.max_retries = 5

    async def initialize(self) -> bool:
        """Load server configuration before opening WebSocket connections."""
        try:
            self.servers_config = await self.config_manager.fetch_server_config()
            if not self.servers_config:
                raise RuntimeError("No CC-enabled servers found in configuration")

            for server in self.servers_config:
                self.connection_states[server["server_id"]] = False

            logging.info("Initialized ClueCollector connector for %s server(s)", len(self.servers_config))
            return True
        except Exception:
            logging.exception("Failed to initialize ClueCollector connector")
            return False

    async def start(self):
        """Start local collection and listen for agent-service requests."""
        self.should_run = True
        logging.info("Starting initial ClueCollector data collection")
        self.data_collector.start_initial_data_collection()

        if not await self.connect_to_all_servers():
            raise RuntimeError("Failed to connect to any configured agent-service server")

        await self.handle_all_server_requests()

    async def connect_to_all_servers(self) -> bool:
        """Open WebSocket connections to every configured agent service."""
        logging.info("Connecting to CC-enabled agent-service servers")
        connection_tasks = [
            asyncio.create_task(
                self.connect_to_server(server["server_id"], server["host"], server["port"])
            )
            for server in self.servers_config
        ]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*connection_tasks, return_exceptions=True),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logging.error("Timed out while connecting to configured agent-service servers")
            return False

        successful_connections = 0
        for server, result in zip(self.servers_config, results):
            server_id = server["server_id"]
            if isinstance(result, Exception):
                logging.error("Failed to connect to %s: %s", server_id, result)
                continue

            successful_connections += 1
            logging.info("Connected to %s", server_id)

        logging.info("Connected to %s/%s server(s)", successful_connections, len(self.servers_config))
        return successful_connections > 0

    async def connect_to_server(self, server_id: str, host: str, port: int):
        """Connect to one agent-service WebSocket endpoint with retries."""
        uri = f"ws://{host}:{port}/ws/{self.client_id}"
        retries = 0

        while retries < self.max_retries and self.should_run:
            try:
                logging.info("Connecting to %s at %s:%s", server_id, host, port)
                websocket = await websockets.connect(uri)
                self.websockets[server_id] = websocket
                self.connection_states[server_id] = True
                return
            except websockets.InvalidStatusCode as exc:
                if exc.status_code in [401, 403, 404]:
                    raise RuntimeError(f"Invalid client ID for server {server_id}") from exc
                retries += 1
                logging.warning(
                    "Connection attempt %s to %s failed with status %s",
                    retries,
                    server_id,
                    exc.status_code,
                )
            except Exception as exc:
                retries += 1
                logging.warning("Connection attempt %s to %s failed: %s", retries, server_id, exc)

            if retries < self.max_retries and self.should_run:
                await asyncio.sleep(self.connection_retry_delay)

        if self.should_run:
            raise RuntimeError(f"Failed to connect to {server_id} after {self.max_retries} attempts")

    async def reconnect_to_server(self, server_id: str):
        """Reconnect one server after a dropped WebSocket connection."""
        server_config = next((s for s in self.servers_config if s["server_id"] == server_id), None)
        if not server_config:
            logging.error("Server config not found for %s", server_id)
            return

        self.connection_states[server_id] = False
        try:
            await self.connect_to_server(server_id, server_config["host"], server_config["port"])
        except Exception:
            logging.exception("Failed to reconnect to %s", server_id)

    async def handle_all_server_requests(self):
        """Run one request handler per active server connection."""
        handler_tasks = [
            asyncio.create_task(self.handle_server_requests(server["server_id"]))
            for server in self.servers_config
            if self.connection_states.get(server["server_id"], False)
        ]

        if not handler_tasks:
            raise RuntimeError("No active WebSocket connections to handle requests")

        logging.info("Starting request handlers for %s server(s)", len(handler_tasks))
        await asyncio.gather(*handler_tasks, return_exceptions=True)

    async def handle_server_requests(self, server_id: str):
        """Receive agent actions from one server and return CC results."""
        logging.info("Starting request handler for %s", server_id)

        while self.should_run:
            try:
                websocket = self.websockets.get(server_id)
                if not websocket or websocket.close_code is not None:
                    logging.warning("Connection to %s is closed; reconnecting", server_id)
                    await self.reconnect_to_server(server_id)
                    await asyncio.sleep(5)
                    continue

                message = await websocket.recv()
                message_dict = json.loads(message)
                action_value = message_dict.get("action", "").strip().lower()
                if not action_value:
                    logging.warning("Received WebSocket message without an action from %s", server_id)
                    continue

                action_enum = self.ACTION_MAP.get(action_value)
                if not action_enum:
                    logging.warning("Unknown action from %s: %s", server_id, action_value)
                    continue

                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.data_collector.get_result,
                    action_enum,
                )

                if result:
                    await websocket.send(json.dumps(result))
                    logging.info("Sent %s response to %s", action_value, server_id)
                else:
                    self.data_collector.queue_action(action_enum)
                    await websocket.send(f"PENDING:{action_value}")
                    logging.info("Queued %s for %s", action_value, server_id)
            except json.JSONDecodeError:
                logging.warning("Received invalid JSON from %s", server_id)
            except websockets.ConnectionClosed:
                logging.warning("Connection to %s closed; reconnecting", server_id)
                await self.reconnect_to_server(server_id)
                await asyncio.sleep(5)
            except Exception:
                logging.exception("Error handling message from %s", server_id)
                await asyncio.sleep(1)

    async def disconnect(self):
        """Close all active WebSocket connections."""
        disconnect_tasks = []
        for server_id, websocket in self.websockets.items():
            if websocket and websocket.close_code is None:
                disconnect_tasks.append(asyncio.create_task(websocket.close()))
                self.connection_states[server_id] = False

        if disconnect_tasks:
            await asyncio.gather(*disconnect_tasks, return_exceptions=True)

        self.websockets.clear()
        logging.info("Disconnected from all agent-service servers")

    async def stop(self):
        """Stop WebSocket connections and the background data collector."""
        self.should_run = False
        await self.disconnect()
        self.data_collector.stop()
        logging.info("ClueCollector connector stopped")


WebSocketClient = MultiServerWebSocketClient
