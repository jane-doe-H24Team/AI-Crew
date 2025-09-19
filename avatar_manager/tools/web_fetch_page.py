import requests
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def web_fetch_page(url: str):
    """Fetches the text content of a given URL."""
    logger.debug(f"Fetching content from URL: {url}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        
        if not soup.body:
            logger.warning(f"Page {url} has no body content.")
            return {"error": "The page has no visible content."}

        body_text = soup.body.get_text(separator=' ', strip=True)
        snippet = body_text[:4000] # Return a larger snippet for a specific page

        logger.info(f"Successfully fetched and parsed content from {url}")
        return {
            "source_url": url,
            "content": snippet
        }

    except requests.RequestException as e:
        logger.error(f"Could not fetch {url}: {e}")
        return {"error": f"Failed to fetch content from the URL: {e}"}
    except Exception as e:
        logger.error(f"An unexpected error occurred while processing {url}: {e}")
        return {"error": f"An unexpected error occurred: {e}"}

def get_tool_definition():
    return {
        "type": "function",
        "function": {
            "name": "web_fetch_page",
            "description": "Use this tool to read the full text content of a specific web page, given its URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL of the web page to read.",
                    }
                },
                "required": ["url"],
            },
        }
    }
