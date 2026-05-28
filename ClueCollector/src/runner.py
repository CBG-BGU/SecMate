"""Terminal entry point for activating ClueCollector in the experiment flow.

This script starts the local collector and connects it to the agent-service
WebSocket bridge. In a deployed experiment this process can run directly on the
participant machine or inside a container with the same environment variables.
"""

import asyncio
import logging
import os
import signal
import sys

from dotenv import load_dotenv

from WebSocketClient import MultiServerWebSocketClient

load_dotenv()


class WebSocketRunner:
    """Coordinates configuration validation and the CC WebSocket client."""

    def __init__(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )

        self.client = None
        self.loop = asyncio.get_event_loop()
        self.is_shutting_down = False

    def get_client_id(self) -> str:
        """Read the CC id assigned by the agent service or experiment UI."""
        configured_client_id = os.getenv("CC_CLIENT_ID")
        if configured_client_id:
            return configured_client_id.strip()

        if os.getenv("USE_LOCAL_CONFIG", "false").lower() == "true":
            return os.getenv("LOCAL_CC_CLIENT_ID", "test_cc")

        try:
            client_id = input("Enter ClueCollector client ID: ").strip()
        except KeyboardInterrupt:
            logging.info("Exiting before connection")
            sys.exit(0)

        if not client_id:
            raise RuntimeError("A ClueCollector client ID is required")

        return client_id

    def validate_environment(self) -> bool:
        """Validate the configuration source used to find agent-service hosts."""
        use_local_config = os.getenv("USE_LOCAL_CONFIG", "false").lower() == "true"

        if use_local_config:
            local_config_path = os.getenv("LOCAL_CONFIG_PATH", "machineConfig.json")
            if not os.path.exists(local_config_path):
                logging.error("Local config file not found: %s", local_config_path)
                return False
            return True

        required_vars = [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_REGION",
            "S3_BUCKET_NAME",
            "S3_CONFIG_KEY",
        ]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            logging.error("Missing required environment variables: %s", ", ".join(missing_vars))
            return False

        return True

    async def shutdown(self, received_signal=None):
        """Gracefully stop the WebSocket client and any outstanding tasks."""
        if self.is_shutting_down:
            return

        self.is_shutting_down = True
        if received_signal:
            logging.info("Received exit signal %s", received_signal)

        if self.client:
            await self.client.stop()

        tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.loop.stop()

    def handle_exception(self, loop, context):
        """Route unexpected async exceptions through the normal shutdown path."""
        message = context.get("exception", context["message"])
        logging.error("Unhandled runner exception: %s", message)
        asyncio.create_task(self.shutdown())

    async def startup(self):
        """Initialize the CC client and keep it connected to agent service."""
        try:
            client_id = self.get_client_id()
            logging.info("Starting ClueCollector connector for client ID %s", client_id)

            self.client = MultiServerWebSocketClient(client_id)
            if not await self.client.initialize():
                await self.shutdown()
                return

            logging.info("Connecting to %s CC-enabled server(s)", len(self.client.servers_config))
            await self.client.start()
        except Exception:
            logging.exception("Failed to start ClueCollector connector")
            await self.shutdown()

    def run(self):
        """Run ClueCollector until interrupted."""
        if not self.validate_environment():
            return

        try:
            if sys.platform != "win32":
                for sig in (signal.SIGTERM, signal.SIGINT):
                    self.loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown(s)))
            else:
                signal.signal(signal.SIGINT, lambda s, f: asyncio.create_task(self.shutdown(s)))
                signal.signal(signal.SIGTERM, lambda s, f: asyncio.create_task(self.shutdown(s)))

            self.loop.set_exception_handler(self.handle_exception)
            self.loop.run_until_complete(self.startup())
            self.loop.run_forever()
        except KeyboardInterrupt:
            self.loop.run_until_complete(self.shutdown())
        finally:
            self.loop.close()
            logging.info("ClueCollector runner stopped")


def main():
    """Script entry point."""
    WebSocketRunner().run()


if __name__ == "__main__":
    main()
