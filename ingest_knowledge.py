import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
import tiktoken
import logging
from bs4 import BeautifulSoup

from avatar_manager.core.embeddings import generate_embedding
from avatar_manager.db import add_document_to_rag, create_rag_tables
from avatar_manager.config import config

# Load environment variables
load_dotenv()

# Configuration
rag_config = config.get('rag', {})
KNOWLEDGE_BASE_DIR = Path(__file__).parent / rag_config.get('knowledge_base_dir', 'knowledge_base')
CHUNK_SIZE = rag_config.get('chunk_size', 500)
CHUNK_OVERLAP = rag_config.get('chunk_overlap', 50)
TOKENIZER_ENCODING = rag_config.get('tokenizer_encoding', 'cl100k_base')
INGEST_FILE_EXTENSIONS = rag_config.get('ingest_file_extensions', ['.txt'])

# Initialize tokenizer for chunking
tokenizer = tiktoken.get_encoding(TOKENIZER_ENCODING)

logger = logging.getLogger(__name__)

def chunk_text(text: str) -> list[str]:
    """Chunks text into smaller pieces based on token count."""
    tokens = tokenizer.encode(text)
    chunks = []
    for i in range(0, len(tokens), CHUNK_SIZE - CHUNK_OVERLAP):
        chunk_tokens = tokens[i : i + CHUNK_SIZE]
        chunks.append(tokenizer.decode(chunk_tokens))
    return chunks

async def ingest_file(file_path: Path):
    """Reads a file, chunks its content, generates embeddings, and stores them in the DB."""
    logger.info(f"Ingesting file: {file_path.name}")
    try:
        content = ""
        if file_path.suffix.lower() in ['.html', '.htm']: # Ensure .htm is also covered
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            soup = BeautifulSoup(html_content, 'html.parser')
            # Remove script and style elements
            for script_or_style in soup(["script", "style"]):
                script_or_style.extract()
            content = soup.get_text(separator=' ', strip=True) # Extract text, preserving some spacing
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        
        if not content.strip(): # Skip empty content after stripping
            logger.warning(f"Skipping empty or unreadable file: {file_path.name}")
            return

        chunks = chunk_text(content)
        logger.info(f"File {file_path.name} chunked into {len(chunks)} pieces.")

        for i, chunk in enumerate(chunks):
            embedding = await generate_embedding(chunk)
            metadata = {"source": str(file_path.name), "chunk_index": i}
            add_document_to_rag(chunk, embedding, metadata)
            logger.debug(f"Ingested chunk {i+1}/{len(chunks)} from {file_path.name}")
        logger.info(f"Successfully ingested {file_path.name}.")

    except Exception as e:
        logger.error(f"Error ingesting file {file_path.name}: {e}")

async def main():
    log_level = config.get('app', {}).get('log_level', 'INFO').upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    logger.info("Starting knowledge base ingestion...")
    create_rag_tables() # Ensure RAG tables exist

    if not KNOWLEDGE_BASE_DIR.exists():
        logger.error(f"Knowledge base directory not found: {KNOWLEDGE_BASE_DIR}")
        return

    for file_path in KNOWLEDGE_BASE_DIR.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in INGEST_FILE_EXTENSIONS:
            await ingest_file(file_path)
        else:
            logger.info(f"Skipping non-text file or directory: {file_path.name}")

    logger.info("Knowledge base ingestion complete.")

if __name__ == "__main__":
    asyncio.run(main())
