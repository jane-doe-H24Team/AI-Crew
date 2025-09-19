import logging
from telegram import Bot
from avatar_manager.connectors.base_connector import BaseConnector
from avatar_manager import db

logger = logging.getLogger(__name__)

class TelegramConnector(BaseConnector):
    def __init__(self, avatar_id: str):
        super().__init__(avatar_id)
        self.token = None
        self.bot = None
        self.username = None

    async def get_credentials(self):
        self.token = self._get_env_var("TELEGRAM_TOKEN", required=False)
        if not self.token:
            self.logger.debug("No Telegram token found for avatar %s", self.avatar_id)
            return False
        self.bot = Bot(self.token)
        bot_info = await self.bot.get_me()
        self.username = bot_info.username
        return True

    async def send_message(self, chat_id: int, text: str):
        if not self.bot:
            self.logger.error("Telegram bot not initialized for avatar %s", self.avatar_id)
            return False

        try:
            await self.bot.send_message(chat_id=chat_id, text=text)
            db.add_message_to_chat_history(
                avatar_id=self.avatar_id,
                platform="telegram",
                chat_id=str(chat_id),
                sender=self.username, # The bot itself is the sender
                message=text
            )
            self.logger.info("[%s] Telegram message sent to chat_id %s", self.avatar_id, chat_id)
            return True
        except Exception as e:
            self.logger.error("[%s] Error sending Telegram message: %s", self.avatar_id, e)
            return False

    async def fetch_updates(self):
        if not self.bot:
            return []

        updates = []
        try:
            # Get updates. This is a simplified approach for polling.
            new_updates = await self.bot.get_updates(offset=None, limit=10, timeout=10)
            for update in new_updates:
                if update.message and update.message.text:
                    # Save incoming message to history
                    db.add_message_to_chat_history(
                        avatar_id=self.avatar_id,
                        platform="telegram",
                        chat_id=str(update.message.chat_id),
                        sender=update.message.from_user.username,
                        message=update.message.text
                    )
                    updates.append({
                        "chat_id": update.message.chat_id,
                        "user_id": update.message.from_user.id,
                        "username": update.message.from_user.username,
                        "text": update.message.text,
                        "update_id": update.update_id # To mark as read later
                    })
            # Mark updates as read by setting offset to the last update_id + 1
            if new_updates:
                last_update_id = new_updates[-1].update_id
                await self.bot.get_updates(offset=last_update_id + 1, limit=1, timeout=1)

        except Exception as e:
            self.logger.error("[%s] Error fetching Telegram updates: %s", self.avatar_id, e)
        return updates

# Note: For a full-fledged Telegram bot, you'd typically use Application.builder().build()
# and run it in a separate process or thread. For the purpose of integrating with
# FastAPI's scheduler, we're using a more direct polling approach here.
# This polling approach is NOT recommended for production bots with high traffic.
# Webhooks are the preferred method for production Telegram bots.
