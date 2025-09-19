from slack_sdk.web.async_client import AsyncWebClient
from .base_connector import BaseConnector
from avatar_manager import db

class SlackConnector(BaseConnector):
    """Connector for Slack."""

    def get_credentials(self):
        """Retrieves credentials for Slack from environment variables."""
        self.token = self._get_env_var("SLACK_BOT_TOKEN")
        self.client = AsyncWebClient(token=self.token)
        self.bot_id = None # Will be fetched later

    async def _get_bot_id(self):
        if self.bot_id is None:
            try:
                response = await self.client.auth_test()
                self.bot_id = response["bot_id"]
            except Exception as e:
                self.logger.error(f"Could not get bot ID: {e}")
        return self.bot_id

    async def fetch_updates(self):
        """Fetches new messages from Slack."""
        # TODO: Implement a more robust way to track processed messages
        # using timestamps (ts) to avoid reprocessing.
        updates = []
        bot_id = await self._get_bot_id()
        if not bot_id:
            return []

        try:
            conv_response = await self.client.conversations_list(types="public_channel,private_channel")
            channels = conv_response["channels"]

            for channel in channels:
                history_response = await self.client.conversations_history(channel=channel["id"], limit=10)
                messages = history_response["messages"]
                for message in messages:
                    if message.get("user") != bot_id and not message.get("bot_id"):
                        updates.append({
                            "channel": channel["id"],
                            "user": message.get("user"),
                            "text": message.get("text"),
                            "ts": message.get("ts"),
                        })
                        db.add_message_to_chat_history(
                            avatar_id=self.avatar_id,
                            platform="slack",
                            chat_id=channel["id"],
                            sender=message.get("user"),
                            message=message.get("text")
                        )
        except Exception as e:
            self.logger.error(f"Error fetching Slack updates: {e}")

        return updates

    async def send_message(self, channel_id: str, subject: str, body: str):
        """Sends a message to a Slack channel."""
        try:
            await self.client.chat_postMessage(channel=channel_id, text=body)
            db.add_message_to_chat_history(
                avatar_id=self.avatar_id,
                platform="slack",
                chat_id=channel_id,
                sender=self.avatar_id,
                message=body
            )
            self.logger.info(f"Sent Slack message to channel: {channel_id}")
        except Exception as e:
            self.logger.error(f"Failed to send Slack message to {channel_id}: {e}")