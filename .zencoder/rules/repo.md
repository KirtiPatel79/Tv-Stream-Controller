---
description: Repository Information Overview
alwaysApply: true
---

# TV Stream Controller Information

## Summary
A Python-based backend service that manages TV stream data. It provides a FastAPI web server for status updates and a Telegram bot for remote management and control of YouTube channel streams.

## Structure
- **`main.py`**: Entry point that initializes the FastAPI application and launches the Telegram bot in a background thread.
- **`telegram_bot.py`**: Contains the Telegram bot implementation for user interaction and control.
- **`youtube.py`**: Integrates with the YouTube API to fetch and manage live streams for specific channels.
- **`state.py`**: Maintains shared application state between the web server and the bot.
- **`requirements.txt`**: Lists the Python package dependencies.
- **`venv/`**: Python virtual environment for local development.

## Language & Runtime
**Language**: Python  
**Version**: 3.12.4  
**Build System**: pip  
**Package Manager**: pip

## Dependencies
**Main Dependencies**:
- `fastapi`: Web framework for building APIs.
- `uvicorn[standard]`: ASGI server for running the FastAPI application.
- `python-telegram-bot`: Library for interacting with the Telegram Bot API.
- `httpx`: Async HTTP client for YouTube API calls.
- `python-dotenv`: Management of environment variables from `.env`.

## Build & Installation
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows)
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Main Files & Resources
**Application Entry Point**: `main.py`
**Configuration**:
- `.env`: Contains sensitive configuration like `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_ID`, and `YOUTUBE_API_KEY`.
- `state.py`: Centralized state management for manual stream overrides.

**Key Scripts**:
- `main.py`: Starts the entire system (API + Bot).
- `telegram_bot.py`: Bot logic and command handlers.
- `youtube.py`: YouTube API data retrieval logic.

## Usage & Operations
**Run Command**:
```bash
uvicorn main:app --reload
```
The application runs a FastAPI server (typically on port 8000) and a Telegram bot concurrently. The bot allows authorized users to update the channel ID and view current stream status.
