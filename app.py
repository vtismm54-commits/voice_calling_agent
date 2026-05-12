import asyncio
import os
import csv
import io
import base64
import json
import traceback
import urllib.parse
import requests
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import httpx

from sales_brain import get_direct_pitch
from config import AGENT_NAME
from session_logger import save_call_session
from session_logger_json import save_call_session_json
from conversation_state import clear_history
from fastapi import UploadFile, File
import shutil
import builtins

# ================= APP SETUP =================
http_client = httpx.AsyncClient(timeout=30)
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= CONFIG =================
SARVAM_API_KEY   = os.getenv("SARVAM_API_KEY")
SARVAM_TTS_URL   = "https://api.sarvam.ai/text-to-speech"
BASE_URL         = os.getenv("BASE_URL", "https://voice-calling-agent-1f3f.onrender.com")
EXOTEL_SID       = os.getenv("EXOTEL_SID")
EXOTEL_API_KEY   = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
EXOTEL_NUMBER    = os.getenv("EXOTEL_NUMBER")
EXOTEL_APP_ID    = os.getenv("EXOTEL_APP_ID")

BASE_DIR           = os.path.dirname(os.path.abspath(__file__))
CLIENTS_FILE       = os.path.join(BASE_DIR, "clients.csv")
LOG_FILE           = os.path.join(BASE_DIR, "call_logs.csv")
HUMAN_AGENT_NUMBER = os.getenv("TRANSFER_TO_NUMBER")

# ================= AUDIO CACHE DIR =================
AUDIO_CACHE_DIR = os.path.join(BASE_DIR, "audio_cache")
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

# ================= GLOBAL STATE =================
clients             = []
current_index       = 0
paused              = False
current_call_sid    = None
call_status_ui      = "Idle"
active_client_data  = None
call_sessions       = {}
latest_messages     = {"user": "", "agent": ""}
call_connected_time = None
transfer_pending    = {}

# In-memory audio cache: phone_number -> 8kHz PCM bytes
audio_cache: dict[str, bytes] = {}
call_in_progress = False
terminal_logs = []

# ================= FULL TERMINAL CAPTURE =================

original_print = builtins.print

def terminal_print(*args, **kwargs):
    try:
        message = " ".join(str(a) for a in args)

        # console માં print
        original_print(*args, **kwargs)

        # dashboard logs માં save
        terminal_logs.append(message)

        # limit
        if len(terminal_logs) > 1000:
            terminal_logs.pop(0)

    except Exception as e:
        original_print("LOGGER ERROR:", e)

# override global print
builtins.print = terminal_print

# ================= LOAD CLIENTS =================
def load_clients():
    global clients
    if not os.path.exists(CLIENTS_FILE):
        clients = []
        return
    with open(CLIENTS_FILE, newline="", encoding="utf-8") as f:
        clients = list(csv.DictReader(f))


import audioop


def convert_16k_to_8k(pcm_bytes: bytes) -> bytes:
    try:
        pcm_8k, _ = audioop.ratecv(pcm_bytes, 2, 1, 16000, 8000, None)
        return pcm_8k
    except Exception as e:
        print("⚠️ Resample error:", e)
        return b""


def normalize_text(text: str) -> str:
    return " ".join(text.strip().split())


def get_client_key(client: dict) -> str:
    """Return a stable filename key for a client based on their phone number."""
    phone = client.get("number") or client.get("mobile_no") or "unknown"
    return str(phone).strip().replace("+", "").replace(" ", "")


def get_audio_cache_path(client_key: str) -> str:
    return os.path.join(AUDIO_CACHE_DIR, f"{client_key}.pcm")


def build_pitch_text(client: dict) -> str:
    name = (
        client.get("name")
        or client.get("Name")
        or client.get("client_name")
        or client.get("Client Name")
        or "sir"
    )

    name = str(name).strip()

    print("🔥 FINAL NAME USED:", name)

    return normalize_text(
        f"हाय {name}, वॉइस ट्यून्स इंडिया से बोल रही हूँ। "
        "सिर्फ 3,250 में यूजीसी वीडियो मिल रहा है। "
        "मैं आपको हमारे एग्जीक्यूटिव से कनेक्ट कर रही हूँ।"
    )


# ================= TTS (STARTUP ONLY) =================
async def generate_sarvam_audio_bytes(text: str) -> bytes:
    """Call TTS API. Used ONLY at startup for pre-generation."""
    for attempt in range(3):
        try:
            response = await http_client.post(
                SARVAM_TTS_URL,
                json={
                    "text": text,
                    "target_language_code": "hi-IN",
                    "speaker": "ishita",
                    "model": "bulbul:v3",
                    "speech_sample_rate": 16000,
                    "output_audio_codec": "linear16",
                    "speech_rate": 1.25
                },
                headers={
                    "api-subscription-key": SARVAM_API_KEY,
                    "Content-Type": "application/json"
                }
            )
            data = response.json()
            audio_base64 = data.get("audios", [None])[0]
            if audio_base64:
                return base64.b64decode(audio_base64)
            print(f"⚠️ TTS empty response (attempt {attempt+1}): {data}")
        except Exception as e:
            print(f"⚠️ TTS error (attempt {attempt+1}): {e}")
        await asyncio.sleep(0.5)
    print("❌ FINAL TTS FAILURE for text:", text[:60])
    return b""


async def preload_all_static_audio():
    """
    Pre-generate and save audio for every client to disk + memory at startup.
    No TTS will be called during live calls.
    """
    print("⚡ Pre-generating client pitch audio...")
    load_clients()

    tasks = []
    for client in clients:
        client_key  = get_client_key(client)
        cache_path  = get_audio_cache_path(client_key)
        pitch_text  = build_pitch_text(client)

        # Load from disk if already cached
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                pcm_8k = f.read()
            if pcm_8k:
                audio_cache[client_key] = pcm_8k
                print(f"  ✅ Loaded from disk: {client_key} ({len(pcm_8k)} bytes)")
                continue

        tasks.append((client_key, cache_path, pitch_text))

    async def _generate_one(client_key, cache_path, pitch_text):
        audio_16k = await generate_sarvam_audio_bytes(pitch_text)
        if not audio_16k:
            print(f"  ❌ TTS failed for {client_key}")
            return
        pcm_8k = convert_16k_to_8k(audio_16k)
        if not pcm_8k:
            print(f"  ❌ Resample failed for {client_key}")
            return
        # Save to disk
        with open(cache_path, "wb") as f:
            f.write(pcm_8k)
        # Load into memory
        audio_cache[client_key] = pcm_8k
        print(f"  ✅ Generated & saved: {client_key} ({len(pcm_8k)} bytes)")

    results = await asyncio.gather(
        *[_generate_one(k, p, t) for k, p, t in tasks],
        return_exceptions=True
    )

    ok = len([r for r in results if not isinstance(r, Exception)])
    total = len(clients)
    print(f"✅ Audio cache ready: {len(audio_cache)}/{total} clients")


def get_cached_audio(client: dict) -> bytes:
    client_key = get_client_key(client)

    if client_key in audio_cache:
        return audio_cache[client_key]

    print(f"❌ No cached audio for client_key={client_key}")
    return b""


# ================= TRANSFER API =================
async def transfer_call_via_api(call_sid: str):
    try:
        if not call_sid:
            print("❌ No CallSid")
            return False
        url     = f"https://api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls/{call_sid}.json"
        payload = {"Url": BASE_URL + "/transfer_to_human"}
        response = requests.post(url, data=payload, auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN))
        print("🔁 Transfer API response:", response.text)
        return True
    except Exception as e:
        print(f"⚠️ Transfer error: {e}")
        return False


@app.api_route("/transfer_to_human", methods=["GET", "POST"])
async def transfer_to_human(request: Request):
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial action="/transfer_fallback" method="POST" timeout="30">{HUMAN_AGENT_NUMBER}</Dial>
</Response>"""
    return Response(content=xml, media_type="application/xml")


# ================= FINALIZE SESSION =================
async def finalize_call_session(call_sid, session_conversation):
    if not call_sid or call_sid not in call_sessions:
        return
    try:
        session           = call_sessions[call_sid]
        end_time          = datetime.now()
        start_time        = session.get("start_time", end_time)
        duration_seconds  = int((end_time - start_time).total_seconds())
        conversation_text = "\n".join(session_conversation or session.get("conversation", []))

        from ai_lead_scoring import ai_calculate_lead_score
        from conversation_summary import generate_conversation_summary
        lead_score = ai_calculate_lead_score(conversation_text)
        summary    = generate_conversation_summary(conversation_text)

        save_call_session(
            session_id=call_sid, start_time=start_time.isoformat(),
            end_time=end_time.isoformat(), duration_seconds=duration_seconds,
            conversation=conversation_text, lead_score=lead_score, summary=summary
        )
        save_call_session_json(
            session_id=call_sid, start_time=start_time.isoformat(),
            end_time=end_time.isoformat(), conversation=conversation_text,
            chat_score=0, final_lead_score=lead_score, followup_required="No"
        )
        call_sessions.pop(call_sid, None)
        print(f"✅ Session saved | {call_sid} | score={lead_score}")
    except Exception as e:
        print(f"⚠️ finalize error: {e}")


# ================================================================
# WEBSOCKET ENDPOINT
# ================================================================
#
# Simplified single-flow architecture:
#   1. Wait for first "media" event (call connected)
#   2. Load pre-cached 8kHz PCM from disk/memory — NO TTS call
#   3. Stream it immediately in 20ms chunks via websocket
#   4. Signal transfer and return
#
# ================================================================

CHUNK_BYTES = 3200   # 20 ms @ 8 kHz 16-bit mono


@app.websocket("/voicebot")
async def voicebot_ws(websocket: WebSocket):
    await websocket.accept()

    call_sid             = websocket.query_params.get("call_sid") or None
    stream_sid           = None
    session_conversation = []

    load_clients()
    client = active_client_data if active_client_data else (
        clients[current_index] if current_index < len(clients) else {}
    )

    # Load pitch audio from cache — zero latency, no API call
    pitch_audio = get_cached_audio(client)
    if not pitch_audio:
        print(f"❌ No pitch audio available for call {call_sid} — hanging up")
        await websocket.close()
        return

    print(f"✅ Pitch audio ready: {len(pitch_audio)} bytes (loaded from cache)")

    
    async def send_chunk(chunk: bytes):

        remainder = len(chunk) % 320

        if remainder:
            chunk += b'\x00' * (320 - remainder)

        payload = base64.b64encode(chunk).decode()

        await websocket.send_text(json.dumps({
            "event": "media",
            "media": {
                "payload": payload
            }
        }))


    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                print(f"⏱️ WebSocket timeout for call {call_sid}")
                break

            msg   = json.loads(raw)
            event = msg.get("event")

            # Capture stream_sid from any event that carries it
            if not stream_sid:
                stream_sid = msg.get("stream_sid") or msg.get("streamSid")

            if event in ("stop", "disconnect"):
                print(f"📴 Call ended: {event}")
                break

        
            if event in ("start", "media"):

                if not stream_sid:
                    stream_sid = (
                        msg.get("streamSid")
                        or msg.get("stream_sid")
                        or msg.get("start", {}).get("streamSid")
                    )

                print(f"⚡ Streaming cached pitch instantly | event={event}")

                frame_index = 0
                start_time = asyncio.get_event_loop().time()

                for i in range(0, len(pitch_audio), CHUNK_BYTES):

                    chunk = pitch_audio[i:i + CHUNK_BYTES]

                    await send_chunk(chunk)

                    frame_index += 1

                    next_time = start_time + frame_index * 0.1
                    now = asyncio.get_event_loop().time()

                    delay = next_time - now

                    if delay > 0:
                        await asyncio.sleep(delay)

                print("✅ Pitch delivered — triggering transfer")

                transfer_pending[call_sid] = True

                await asyncio.sleep(1)

                await send_chunk(b'\x00' * CHUNK_BYTES)

                await websocket.close()

                print("🔁 WebSocket closed properly")

                return



    except WebSocketDisconnect:
        print(f"📴 WebSocket disconnected: {call_sid}")
    except Exception as e:
        print(f"⚠️ WebSocket error: {e}")
        traceback.print_exc()
    finally:
        await finalize_call_session(call_sid, session_conversation)
        print("🔒 Voicebot session closed")


# ================================================================
# /voice — Exotel entry point
# ================================================================
@app.api_route("/voice", methods=["GET", "POST"])
async def voice(request: Request):
    form = {}
    try:
        form = await request.form()
    except Exception:
        pass

    call_sid = (
        form.get("CallSid")
        or form.get("CallUUID")
        or request.query_params.get("CallSid")
        or request.query_params.get("CallUUID")
    )

    print(f"📞 /voice | CallSid={call_sid} | transfer_pending={call_sid in transfer_pending}")

    if call_sid and call_sid in transfer_pending:
        transfer_pending.pop(call_sid, None)
        print(f"🔁 Transfer to human: {HUMAN_AGENT_NUMBER}")
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial action="/transfer_fallback" method="POST" timeout="30">{HUMAN_AGENT_NUMBER}</Dial>
</Response>"""
        return Response(content=xml, media_type="application/xml")
    
    stream_call_sid = call_sid or "unknown"

   
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Connect>
            <Stream url="{BASE_URL.replace('https://', 'wss://')}/voicebot?call_sid={stream_call_sid}" />
        </Connect>
    </Response>"""


    return Response(content=xml, media_type="application/xml")


# ================= STATUS CALLBACK =================
@app.post("/status")
async def call_status(request: Request):
    global current_index, call_status_ui, active_client_data, call_in_progress

    form     = await request.form()
    call_sid = form.get("CallSid") or form.get("CallUUID")
    status   = form.get("CallStatus") or form.get("Status")

    print(f"📊 Status | CallSid={call_sid} | Status={status}")

    if status not in ["completed", "busy", "failed", "no-answer"]:
        return Response("")
    
    call_in_progress = False   # ✅ CALL FULLY END

    if call_sid not in call_sessions:
        print(f"⚠️ No session for {call_sid} — moving to next")
        call_status_ui = "Completed"
        if active_client_data:
            active_client_data = None
        else:
            current_index += 1
        await asyncio.sleep(2)
        if not paused and not call_in_progress:
            auto_call_next()
        return Response("")

    session           = call_sessions[call_sid]
    end_time          = datetime.now()
    start_time        = session["start_time"]
    duration_seconds  = int((end_time - start_time).total_seconds())
    conversation_text = "\n".join(session["conversation"])

    from ai_lead_scoring import ai_calculate_lead_score
    from conversation_summary import generate_conversation_summary
    lead_score = ai_calculate_lead_score(conversation_text)
    summary    = generate_conversation_summary(conversation_text)

    save_call_session(
        session_id=call_sid, start_time=start_time.isoformat(),
        end_time=end_time.isoformat(), duration_seconds=duration_seconds,
        conversation=conversation_text, lead_score=lead_score, summary=summary
    )
    save_call_session_json(
        session_id=call_sid, start_time=start_time.isoformat(),
        end_time=end_time.isoformat(), conversation=conversation_text,
        chat_score=0, final_lead_score=lead_score, followup_required="No"
    )
    call_sessions.pop(call_sid, None)
    call_status_ui = "Completed"

    if active_client_data:
        active_client_data = None
    else:
        current_index += 1

    await asyncio.sleep(1)
    if not paused and not call_in_progress:
        auto_call_next()
    return Response("")


# ================= CALL LOGIC =================
def make_call(to_number, client=None):
    global current_call_sid, call_status_ui, call_in_progress

    call_status_ui = "Ringing"
    call_in_progress = True   # ✅ ADD THIS

    to_number = str(to_number).strip()
    if len(to_number) == 10:
        to_number = "+91" + to_number

    url     = f"https://api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"
    payload = {
        "From"          : to_number,
        "CallerId"      : EXOTEL_NUMBER,
        "Url"           : "http://my.exotel.com/voicetunesindia1/exoml/start_voice/1199576",
        "TimeOut"       : 30,
        "StatusCallback": BASE_URL + "/status"
    }

    print("📲 Calling:", to_number)

    response = requests.post(url, data=payload, auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN))
    print("Exotel response:", response.text)

    try:
        current_call_sid = response.json()["Call"]["Sid"]
    except Exception:
        print("⚠️ Could not parse Exotel response")


def auto_call_next():
    global call_in_progress

    load_clients()

    # ❌ IMPORTANT CONTROL
    if paused or current_index >= len(clients) or call_in_progress:
        return

    client = clients[current_index]
    phone  = client.get("number") or client.get("mobile_no")

    if phone:
        make_call(phone, client=client)


@app.post("/transfer_fallback")
async def transfer_fallback(request: Request):
    form        = await request.form()
    dial_status = form.get("DialCallStatus")
    print(f"📞 Transfer fallback | DialCallStatus={dial_status}")

    FALLBACK_NUMBER = "+919173793068"

    if dial_status == "answered":
        return Response(
            content="""<?xml version="1.0" encoding="UTF-8"?>
<Response><Hangup /></Response>""",
            media_type="application/xml"
        )

    if dial_status in ["busy", "failed", "no-answer"]:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial action="/transfer_fallback2" method="POST" timeout="30">{FALLBACK_NUMBER}</Dial>
</Response>"""
        return Response(content=xml, media_type="application/xml")

    return Response(
        content="""<?xml version="1.0" encoding="UTF-8"?>
<Response><Hangup /></Response>""",
        media_type="application/xml"
    )


# ================= DASHBOARD =================
@app.get("/")
async def dashboard(request: Request):
    
    return templates.TemplateResponse(
        request,
        "dashboard.html"
    )


@app.get("/call_status_ui")
async def call_status_ui_route():
    return JSONResponse({"status": call_status_ui})


@app.get("/latest_messages")
async def latest():
    last_score = "--"
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, newline="", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            if reader:
                last_score = reader[-1].get("lead_score", "--")
    return JSONResponse({
        "user"      : latest_messages["user"],
        "agent"     : latest_messages["agent"],
        "lead_score": last_score
    })


@app.get("/call_timer")
async def call_timer():
    if not call_connected_time:
        return JSONResponse({"seconds": 0})
    return JSONResponse({"seconds": int((datetime.now() - call_connected_time).total_seconds())})


@app.get("/get_clients")
async def get_clients():
    load_clients()
    columns = list(clients[0].keys()) if clients else []
    return JSONResponse({"columns": columns, "clients": clients, "current_index": current_index})


@app.get("/logs")
async def logs_page(request: Request):
 
    return templates.TemplateResponse(
        request,
        "logs.html"
    )




@app.get("/api/logs")
async def api_logs():
    if not os.path.exists(LOG_FILE):
        return JSONResponse({"columns": [], "logs": []})
    with open(LOG_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return JSONResponse({"columns": [], "logs": []})
    columns = rows[0]
    return JSONResponse({
        "columns": columns,
        "logs"   : [{columns[i]: row[i] if i < len(row) else "" for i in range(len(columns))} for row in rows[1:]]
    })


@app.post("/start_auto_call")
async def start_auto_call():
    global paused, current_index
    paused        = False
    current_index = 0
    auto_call_next()
    return JSONResponse({"status": "Started"})


@app.post("/pause_calling")
async def pause_calling():
    global paused
    paused = True
    return JSONResponse({"status": "Paused"})


@app.post("/resume_calling")
async def resume_calling():
    global paused
    paused = False
    auto_call_next()
    return JSONResponse({"status": "Resumed"})


@app.post("/cut_call")
async def cut_call():
    global current_call_sid
    if not current_call_sid:
        return JSONResponse({"status": "No Active Call"})
    url      = f"https://api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls/{current_call_sid}.json"
    response = requests.post(url, data={"Status": "completed"}, auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN))
    return JSONResponse({"status": "Call Ended", "exotel_response": response.text})


@app.get("/last_lead_details")
async def last_lead_details():
    if not os.path.exists(LOG_FILE):
        return JSONResponse({"status": "No Data"})
    with open(LOG_FILE, newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    if not reader:
        return JSONResponse({"status": "No Data"})
    return JSONResponse({"status": "Success", "data": reader[-1]})


@app.delete("/delete_log/{session_id}")
async def delete_log(session_id: str):
    if not os.path.exists(LOG_FILE):
        return JSONResponse({"status": "No file"})
    with open(LOG_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return JSONResponse({"status": "Empty"})
    updated = [r for r in rows if r.get("session_id") != session_id]
    if len(updated) == len(rows):
        return JSONResponse({"status": "Not found"})
    with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(updated)
    return JSONResponse({"status": "Deleted"})


@app.get("/get_number")
async def get_number():
    load_clients()
    global current_index
    number = None
    if current_index < len(clients):
        number = clients[current_index].get("number") or clients[current_index].get("mobile_no")
    print("Dialing customer:", number)
    return {"numbers": [number]}


# ================= AUDIO CACHE MANAGEMENT API =================
@app.post("/regenerate_audio_cache")
async def regenerate_audio_cache():
    """
    Force re-generate all client audio files.
    Useful when pitch text changes or new clients are added.
    """
    # Clear existing cache
    audio_cache.clear()
    for f in os.listdir(AUDIO_CACHE_DIR):
        if f.endswith(".pcm"):
            os.remove(os.path.join(AUDIO_CACHE_DIR, f))
    await preload_all_static_audio()
    return JSONResponse({"status": "Cache regenerated", "clients_cached": len(audio_cache)})


@app.get("/audio_cache_status")
async def audio_cache_status():
    """Check how many clients have audio pre-cached."""
    load_clients()
    cached_keys = set(audio_cache.keys())
    disk_files  = {f.replace(".pcm", "") for f in os.listdir(AUDIO_CACHE_DIR) if f.endswith(".pcm")}
    missing     = []
    for client in clients:
        key = get_client_key(client)
        if key not in cached_keys and key not in disk_files:
            missing.append(key)
    return JSONResponse({
        "total_clients"   : len(clients),
        "in_memory_cache" : len(cached_keys),
        "on_disk_cache"   : len(disk_files),
        "missing"         : missing
    })

@app.get("/terminal_logs")
async def get_terminal_logs():
    return JSONResponse({
        "logs": terminal_logs
    })

@app.post("/upload_csv")
async def upload_csv(file: UploadFile = File(...)):
    global clients

    try:
        # save uploaded csv
        with open(CLIENTS_FILE, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # reload clients instantly
        load_clients()

        # clear old audio cache
        audio_cache.clear()

        # regenerate audio automatically
        await preload_all_static_audio()

        return JSONResponse({
            "status": "CSV uploaded successfully"
        })

    except Exception as e:
        return JSONResponse({
            "status": str(e)
        })
    

@app.delete("/delete_all_clients")
async def delete_all_clients():
    global clients

    try:
        clients = []

        with open(CLIENTS_FILE, "w", encoding="utf-8") as f:
            f.write("name,number\n")

        audio_cache.clear()

        return JSONResponse({
            "status": "All clients deleted"
        })

    except Exception as e:
        return JSONResponse({
            "status": str(e)
        })


# ================= STARTUP =================
@app.on_event("startup")
async def startup_event():
    await preload_all_static_audio()


if __name__ == "__main__":
    import uvicorn
    load_clients()
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)