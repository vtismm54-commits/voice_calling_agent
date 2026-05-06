import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
AGENT_NAME = "Aarav"
WEBHOOK_URL = "https://unmagnanimous-undelayingly-laraine.ngrok-free.dev/voice"
ACCOUNT_SID=os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN=os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE=os.getenv("TWILIO_PHONE")


if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY not found in environment")
