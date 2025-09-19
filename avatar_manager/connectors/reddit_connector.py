import praw
from .base_connector import BaseConnector
from avatar_manager import db

class RedditConnector(BaseConnector):
    """Connector for Reddit."""

    def get_credentials(self):
        """Retrieves credentials for Reddit from environment variables."""
        self.client_id = self._get_env_var("REDDIT_CLIENT_ID")
        self.client_secret = self._get_env_var("REDDIT_CLIENT_SECRET")
        self.user_agent = self._get_env_var("REDDIT_USER_AGENT")
        self.username = self._get_env_var("REDDIT_USERNAME")
        self.password = self._get_env_var("REDDIT_PASSWORD")

        self.reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent,
            username=self.username,
            password=self.password,
        )

    async def fetch_updates(self):
        """Fetches new mentions and messages from Reddit."""
        updates = []
        unread_items = list(self.reddit.inbox.unread(limit=None))
        if unread_items:
            for item in unread_items:
                update_data = {
                    "id": item.id,
                    "author": item.author.name,
                    "body": item.body,
                    "type": "comment" if isinstance(item, praw.models.Comment) else "message"
                }
                updates.append(update_data)
                db.add_message_to_chat_history(
                    avatar_id=self.avatar_id,
                    platform="reddit",
                    chat_id=item.id,
                    sender=item.author.name,
                    message=item.body
                )
            self.reddit.inbox.mark_read(unread_items)
        return updates

    async def send_message(self, recipient: str, subject: str, body: str):
        """Sends a message or reply on Reddit."""
        try:
            item = self.reddit.comment(recipient) if subject == "comment" else self.reddit.message(recipient)
            item.reply(body)
            db.add_message_to_chat_history(
                avatar_id=self.avatar_id,
                platform="reddit",
                chat_id=recipient,
                sender=self.avatar_id,
                message=body
            )
            self.logger.info(f"Replied to Reddit item: {recipient}")
        except Exception as e:
            self.logger.error(f"Failed to send Reddit reply to {recipient}: {e}")