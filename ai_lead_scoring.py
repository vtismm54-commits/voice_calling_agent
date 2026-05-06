import requests
import re
from config import OPENROUTER_API_KEY

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "meta-llama/llama-3.1-8b-instruct"


def ai_calculate_lead_score(conversation_text: str) -> int:
    system_prompt = """
You are a strict scoring engine.

IMPORTANT RULES:
- You MUST reply with ONLY a number between 0 and 100.
- Do NOT write words.
- Do NOT write "Assistant".
- Do NOT write labels.
- Example valid reply: 65
- Example invalid replies: "Assistant: 65", "Score is 65", "Sixty five"

Scoring guide:
80–100 = Hot lead
50–79 = Warm lead
20–49 = Cold lead
0–19 = Not interested
"""


    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Conversation:\n{conversation_text}"
            }
        ],
        "temperature": 0.0,
        "max_tokens": 10
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://voicetunesindia.com",
        "X-Title": "VoiceTunesAIScorer"
    }

    try:
        response = requests.post(
            OPENROUTER_URL,
            json=payload,
            headers=headers,
            timeout=60
        )

        data = response.json()

        raw = data["choices"][0]["message"]["content"]
        print("🧠 AI raw score response:", repr(raw))

        # 🔥 Extract first number safely
        match = re.search(r"\d{1,3}", raw)

        if match:
            score = int(match.group())
            return min(max(score, 0), 100)

        # 🔁 Fallback if AI replied weirdly
        return 40   # neutral warm lead fallback

    except Exception as e:
        print("⚠️ AI scoring failed:", e)
        return 40   # NEVER return 0
