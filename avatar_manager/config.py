import yaml
from pathlib import Path

import logging

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

def load_config() -> dict:
    """Loads the configuration from the config.yaml file."""
    try:
        with open(_CONFIG_PATH, 'r') as f:
            config = yaml.safe_load(f)
        logger.info("Configuration loaded successfully.")
        return config
    except FileNotFoundError:
        logger.error(f"Configuration file not found at {_CONFIG_PATH}")
        # Return an empty dict to avoid breaking the application
        # The application should handle the case where the config is empty
        return {}
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file: {e}")
        return {}

# Load the configuration once when the module is imported
config = load_config()
