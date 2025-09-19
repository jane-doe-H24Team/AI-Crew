# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]


## [0.1.0] - 2025-09-19

### Added
- **Tool-Using Capabilities**: Implemented a major new feature allowing avatars to use tools.
  - Created an extensible `ToolManager` to automatically discover and load tools.
  - Added a `web_search` tool using the official Google Search API for reliable, current information.
  - Added a `web_fetch_page` tool to read and summarize content from a specific URL.
  - Added a `wikipedia` tool for encyclopedic knowledge.
  - Added a `calculator` tool for mathematical computations.
- **New Connectors**: Added full support for Reddit and Slack, including configuration, message fetching, and replying.
- **Flexible LLM Engine**: Added support for any `OpenAI-compatible` LLM engine alongside `ollama`.
- **New Documentation**:
  - Added setup guide for Reddit (`setup_reddit_bot.html`).
  - Added setup guide for Slack (`setup_slack_bot.html`).
  - Added setup guide for the Google Search API (`setup_google_search_api.html`).
  - Updated `README.md` to document the new tool system, connectors, and LLM engine flexibility.
- **Configuration**:
  - Added a configurable default search language for tools.

### Changed
- **LLM Interaction Core**: Major refactoring of `generator.py` to support the multi-step logic required for tool usage.
- **Web Search Implementation**: Replaced an unreliable web scraping tool with a robust solution based on the official Google Search API.
- **Tool Prompting**: Improved tool descriptions to help the LLM make better choices about which tool to use for a given task.
- **LLM Abstraction**: Refactored `avatar_manager/core/generator.py` to abstract LLM interactions.
- **Configuration Update**: Updated `config.yaml` and `env.example` to support new connectors and the Google Search API.

### Fixed
- **Tool Loading**: Fixed a `ModuleNotFoundError` caused by an incorrect tool implementation that tried to call an internal API.
- **Tool Execution with Incompatible Models**: Implemented a graceful fallback in `generator.py` to prevent crashes when an LLM engine does not support tool calling.
- **Tool Discovery**: Fixed a bug in the `ToolManager` that prevented a correctly named tool from being loaded, and improved its debug logging.
- **Search Language**: Fixed an issue where the web search tool was hardcoded to English, making it configurable.