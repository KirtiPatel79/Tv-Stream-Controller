import json
import os

STATE_FILE = "app_state.json"

# Global state objects
manual_stream = {
    "enabled": False,
    "title": None,
    "url": None,
    "updated_at": None,
    "thumbnail": None
}

presets = [
    {"title": "Evening Aarti", "url": "https://www.youtube.com/watch?v=6QZZ2ZkgVuU"}
]

def load_state():
    global manual_stream, presets
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if "manual_stream" in data:
                    manual_stream.update(data["manual_stream"])
                if "presets" in data:
                    presets.clear()
                    presets.extend(data["presets"])
        except Exception as e:
            print(f"Error loading state: {e}")

def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump({
            "manual_stream": manual_stream,
            "presets": presets
        }, f, indent=2)

# Initialize on import
load_state()
