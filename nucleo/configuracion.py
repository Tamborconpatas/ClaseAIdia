import os
import json

CONFIG_FILE = "transcriber_config.json"

DEFAULT_CONFIG = {
    "language": "es",
    "beam_size": 5,
    "vad_filter": True,
    "compute_type": "default", # "default", "int8", "float16", "int8_float16"
    "ollama_model": "llama3",
    "ollama_max_tokens": 2048,
    "ollama_url": "http://localhost:11434",
    "ollama_chunk_chars": 6000
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return DEFAULT_CONFIG

def save_config(config_dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_dict, f, indent=4)

def get_param(key):
    config = load_config()
    return config.get(key, DEFAULT_CONFIG.get(key))

def set_param(key, value):
    config = load_config()
    config[key] = value
    save_config(config)
