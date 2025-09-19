import os
from dotenv import load_dotenv
import logging
from functools import wraps
from typing import Optional
from avatar_manager.config import config
import json
from psycopg2.extras import DictCursor # Moved import to top

logger = logging.getLogger(__name__)
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
database_config = config.get('database', {})
vector_dimension = database_config.get('vector_dimension', 768)

_db_connection = None
_db_connection_failed = False

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    global _db_connection, _db_connection_failed
    if _db_connection:
        return _db_connection
    if _db_connection_failed:
        return None

    if not DATABASE_URL:
        logger.warning("DATABASE_URL environment variable not set. Database functionality will be disabled.")
        _db_connection_failed = True
        return None
    try:
        import psycopg2
        from psycopg2 import Error
        from psycopg2.extensions import register_adapter, AsIs
        
        conn = psycopg2.connect(DATABASE_URL)
        
        

        _db_connection = conn
        return conn
    except ImportError as e:
        logger.error(f"Failed to import psycopg2: {e}. Please install it with 'pip install psycopg2-binary'. Database functionality will be disabled.")
        _db_connection_failed = True
        return None
    except Exception as e:
        logger.error(f"Error connecting to PostgreSQL database: {e}. Database functionality will be disabled.")
        _db_connection_failed = True
        return None

def db_operation(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        conn = get_db_connection()
        if not conn:
            # Return a default value if the function has a return annotation
            if 'return' in func.__annotations__:
                return func.__annotations__['return']()
            return

        try:
            return func(conn, *args, **kwargs)
        except Exception as e: # Catching generic exception to avoid psycopg2 import at top level
            logger.error(f"Database error in {func.__name__}: {e}")
            if conn:
                try:
                    conn.rollback()
                except Exception as rb_e:
                    logger.error(f"Error during rollback: {rb_e}")
        finally:
            # We are not closing the connection here to allow connection reuse
            pass
    return wrapper

@db_operation
def create_email_history_table(conn):
    """Creates the email_history table if it doesn't exist."""
    logger.debug("Creating email_history table if it doesn't exist...")
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS email_history (
            id SERIAL PRIMARY KEY,
            avatar_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            subject TEXT,
            message TEXT NOT NULL,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    conn.commit()
    cur.close()
    logger.debug("email_history table created/verified successfully.")

@db_operation
def create_rag_tables(conn):
    """Creates RAG-related tables (e.g., documents) if they don't exist."""
    logger.debug("Creating RAG tables if they don't exist...")
    cur = conn.cursor()
    try:
        cur.execute(f'''
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                embedding VECTOR({vector_dimension}) NOT NULL,
                metadata JSONB
            );
        ''')
        conn.commit()
        logger.debug("RAG tables created/verified successfully.")
    except Exception as e:
        logger.warning(f"Could not create RAG tables (documents). This might be due to missing pg_vector extension: {e}")
        conn.rollback() # Ensure rollback if this specific part fails
    finally:
        cur.close()

@db_operation
def add_email_to_history(conn, avatar_id: str, sender: str, recipient: str, subject: str, message: str):
    """Adds an email to the conversation history."""
    logger.debug(f"Adding email to history for avatar {avatar_id} from {sender} to {recipient}")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO email_history (avatar_id, sender, recipient, subject, message) VALUES (%s, %s, %s, %s, %s)",
        (avatar_id, sender, recipient, subject, message)
    )
    conn.commit()
    cur.close()

@db_operation
def get_email_history(conn, avatar_id: str, sender: str, limit: int = 10) -> list:
    """Retrieves the conversation history for a specific sender."""
    logger.debug(f"Getting email history for avatar {avatar_id} with {sender}")
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute(
        """
        SELECT sender, message, timestamp 
        FROM email_history 
        WHERE avatar_id = %s AND (sender = %s OR recipient = %s)
        ORDER BY timestamp DESC
        LIMIT %s
        """,
        (avatar_id, sender, sender, limit)
    )
    history = cur.fetchall()
    cur.close()
    return [dict(row) for row in history] if history else []

@db_operation
def create_chat_history_table(conn):
    """Creates the chat_history table if it doesn't exist."""
    logger.debug("Creating chat_history table if it doesn't exist...")
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            avatar_id VARCHAR(255) NOT NULL,
            platform VARCHAR(50) NOT NULL,
            chat_id VARCHAR(255) NOT NULL,
            sender VARCHAR(255) NOT NULL,
            message TEXT NOT NULL,
            timestamp TIMESTAMPTZ DEFAULT NOW()
        );
    ''')
    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_chat_history_lookup
        ON chat_history (avatar_id, platform, chat_id, timestamp DESC);
    ''')
    conn.commit()
    cur.close()
    logger.debug("chat_history table created/verified successfully.")

@db_operation
def add_message_to_chat_history(conn, avatar_id: str, platform: str, chat_id: str, sender: str, message: str):
    """Adds a chat message to the conversation history."""
    logger.debug(f"Adding {platform} message to history for avatar {avatar_id} in chat {chat_id}")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chat_history (avatar_id, platform, chat_id, sender, message) VALUES (%s, %s, %s, %s, %s)",
        (avatar_id, platform, chat_id, sender, message)
    )
    conn.commit()
    cur.close()

@db_operation
def get_chat_history(conn, avatar_id: str, platform: str, chat_id: str, limit: int = 10) -> list:
    """Retrieves the conversation history for a specific chat."""
    logger.debug(f"Getting {platform} chat history for avatar {avatar_id} in chat {chat_id}")
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute(
        """
        SELECT sender, message, timestamp
        FROM chat_history
        WHERE avatar_id = %s AND platform = %s AND chat_id = %s
        ORDER BY timestamp DESC
        LIMIT %s
        """,
        (avatar_id, platform, chat_id, limit)
    )
    history = cur.fetchall()
    cur.close()
    return [dict(row) for row in history] if history else []

@db_operation
def add_document_to_rag(conn, content: str, embedding: list, metadata: dict = None):
    """Adds a document chunk and its embedding to the RAG knowledge base."""
    logger.debug(f"Adding document to RAG knowledge base. Content length: {len(content)}")
    cur = conn.cursor()
    # Convert metadata dict to JSON string if it's not None
    json_metadata = json.dumps(metadata) if metadata is not None else None

    cur.execute(
        "INSERT INTO documents (content, embedding, metadata) VALUES (%s, %s, %s)",
        (content, "[" + ",".join(map(str, embedding)) + "]", json_metadata) # Pass the JSON string
    )
    conn.commit()
    cur.close()

@db_operation
def search_rag_documents(conn, query_embedding: list, limit: int = 5, distance_threshold: Optional[float] = None) -> list:
    """Performs a similarity search in the RAG knowledge base."""
    logger.debug(f"Searching RAG documents with query embedding (first 5 elements): {query_embedding[:5]}) with limit {limit} and threshold {distance_threshold}")
    cur = conn.cursor(cursor_factory=DictCursor)

    sql_query = "SELECT content, metadata, embedding <-> %s AS distance FROM documents"
    vector_string = "[" + ",".join(map(str, query_embedding)) + "]"
    params = [vector_string]

    if distance_threshold is not None:
        sql_query += " WHERE (embedding <-> %s) < %s" # Re-calculate distance for WHERE clause
        params.append(vector_string)
        params.append(distance_threshold)

    sql_query += " ORDER BY distance LIMIT %s"
    params.append(limit)

    cur.execute(sql_query, tuple(params))
    results = cur.fetchall()
    cur.close()
    return [dict(row) for row in results] if results else []