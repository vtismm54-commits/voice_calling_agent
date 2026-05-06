import requests
from config import OPENROUTER_API_KEY

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "meta-llama/llama-3.1-8b-instruct"


def generate_conversation_summary(conversation_text: str) -> str:
    # 🔒 No conversation safety
    if not conversation_text.strip():
        return "कोई बातचीत रिकॉर्ड नहीं हुई।"

    system_prompt = """
नीचे दी गई सेल्स कॉल का 2–3 छोटी लाइनों में सारांश दीजिए।

ध्यान दें:
- क्लाइंट की ज़रूरत क्या थी
- इंटरेस्ट लेवल कैसा था
- अगला कदम क्या है (डेमो / WhatsApp / फॉलो-अप)

केवल सारांश टेक्स्ट लिखें, कुछ और नहीं।
"""

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": conversation_text}
        ],
        "temperature": 0.3,
        "max_tokens": 120
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://voicetunesindia.com",
        "X-Title": "VoiceTunesSummaryEngine"
    }

    try:
        response = requests.post(
            OPENROUTER_URL,
            json=payload,
            headers=headers,
            timeout=15   # 🔥 NEVER BLOCK
        )

        if response.status_code != 200:
            return "सारांश उपलब्ध नहीं है।"

        data = response.json()

        if "choices" not in data or not data["choices"]:
            return "सारांश उपलब्ध नहीं है।"

        summary = data["choices"][0]["message"].get("content", "").strip()
        return summary or "सारांश उपलब्ध नहीं है।"

    except requests.exceptions.Timeout:
        return "टाइमआउट के कारण सारांश स्किप किया गया।"

    except Exception:
        return "आंशिक कॉल। क्लाइंट की बातचीत रिकॉर्ड की गई।"