# main.py
from dotenv import load_dotenv
load_dotenv()

import os
import threading
import uvicorn
from fastapi import FastAPI
from state import manual_stream, presets
from youtube import fetch_channel_streams
from telegram_bot import start_bot

app = FastAPI(title="TV Stream Controller")


@app.on_event("startup")
def startup():
    threading.Thread(target=start_bot, daemon=True).start()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/current")
def get_status():
    return {
        "manual_stream": manual_stream,
        "presets": presets
    }


@app.get("/channel-streams")
async def get_channel_streams():
    streams = await fetch_channel_streams()
    return {"streams": streams}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
