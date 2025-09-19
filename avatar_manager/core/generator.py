import ollama
import requests
import json
from pathlib import Path
from avatar_manager import db
from avatar_manager.core.embeddings import generate_embedding
from avatar_manager.config import config
from avatar_manager.tools import tool_manager

import logging

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATES_DIR = Path(__file__).parent.parent / "prompts"

# --- LLM Configuration ---
llm_config = config.get('llm', {})
default_llm_engine = llm_config.get('default_engine', 'ollama')
default_llm_model = llm_config.get('default_model', 'llama3:8b')
default_llm_options = llm_config.get('default_options', {'temperature': 0.7})
filter_model = llm_config.get('filter_model', 'llama3:8b')
openai_compatible_config = llm_config.get('openai_compatible', {})
default_openai_api_base = openai_compatible_config.get('api_base')
default_openai_api_key = openai_compatible_config.get('api_key')

# --- Avatar Configuration ---
avatar_config = config.get('avatar', {})
default_email_history_limit = avatar_config.get('default_email_history_limit', 10)
default_chat_history_limit = avatar_config.get('default_chat_history_limit', 10)

# --- RAG Configuration ---
rag_config = config.get('rag', {})
default_rag_distance_threshold = rag_config.get('distance_threshold', None)

def _load_prompt_template(template_name: str) -> str:
    template_path = _PROMPT_TEMPLATES_DIR / template_name
    with open(template_path, 'r') as f:
        return f.read()

def _get_llm_config(avatar_profile: dict = None, model_override: str = None, options_override: dict = None) -> dict:
    if avatar_profile is None: avatar_profile = {}
    engine = avatar_profile.get('llm_engine', default_llm_engine)
    model = model_override or avatar_profile.get('llm_model', default_llm_model)
    options = options_override or avatar_profile.get('llm_options', default_llm_options)
    if engine == 'openai_compatible':
        api_base = avatar_profile.get('llm_api_base', default_openai_api_base)
        api_key = avatar_profile.get('llm_api_key', default_openai_api_key)
        if not api_base: raise ValueError("llm_api_base must be configured for openai_compatible engine")
        return {"engine": engine, "model": model, "options": options, "api_base": api_base, "api_key": api_key}
    return {"engine": "ollama", "model": model, "options": options}

def _chat_completion(messages: list, llm_config: dict, tools: list = None) -> dict:
    engine = llm_config['engine']
    model = llm_config['model']
    options = llm_config['options']
    logger.debug(f"Using LLM engine: {engine}, model: {model}")

    if engine == 'openai_compatible':
        api_base = llm_config['api_base']
        api_key = llm_config.get('api_key')
        headers = {"Content-Type": "application/json"}
        if api_key: headers["Authorization"] = f"Bearer {api_key}"

        payload = {"model": model, "messages": messages, **options}
        if tools:
            payload['tools'] = tools
            payload['tool_choice'] = "auto"

        try:
            response = requests.post(f"{api_base}/chat/completions", headers=headers, json=payload)
            
            # Graceful fallback for models that don't support tools
            if response.status_code == 400 and 'tools' in payload:
                logger.warning("Tool call failed with 400 Bad Request. Retrying without tools.")
                payload.pop('tools', None)
                payload.pop('tool_choice', None)
                response = requests.post(f"{api_base}/chat/completions", headers=headers, json=payload)

            response.raise_for_status()
            return response.json()['choices'][0]
        except requests.RequestException as e:
            logger.error(f"Error calling OpenAI-compatible API: {e}")
            raise
    
    # Ollama fallback
    if tools:
        logger.warning("Tool calling is not natively supported for the 'ollama' engine. Tools will be ignored.")
    
    response = ollama.chat(model=model, messages=messages, options=options)
    return {'message': response['message']}

async def _get_rag_context(query: str, limit: int = 3) -> str:
    if not query: return ""
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
    prompt = f'''You are a strict email filter. Decide if the following email requires a reply. Respond ONLY with the single word 'REPLY' or 'IGNORE'.

REPLY to: Direct questions, requests for action, important project updates, or personal messages from known contacts.
IGNORE: Spam, advertisements, automatic notifications, newsletters, or messages that are purely informational and don't need a response.

Email to analyze:
From: {incoming_email['from']}
Subject: {incoming_email['subject']}
Body: {incoming_email['body']}

Your decision:'''
    try:
        llm_conf = _get_llm_config(model_override=filter_model, options_override={"temperature": 0.0})
        response_choice = _chat_completion(messages=[{"role": "user", "content": prompt}], llm_config=llm_conf)
        decision = response_choice['message']['content'].strip().upper()
        logger.debug("Filter decision: %s", decision)
        return "REPLY" in decision
    except Exception as e:
        logger.error("Error during filter decision: %s", e)
        return False

async def _generate_response(avatar_profile: dict, prompt_template_name: str, context: dict):
    llm_conf = _get_llm_config(avatar_profile)
    prompt_template = _load_prompt_template(prompt_template_name)
    
    rag_query = context.get('rag_query')
    rag_context = await _get_rag_context(rag_query) if rag_query else ""
    context['rag_context'] = f"\n\nRelevant information from knowledge base:\n{rag_context}\n" if rag_context else ""

    prompt = prompt_template.format(**context)
    messages = [{"role": "user", "content": prompt}]
    
    # Get tool definitions if the avatar has tools configured
    avatar_tools = avatar_profile.get("tools", [])
    tool_definitions = []
    if avatar_tools and llm_conf.get('engine') == 'openai_compatible':
        tool_definitions = tool_manager.get_tool_definitions(avatar_tools)
        logger.debug("Providing tools to LLM: %s", [t['function']['name'] for t in tool_definitions])

    logger.info("[%s] Generating response with model %s...", avatar_profile['name'], llm_conf['model'])

    try:
        response_choice = _chat_completion(messages, llm_conf, tools=tool_definitions or None)
        response_message = response_choice['message']

        # Check if the model wants to call a tool
        if response_message.get("tool_calls"):
            logger.info("LLM requested a tool call: %s", response_message["tool_calls"])
            messages.append(response_message) # Append the assistant's turn

            for tool_call in response_message["tool_calls"]:
                function_name = tool_call['function']['name']
                try:
                    function_args = json.loads(tool_call['function']['arguments'])
                    tool_result = tool_manager.execute_tool(function_name, **function_args)
                    messages.append({
                        "tool_call_id": tool_call['id'],
                        "role": "tool",
                        "name": function_name,
                        "content": json.dumps(tool_result)
                    })
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode tool arguments for {function_name}")
                    messages.append({"role": "tool", "content": "Error: Invalid arguments"})
            
            # Add a final instruction to force the model to use the tool's output
            final_instruction = "Based *only* on the information provided by the tool results, summarize the recent news for the user. Do not use any prior knowledge. If the tool results are empty or do not contain relevant news, say that you could not find any specific recent news."
            messages.append({"role": "user", "content": final_instruction})

            # Make a second call to the LLM with the tool result
            logger.info("Sending tool results and final instruction back to LLM for final response.")
            final_response_choice = _chat_completion(messages, llm_conf)
            return final_response_choice['message']['content']
        else:
            logger.debug("LLM provided a standard text response (no tool call).")

        # If no tool call, just return the content
        return response_message['content']

    except Exception as e:
        logger.error("Error generating response with LLM: %s", e)
        return "I'm sorry, but I'm currently unable to process your request."

async def generate_reply(avatar_profile: dict, incoming_email: dict, avatar_id: str):
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
    context = {
        "avatar_name": avatar_profile['name'],
        "personality": avatar_profile['personality'],
        "thread_title": thread_details['title'],
        "thread_body": thread_details['body'],
        "rag_query": thread_details['body']
    }
    return await _generate_response(avatar_profile, "github_comment_template.txt", context)

async def generate_telegram_reply(avatar_profile: dict, telegram_message: dict, avatar_id: str):
    chat_history_limit = avatar_profile.get("chat_history_limit", default_chat_history_limit)
    history = db.get_chat_history(avatar_id=avatar_id, platform="telegram", chat_id=str(telegram_message['chat_id']), limit=chat_history_limit)
    conversation_history = "\n".join([f"{h['sender']}: {h['message']}" for h in reversed(history)])
    context = {
        "avatar_name": avatar_profile['name'],
        "personality": avatar_profile['personality'],
        "conversation_history": conversation_history,
        "username": telegram_message['username'],
        "message_text": telegram_message['text'],
        "rag_query": telegram_message['text']
    }
    return await _generate_response(avatar_profile, "telegram_message_template.txt", context)

async def generate_discord_reply(avatar_profile: dict, discord_message: dict, avatar_id: str):
    chat_history_limit = avatar_profile.get("chat_history_limit", default_chat_history_limit)
    history = db.get_chat_history(avatar_id=avatar_id, platform="discord", chat_id=str(discord_message['channel_id']), limit=chat_history_limit)
    conversation_history = "\n".join([f"{h['sender']}: {h['message']}" for h in reversed(history)])
    context = {
        "avatar_name": avatar_profile['name'],
        "personality": avatar_profile['personality'],
        "conversation_history": conversation_history,
        "username": discord_message['username'],
        "channel_id": discord_message['channel_id'],
        "message_text": discord_message['text'],
        "rag_query": discord_message['text']
    }
    return await _generate_response(avatar_profile, "discord_message_template.txt", context)

async def generate_internal_reply(avatar_profile: dict, internal_message: dict, avatar_id: str):
    chat_history_limit = avatar_profile.get("chat_history_limit", default_chat_history_limit)
    history = db.get_chat_history(avatar_id=avatar_id, platform="internal", chat_id=internal_message['from_avatar'], limit=chat_history_limit)
    conversation_history = "\n".join([f"{h['sender']}: {h['message']}" for h in reversed(history)])
    context = {
        "avatar_name": avatar_profile['name'],
        "personality": avatar_profile['personality'],
        "conversation_history": conversation_history,
        "from_avatar": internal_message['from_avatar'],
        "message_text": internal_message['text'],
        "rag_query": internal_message['text']
    }
    return await _generate_response(avatar_profile, "telegram_message_template.txt", context)

async def generate_reddit_reply(avatar_profile: dict, reddit_message: dict, avatar_id: str):
    chat_history_limit = avatar_profile.get("chat_history_limit", default_chat_history_limit)
    history = db.get_chat_history(avatar_id=avatar_id, platform="reddit", chat_id=str(reddit_message['id']), limit=chat_history_limit)
    conversation_history = "\n".join([f"{h['sender']}: {h['message']}" for h in reversed(history)])
    context = {
        "avatar_name": avatar_profile['name'],
        "personality": avatar_profile['personality'],
        "conversation_history": conversation_history,
        "username": reddit_message['author'],
        "message_text": reddit_message['body'],
        "rag_query": reddit_message['body']
    }
    return await _generate_response(avatar_profile, "reddit_reply_template.txt", context)

async def generate_slack_reply(avatar_profile: dict, slack_message: dict, avatar_id: str):
    chat_history_limit = avatar_profile.get("chat_history_limit", default_chat_history_limit)
    history = db.get_chat_history(avatar_id=avatar_id, platform="slack", chat_id=slack_message['channel'], limit=chat_history_limit)
    conversation_history = "\n".join([f"{h['sender']}: {h['message']}" for h in reversed(history)])
    context = {
        "avatar_name": avatar_profile['name'],
        "personality": avatar_profile['personality'],
        "conversation_history": conversation_history,
        "username": slack_message['user'],
        "channel_name": slack_message['channel'],
        "message_text": slack_message['text'],
        "rag_query": slack_message['text']
    }
    return await _generate_response(avatar_profile, "slack_reply_template.txt", context)
