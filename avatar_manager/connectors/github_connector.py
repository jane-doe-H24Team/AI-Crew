import requests
from avatar_manager.connectors.base_connector import BaseConnector

import logging

logger = logging.getLogger(__name__)

API_URL = "https://api.github.com"

class GithubConnector(BaseConnector):
    def __init__(self, avatar_id: str):
        super().__init__(avatar_id)
        self.username = None
        self.token = None

    def get_credentials(self):
        self.username = self._get_env_var("GITHUB_USERNAME", required=False)
        self.token = self._get_env_var("GITHUB_TOKEN", required=False)
        if not self.token:
            self.logger.debug("No GitHub token found for avatar %s", self.avatar_id)
            return False
        return True

    async def fetch_updates(self):
        """Fetches unread notifications where the user has been mentioned."""
        if not self.token:
            return []
        headers = {'Authorization': f'token {self.token}', 'Accept': 'application/vnd.github.v3+json'}
        try:
            response = requests.get(f"{API_URL}/notifications", headers=headers)
            response.raise_for_status()
            self.logger.debug("GitHub notifications raw response: %s", response.json())
            
            unread_mentions = []
            for notification in response.json():
                if notification.get('reason') == 'mention':
                    unread_mentions.append(notification)
                    
            return unread_mentions
        except requests.exceptions.RequestException as e:
            self.logger.error("Error fetching unread notifications for %s: %s", self.avatar_id, e)
            return []

    async def send_message(self, comments_url: str, body: str):
        """Posts a comment on an issue or pull request."""
        if not self.token:
            return False
        headers = {'Authorization': f'token {self.token}', 'Accept': 'application/vnd.github.v3+json'}
        try:
            response = requests.post(comments_url, json={'body': body}, headers=headers)
            response.raise_for_status()
            self.logger.info("[%s] Successfully posted comment to %s", self.avatar_id, comments_url)
            return True
        except requests.exceptions.RequestException as e:
            self.logger.error("[%s] Error posting comment to %s: %s", self.avatar_id, e)
            return False

    def get_thread_details(self, url: str):
        """Fetches details of an issue or pull request from a URL."""
        if not self.token:
            return {}
        headers = {'Authorization': f'token {self.token}', 'Accept': 'application/vnd.github.v3+json'}
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error("Error fetching thread details from %s for %s: %s", url, self.avatar_id, e)
            return {} # Return empty dict on error

    def mark_thread_as_read(self, thread_id: str):
        """Marks a notification as read."""
        if not self.token:
            return
        headers = {'Authorization': f'token {self.token}'}
        try:
            response = requests.patch(f"{API_URL}/notifications/threads/{thread_id}", headers=headers)
            response.raise_for_status() # Still raise for status internally to catch network/API errors
            self.logger.info("[%s] Successfully marked thread %s as read.", self.avatar_id, thread_id)
        except requests.exceptions.RequestException as e:
            self.logger.warning("[%s] Failed to mark thread %s as read: %s", self.avatar_id, thread_id, e)
            # Does not raise an error if it fails, as it's not critical
