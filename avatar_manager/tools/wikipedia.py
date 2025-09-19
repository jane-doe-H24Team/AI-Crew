import wikipediaapi

def wikipedia(query: str, lang: str = 'en'):
    """Searches for a page on Wikipedia and returns a summary."""
    try:
        wiki = wikipediaapi.Wikipedia(user_agent='AI-Crew/1.0', language=lang)
        page = wiki.page(query)
        if page.exists():
            return {"title": page.title, "summary": page.summary[0:500] + "..."}
        else:
            return {"error": f"Page '{query}' not found."}
    except Exception as e:
        return f"Error during Wikipedia search: {e}"

def get_tool_definition():
    return {
        "type": "function",
        "function": {
            "name": "wikipedia",
            "description": "Use this tool for general, encyclopedic, or historical information. Best for questions like 'what is...' or 'who was...'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The title of the page to search for.",
                    },
                    "lang": {
                        "type": "string",
                        "description": "The language of the Wikipedia to search (e.g., 'en', 'it', 'es'). Defaults to 'en'.",
                    }
                },
                "required": ["query"],
            },
        }
    }
