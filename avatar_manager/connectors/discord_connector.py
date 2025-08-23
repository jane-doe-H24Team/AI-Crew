import os
import logging
import discord
from avatar_manager.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)

class DiscordConnector(BaseConnector):
    def __init__(self, avatar_id: str):
        super().__init__(avatar_id)
        self.token = None
        self.client = None

    def get_credentials(self):
        self.token = self._get_env_var("DISCORD_TOKEN", required=False)
        if not self.token:
            self.logger.debug("No Discord token found for avatar %s", self.avatar_id)
            return False
        
        # Intents are crucial for Discord bots
        intents = discord.Intents.default()
        intents.message_content = True # Required to read message content
        intents.members = True # Required for some member-related events
        intents.guilds = True # Required for guild-related events

        self.client = discord.Client(intents=intents)

        @self.client.event
        async def on_ready():
            self.logger.info(f"Discord bot {self.client.user} has connected to Discord!")

        # We don't handle on_message here directly, as we'll poll for updates
        # This is a simplified setup for polling, not ideal for production Discord bots
        return True

    async def send_message(self, channel_id: int, text: str):
        if not self.client or not self.client.is_ready():
            self.logger.error("Discord client not ready for avatar %s", self.avatar_id)
            return False

        try:
            channel = self.client.get_channel(channel_id)
            if not channel:
                self.logger.error(f"Channel {channel_id} not found for avatar {self.avatar_id}")
                return False
            await channel.send(text)
            self.logger.info("[%s] Discord message sent to channel %s", self.avatar_id, channel_id)
            return True
        except Exception as e:
            self.logger.error("[%s] Error sending Discord message: %s", self.avatar_id, e)
            return False

    async def fetch_updates(self):
        if not self.client:
            return []

        updates = []
        # This is a very basic polling mechanism for Discord.
        # In a real application, you'd typically use webhooks or run the bot's event loop.
        # For simplicity with FastAPI's scheduler, we'll try to fetch recent messages.
        # Note: discord.py client.fetch_channel and channel.history are blocking for large histories.
        # This approach is highly inefficient and not recommended for production.
        # A proper Discord bot would run its own event loop and process events as they come.

        # To get messages, we need to iterate through guilds and channels
        # This part is complex for polling and usually handled by the bot's event loop.
        # For a scheduled check, we would need to store the last checked message ID per channel
        # and fetch messages since then.
        
        # For demonstration, we'll just return an empty list for now.
        # A proper implementation would involve running the discord.Client in a separate async task
        # and collecting messages from its on_message event.
        self.logger.warning("[%s] Discord polling is highly inefficient and not fully implemented for scheduled checks. Consider running discord.Client in a separate task.", self.avatar_id)
        return updates

# Note: For a full-fledged Discord bot, you'd typically run client.run(TOKEN) in a separate process/thread.
# Integrating discord.py's event loop with FastAPI's scheduler for polling is complex and inefficient.
# The recommended way is to use webhooks or run the bot as a separate service.
