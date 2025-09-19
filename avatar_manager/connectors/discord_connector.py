import os
import logging
import discord
import asyncio
from avatar_manager.connectors.base_connector import BaseConnector
from avatar_manager import db

logger = logging.getLogger(__name__)

class DiscordConnector(BaseConnector):
    def __init__(self, avatar_id: str):
        super().__init__(avatar_id)
        self.token = None
        self.client = None
        self.processed_messages = set()

    async def get_credentials(self):
        self.token = self._get_env_var("DISCORD_TOKEN", required=False)
        if not self.token:
            self.logger.debug("No Discord token found for avatar %s", self.avatar_id)
            return False
        
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True

        self.client = discord.Client(intents=intents)

        @self.client.event
        async def on_ready():
            self.logger.info(f"Discord bot {self.client.user} has connected to Discord!")

        # Start the client in a background task
        asyncio.create_task(self.client.start(self.token))
        # It's not ideal to wait here, but we need the client to be ready for the first run.
        await asyncio.sleep(5) # Give client time to connect
        return True

    async def send_message(self, channel_id: int, text: str):
        if not self.client or not self.client.is_ready():
            self.logger.error("Discord client not ready for avatar %s", self.avatar_id)
            return False

        try:
            channel = self.client.get_channel(int(channel_id))
            if not channel:
                self.logger.error(f"Channel {channel_id} not found for avatar {self.avatar_id}")
                return False
            await channel.send(text)
            db.add_message_to_chat_history(
                avatar_id=self.avatar_id,
                platform="discord",
                chat_id=str(channel_id),
                sender=self.client.user.name,
                message=text
            )
            self.logger.info("[%s] Discord message sent to channel %s", self.avatar_id, channel_id)
            return True
        except Exception as e:
            self.logger.error("[%s] Error sending Discord message: %s", self.avatar_id, e)
            return False

    async def fetch_updates(self):
        if not self.client or not self.client.is_ready():
            self.logger.warning("[%s] Discord client not ready, skipping fetch.", self.avatar_id)
            return []

        updates = []
        self.logger.debug("[%s] Discord polling is highly inefficient. This implementation fetches the last message from each channel and may miss messages.", self.avatar_id)
        
        for guild in self.client.guilds:
            for channel in guild.text_channels:
                try:
                    # Fetch the last message
                    async for message in channel.history(limit=1):
                        # Avoid processing own messages and already processed messages
                        if message.author == self.client.user or message.id in self.processed_messages:
                            continue

                        self.processed_messages.add(message.id)
                        db.add_message_to_chat_history(
                            avatar_id=self.avatar_id,
                            platform="discord",
                            chat_id=str(channel.id),
                            sender=message.author.name,
                            message=message.content
                        )
                        updates.append({
                            "channel_id": channel.id,
                            "username": message.author.name,
                            "text": message.content
                        })
                except discord.errors.Forbidden:
                    self.logger.debug("[%s] No permission to read history in channel %s", self.avatar_id, channel.name)
                except Exception as e:
                    self.logger.error("[%s] Error fetching from channel %s: %s", self.avatar_id, channel.name, e)
        
        return updates

# Note: For a full-fledged Discord bot, you'd typically run client.run(TOKEN) in a separate process/thread.
# Integrating discord.py's event loop with FastAPI's scheduler for polling is complex and inefficient.
# The recommended way is to use webhooks or run the bot as a separate service.
