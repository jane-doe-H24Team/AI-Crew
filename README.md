# AI Crew

AI Crew is a multi-agent system designed to manage a team of autonomous avatars. These avatars can perform various tasks, such as replying to emails, participating in GitHub discussions, and interacting with social media platforms like Telegram and Discord. The system is designed to be highly extensible, allowing for the addition of new avatars, new functionalities, and new communication channels.

The core of the project is an orchestrator built with FastAPI that manages the avatars' lifecycle and interactions. Each avatar has its own personality, skills, and schedule, defined in a YAML profile. The avatars are powered by language models (LLMs) running locally, which allows for greater privacy and control. To enhance the quality and relevance of LLM responses, the system incorporates **Retrieval Augmented Generation (RAG)**, leveraging a knowledge base stored in PostgreSQL with the `pg_vector` extension.

## Features

-   **Autonomous Avatars**: The avatars are autonomous and can perform tasks without human intervention.
-   **Email Integration**: The avatars can read and reply to emails, maintaining conversation history.
-   **GitHub Integration**: The avatars can participate in GitHub discussions by commenting on issues and pull requests where they are mentioned.
-   **Telegram Integration**: The avatars can send and receive messages on Telegram.
-   **Discord Integration**: The avatars can send and receive messages on Discord.
-   **Retrieval Augmented Generation (RAG)**: Enhances LLM responses by retrieving relevant information from a custom knowledge base, ensuring more accurate and contextually rich replies.
-   **Local LLMs**: The use of local LLMs (via Ollama) ensures privacy and allows for greater control over the models.
-   **Agent Workflow**: Avatar can send internal messages each other enabling collaborative workflows.
-   **Extensible**: The system is designed to be highly extensible. You can easily add new avatars, new connectors, and new functionalities.

## Architecture

The project is composed of the following components:

-   **Orchestrator**: A FastAPI application (`avatar_manager/main.py`) that serves as the entry point of the system. It loads the avatar profiles, schedules the tasks, and exposes an API to interact with the system.
-   **Avatar Profiles**: YAML files located in the `profiles/` directory. Each file defines an avatar, including its name, personality, skills, LLM model, and schedule. It also allows for configuration of the email conversation history limit (`email_history_limit`).
-   **Connectors**: Python modules in the `avatar_manager/connectors/` directory that handle the communication with external services. These are abstracted via a `BaseConnector` interface, making it easy to add new platforms. Currently, there are connectors for:
    *   Email (IMAP and SMTP)
    *   GitHub
    *   Telegram
    *   Discord
-   **Core**: The `avatar_manager/core/` directory contains the core logic of the avatars, including:
    *   `generator.py`: Responsible for generating replies and comments using LLMs, now augmented with RAG.
    *   `embeddings.py`: Handles the generation of vector embeddings for text using Ollama.
-   **Prompts**: The `avatar_manager/prompts/` directory contains the prompt templates used to interact with the LLMs.
-   **Database (PostgreSQL with pg_vector)**: Used for persistent storage of conversation history and the RAG knowledge base. `pg_vector` enables efficient similarity search for retrieving relevant information.
-   **Ollama**: The system relies on a local installation of Ollama to run the LLMs (for both generation and embedding). Each avatar can be configured to use a different model.
-   **Internal Event Bus**: A core component (`avatar_manager/internal_events.py`) facilitating asynchronous, decoupled communication between avatars. Avatars can publish messages (e.g., task hand-offs, escalation requests) to the bus, and other avatars can subscribe to specific message types or messages addressed directly to them, enabling complex collaborative workflows.

## How it works

1.  The **Orchestrator** loads the avatar profiles from the `profiles/` directory and initializes the configured connectors for each avatar.
2.  A scheduler triggers the execution of tasks for each avatar, according to its schedule.
3.  The **Connectors** are used to fetch data from external services (e.g., unread emails, GitHub notifications, Telegram/Discord messages).
4.  For each incoming message, the `generator.py` module:
    *   Uses an LLM to decide whether a reply is needed (for emails).
    *   Generates an embedding of the incoming message/query.
    *   Performs a similarity search in the **RAG knowledge base** (PostgreSQL with `pg_vector`) to retrieve relevant contextual information.
    *   Uses another LLM to generate the content of the reply, based on the avatar's personality, the conversation history (for emails), the incoming message, and the **retrieved RAG context**.
5.  The **Connectors** are used to send the reply to the external service.

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
5.  Update the `.env` file with your credentials for the email, GitHub, Telegram, and Discord accounts of your avatars, and your PostgreSQL `DATABASE_URL`.
    ```
    # Example .env entries
    DATABASE_URL="postgresql://your_rag_user:your_password@localhost:5432/rag_db"

    # For a specific avatar (e.g., JOHN_DOE)
    JOHN_DOE_EMAIL_ADDRESS="john.doe@example.com"
    JOHN_DOE_EMAIL_PASSWORD="your_email_password"
    JOHN_DOE_IMAP_SERVER="imap.example.com"
    JOHN_DOE_SMTP_SERVER="smtp.example.com"

    JOHN_DOE_GITHUB_USERNAME="john_doe_gh"
    JOHN_DOE_GITHUB_TOKEN="your_github_token"

    JOHN_DOE_TELEGRAM_TOKEN="your_telegram_bot_token"

    JOHN_DOE_DISCORD_TOKEN="your_discord_bot_token"
    ```
6.  **Download Ollama Avatar and Embedding Models**:
    ```bash
    ollama pull llama3:8b # Default avatar model
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
-   `PUT /log_level?level=DEBUG`: Sets the logging level.
-   `POST /trigger_schedule`: Manually triggers the execution of the tasks.

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

### Avatars

To add a new avatar, create a new YAML file in the `profiles/` directory. You can use the existing profiles as a template. The following fields are available:

-   `name`: The avatar's name.
-   `personality`: A description of the avatar's personality.
-   `skills`: A list of the avatar's skills.
-   `llm_model`: The LLM to use for this avatar (e.g., `llama3:8b`).
-   `llm_options`: The options to use with the LLM (e.g., `temperature`, `top_p`).
-   `email_history_limit`: (Optional) The number of past email messages to include in the conversation history for the LLM. Defaults to 10.
-   `gender`: The avatar's gender.
-   `birth_date`: The avatar's birth date.
-   `country`: The avatar's country.
-   `image_url`: The URL of the avatar's image.
-   `schedule`: The avatar's schedule.

### Credentials

The credentials for the external services are stored in the `.env` file. The variable names are prefixed with the avatar ID (e.g., `JOHN_DOE_EMAIL_ADDRESS`).

## Known Limitations

This project is a Proof of Concept (POC) and is not intended for production use without further development. Key limitations include:

-   **Inefficient Polling:** The connectors for Telegram and Discord use polling (periodic checks) to fetch updates, which is inefficient and can lead to delays. For a production environment, this should be replaced with a webhook-based system.
-   **Hardware Requirements:** The use of local LLMs via Ollama can be resource-intensive. Running multiple avatars with large models may require a powerful machine with significant RAM and a capable GPU.
-   **Lack of Automated Testing:** The project currently lacks a suite of automated tests. This is a critical component for ensuring reliability and stability in a production system.
-   **Database Tuning:** Missing indexes and cleanup procedures.

## How to contribute

### Adding a new connector

To add a new connector, create a new Python module in the `avatar_manager/connectors/` directory. The connector should implement the `BaseConnector` interface. Then, you need to update the `avatar_manager/main.py` file to initialize the new connector for each avatar and add a new scheduled task that uses it.

### Adding a new functionality

To add a new functionality, you might need to update the `avatar_manager/core/generator.py` module to add a new function that generates the content for the new functionality. You might also need to add a new prompt template in the `avatar_manager/prompts/` directory.

## License

This project is licensed under the Apache License, Version 2.0. See the [LICENSE](LICENSE) file for details.