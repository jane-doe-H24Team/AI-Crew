import ollama
from pathlib import Path
from avatar_manager import db
from avatar_manager.core.embeddings import generate_embedding
from avatar_manager.config import config

import logging

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATES_DIR = Path(__file__).parent.parent / "prompts"

llm_config = config.get('llm', {})
default_llm_model = llm_config.get('default_model', 'llama3:8b')
default_llm_options = llm_config.get('default_options', {'temperature': 0.7})
filter_model = llm_config.get('filter_model', 'llama3:8b')

avatar_config = config.get('avatar', {})
default_email_history_limit = avatar_config.get('default_email_history_limit', 10)

rag_config = config.get('rag', {})
default_rag_distance_threshold = rag_config.get('distance_threshold', None)

def _load_prompt_template(template_name: str) -> str:
    template_path = _PROMPT_TEMPLATES_DIR / template_name
    with open(template_path, 'r') as f:
        return f.read()

async def _get_rag_context(query: str, limit: int = 3) -> str:
    """Generates an embedding for the query and retrieves relevant documents from RAG DB."""
    if not query:
        return ""
    try:
        query_embedding = await generate_embedding(query)
        results = db.search_rag_documents(query_embedding, limit=limit, distance_threshold=default_rag_distance_threshold)
        if results:
            context = "\n---\n".join([r['content'] for r in results])
            logger.debug(f"Retrieved RAG context (first 100 chars): {context[:100]}...")
            return context
    except Exception as e:
        logger.error(f"Error retrieving RAG context for query '{query[:50]}...': {e}")
    return ""

def should_reply_to_email(incoming_email: dict) -> bool:
    """
    Usa l'LLM per decidere se un'email necessita di una risposta.
    """ 
    prompt = f"""You are a strict email filter. Decide if the following email requires a reply. Respond ONLY with the single word 'REPLY' or 'IGNORE'.

REPLY to: Direct questions, requests for action, important project updates, or personal messages from known contacts.
IGNORE: Spam, advertisements, automatic notifications, newsletters, or messages that are purely informational and don't need a response.

Email to analyze:
From: {incoming_email['from']}
Subject: {incoming_email['subject']}
Body: {incoming_email['body']}

Your decision:"""

    try:
        # For this decision, we want deterministic output, so we override temperature
        response = ollama.chat(
            model=filter_model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.0} 
        )
        decision = response['message']['content'].strip().upper()
        logger.debug("Filter decision: %s", decision)
        return "REPLY" in decision
    except Exception as e:
        logger.error("Error during filter decision: %s", e)
        return False # Per sicurezza, non rispondiamo

async def _generate_response(avatar_profile: dict, prompt_template_name: str, context: dict):
    model = avatar_profile.get("llm_model", default_llm_model)
    llm_options = avatar_profile.get("llm_options", default_llm_options)

    prompt_template = _load_prompt_template(prompt_template_name)
    
    rag_query = context.get('rag_query')
    rag_context = await _get_rag_context(rag_query) if rag_query else ""
    if rag_context:
        context['rag_context'] = f"\n\nRelevant information from knowledge base:\n{rag_context}\n"
    else:
        context['rag_context'] = ""

    prompt = prompt_template.format(**context)

    logger.info("[%s] Generating response with model %s and options %s...", avatar_profile['name'], model, llm_options)

    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options=llm_options
        )
        return response['message']['content']
    except Exception as e:
        logger.error("Error generating response with Ollama: %s", e)
        return "I'm sorry, but I'm currently unable to process your request."

async def generate_reply(avatar_profile: dict, incoming_email: dict, avatar_id: str):
    """
    Genera una risposta ad una email usando l'LLM specificato nel profilo dell'avatar.
    """
    email_history_limit = avatar_profile.get("email_history_limit", default_email_history_limit)
    
    history = db.get_email_history(avatar_id, incoming_email['from'], limit=email_history_limit)
    conversation_history = "\n".join([f"{h['sender']}: {h['message']}" for h in reversed(history)])

    context = {
        "avatar_name": avatar_profile['name'],
        "personality": avatar_profile['personality'],
        "conversation_history": conversation_history,
        "email_from": incoming_email['from'],
        "email_subject": incoming_email['subject'],
        "email_body": incoming_email['body'],
        "rag_query": incoming_email['body']
    }

    return await _generate_response(avatar_profile, "email_reply_template.txt", context)

async def generate_github_comment(avatar_profile: dict, thread_details: dict):
    """
    Genera un commento per una issue/PR di GitHub.
    """
    context = {
        "avatar_name": avatar_profile['name'],
        "personality": avatar_profile['personality'],
        "thread_title": thread_details['title'],
        "thread_body": thread_details['body'],
        "rag_query": thread_details['body']
    }

    return await _generate_response(avatar_profile, "github_comment_template.txt", context)

async def generate_telegram_reply(avatar_profile: dict, telegram_message: dict):
    """
a    Genera una risposta a un messaggio Telegram.
    """
    context = {
        "avatar_name": avatar_profile['name'],
        "personality": avatar_profile['personality'],
        "username": telegram_message['username'],
        "message_text": telegram_message['text'],
        "rag_query": telegram_message['text']
    }

    return await _generate_response(avatar_profile, "telegram_message_template.txt", context)

async def generate_discord_reply(avatar_profile: dict, discord_message: dict):
    """
    Genera una risposta a un messaggio Discord.
    """
    context = {
        "avatar_name": avatar_profile['name'],
        "personality": avatar_profile['personality'],
        "username": discord_message['username'],
        "channel_id": discord_message['channel_id'],
        "message_text": discord_message['text'],
        "rag_query": discord_message['text']
    }

    return await _generate_response(avatar_profile, "discord_message_template.txt", context)