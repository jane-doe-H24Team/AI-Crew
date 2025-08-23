from abc import ABC, abstractmethod
import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

class BaseConnector(ABC):
    """Abstract base class for all connectors."""

    def __init__(self, avatar_id: str):
        self.avatar_id = avatar_id
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def get_credentials(self):
        """Abstract method to retrieve credentials for the connector."""
        pass

    @abstractmethod
    async def fetch_updates(self):
        """Abstract method to fetch new updates/messages from the service."""
        pass

    @abstractmethod
    async def send_message(self, recipient: str, subject: str, body: str):
        """Abstract method to send a message to the service."""
        pass

    def _get_env_var(self, var_name: str, required: bool = True):
        prefix = self.avatar_id.upper().replace("-", "_")
        full_var_name = f"{prefix}_{var_name}"
        value = os.getenv(full_var_name)
        if required and not value:
            self.logger.error("Missing environment variable: %s for avatar %s", full_var_name, self.avatar_id)
            raise ValueError(f"Missing environment variable: {full_var_name}")
        return value
