import os
import logging
from googleapiclient.discovery import build
from avatar_manager.config import config

logger = logging.getLogger(__name__)

# --- Configuration ---
API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
tools_config = config.get('tools', {})
default_lang = tools_config.get('default_search_language', 'en')

def web_search(query: str, lang: str = None, num_results: int = 3):
    """Performs a web search using the official Google Custom Search API and returns the top results."""
    search_lang = lang or default_lang
    logger.debug(f"Performing Google API search for query: '{query}' in lang '{search_lang}'")
    
    if not API_KEY or not SEARCH_ENGINE_ID:
        error_msg = "Google Search API key or Search Engine ID are not configured. Please set GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID in your .env file."
        logger.error(error_msg)
        return {"error": error_msg}

    try:
        service = build("customsearch", "v1", developerKey=API_KEY)
        res = service.cse().list(q=query, cx=SEARCH_ENGINE_ID, num=num_results, lr=f"lang_{search_lang}").execute()
        
        items = res.get('items', [])
        if not items:
            return {"error": "No results found."}

        # Format the results for the LLM
        formatted_results = []
        for item in items:
            formatted_results.append({
                "title": item.get('title'),
                "link": item.get('link'),
                "snippet": item.get('snippet')
            })
        
        return {"results": formatted_results}

    except Exception as e:
        logger.error(f"An error occurred during Google API search: {e}", exc_info=True)
        return {"error": f"An error occurred during the search: {e}"}

def get_tool_definition():
    return {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Use this tool to get current events, recent information, or timely news on any topic using Google Search. Returns a list of search results with titles, links, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to use.",
                    },
                    "lang": {
                        "type": "string",
                        "description": f"The language for the search (e.g., 'en', 'it'). Defaults to '{default_lang}'.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "The number of search results to return. Defaults to 3.",
                    }
                },
                "required": ["query"],
            },
        }
    }
