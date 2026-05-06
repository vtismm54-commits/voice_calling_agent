# =========================
# SALES BRAIN - AUTO TRANSFER FLOW
# =========================

TRANSFER_MESSAGE = ""   # ❌ completely remove voice

# 🔥 Direct opening pitch (NO QUESTION)
def get_direct_pitch(client_name="sir"):
    return (
        f"हाय {client_name}, मैं वॉइस ट्यून्स इंडिया से बात कर रही हूँ। "
        "अभी सिर्फ 3,250 में हम आपको पूरा यूजीसी वीडियो बनाकर दे रहे हैं। "
        "मैं आपको हमारे ह्यूमन एग्जीक्यूटिव से कनेक्ट कर रही हूँ।"
    )


EXIT_SCRIPT = ""  # ❌ not needed

ALL_AGENT_SPEECH = [
    "",  # no hello
]

CALL_STAGE = {
    "stage": "start",
}


def is_yes(text):
    return False   # ❌ not needed


def is_no(text):
    return False   # ❌ not needed


def generate_response(user_speech, client=None):
    stage = CALL_STAGE.get("stage")

    # 👉 Get client name
    client_name = "sir"
    if client:
        client_name = client.get("name") or client.get("client_name") or "sir"

    # 🔥 STAGE 1: बोलो और तुरंत transfer
    if stage == "start":
        CALL_STAGE["stage"] = "done"
        return get_direct_pitch(client_name)

    # 🔥 STAGE 2: Direct transfer (no logic)
    return "__TRANSFER_CALL__"