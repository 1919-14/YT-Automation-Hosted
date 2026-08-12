"""
config.py — loads .env and exposes settings as simple constants.

Every other module imports from here instead of reading os.environ
directly, so provider/model/key changes only ever touch .env.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure UTF-8 output encoding across Windows/Linux terminals for emoji logging safety
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")


# Prevent PyTorch CUDA memory fragmentation on GPUs with <= 6GB VRAM
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

# Cap background CPU thread consumption (4 threads max) so laptop stays 100% responsive for user work
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")


def _require(key):
    val = os.getenv(key)
    if not val:
        raise RuntimeError(
            f"Missing required env var: {key}. "
            f"Copy .env.example to .env and fill it in."
        )
    return val


# --- LLM --- Tier 1: OpenCode Zen (primary)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "opencode_zen")
LLM_BASE_URL = _require("LLM_BASE_URL")
LLM_API_KEY = _require("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash-free")

# --- LLM --- Tier 2: Groq 10-key pool (openai/gpt-oss-120b)
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = os.getenv("LLM_MODEL1", "openai/gpt-oss-120b")
GROQ_API_KEYS = [
    v for v in (
        os.getenv(f"LLM_API_KEY{i}", "") for i in range(1, 11)
    ) if v
]

# --- LLM --- Tier 3: Google Gemini AI Studio (ultimate fallback)
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODEL = os.getenv("LLM_MODEL2", "gemini-2.5-flash-lite")
GEMINI_API_KEY = os.getenv("LLM_API_KEY11", "")


# --- YouTube ---
YT_CLIENT_SECRETS_FILE = PROJECT_ROOT / os.getenv(
    "YT_CLIENT_SECRETS_FILE", "data/yt_client_secret.json"
)
YT_TOKEN_FILE = PROJECT_ROOT / os.getenv("YT_TOKEN_FILE", "data/yt_token.json")

# --- Telegram Bot ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Pexels ---
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

# --- Local models ---
SD_MODEL_ID = os.getenv("SD_MODEL", "stabilityai/sdxl-turbo")
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")  # "cpu" or "cuda" — see SETUP.md for the Windows CUDA DLL note

# --- Visual pipeline ---
SHOT_MIN_DURATION = float(os.getenv("SHOT_MIN_DURATION", "2.0"))  # seconds
SHOT_MAX_DURATION = float(os.getenv("SHOT_MAX_DURATION", "5.0"))  # seconds
SDXL_INFERENCE_STEPS = int(os.getenv("SDXL_INFERENCE_STEPS", "4"))  # 1-4 for turbo
ENABLE_AVATAR_OVERLAY = os.getenv("ENABLE_AVATAR_OVERLAY", "true").lower() == "true"

# --- Paths ---
ASSETS_DIR = PROJECT_ROOT / "assets"
OUTPUT_DIR = PROJECT_ROOT / "output"
LOGS_DIR = PROJECT_ROOT / "logs"


def cleanup_vram():
    """Explicitly releases GPU VRAM memory and runs garbage collection."""
    import gc
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass


if __name__ == "__main__":
    print(f"Provider:  {LLM_PROVIDER}")
    print(f"Base URL:  {LLM_BASE_URL}")
    print(f"Model:     {LLM_MODEL}")
    print(f"API key:   {LLM_API_KEY[:8]}...{LLM_API_KEY[-4:]}")
