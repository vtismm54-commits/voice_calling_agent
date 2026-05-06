import json
import os
from datetime import datetime

JSON_FILE = "call_sessions.json"


def save_call_session_json(
    session_id,
    start_time,
    end_time,
    conversation,
    chat_score,
    final_lead_score,
    followup_required
):

    session_data = {
        "session_id": session_id,
        "start_time": start_time,
        "end_time": end_time,
        "conversation": conversation.split("\n"),
        "chat_score": chat_score,
        "final_lead_score": final_lead_score,
        "saved_at": datetime.now().isoformat(timespec="seconds")
    }

    # If file exists → append, else create new list
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    else:
        data = []

    data.append(session_data)

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
