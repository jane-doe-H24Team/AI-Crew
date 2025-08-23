import ollama
import logging
from avatar_manager.config import config

logger = logging.getLogger(__name__)

embeddings_config = config.get('embeddings', {})
DEFAULT_EMBEDDING_MODEL = embeddings_config.get('default_model', 'nomic-embed-text')

async def generate_embedding(text: str, model: str = DEFAULT_EMBEDDING_MODEL) -> list:
    """Generates an embedding for the given text using Ollama."""
    try:
        response = ollama.embeddings(model=model, prompt=text)
        return response['embedding']
    except Exception as e:
        logger.error(f"Error generating embedding with Ollama model {model}: {e}")
        raise
