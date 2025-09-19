# AI Crew

AI Crew is a multi-agent system designed to manage a team of autonomous avatars. These avatars can perform various tasks, such as replying to emails, participating in GitHub discussions, and interacting with social media platforms like Telegram, Discord, Reddit and Slack. The system is designed to be highly extensible, allowing for the addition of new avatars, new functionalities, and new communication channels.

The core of the project is an orchestrator built with FastAPI that manages the avatars' lifecycle and interactions. Each avatar has its own personality, skills, and schedule, defined in a YAML profile. The avatars are powered by language models (LLMs), giving users the flexibility to use local instances (like Ollama or vLLM) or cloud-based services. To enhance the quality and relevance of LLM responses, the system incorporates Retrieval Augmented Generation (RAG), leveraging a knowledge base stored in PostgreSQL with the `pg_vector` extension.

## Features

-   **Autonomous Avatars**: The avatars are autonomous and can perform tasks without human intervention.
-   **Tool Usage**: Avatars can use external tools to perform actions, such as web searches, calculations, or interacting with other APIs. This feature is powered by the LLM's function calling capabilities.
-   **Flexible LLM Engine**: Supports multiple LLM backends, including Ollama and any OpenAI-compatible API (e.g., vLLM, Together.ai).
-   **Multi-Platform Connectors**: Integration with Email, GitHub, Telegram, Discord, Reddit, and Slack.
-   **Retrieval Augmented Generation (RAG)**: Enhances LLM responses by retrieving relevant information from a custom knowledge base.
-   **Agent Workflow**: Avatars can send internal messages to each other, enabling collaborative workflows.
-   **Extensible**: The system is designed to be highly extensible. You can easily add new avatars, connectors, and tools.

## Architecture

The project is composed of the following components:

-   **Orchestrator**: A FastAPI application (`avatar_manager/main.py`) that serves as the entry point of the system.
-   **Avatar Profiles**: YAML files in the `profiles/` directory defining each avatar's personality, skills, and configuration.
-   **Connectors**: Modules in `avatar_manager/connectors/` for communication with external services.
-   **Tools**: Modules in `avatar_manager/tools/` that define the tools available to the avatars.
-   **Core**: The `avatar_manager/core/` directory contains the core logic, including the `generator.py` which now handles tool usage.
-   **LLM Engines**: Support for Ollama and OpenAI-compatible APIs.

## How it works

1.  The **Orchestrator** loads the avatar profiles and the available tools.
2.  The scheduler triggers tasks for each avatar.
3.  The **Connectors** fetch data from external services.
4.  For each incoming message, the `generator.py` module:
    *   Provides the LLM with the user's message, the conversation history, RAG context, and the definitions of the tools the avatar is allowed to use.
    *   The LLM decides whether to respond directly or to use a tool.
    *   If a tool is chosen, the system executes the tool's Python function and sends the result back to the LLM.
    *   The LLM uses the tool's result to generate a final response.
5.  The **Connectors** send the final reply.

## Getting Started

### Prerequisites

-   Python 3.9.1+
-   Ollama installed and running (with `nomic-embed-text` or your chosen embedding model pulled)
-   PostgreSQL with `pg_vector` extension enabled is strongly suggested but not mandatory

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/your-username/AI-crew.git
    cd AI-crew
    ```
2.  Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```
3.  **PostgreSQL and pg_vector Setup**:
    *   Ensure PostgreSQL is installed and running on your system.
    *   Access your PostgreSQL prompt (e.g., `psql -U postgres`).
    *   Create a new database and user (e.g., `CREATE DATABASE rag_db; CREATE USER your_rag_user WITH PASSWORD 'your_password'; GRANT ALL PRIVILEGES ON DATABASE rag_db TO your_rag_user;`).
    *   Connect to your new database (e.g., `\c rag_db your_rag_user`).
    *   Enable the `pg_vector` extension: `CREATE EXTENSION vector;`
    *   Exit psql (`\q`).
4.  Create a `.env` file for your credentials. You can use the `.env.example` file as a template.
    ```bash
    cp .env.example .env
    ```
5.  Update the `.env` file with all required credentials. This includes:
    - The `DATABASE_URL` for PostgreSQL.
    - The **Google Search API credentials** for the `web_search` tool. Follow the guide in `examples/setup_google_search_api.html` to get your `GOOGLE_SEARCH_API_KEY` and `GOOGLE_SEARCH_ENGINE_ID`.
    - The credentials for each avatar's connectors (Email, GitHub, etc.), using `.env.example` as a template.
6.  **Download Ollama Avatar and Embedding Models**:
    ```bash
    ollama pull llama3:8b        # Default avatar model
    ollama pull llama3.1:8b      # If You want to use Tools
    ollama pull nomic-embed-text # Or your chosen embedding model
    ```
7.  **Ingest Knowledge Base**:
    *   Create a `knowledge_base` directory in the project root:
        ```bash
        mkdir knowledge_base
        ```
    *   Place your text files (e.g., `.txt` files) containing the knowledge you want your avatars to use into this directory.
    *   Run the ingestion script:
        ```bash
        python ingest_knowledge.py
        ```

### Running the Application

Use uvicorn to run the FastAPI server:

```bash
uvicorn avatar_manager.main:app
```

The API will be available at `http://127.0.0.1:8000`.

### API Endpoints

-   `GET /`: Returns a welcome message.
-   `GET /avatars`: Returns the loaded avatar profiles.
-   `GET /avatars/{avatar_id}`: Returns the profile of a specific avatar.
-   `PUT /log_level?level=DEBUG`: Sets the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
-   `POST /trigger_schedule`: Manually triggers the execution of the tasks.

For example:

```bash
curl -X POST 'http://127.0.0.1:8000/trigger_schedule'
```
 

## Usage Examples

To illustrate the versatility of AI-Crew, we've prepared several examples demonstrating different use cases, from single-avatar applications to multi-avatar collaborations. These examples include suggested avatar configurations, prompting strategies, and RAG knowledge base content.

You can view these examples by opening the following HTML files in your browser:

### Single Avatar Examples
- [Automated Customer Support Assistant (Email-based)](./examples/customer_support_assistant.html)
- [GitHub Issue Triage and Initial Response](./examples/github_issue_triage.html)
- [Telegram/Discord Community Moderator (Q&A)](./examples/community_moderator.html)
- [Eliza Doolittle - The Rogerian Psychologist](./examples/eliza_doolittle.html)

### Multi-Avatar Crew Examples
- [Brainstorming Group](./examples/crew_brainstorming.html)
- [Automated Software Development Lifecycle (SDLC) Assistant Crew](./examples/crew_sdlc_assistant.html)
- [Multi-Channel Customer Support with Escalation Crew](./examples/crew_customer_support.html)
- [Content Curation and Dissemination Crew](./examples/crew_content_curation.html)


## Configuration

### LLM Configuration

You can configure the LLM engine globally in `config.yaml`.

```yaml
# config.yaml
llm:
  default_engine: "ollama"  # Can be 'ollama' or 'openai_compatible'
  default_model: "llama3:8b"
  default_options:
    temperature: 0.7
  filter_model: "llama3:8b"
  openai_compatible:
    api_base: "" # e.g. http://localhost:8000/v1 for a local vLLM instance, http://localhost:11434/v1 for Llama.cpp
    api_key: ""    # Optional API key
```

- `default_engine`: Choose between `ollama` and `openai_compatible`.
- `openai_compatible`: If you use `openai_compatible`, you must provide the `api_base` URL for your LLM server. An `api_key` can also be provided if required by the service.

### Avatars

To add a new avatar, create a new YAML file in the `profiles/` directory. You can override the global LLM settings and enable tools on a per-avatar basis.

-   `name`: The avatar's name.
-   `personality`: A description of the avatar's personality.
-   `skills`: A list of the avatar's skills.
-   `schedule`: The avatar's schedule.
-   `tools`: (Optional) A list of tools the avatar is allowed to use (e.g., `["web_search"]`).

**LLM settings for an avatar (Optional):**
-   `llm_engine`: Override the default engine. **Note:** Tool usage is only supported for `openai_compatible` engines.
-   `llm_model`: The model to use for this avatar.
-   `llm_api_base`: The API base URL for the `openai_compatible` engine.

### Tool Usage

AI-Crew allows avatars to use tools to interact with the outside world beyond simple chat.

#### How it Works

The tool usage feature leverages the function-calling capabilities of modern LLMs. When an avatar receives a prompt, it can decide to call one of the tools it has been configured to use. The system executes the tool, and the result is fed back to the avatar, which then formulates a final response.

#### Creating a New Tool

Adding a new tool is simple:

1.  **Create a Python file** in the `avatar_manager/tools/` directory (e.g., `my_tool.py`).
2.  **Define the execution function**. The name of the function should match the name of the file (e.g., `def my_tool(...)`).
3.  **Define the tool's specification** in a `get_tool_definition()` function within the same file. This definition follows the OpenAI function calling specification.

**Example: `avatar_manager/tools/calculator.py`**

```python
# The function that performs the action
def calculator(expression: str):
    try:
        return eval(expression)
    except Exception as e:
        return f"Error: {e}"

# The definition the LLM will see
def get_tool_definition():
    return {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a mathematical expression.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate.",
                    }
                },
                "required": ["expression"],
            },
        }
    }
```

#### Enabling Tools for an Avatar

To allow an avatar to use a tool, add the tool's name (the filename without `.py`) to the `tools` list in the avatar's profile YAML file.

```yaml
# profiles/math_bot.yaml
name: "MathBot"
personality: "A bot that loves to calculate things."
llm_engine: "openai_compatible"
tools:
  - "calculator"
  - "web_search"
  - "wikipedia"
```

## Known Limitations

This project is a Proof of Concept (POC) and is not intended for production use without further development. Key limitations include

-   **Inefficient Polling:** The connectors for Telegram and Discord use polling (periodic checks) to fetch updates, which is inefficient and can lead to delays. For a production environment, this should be replaced with a webhook-based system.
-   **Hardware Requirements:** The use of local LLMs via Ollama can be resource-intensive. Running multiple avatars with large models may require a powerful machine with significant RAM and a capable GPU.
-   **Lack of Automated Testing:** The project currently lacks a suite of automated tests. This is a critical component for ensuring reliability and stability in a production system.
-   **Database Tuning:** Missing indexes and cleanup procedures.
-   **Tool Calling Engine Support**: The tool calling feature is currently only supported by `openai_compatible` LLM engines. The native `ollama` engine does not support this functionality, but you can use Llama.cpp interface anyway.


## How to contribute

### Adding a new connector

To add a new connector, create a new Python module in the `avatar_manager/connectors/` directory. The connector should implement the `BaseConnector` interface. Then, you need to update the `avatar_manager/main.py` file to initialize the new connector for each avatar and add a new scheduled task that uses it.

### Adding a new functionality

To add a new functionality, you might need to update the `avatar_manager/core/generator.py` module to add a new function that generates the content for the new functionality. You might also need to add a new prompt template in the `avatar_manager/prompts/` directory.

## License

This project is licensed under the Apache License, Version 2.0. See the [LICENSE](LICENSE) file for details.
