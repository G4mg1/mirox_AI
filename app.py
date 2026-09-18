"""MiroxAI v33 — circular video progress, reliable frames, AgentWeb, no agent."""

import os, re, sys, json, time, uuid, random, base64, socket, platform
import html as _html, threading, urllib.parse, zipfile, io, concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, deque
import queue as _q

import requests
from flask import (Flask, request, jsonify, session, send_from_directory, Response, g)

app = Flask(__name__, static_folder=".", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
START_TIME = time.time()

IO_POOL = ThreadPoolExecutor(max_workers=24, thread_name_prefix="mirox-io")
BG_POOL = ThreadPoolExecutor(max_workers=12, thread_name_prefix="mirox-bg")

MAX_ATTACHMENT_CHARS = 12000
MAX_VISION_BYTES = 8 * 1024 * 1024
IMAGES_DIR = os.environ.get("MIROXAI_IMAGES_DIR", "generated_images")
os.makedirs(IMAGES_DIR, exist_ok=True)

CHAT_TIMEOUT = int(os.environ.get("CHAT_TIMEOUT", "60"))
HF_MAX_TOKENS = 16384
MAX_HISTORY_MESSAGES = int(os.environ.get("MAX_HISTORY_MESSAGES", "10"))
FIRST_TOKEN_DEADLINE = int(os.environ.get("FIRST_TOKEN_DEADLINE", "25"))

VIDEO_FRAME_COUNT = int(os.environ.get("VIDEO_FRAME_COUNT", "20"))
VIDEO_FPS         = int(os.environ.get("VIDEO_FPS", "4"))
VIDEO_SIZE        = int(os.environ.get("VIDEO_SIZE", "512"))
VIDEO_CONCURRENCY = int(os.environ.get("VIDEO_CONCURRENCY", "4"))
VIDEO_RETRY_MAX   = int(os.environ.get("VIDEO_RETRY_MAX", "5"))

ONLINE_WINDOW = int(os.environ.get("ONLINE_WINDOW", "60"))

SUBSCRIPTION_TIERS = {
    "free": {"label":"Free","tagline":"Get started","keys_per_period":2,"refill_days":30,
        "daily_limit":50,"images_allowed":True,"images_per_5h":5,
        "vision_per_day":10,"vision_unlimited":False,"api_key_images":False,
        "video_allowed":False,"video_per_day":0,
        "models_allowed":["mirox-gen1"],"subscription_days":30,
        "price_robux":0,"price_afg":0,"gamepass_id":None,
        "perks":["50 responses / day","2 API keys / month","5 images every 5 hours",
                 "10 image visions / day","Lite mode after daily limit","No API image gen",
                 "No video generation"]},
    "pro": {"label":"Pro","tagline":"For builders","keys_per_period":5,"refill_days":5,
        "daily_limit":500,"images_allowed":True,"images_per_5h":-1,
        "vision_per_day":-1,"vision_unlimited":True,"api_key_images":True,
        "video_allowed":True,"video_per_day":5,
        "models_allowed":["mirox-gen1","mirox-ultra-v1"],"subscription_days":30,
        "price_robux":250,"price_afg":120,"gamepass_id":"1982144889",
        "perks":["500 responses / day","5 API keys every 5 days","Both AI models",
                 "Unlimited images","Unlimited image vision","API image generation",
                 "5 silent videos / day (5s each)"]},
    "ultimate": {"label":"Ultimate","tagline":"Maximum power","keys_per_period":10,"refill_days":1,
        "daily_limit":3000,"images_allowed":True,"images_per_5h":-1,
        "vision_per_day":-1,"vision_unlimited":True,"api_key_images":True,
        "video_allowed":True,"video_per_day":-1,
        "models_allowed":["mirox-gen1","mirox-ultra-v1"],"subscription_days":365,
        "price_robux":1200,"price_afg":450,"gamepass_id":"1983380864",
        "perks":["3,000 responses / day","10 API keys daily","Both models + math",
                 "Unlimited images","Unlimited image vision","API image generation",
                 "Unlimited silent videos (5s each)","Full 1-year subscription"]},
}
DEFAULT_TIER = "free"

def _norm_url(raw):
    url = (raw or "").strip()
    if not url: return url
    url = re.sub(r"^(https?)(?!://)/+", r"\1://", url, flags=re.I)
    if not re.match(r"^https?://", url, flags=re.I): url = "https://" + url
    return url.rstrip("/")

AIROUTE_BASE_URL = _norm_url(os.environ.get("AIROUTE_BASE_URL", "https://route-ai-playground.lovable.app"))
AIROUTE_ENV_KEY = os.environ.get("AIROUTE_KEY", "")
AIROUTE_IMAGE_MODEL = os.environ.get("AIROUTE_IMAGE_MODEL", "google/gemini-3.7-flash")

HF_ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"
HF_POOL_GEN1 = ["Qwen/Qwen2.5-Coder-32B-Instruct:fastest","deepseek-ai/DeepSeek-V3-0324:fastest",
    "meta-llama/Llama-3.1-8B-Instruct:fastest","openai/gpt-oss-20b:fastest"]
HF_POOL_ULTRA = ["Qwen/Qwen3-235B-A22B-Instruct-2507:fastest","deepseek-ai/DeepSeek-R1-0528:fastest",
    "deepseek-ai/DeepSeek-V3-0324:fastest","Qwen/Qwen2.5-Coder-32B-Instruct:fastest"]
ENSEMBLE_SIZES = {"mirox-gen1":4,"mirox-ultra-v1":6}

POLLINATIONS_VISION_URL = "https://gen.pollinations.ai/v1/chat/completions"
POLLINATIONS_VISION_MODEL = os.environ.get("POLLINATIONS_VISION_MODEL", "openai")
HF_VISION_MODELS = ["Qwen/Qwen2-VL-7B-Instruct","Qwen/Qwen2.5-VL-7B-Instruct"]

POLLINATIONS_URL = "https://gen.pollinations.ai/v1/chat/completions"
POLLINATIONS_MODEL = os.environ.get("POLLINATIONS_MODEL","openai")
POLLINATIONS_LITE_MODEL = os.environ.get("POLLINATIONS_LITE_MODEL","openai")

_CODE_RULES = (
    "## Code — CRITICAL RULES (READ CAREFULLY)\n"
    "- ALWAYS output the COMPLETE, runnable file content.\n"
    "- NEVER truncate. NEVER write `// rest of code`, `...`, `/* ... */`, or similar placeholders.\n"
    "- Every function, class, and block MUST be fully written and properly closed.\n"
    "- Include every import, every dependency entry, every closing bracket.\n"
    "- If a file is long, still print it in full. Do NOT abbreviate even one line.\n"
    "- Do not summarize the code. Do not describe it. Print it.\n\n"
    "## Project files — REQUIRED FORMAT\n"
    "When building any project, output EVERY file using this EXACT fence:\n\n"
    "```file:path/to/file.ext\n"
    "<complete file content — no placeholders>\n"
    "```\n\n"
    "Rules for project files:\n"
    "- Open the fence with `file:` followed by the exact relative path.\n"
    "- Close with a single ``` on its own line.\n"
    "- The content inside MUST be the entire file — nothing omitted.\n"
    "- Include package.json / requirements.txt / index.html / README.md as needed.\n"
    "- Never mix explanation text inside the fence. Put explanations outside.\n"
)

MODEL_PRESETS = {
    "mirox-gen1": {"label":"MiroxGen1","tagline":"Fast + code",
        "airoute_model":"google/gemini-3.1-flash-lite",
        "system_prompt":("You are MiroxGen1, MiroxAI's fast everyday assistant. Be concise.\n\n"
            + _CODE_RULES +
            "\nIf asked what powers you, say MiroxGen1 by MiroxAI.")},
    "mirox-ultra-v1": {"label":"MiroxUltraV1","tagline":"Deep reasoning + math",
        "airoute_model":"google/gemini-3.1-pro-preview",
        "system_prompt":("You are MiroxUltraV1, MiroxAI's most capable reasoning, math, and coding model. Think step by step.\n\n"
            + _CODE_RULES +
            "\n## Math\nShow your work. Verify your answer.\n\n"
            "If asked what powers you, say MiroxUltraV1 by MiroxAI.")},
}
DEFAULT_MODEL_PRESET = "mirox-gen1"

BAN_FILE = os.environ.get("BAN_FILE","banned_ips.txt")
IP_LOG_FILE = os.environ.get("IP_LOG_FILE","ip_log.txt")
CHAT_LOG_FILE = os.environ.get("CHAT_LOG_FILE","chat_log.jsonl")
IMAGE_LOG_FILE = os.environ.get("IMAGE_LOG_FILE","image_log.jsonl")
REPORT_FILE = os.environ.get("REPORT_FILE","reports.jsonl")
DATA_FILE = os.environ.get("MIROXAI_DATA_FILE","miroxai_data.json")

BANNED_IPS = {}; BAN_LOCK = threading.Lock()
LAST_SEEN = {}; LAST_SEEN_LOCK = threading.Lock()
RESPONSE_TIMES = deque(maxlen=500); RT_LOCK = threading.Lock()
ROUTE_HITS = Counter(); ROUTE_LOCK = threading.Lock()
RECENT_ERRORS = deque(maxlen=80); ERR_LOCK = threading.Lock()
CONFIG_LOCK = threading.Lock()
STATE_VERSION = {"v":0}
DATA_LOCK = threading.Lock()
REQUEST_FEED = deque(maxlen=200); REQUEST_LOCK = threading.Lock()
_req_times = {}; _rate_lock = threading.Lock()
ADMIN_SESSIONS = {}; ADMIN_SESS_LOCK = threading.Lock()

MAINTENANCE = {"enabled":False,"message":"MiroxAI is under maintenance. Please check back soon."}
UPDATING = {"enabled":False,"message":"System updating"}
BROADCAST = {"id":0,"message":"","type":"info","targets":"all","ts":0}
BROADCAST_HISTORY = deque(maxlen=20)
BROADCAST_COUNTER = {"n":0}
EVENT = {"id":0,"name":"","until":0}
EVENT_COUNTER = {"n":0}

def _bump():
    with CONFIG_LOCK: STATE_VERSION["v"] += 1

def _record_error(src, msg):
    try:
        with ERR_LOCK: RECENT_ERRORS.append({"ts":time.time(),"source":src,"message":str(msg)[:300]})
    except Exception: pass

def parse_user_agent(ua):
    if not ua: return {"device":"Unknown","os":"Unknown","browser":"Unknown"}
    u = ua.lower()
    o = ("Windows" if "windows" in u else "iOS" if "iphone" in u or "ipad" in u else
         "macOS" if "mac os x" in u or "macintosh" in u else "Android" if "android" in u else
         "Linux" if "linux" in u else "Unknown")
    b = ("Edge" if "edg/" in u else "Opera" if "opr/" in u or "opera" in u else
         "Chrome" if "chrome/" in u and "chromium" not in u else "Firefox" if "firefox/" in u else
         "Safari" if "safari/" in u and "chrome" not in u else "Unknown")
    if "bot" in u or "curl/" in u or "python-requests" in u: d = "Bot"
    elif "ipad" in u or "tablet" in u: d = "Tablet"
    elif "mobile" in u or "iphone" in u or "android" in u: d = "Mobile"
    else: d = "Desktop"
    return {"device":d,"os":o,"browser":b}

def _mark_seen(ip, path):
    if not ip or ip == "unknown": return
    dev = parse_user_agent((request.headers.get("User-Agent") or "")[:200])
    with LAST_SEEN_LOCK:
        LAST_SEEN[ip] = {"ts":time.time(),"path":path,"device":dev["device"],"os":dev["os"],"browser":dev["browser"]}
        if len(LAST_SEEN) > 5000:
            cutoff = time.time() - 3600
            for k in [k for k,v in LAST_SEEN.items() if v["ts"] < cutoff]: LAST_SEEN.pop(k, None)

def _online_ips():
    now = time.time(); cutoff = now - ONLINE_WINDOW
    with LAST_SEEN_LOCK:
        items = [{"ip":k,**v} for k,v in LAST_SEEN.items() if v["ts"] >= cutoff]
    items.sort(key=lambda x:-x["ts"]); return items

def _response_stats():
    with RT_LOCK: vals = sorted(RESPONSE_TIMES)
    if not vals: return {"count":0,"avg":None,"p50":None,"p95":None}
    n = len(vals)
    return {"count":n,"avg":round(sum(vals)/n),"p50":round(vals[n//2]),"p95":round(vals[min(n-1,int(n*0.95))])}

def _app_json(path, obj):
    try:
        with open(path, "a", encoding="utf-8") as f: f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except OSError: pass

def log_chat_event(ip, user, model, ms, msg, reply, cid, vision=False, via_key=False):
    BG_POOL.submit(_app_json, CHAT_LOG_FILE, {"ts":time.time(),"ip":ip,"user":user or "anon",
        "model":model or "","ms":ms,"msg":(msg or "")[:2000],"reply":(reply or "")[:4000],
        "conv":cid,"vision":bool(vision),"via_key":bool(via_key)})

def log_image_event(ip, user, prompt, style, ratio, ok, ms, error=None, file=None):
    BG_POOL.submit(_app_json, IMAGE_LOG_FILE, {"ts":time.time(),"ip":ip,"user":user or "anon",
        "prompt":(prompt or "")[:1000],"style":style or "","ratio":ratio or "",
        "ok":bool(ok),"ms":ms,"error":(error or "")[:500] if error else None,"file":file or ""})

def _client_ip():
    fwd = request.headers.get("X-Forwarded-For")
    if fwd: return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"

def _now(): return time.strftime("%Y-%m-%d %H:%M:%S")

def load_banned_ips():
    if not os.path.exists(BAN_FILE): return
    try:
        with open(BAN_FILE,"r",encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t"); ip = parts[0].strip()
                if ip: BANNED_IPS[ip] = {"reason":parts[1].strip() if len(parts) > 1 else "","ts":time.time()}
    except Exception: pass

def save_banned_ips():
    with BAN_LOCK:
        lines = [f"{ip}\t{(info.get('reason') or '').replace(chr(9),' ')}" for ip,info in BANNED_IPS.items()]
    try:
        with open(BAN_FILE,"w",encoding="utf-8") as f: f.write("\n".join(lines))
    except OSError: pass

def is_ip_banned(ip):
    with BAN_LOCK: return ip in BANNED_IPS

def get_ban_reason(ip):
    with BAN_LOCK:
        info = BANNED_IPS.get(ip)
        return (info or {}).get("reason","") if info else ""

def ban_ip(ip, reason=""):
    ip = (ip or "").strip()
    if not ip: return
    with BAN_LOCK: BANNED_IPS[ip] = {"reason":reason,"ts":time.time()}
    save_banned_ips(); _bump()

def unban_ip(ip):
    ip = (ip or "").strip()
    if not ip: return
    with BAN_LOCK: BANNED_IPS.pop(ip, None)
    save_banned_ips(); _bump()

def _rate_exceeded(ip):
    if not ip or ip == "unknown": return False
    now = time.time()
    with _rate_lock:
        dq = _req_times.setdefault(ip, deque(maxlen=1020))
        while dq and now - dq[0] > 5.0: dq.popleft()
        dq.append(now)
        if sum(1 for t in dq if now - t <= 3.0) >= 100: return True
        if len(dq) >= 1000: return True
    return False

def _save_image(uri):
    try:
        if not uri or not uri.startswith("data:"): return ""
        header, _, data = uri.partition(",")
        if not data: return ""
        m = re.match(r"data:([^;]+);base64", header)
        mime = (m.group(1) if m else "image/png").lower()
        ext = {"image/png":".png","image/jpeg":".jpg","image/jpg":".jpg","image/gif":".gif","image/webp":".webp"}.get(mime,".png")
        fn = f"{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
        with open(os.path.join(IMAGES_DIR, fn),"wb") as f: f.write(base64.b64decode(data))
        return fn
    except Exception: return ""

def _load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE,"r",encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return {"users":{}, "reports":[]}

DATA_STORE = _load_data()
DATA_STORE.setdefault("reports", [])

def save_data():
    with DATA_LOCK:
        tmp = DATA_FILE + ".tmp"
        try:
            with open(tmp,"w",encoding="utf-8") as f: json.dump(DATA_STORE, f, indent=2)
            os.replace(tmp, DATA_FILE)
        except OSError: pass

def get_user_record(uid):
    rec = DATA_STORE["users"].setdefault(uid, {})
    defaults = {"name":None,"email":None,"persona":"","memory":[],"history":[],
        "tier":DEFAULT_TIER,"tier_started":time.time(),"tier_expires":time.time()+30*86400,
        "api_keys":[],"key_period_start":time.time(),"keys_generated_in_period":0,
        "daily_date":"","daily_count":0,
        "img_gen_5h_start":time.time(),"img_gen_5h_count":0,
        "vision_day":"","vision_count":0,
        "video_day":"","video_count":0,
        "warnings":[], "banned":False, "ban_reason":"", "reports":[],
        "created":time.time(),"last_seen":time.time()}
    for k,v in defaults.items(): rec.setdefault(k, v)
    rec["last_seen"] = time.time()
    return rec

def get_tier_config(tier):
    return SUBSCRIPTION_TIERS.get(tier or DEFAULT_TIER, SUBSCRIPTION_TIERS[DEFAULT_TIER])

def refresh_tier_expiry(rec):
    now = time.time()
    if rec.get("tier") and rec["tier"] != "free" and now > rec.get("tier_expires",0):
        rec["tier"] = "free"; rec["tier_started"] = now
        rec["tier_expires"] = now + 30*86400
        return True
    return False

def _reset_period_if_needed(rec):
    cfg = get_tier_config(rec.get("tier"))
    if time.time() - rec.get("key_period_start",0) >= cfg["refill_days"]*86400:
        rec["key_period_start"] = time.time(); rec["keys_generated_in_period"] = 0
        return True
    return False

def _reset_daily_if_needed(rec):
    today = time.strftime("%Y-%m-%d")
    if rec.get("daily_date") != today:
        rec["daily_date"] = today; rec["daily_count"] = 0
        return True
    return False

def _reset_img5h_if_needed(rec):
    if time.time() - rec.get("img_gen_5h_start",0) >= 5*3600:
        rec["img_gen_5h_start"] = time.time(); rec["img_gen_5h_count"] = 0
        return True
    return False

def _reset_vision_day_if_needed(rec):
    today = time.strftime("%Y-%m-%d")
    if rec.get("vision_day") != today:
        rec["vision_day"] = today; rec["vision_count"] = 0
        return True
    return False

def _reset_video_day_if_needed(rec):
    today = time.strftime("%Y-%m-%d")
    if rec.get("video_day") != today:
        rec["video_day"] = today; rec["video_count"] = 0
        return True
    return False

def _key_remaining(rec):
    cfg = get_tier_config(rec.get("tier"))
    return max(0, cfg["keys_per_period"] - rec.get("keys_generated_in_period",0))

def _key_refill_seconds(rec):
    cfg = get_tier_config(rec.get("tier"))
    return max(0, int(cfg["refill_days"]*86400 - (time.time() - rec.get("key_period_start",0))))

def _daily_remaining(rec):
    cfg = get_tier_config(rec.get("tier"))
    return max(0, cfg["daily_limit"] - rec.get("daily_count",0))

def _img_5h_remaining(rec):
    cfg = get_tier_config(rec.get("tier"))
    if cfg.get("images_per_5h",-1) < 0: return -1
    return max(0, cfg["images_per_5h"] - rec.get("img_gen_5h_count",0))

def _img_5h_refill_seconds(rec):
    return max(0, int(5*3600 - (time.time() - rec.get("img_gen_5h_start",0))))

def _vision_remaining(rec):
    cfg = get_tier_config(rec.get("tier"))
    if cfg.get("vision_unlimited"): return -1
    return max(0, cfg.get("vision_per_day",10) - rec.get("vision_count",0))

def _video_remaining(rec):
    cfg = get_tier_config(rec.get("tier"))
    if not cfg.get("video_allowed"): return 0
    if cfg.get("video_per_day",0) < 0: return -1
    return max(0, cfg.get("video_per_day",0) - rec.get("video_count",0))

def _is_lite_mode(rec):
    if rec.get("tier") != "free": return False
    return _daily_remaining(rec) <= 0

def _daily_reset_seconds(rec):
    now = time.time(); gm = time.gmtime(now)
    return int(86400 - (gm.tm_hour*3600 + gm.tm_min*60 + gm.tm_sec))

def _new_api_key(tier):
    prefix = {"free":"mirox_free","pro":"mirox_pro","ultimate":"mirox_ult"}.get(tier,"mirox_free")
    return f"{prefix}_{uuid.uuid4().hex}"

def _extract_bearer():
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "): return auth[7:].strip()
    return (request.headers.get("X-API-Key") or "").strip()

def _find_user_by_api_key(key):
    if not key: return None
    with DATA_LOCK:
        for uid, rec in DATA_STORE.get("users", {}).items():
            for k in rec.get("api_keys", []):
                if k.get("key") == key and not k.get("revoked"):
                    return uid, rec, k
    return None

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    ADMIN_PASSWORD = f"{random.randint(0,9999):04d}"
    print("="*70); print(f"  ADMIN PASSWORD: {ADMIN_PASSWORD}"); print("="*70)

def get_admin_config(): return DATA_STORE.setdefault("admin_config", {})

def is_admin():
    tok = session.get("admin_token")
    if tok:
        with ADMIN_SESS_LOCK:
            s = ADMIN_SESSIONS.get(tok)
            if s:
                s["last_seen"] = time.time(); session["is_admin"] = True; return True
            ADMIN_SESSIONS[tok] = {"token":tok,"ip":_client_ip(),"login_ts":time.time(),"last_seen":time.time()}
        session["is_admin"] = True; return True
    return False

def get_user_id():
    if session.get("user_id"): return session["user_id"]
    if "anon_id" not in session: session["anon_id"] = "anon-" + uuid.uuid4().hex[:8]
    return session["anon_id"]

def get_airoute_key(): return get_admin_config().get("airoute_key") or AIROUTE_ENV_KEY
def get_hf_key(): return get_admin_config().get("hf_key") or os.environ.get("HF_TOKEN","")
def get_pollinations_key(): return get_admin_config().get("pollinations_key") or os.environ.get("POLLINATIONS_KEY","")

_SESSION_TOKENS = {}; _SESSION_LOCK = threading.Lock(); SESSION_TTL = 600

def _get_session_token(api_key, force_refresh=False):
    if not api_key: raise RuntimeError("No API key.")
    now = time.time()
    with _SESSION_LOCK:
        entry = _SESSION_TOKENS.get(api_key)
        if entry and not force_refresh and (now - entry["ts"]) < SESSION_TTL: return entry["token"]
    url = f"{AIROUTE_BASE_URL}/api/public/v1/handshake"
    try: r = requests.post(url, json={"step":"connect","api_key":api_key}, timeout=10)
    except Exception as e: raise RuntimeError(f"Handshake failed: {e}")
    if r.status_code == 401: raise RuntimeError("API key rejected.")
    r.raise_for_status()
    data = r.json()
    token = data.get("session_token") or data.get("token")
    if not token: raise RuntimeError("No session_token.")
    with _SESSION_LOCK: _SESSION_TOKENS[api_key] = {"token":token,"ts":now}
    return token

def _clear_session_token(api_key):
    with _SESSION_LOCK: _SESSION_TOKENS.pop(api_key, None)

def _raise_airoute(r):
    if r.status_code == 401: raise RuntimeError("API key invalid.")
    if r.status_code == 402: raise RuntimeError("Out of credits.")
    if r.status_code == 429: raise RuntimeError("Rate-limited.")
    r.raise_for_status()

def call_airoute_chat(model, api_key, prompt):
    token = _get_session_token(api_key)
    def _do(tok):
        try:
            return requests.post(f"{AIROUTE_BASE_URL}/api/public/v1/chat",
                headers={"Authorization":f"Bearer {tok}"},
                json={"model":model,"prompt":prompt}, timeout=CHAT_TIMEOUT)
        except Exception as e: raise RuntimeError(f"AIRoute: {e}")
    r = _do(token)
    if r.status_code == 401:
        _clear_session_token(api_key); token = _get_session_token(api_key, True); r = _do(token)
    _raise_airoute(r); return r.json()

def call_airoute_image(model, api_key, prompt):
    token = _get_session_token(api_key)
    def _do(tok):
        try:
            return requests.post(f"{AIROUTE_BASE_URL}/api/public/v1/images",
                headers={"Authorization":f"Bearer {tok}"},
                json={"model":model,"prompt":prompt}, timeout=120)
        except Exception as e: raise RuntimeError(f"AIRoute images: {e}")
    r = _do(token)
    if r.status_code == 401:
        _clear_session_token(api_key); token = _get_session_token(api_key, True); r = _do(token)
    _raise_airoute(r); return r.json()

def _choice0(obj):
    if not isinstance(obj, dict): return {}
    ch = obj.get("choices")
    if not isinstance(ch, list) or not ch: return {}
    c = ch[0]
    return c if isinstance(c, dict) else {}

def get_hf_models_for(model_id):
    return list(HF_POOL_ULTRA) if model_id == "mirox-ultra-v1" else list(HF_POOL_GEN1)

def call_hf_chat(hf_model, messages, timeout=None):
    key = get_hf_key()
    if not key: raise RuntimeError("No HF token.")
    try:
        r = requests.post(HF_ROUTER_URL, headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
            json={"model":hf_model,"messages":messages,"stream":False,"max_tokens":HF_MAX_TOKENS,"temperature":0.7},
            timeout=timeout or CHAT_TIMEOUT)
    except Exception as e: raise RuntimeError(f"HF: {e}")
    if r.status_code == 200:
        data = r.json()
        ch = _choice0(data)
        content = (ch.get("message") or {}).get("content") or ""
        if content: return content
        raise RuntimeError("HF empty.")
    if r.status_code == 401: raise RuntimeError("HF token rejected.")
    if r.status_code == 429: raise RuntimeError("HF rate-limited.")
    raise RuntimeError(f"HF HTTP {r.status_code}")

def call_vision(messages):
    headers = {"Content-Type":"application/json"}
    tok = get_pollinations_key()
    if tok: headers["Authorization"] = f"Bearer {tok}"
    try:
        r = requests.post(POLLINATIONS_VISION_URL, headers=headers,
            json={"model":POLLINATIONS_VISION_MODEL,"messages":messages,"max_tokens":2048},
            timeout=CHAT_TIMEOUT)
        if r.status_code == 200:
            try:
                data = r.json()
                ch = _choice0(data)
                text = (ch.get("message") or {}).get("content") or ""
                if text: return text
            except Exception: pass
    except Exception as e:
        _record_error("vision-pollinations", e)
    key = get_hf_key()
    if key:
        for m in HF_VISION_MODELS:
            try:
                r = requests.post(HF_ROUTER_URL,
                    headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
                    json={"model":m,"messages":messages,"stream":False,"max_tokens":1024,"temperature":0.6},
                    timeout=CHAT_TIMEOUT)
                if r.status_code == 200:
                    data = r.json(); ch = _choice0(data)
                    text = (ch.get("message") or {}).get("content") or ""
                    if text: return text
            except Exception as e:
                _record_error("vision-hf", e)
    raise RuntimeError("Vision providers unavailable. Check your Pollinations or Hugging Face key in admin settings.")

def _hf_call_slot(hf_model, messages, timeout):
    started = time.time()
    try:
        text = call_hf_chat(hf_model, messages, timeout=timeout)
        return {"model":hf_model,"text":text,"ok":True,"ms":int((time.time()-started)*1000),"error":None}
    except Exception as e:
        return {"model":hf_model,"text":"","ok":False,"ms":int((time.time()-started)*1000),"error":str(e)}

def _score_response(resp_text, user_message):
    if not resp_text: return -10000
    t = resp_text.strip(); low = t.lower(); score = 0
    refusals = ("i can't","i cannot","i'm sorry","i am sorry","i'm not able","i am unable","as an ai","i don't have")
    if any(low.startswith(s) for s in refusals): score -= 800
    if "```" in t: score += 60 * t.count("```")
    if "```file:" in t: score += 300
    if "// rest of" in low or "// ..." in low or "/* ... */" in low or "... (rest" in low: score -= 1200
    if "// TODO" in t or "<!-- rest" in low: score -= 600
    L = len(t)
    if L < 40: score -= 400
    elif L < 100: score += 20
    elif L < 400: score += L * 0.15
    elif L < 1200: score += 60
    else: score += 40 + min(L-1200, 2000) * 0.02
    return score

def call_hf_ensemble(model_id, messages):
    pool = get_hf_models_for(model_id)[:ENSEMBLE_SIZES.get(model_id,4)]
    stats = {"model_id":model_id,"attempted":len(pool),"ok_count":0,"results":[],"winner":None}
    results = []
    futures = [IO_POOL.submit(_hf_call_slot, m, messages, CHAT_TIMEOUT) for m in pool]
    deadline = time.time() + CHAT_TIMEOUT
    for fut in concurrent.futures.as_completed(futures, timeout=max(1, deadline-time.time())):
        try: results.append(fut.result(timeout=1))
        except Exception as e:
            results.append({"model":"?","text":"","ok":False,"ms":0,"error":str(e)})
    stats["results"] = results
    ok = [r for r in results if r["ok"] and r["text"].strip()]
    stats["ok_count"] = len(ok)
    if not ok: raise RuntimeError("All ensemble models failed.")
    user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user" and isinstance(m.get("content"), str): user_msg = m["content"]; break
    best = max(ok, key=lambda r: _score_response(r["text"], user_msg))
    stats["winner"] = best["model"]
    return best["text"], stats

def stream_hf_single(hf_model, messages):
    key = get_hf_key()
    if not key: raise RuntimeError("No HF token.")
    try:
        r = requests.post(HF_ROUTER_URL, headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
            json={"model":hf_model,"messages":messages,"stream":True,"max_tokens":HF_MAX_TOKENS,"temperature":0.7},
            timeout=CHAT_TIMEOUT, stream=True)
    except Exception as e: raise RuntimeError(f"HF: {e}")
    if r.status_code != 200:
        if r.status_code == 401: raise RuntimeError("HF token rejected.")
        if r.status_code == 429: raise RuntimeError("HF rate-limited.")
        raise RuntimeError(f"HF HTTP {r.status_code}")
    for raw in r.iter_lines(decode_unicode=True):
        if not raw: continue
        line = raw.strip()
        if not line.startswith("data:"): continue
        payload = line[5:].strip()
        if payload == "[DONE]": return
        try: obj = json.loads(payload)
        except Exception: continue
        ch = _choice0(obj)
        delta = (ch.get("delta") or {}).get("content") or ""
        if delta: yield delta

def hf_available(): return bool(get_hf_key())

def _stream_from_airoute(model, api_key, prompt):
    token = _get_session_token(api_key)
    try:
        r = requests.post(f"{AIROUTE_BASE_URL}/api/public/v1/chat",
            headers={"Authorization":f"Bearer {token}"},
            json={"model":model,"prompt":prompt,"stream":True}, timeout=CHAT_TIMEOUT, stream=True)
    except Exception as e: raise RuntimeError(f"Airoute: {e}")
    if r.status_code == 401:
        _clear_session_token(api_key); token = _get_session_token(api_key, True)
        r = requests.post(f"{AIROUTE_BASE_URL}/api/public/v1/chat",
            headers={"Authorization":f"Bearer {token}"},
            json={"model":model,"prompt":prompt,"stream":True}, timeout=CHAT_TIMEOUT, stream=True)
    _raise_airoute(r)
    ct = (r.headers.get("content-type") or "").lower()
    if "text/event-stream" in ct or "stream" in ct:
        for raw in r.iter_lines(decode_unicode=True):
            if not raw: continue
            line = raw.strip()
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload == "[DONE]": return
                try: obj = json.loads(payload)
                except Exception: continue
                delta = obj.get("delta") or obj.get("text")
                if not delta:
                    ch = _choice0(obj)
                    delta = (ch.get("delta") or {}).get("content") or ch.get("text") or ""
                if delta: yield delta
    else:
        try: obj = r.json()
        except Exception: return
        ch = _choice0(obj)
        text = obj.get("text") or obj.get("reply") or (ch.get("message") or {}).get("content") or ""
        if text: yield text

def _stream_from_pollinations(messages, lite=False):
    headers = {"Content-Type":"application/json"}
    tok = get_pollinations_key()
    if tok: headers["Authorization"] = f"Bearer {tok}"
    model = POLLINATIONS_LITE_MODEL if lite else POLLINATIONS_MODEL
    try:
        r = requests.post(POLLINATIONS_URL, headers=headers,
            json={"model":model,"messages":messages,"stream":True},
            timeout=CHAT_TIMEOUT, stream=True)
    except Exception as e: raise RuntimeError(f"Pollinations: {e}")
    if r.status_code == 401: raise RuntimeError("Pollinations key rejected.")
    if r.status_code == 429: raise RuntimeError("Pollinations rate-limited.")
    r.raise_for_status()
    for raw in r.iter_lines(decode_unicode=True):
        if not raw: continue
        line = raw.strip()
        if not line.startswith("data:"): continue
        payload = line[5:].strip()
        if payload == "[DONE]": return
        try: obj = json.loads(payload)
        except Exception: continue
        ch = _choice0(obj)
        delta = (ch.get("delta") or {}).get("content") or ""
        if delta: yield delta

def _race_stream(messages, preset, lite, state):
    q = _q.Queue(); stop = threading.Event(); state["provider"] = None
    def worker(tag, gen_factory):
        try:
            for delta in gen_factory():
                if stop.is_set(): return
                q.put((tag, "d", delta))
            q.put((tag, "e", None))
        except Exception as ex:
            q.put((tag, "x", str(ex)[:200]))
    if not lite and get_airoute_key():
        t = threading.Thread(target=worker, args=("airoute",
            lambda: _stream_from_airoute(preset["airoute_model"], get_airoute_key(), flatten_messages(messages))), daemon=True)
        t.start()
    t = threading.Thread(target=worker, args=("pollinations",
        lambda: _stream_from_pollinations(messages, lite=lite)), daemon=True)
    t.start()
    winner = None
    deadline = time.time() + FIRST_TOKEN_DEADLINE
    while time.time() < deadline:
        try: tag, kind, payload = q.get(timeout=0.3)
        except _q.Empty: continue
        if kind == "d" and payload:
            winner = tag; state["provider"] = tag
            yield payload; break
    if winner:
        while True:
            try: tag, kind, payload = q.get(timeout=120)
            except _q.Empty: break
            if tag != winner: continue
            if kind == "d": yield payload
            elif kind in ("e","x"): break
        stop.set(); return
    stop.set()

MAX_PERSONA_CHARS = 1500; MAX_MEMORY_FACTS = 40; MAX_MEMORY_FACT_CHARS = 300; MAX_TRAINING_CHARS = 8000

def _parse_few_shot(raw):
    if not raw: return []
    out = []
    for block in re.split(r"\n\s*---+\s*\n", raw):
        block = block.strip()
        if not block: continue
        m = re.search(r"USER\s*:\s*(.+?)(?=\nASSISTANT\s*:|\Z)", block, re.I|re.S)
        a = re.search(r"ASSISTANT\s*:\s*(.+)", block, re.I|re.S)
        if m and a: out.append({"user":m.group(1).strip(),"assistant":a.group(1).strip()})
    return out[:8]

def _reasoning_block(depth):
    d = (depth or "auto").lower()
    if d == "short": return "Keep replies to 1-3 sentences unless asked for detail."
    if d == "deep": return "Think step by step. Show your reasoning."
    if d == "expert": return "Reason deeply. Consider tradeoffs, edge cases, alternatives."
    return None

def build_messages(user_message, preset, custom_persona, memory_facts,
                   file_name, file_content, search_snippets,
                   conversation_history, training, image_data_url=None):
    parts = [preset["system_prompt"]]
    if training.get("style"): parts.append(f"# Style guide\n{training['style']}")
    if training.get("code"): parts.append(f"# Coding rules\n{training['code']}")
    rb = _reasoning_block(training.get("reasoning","auto"))
    if rb: parts.append(f"# Reasoning\n{rb}")
    mid = preset.get("_id","")
    trained = training.get("_by_id",{}).get(mid,"")
    if trained: parts.append(f"# Model-specific\n{trained}")
    if training.get("shared"): parts.append(f"# Shared knowledge\n{training['shared']}")
    if custom_persona: parts.append(f"User persona: {custom_persona}")
    if memory_facts: parts.append("Known facts:\n" + "\n".join(f"- {f['text']}" for f in memory_facts))
    if search_snippets: parts.append("Web results:\n" + "\n".join(f"- {s}" for s in search_snippets))
    if file_content: parts.append(f"Attached '{file_name}':\n\n{file_content}")
    parts.append("If you learn a durable fact, include `remember:<fact>`.")
    msgs = [{"role":"system","content":"\n\n".join(parts)}]
    for ex in _parse_few_shot(training.get("few_shot","")):
        msgs.append({"role":"user","content":ex["user"]})
        msgs.append({"role":"assistant","content":ex["assistant"]})
    for turn in conversation_history[-MAX_HISTORY_MESSAGES:]:
        msgs.append({"role":"user" if turn.get("role")=="user" else "assistant","content":turn.get("text","")})
    if image_data_url:
        msgs.append({"role":"user","content":[
            {"type":"text","text":user_message or "Describe this image in detail."},
            {"type":"image_url","image_url":{"url":image_data_url}}
        ]})
    else:
        msgs.append({"role":"user","content":user_message})
    return msgs

def get_training_data():
    cfg = get_admin_config()
    return {"_by_id":{"mirox-gen1":cfg.get("train_gen1",""),"mirox-ultra-v1":cfg.get("train_ultra","")},
            "shared":cfg.get("train_shared",""),"style":cfg.get("train_style",""),
            "code":cfg.get("train_code",""),"few_shot":cfg.get("train_few_shot",""),
            "reasoning":cfg.get("train_reasoning","auto")}

def flatten_messages(messages):
    out = []
    for m in messages:
        c = m["content"]
        if isinstance(c, list):
            c = " ".join(x.get("text","[image]") if isinstance(x, dict) else str(x) for x in c)
        if m["role"] == "system": out.append(c)
        elif m["role"] == "user": out.append(f"User: {c}")
        else: out.append(f"Assistant: {c}")
    out.append("Assistant:")
    return "\n\n".join(out)

MEMORY_PATTERN = re.compile(r"remember\s*:\s*(.+?)(?=\n|$)", re.I)
FILE_BLOCK_RE = re.compile(r"```file:([^\n`]+)\n([\s\S]*?)\n```", re.MULTILINE)

_TRUNCATION_MARKERS = (
    "// rest of", "// ...", "/* ... */", "# rest of", "# ...",
    "... (rest", "<!-- rest of", "// TODO: implement",
    "// Your code here", "# Your code here", "// add code here",
    "// implementation goes here", "// implement this",
)

def _looks_truncated(content: str) -> bool:
    if not content: return True
    low = content.lower()
    for m in _TRUNCATION_MARKERS:
        if m.lower() in low: return True
    if len(content.strip()) < 40: return True
    return False

def parse_project_files(text):
    files = []
    if not text: return files
    for m in FILE_BLOCK_RE.finditer(text):
        path = m.group(1).strip(); content = m.group(2)
        ext = path.split(".")[-1].lower() if "." in path.split("/")[-1] else "plaintext"
        files.append({"path":path,"content":content,"lang":ext,
                      "truncated": _looks_truncated(content)})
    return files

def extract_memory_writes(t):
    return [m.strip()[:MAX_MEMORY_FACT_CHARS] for m in MEMORY_PATTERN.findall(t) if m.strip()]

def web_search_snippets(q, max_results=5):
    try:
        r = requests.get("https://api.duckduckgo.com/",
            params={"q":q,"format":"json","no_html":1,"skip_disambig":1}, timeout=6)
        r.raise_for_status(); d = r.json()
    except Exception: return []
    sn = []
    if d.get("AbstractText"): sn.append(d["AbstractText"])
    for t in d.get("RelatedTopics", []):
        if len(sn) >= max_results: break
        if isinstance(t, dict) and t.get("Text"): sn.append(t["Text"])
    return sn[:max_results]

STYLE_SUFFIXES = {"photo":"photorealistic","illustration":"digital illustration","anime":"anime style","3d":"3D render"}
RATIO_HINTS = {"1:1":"square","3:4":"portrait","4:3":"landscape","16:9":"widescreen"}
RATIO_SIZES = {"1:1":(1024,1024),"3:4":(896,1152),"4:3":(1152,896),"16:9":(1280,720)}

def call_pollinations_image(prompt, w, h):
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"
    try:
        r = requests.get(url, params={"width":w,"height":h,"nologo":"true"},
            headers={"User-Agent":"Mozilla/5.0"}, timeout=60)
    except Exception as e: raise RuntimeError(f"Pollinations img: {e}")
    r.raise_for_status()
    ct = r.headers.get("content-type","image/jpeg")
    if "image" not in ct: raise RuntimeError("No image.")
    return f"data:{ct};base64,{base64.b64encode(r.content).decode()}"

def _read_jsonl(path, n=200):
    if not os.path.exists(path): return []
    try:
        with open(path, encoding="utf-8", errors="replace") as f: lines = f.read().splitlines()
        lines = lines[-n:] if len(lines) > n else lines
        out = []
        for l in lines:
            l = l.strip()
            if not l: continue
            try: out.append(json.loads(l))
            except json.JSONDecodeError: pass
        return out
    except OSError: return []

def _count(path):
    if not os.path.exists(path): return 0
    try:
        with open(path, "rb") as f: return sum(1 for _ in f)
    except OSError: return 0

def _set_broadcast(message, btype="info", targets="all"):
    if btype not in ("info","warn","danger","success"): btype = "info"
    with CONFIG_LOCK:
        BROADCAST_COUNTER["n"] += 1
        BROADCAST["id"] = BROADCAST_COUNTER["n"]
        BROADCAST["message"] = (message or "")[:500]
        BROADCAST["type"] = btype
        BROADCAST["targets"] = targets or "all"
        BROADCAST["ts"] = time.time()
        if message:
            BROADCAST_HISTORY.appendleft({"id":BROADCAST["id"],"message":BROADCAST["message"],
                "type":btype,"ts":BROADCAST["ts"]})
    _bump(); return dict(BROADCAST)

_SPOOF_SVG = ("<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'>"
    "<rect width='240' height='240' fill='#f5f5f8'/>"
    "<circle cx='120' cy='100' r='32' fill='none' stroke='#c0c0cc' stroke-width='2'/>"
    "<path d='M90 90 L150 90' stroke='#c0c0cc' stroke-width='2'/>"
    "<text x='120' y='180' text-anchor='middle' fill='#8888a0' font-family='sans-serif' font-size='13'>no image</text></svg>")

def _migrate_report(rep):
    if "messages" in rep: return rep
    rep["messages"] = [{"from": "user", "text": rep.get("message",""), "ts": rep.get("ts", time.time())}]
    if rep.get("admin_reply"):
        rep["messages"].append({"from": "admin", "text": rep["admin_reply"], "ts": rep.get("replied_ts") or time.time()})
    rep["status"] = "replied" if rep.get("admin_reply") else "open"
    rep["unread_user"] = 1 if rep.get("admin_reply") and not rep.get("user_seen") else 0
    rep["unread_admin"] = 0 if rep.get("admin_reply") else 1
    rep["last_ts"] = rep.get("replied_ts") or rep.get("ts") or time.time()
    return rep

for _r in DATA_STORE.get("reports", []):
    _migrate_report(_r)

# ============================================================== Public routes
@app.route("/api/models")
def list_models():
    return jsonify({"models":[{"id":k,"label":v["label"],"tagline":v["tagline"]} for k,v in MODEL_PRESETS.items()],
                    "default":DEFAULT_MODEL_PRESET})

@app.route("/api/ping")
def ping(): return jsonify({"pong":True,"t":time.time()})

@app.route("/api/me")
def api_me():
    uid = session.get("user_id")
    if not uid: return jsonify({"user":None})
    rec = get_user_record(uid); refresh_tier_expiry(rec)
    cfg = get_tier_config(rec["tier"])
    return jsonify({"user":{"id":uid,"name":session.get("user_name"),"email":session.get("user_email"),
        "tier":rec["tier"],"tier_label":cfg["label"]}})

@app.route("/api/health")
def health(): return jsonify({"status":"ok","app":"MiroxAI","https":request.is_secure})

@app.route("/api/client-status")
def client_status():
    ip = _client_ip()
    banned = is_ip_banned(ip); reason = get_ban_reason(ip) if banned else ""
    admin = is_admin(); now = time.time()
    with CONFIG_LOCK:
        maint = bool(MAINTENANCE["enabled"]) and not admin
        upd = bool(UPDATING["enabled"]) and not admin
        upd_msg = UPDATING["message"] if upd else ""
        if EVENT["until"] > now and EVENT["name"] and not admin: ev = {"id":EVENT["id"],"name":EVENT["name"]}
        else: ev = {"id":0,"name":""}
        bcast = dict(BROADCAST)
        ver = STATE_VERSION["v"]
    b_out = {"id":0,"message":"","type":"info","ts":0}
    if bcast.get("message"):
        t = bcast.get("targets","all")
        if t == "all" or (isinstance(t,list) and ip in t):
            b_out = {"id":bcast.get("id",0),"message":bcast.get("message",""),
                     "type":bcast.get("type","info"),"ts":bcast.get("ts",0)}
    r = jsonify({"banned":banned,"reason":reason,"maintenance":maint,"updating":upd,
        "updating_message":upd_msg,"broadcast":b_out,"event":ev,"version":ver})
    r.headers["Cache-Control"] = "no-store, max-age=0"
    return r

@app.route("/api/auth/simple-login", methods=["POST"])
def simple_login():
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    email = (d.get("email") or "").strip().lower()
    if not name or "@" not in email:
        return jsonify({"ok":False,"error":"Name and email are required."}), 400
    uid = "email:" + email
    session["user_id"] = uid; session["user_name"] = name; session["user_email"] = email
    rec = get_user_record(uid)
    if rec.get("banned"):
        return jsonify({"ok":False,"error":f"Your account is banned. Reason: {rec.get('ban_reason','')}"}), 403
    rec["name"] = name; rec["email"] = email
    BG_POOL.submit(save_data); refresh_tier_expiry(rec)
    cfg = get_tier_config(rec["tier"])
    return jsonify({"ok":True,"user":{"id":uid,"name":name,"email":email,
        "tier":rec["tier"],"tier_label":cfg["label"]}})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear(); return jsonify({"ok":True})

@app.route("/api/subscription/plans")
def subscription_plans():
    cfg = get_admin_config()
    plans = []
    for tid,t in SUBSCRIPTION_TIERS.items():
        plans.append({"id":tid,"label":t["label"],"tagline":t["tagline"],
            "price_robux":t["price_robux"],"price_afg":t["price_afg"],
            "gamepass_id":t["gamepass_id"],"perks":t["perks"],
            "keys_per_period":t["keys_per_period"],"refill_days":t["refill_days"],
            "daily_limit":t["daily_limit"],"images_allowed":t["images_allowed"],
            "video_allowed":t["video_allowed"],"video_per_day":t["video_per_day"],
            "models_allowed":t["models_allowed"],"subscription_days":t["subscription_days"]})
    return jsonify({"plans":plans,"admin_email":cfg.get("contact_email",""),
                    "admin_phone":cfg.get("contact_phone","")})

@app.route("/api/subscription/me")
def subscription_me():
    uid = session.get("user_id")
    if not uid: return jsonify({"ok":False,"error":"Not signed in."}), 401
    rec = get_user_record(uid)
    refresh_tier_expiry(rec); _reset_period_if_needed(rec); _reset_daily_if_needed(rec)
    _reset_img5h_if_needed(rec); _reset_vision_day_if_needed(rec); _reset_video_day_if_needed(rec)
    cfg = get_tier_config(rec["tier"])
    lite = _is_lite_mode(rec)
    img_rem = _img_5h_remaining(rec); vis_rem = _vision_remaining(rec); vid_rem = _video_remaining(rec)
    BG_POOL.submit(save_data)
    return jsonify({"ok":True,"tier":rec["tier"],"tier_label":cfg["label"],
        "tier_started":rec.get("tier_started"),"tier_expires":rec.get("tier_expires"),
        "subscription_days":cfg["subscription_days"],
        "daily_limit":cfg["daily_limit"],"daily_used":rec.get("daily_count",0),
        "daily_remaining":_daily_remaining(rec),"lite_mode":lite,
        "daily_reset_seconds":_daily_reset_seconds(rec) if lite else 0,
        "keys_per_period":cfg["keys_per_period"],"keys_generated":rec.get("keys_generated_in_period",0),
        "keys_remaining":_key_remaining(rec),"key_refill_seconds":_key_refill_seconds(rec),
        "refill_days":cfg["refill_days"],"images_allowed":cfg["images_allowed"],
        "img_5h_remaining":img_rem,"img_5h_refill_seconds":_img_5h_refill_seconds(rec) if img_rem >= 0 else 0,
        "vision_remaining":vis_rem,"vision_unlimited":cfg.get("vision_unlimited",False),
        "video_allowed":cfg.get("video_allowed",False),
        "video_remaining":vid_rem,
        "models_allowed":cfg["models_allowed"]})

@app.route("/api/keys", methods=["GET"])
def list_keys():
    uid = session.get("user_id")
    if not uid: return jsonify({"ok":False,"error":"Not signed in."}), 401
    rec = get_user_record(uid)
    safe = []
    for k in rec.get("api_keys",[]):
        safe.append({"id":k["id"],"name":k.get("name"),
            "key":k.get("key","") if not k.get("revoked") else "",
            "key_preview":(k.get("key","")[:16] + "…" + k.get("key","")[-4:]) if k.get("key") else "(revoked)",
            "tier":k.get("tier"),"created":k.get("created"),"revoked":k.get("revoked",False)})
    return jsonify({"ok":True,"keys":safe})

@app.route("/api/keys/generate", methods=["POST"])
def generate_key():
    uid = session.get("user_id")
    if not uid: return jsonify({"ok":False,"error":"Sign in first."}), 401
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "My key").strip()[:60]
    rec = get_user_record(uid)
    refresh_tier_expiry(rec); _reset_period_if_needed(rec)
    if _key_remaining(rec) <= 0:
        wait_sec = _key_refill_seconds(rec)
        days = wait_sec // 86400; hours = (wait_sec % 86400) // 3600
        wait_str = f"{days}d {hours}h" if days else f"{hours}h"
        return jsonify({"ok":False,"error":f"No keys left in this period. Refill in {wait_str}.",
                        "refill_seconds":wait_sec}), 429
    new_key = _new_api_key(rec["tier"])
    entry = {"id":str(uuid.uuid4()),"name":name,"key":new_key,
             "tier":rec["tier"],"created":time.time(),"revoked":False}
    rec.setdefault("api_keys",[]).append(entry)
    rec["keys_generated_in_period"] = rec.get("keys_generated_in_period",0) + 1
    if not rec.get("active_key_id"): rec["active_key_id"] = entry["id"]
    BG_POOL.submit(save_data)
    return jsonify({"ok":True,"key":new_key,"id":entry["id"],"remaining":_key_remaining(rec)})

@app.route("/api/keys/<kid>", methods=["DELETE"])
def revoke_key(kid):
    uid = session.get("user_id")
    if not uid: return jsonify({"ok":False}), 401
    rec = get_user_record(uid)
    for k in rec.get("api_keys",[]):
        if k["id"] == kid: k["revoked"] = True; k["key"] = ""; break
    if rec.get("active_key_id") == kid: rec["active_key_id"] = None
    BG_POOL.submit(save_data); return jsonify({"ok":True})

@app.route("/api/history")
def list_history():
    uid = session.get("user_id")
    if not uid: return jsonify({"conversations":[]})
    rec = get_user_record(uid)
    convos = sorted(({"id":c["id"],"title":c["title"],"updated":c["updated"]}
                     for c in rec["history"]), key=lambda c:c["updated"], reverse=True)
    return jsonify({"conversations":convos})

@app.route("/api/history/search")
def search_history():
    uid = session.get("user_id")
    if not uid: return jsonify({"conversations":[]})
    q = (request.args.get("q") or "").strip().lower()
    rec = get_user_record(uid)
    out = []
    for c in rec["history"]:
        if not q or q in (c.get("title") or "").lower():
            out.append({"id":c["id"],"title":c["title"],"updated":c["updated"]})
        else:
            for m in c.get("messages",[]):
                if q in (m.get("text") or "").lower():
                    out.append({"id":c["id"],"title":c["title"],"updated":c["updated"],"match":(m.get("text") or "")[:120]})
                    break
    out.sort(key=lambda x:x["updated"], reverse=True)
    return jsonify({"conversations":out[:50]})

@app.route("/api/history/<cid>")
def get_conversation(cid):
    uid = session.get("user_id")
    if not uid: return jsonify({"error":"Not found."}), 404
    rec = get_user_record(uid)
    c = next((c for c in rec["history"] if c["id"] == cid), None)
    if not c: return jsonify({"error":"Not found."}), 404
    return jsonify(c)

@app.route("/api/history/<cid>", methods=["DELETE"])
def delete_conversation(cid):
    uid = session.get("user_id")
    if not uid: return jsonify({"error":"Not found."}), 404
    rec = get_user_record(uid)
    rec["history"] = [c for c in rec["history"] if c["id"] != cid]
    BG_POOL.submit(save_data); return jsonify({"ok":True})

@app.route("/api/history/<cid>/rename", methods=["POST"])
def rename_conversation(cid):
    uid = session.get("user_id")
    if not uid: return jsonify({"error":"Not found."}), 404
    rec = get_user_record(uid)
    c = next((c for c in rec["history"] if c["id"] == cid), None)
    if not c: return jsonify({"error":"Not found."}), 404
    d = request.get_json(silent=True) or {}
    title = (d.get("title") or "").strip()[:80]
    if not title: return jsonify({"ok":False,"error":"Empty."}), 400
    c["title"] = title; BG_POOL.submit(save_data); return jsonify({"ok":True})

@app.route("/api/feedback", methods=["POST"])
def feedback(): return jsonify({"ok":True})

# ============================================================== Reports
@app.route("/api/report", methods=["POST"])
def submit_report():
    uid = session.get("user_id") or get_user_id()
    rec = get_user_record(uid)
    d = request.get_json(silent=True) or {}
    subject = (d.get("subject") or "").strip()[:120]
    message = (d.get("message") or "").strip()[:4000]
    category = (d.get("category") or "general").strip()[:40]
    if not message:
        return jsonify({"ok":False,"error":"Please describe your issue."}), 400
    ip = _client_ip()
    now = time.time()
    rep = {"id": str(uuid.uuid4()),"ts": now,"last_ts": now,"ip": ip,"uid": uid,
        "name": rec.get("name"),"email": rec.get("email"),
        "subject": subject or "(no subject)","category": category,"status": "open",
        "messages": [{"from": "user", "text": message, "ts": now}],
        "unread_user": 0,"unread_admin": 1}
    with DATA_LOCK:
        DATA_STORE.setdefault("reports", []).append(rep)
        DATA_STORE["reports"] = DATA_STORE["reports"][-500:]
    BG_POOL.submit(save_data)
    _app_json(REPORT_FILE, rep)
    return jsonify({"ok": True,"ticket_id": rep["id"][:8].upper(),"eta_min": 15,"eta_max": 30,
        "message": "A customer service agent will reply in 15 to 30 minutes. Please keep this window open."})

@app.route("/api/report/mine")
def my_reports():
    uid = session.get("user_id") or get_user_id()
    with DATA_LOCK:
        mine = [r for r in DATA_STORE.get("reports", []) if r.get("uid") == uid]
    mine.sort(key=lambda r: -(r.get("last_ts") or r.get("ts") or 0))
    changed = False
    for r in mine:
        if r.get("unread_user"): r["unread_user"] = 0; changed = True
    if changed: BG_POOL.submit(save_data)
    return jsonify({"ok":True, "reports": mine[:30]})

@app.route("/api/report/<rid>/reply", methods=["POST"])
def user_reply_report(rid):
    uid = session.get("user_id") or get_user_id()
    d = request.get_json(silent=True) or {}
    text = (d.get("text") or "").strip()[:4000]
    if not text: return jsonify({"ok":False,"error":"Empty message."}), 400
    with DATA_LOCK:
        rep = next((r for r in DATA_STORE.get("reports", []) if r.get("id") == rid), None)
        if not rep: return jsonify({"ok":False,"error":"Ticket not found."}), 404
        if rep.get("uid") != uid: return jsonify({"ok":False,"error":"This is not your ticket."}), 403
        now = time.time()
        rep.setdefault("messages", []).append({"from": "user", "text": text, "ts": now})
        rep["last_ts"] = now; rep["status"] = "open"
        rep["unread_admin"] = (rep.get("unread_admin", 0) or 0) + 1
    BG_POOL.submit(save_data)
    return jsonify({"ok":True})

# ============================================================== Settings
@app.route("/api/settings/airoute", methods=["GET","POST"])
def airoute_settings():
    if request.method == "GET": return jsonify({"configured":bool(get_airoute_key()),"is_admin":is_admin()})
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    d = request.get_json(silent=True) or {}
    tok = (d.get("token") or "").strip()
    if not tok: return jsonify({"ok":False,"error":"Key required."}), 400
    get_admin_config()["airoute_key"] = tok; BG_POOL.submit(save_data); _SESSION_TOKENS.clear()
    return jsonify({"ok":True})

@app.route("/api/settings/huggingface", methods=["GET","POST"])
def hf_settings():
    if request.method == "GET": return jsonify({"configured":bool(get_hf_key()),"is_admin":is_admin()})
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    d = request.get_json(silent=True) or {}
    get_admin_config()["hf_key"] = (d.get("token") or "").strip() or None
    BG_POOL.submit(save_data); return jsonify({"ok":True})

@app.route("/api/settings/huggingface/test", methods=["POST"])
def hf_test():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    if not get_hf_key(): return jsonify({"ok":False,"error":"No HF token."})
    try:
        m = HF_POOL_GEN1[0]
        txt = call_hf_chat(m, [{"role":"user","content":"Reply with exactly: ok"}], timeout=15)
        return jsonify({"ok":True,"message":f"gen1: OK · {m}","reply":(txt or "")[:30]})
    except Exception as e: return jsonify({"ok":False,"error":str(e)[:400]})

@app.route("/api/settings/pollinations", methods=["GET","POST"])
def pollinations_settings():
    if request.method == "GET": return jsonify({"configured":bool(get_pollinations_key()),"is_admin":is_admin()})
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    d = request.get_json(silent=True) or {}
    get_admin_config()["pollinations_key"] = (d.get("token") or "").strip() or None
    BG_POOL.submit(save_data); return jsonify({"ok":True})

@app.route("/api/settings/persona", methods=["GET","POST"])
def persona_settings():
    uid = session.get("user_id")
    if not uid: return jsonify({"persona":""})
    rec = get_user_record(uid)
    if request.method == "GET": return jsonify({"persona":rec.get("persona","")})
    d = request.get_json(silent=True) or {}
    rec["persona"] = (d.get("persona") or "").strip()[:MAX_PERSONA_CHARS]
    BG_POOL.submit(save_data); return jsonify({"ok":True})

@app.route("/api/memory", methods=["GET"])
def list_memory():
    uid = session.get("user_id")
    if not uid: return jsonify({"facts":[]})
    return jsonify({"facts":get_user_record(uid).get("memory",[])})

@app.route("/api/memory", methods=["POST"])
def add_memory():
    uid = session.get("user_id")
    if not uid: return jsonify({"ok":False}), 401
    rec = get_user_record(uid)
    d = request.get_json(silent=True) or {}
    fact = (d.get("fact") or "").strip()[:MAX_MEMORY_FACT_CHARS]
    if not fact: return jsonify({"ok":False,"error":"Empty."}), 400
    e = {"id":str(uuid.uuid4()),"text":fact,"added":time.time()}
    rec.setdefault("memory",[]).append(e); rec["memory"] = rec["memory"][-MAX_MEMORY_FACTS:]
    BG_POOL.submit(save_data); return jsonify({"ok":True,"fact":e})

@app.route("/api/memory/<fid>", methods=["DELETE"])
def delete_memory(fid):
    uid = session.get("user_id")
    if not uid: return jsonify({"ok":False}), 401
    rec = get_user_record(uid)
    rec["memory"] = [f for f in rec.get("memory",[]) if f["id"] != fid]
    BG_POOL.submit(save_data); return jsonify({"ok":True})

# ============================================================== Images
@app.route("/api/image/generate", methods=["POST"])
def generate_image():
    uid = session.get("user_id")
    if not uid: return jsonify({"error":"Sign in required."}), 401
    rec = get_user_record(uid)
    refresh_tier_expiry(rec); _reset_img5h_if_needed(rec)
    cfg = get_tier_config(rec["tier"])
    if not cfg["images_allowed"]:
        return jsonify({"error":f"Image generation is not available on the {cfg['label']} plan."}), 403
    if cfg.get("images_per_5h",-1) >= 0 and _img_5h_remaining(rec) <= 0:
        rem = _img_5h_refill_seconds(rec)
        h = rem // 3600; m = (rem % 3600) // 60
        return jsonify({"error":f"Free plan: 5 images per 5 hours. Refill in {h}h {m}m.",
                        "refill_seconds":rem}), 429
    ip = _client_ip()
    d = request.get_json(silent=True) or {}
    prompt = (d.get("prompt") or "").strip()
    style = (d.get("style") or "").strip()
    ratio = (d.get("ratio") or "1:1").strip()
    if not prompt: return jsonify({"error":"Please describe what you want first."}), 400
    full = prompt
    if style in STYLE_SUFFIXES: full += f", {STYLE_SUFFIXES[style]}"
    if ratio in RATIO_HINTS: full += f", {RATIO_HINTS[ratio]}"
    started = time.time()
    key = get_airoute_key()
    if key:
        try:
            r = call_airoute_image(AIROUTE_IMAGE_MODEL, key, full)
            img = r.get("image")
            if img:
                ms = r.get("ms") or int((time.time()-started)*1000)
                fn = _save_image(img)
                rec["img_gen_5h_count"] = rec.get("img_gen_5h_count",0) + 1
                BG_POOL.submit(save_data)
                log_image_event(ip, uid, prompt, style, ratio, True, ms, None, fn)
                return jsonify({"image":img,"prompt":full,"ms":ms,"remaining":_img_5h_remaining(rec)})
        except Exception: pass
    try:
        w,h = RATIO_SIZES.get(ratio, RATIO_SIZES["1:1"])
        img = call_pollinations_image(full, w, h)
        ms = int((time.time()-started)*1000)
        fn = _save_image(img)
        rec["img_gen_5h_count"] = rec.get("img_gen_5h_count",0) + 1
        BG_POOL.submit(save_data)
        log_image_event(ip, uid, prompt, style, ratio, True, ms, None, fn)
        return jsonify({"image":img,"prompt":full,"remaining":_img_5h_remaining(rec)})
    except Exception as e:
        ms = int((time.time()-started)*1000)
        log_image_event(ip, uid, prompt, style, ratio, False, ms, str(e), None)
        _record_error("image", e)
        return jsonify({"error":f"Image generation failed: {e}"}), 400

@app.route("/api/admin/images/<filename>")
def admin_image_file(filename):
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    if not filename or not re.match(r"^[A-Za-z0-9_.-]+$", filename) or ".." in filename:
        return jsonify({"ok":False,"error":"Invalid filename."}), 400
    full = os.path.join(IMAGES_DIR, filename)
    if not os.path.isfile(full):
        return Response(_SPOOF_SVG.encode(), mimetype="image/svg+xml")
    return send_from_directory(IMAGES_DIR, filename)

# ============================================================== Video generation
_VIDEO_ATTEMPT_SUFFIXES = [
    "", ", high quality", ", detailed, sharp focus",
    ", cinematic lighting", ", ultra detailed render",
]

def _gen_frame_once(prompt, w, h, attempt=0):
    suffix = _VIDEO_ATTEMPT_SUFFIXES[attempt % len(_VIDEO_ATTEMPT_SUFFIXES)]
    p = prompt + suffix
    try:
        uri = call_pollinations_image(p, w, h)
        if uri and isinstance(uri, str) and uri.startswith("data:image"):
            return uri
    except Exception as e:
        _record_error("video-frame", e)
    return None

def _gen_frame(prompt, w, h, retries=VIDEO_RETRY_MAX):
    for attempt in range(retries):
        uri = _gen_frame_once(prompt, w, h, attempt)
        if uri: return uri
        time.sleep(0.4 + attempt * 0.5 + random.random() * 0.3)
    return None

@app.route("/api/video/generate", methods=["POST"])
def generate_video():
    uid = session.get("user_id")
    if not uid: return jsonify({"error": "Sign in required."}), 401
    rec = get_user_record(uid)
    refresh_tier_expiry(rec); _reset_video_day_if_needed(rec)
    cfg = get_tier_config(rec["tier"])
    if not cfg.get("video_allowed"):
        return jsonify({"error": f"Video generation requires Pro or Ultimate. Your plan: {cfg['label']}."}), 403
    rem = _video_remaining(rec)
    if rem == 0:
        return jsonify({"error": "Daily video limit reached. Try again tomorrow or upgrade to Ultimate."}), 429

    d = request.get_json(silent=True) or {}
    prompt = (d.get("prompt") or "").strip()
    style = (d.get("style") or "").strip()
    if not prompt:
        return jsonify({"error": "Please describe the video first."}), 400

    base_prompt = prompt
    if style in STYLE_SUFFIXES:
        base_prompt += f", {STYLE_SUFFIXES[style]}"

    n = VIDEO_FRAME_COUNT
    sz = VIDEO_SIZE

    motion_phrases = [
        "wide establishing shot","slight zoom in","camera pans left slowly",
        "camera pans right slowly","medium shot, subject centered","close-up detail",
        "camera pulls back","slight upward tilt","slight downward tilt",
        "subject turns slightly left","subject turns slightly right","camera orbits to the left",
        "camera orbits to the right","medium-wide shot, deeper focus","medium shot, soft focus",
        "closer medium shot","close-up on subject","wide shot again",
        "camera slowly zooms out","final wide shot",
    ]
    prompts = [
        f"{base_prompt}, {motion_phrases[i % len(motion_phrases)]}, "
        f"frame {i+1} of {n}, cinematic, smooth continuous motion, consistent character, same subject"
        for i in range(n)
    ]

    started = time.time()
    frames = [None] * n

    try:
        with ThreadPoolExecutor(max_workers=VIDEO_CONCURRENCY) as vp:
            futures = {vp.submit(_gen_frame, p, sz, sz, VIDEO_RETRY_MAX): i for i, p in enumerate(prompts)}
            for fut in concurrent.futures.as_completed(futures):
                i = futures[fut]
                try: frames[i] = fut.result()
                except Exception: frames[i] = None
    except Exception as e:
        _record_error("video-batch", e)

    for i, f in enumerate(frames):
        if not f:
            frames[i] = _gen_frame(prompts[i], sz, sz, VIDEO_RETRY_MAX)

    still_missing = [i for i, f in enumerate(frames) if not f]
    if still_missing:
        _record_error("video", f"retrying {len(still_missing)} missing frames")
        for i in still_missing:
            frames[i] = _gen_frame(prompts[i], sz, sz, VIDEO_RETRY_MAX + 2)

    ordered = [f for f in frames if isinstance(f, str) and f.startswith("data:image")]
    if len(ordered) < 6:
        return jsonify({"error": f"Video generation failed — only {len(ordered)}/{n} frames succeeded. Please try again."}), 500

    filled = []
    last_good = None
    for f in frames:
        if isinstance(f, str) and f.startswith("data:image"):
            filled.append(f); last_good = f
        elif last_good is not None:
            filled.append(last_good)
    if not filled:
        return jsonify({"error": "Video generation failed — no valid frames."}), 500

    ms = int((time.time() - started) * 1000)
    log_image_event(_client_ip(), uid, f"[VIDEO] {prompt}", style, "video", True, ms, None, None)
    rec["video_count"] = rec.get("video_count", 0) + 1
    BG_POOL.submit(save_data)

    return jsonify({
        "ok": True,
        "frames": filled,
        "fps": VIDEO_FPS,
        "duration": 5,
        "count": len(filled),
        "size": sz,
        "ms": ms,
        "sound_note": "Sound will come soon",
        "remaining": _video_remaining(rec),
    })

# ============================================================== Project download
@app.route("/api/project/download", methods=["POST"])
def project_download():
    d = request.get_json(silent=True) or {}
    files = d.get("files") or []
    if not isinstance(files, list) or not files: return jsonify({"error":"No files."}), 400
    skipped = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as z:
        for f in files:
            path = (f.get("path") or "file.txt").strip()
            path = re.sub(r'[<>:"|?*\x00-\x1f]', "_", path).replace("..","_").lstrip("/\\")
            if not path: path = "file.txt"
            content = f.get("content") or ""
            if _looks_truncated(content): skipped.append(path)
            try: z.writestr(path, content)
            except Exception: pass
        if skipped:
            note = ("The following files look incomplete:\n\n" + "\n".join(f"- {p}" for p in skipped))
            z.writestr("_INCOMPLETE_FILES.txt", note)
    buf.seek(0)
    return Response(buf.read(), mimetype="application/zip",
        headers={"Content-Disposition":'attachment; filename="miroxai-project.zip"'})

# ============================================================== Chat
@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    uid = session.get("user_id")
    if not uid: return jsonify({"error":"Sign in first."}), 401
    rec = get_user_record(uid)
    if rec.get("banned"): return jsonify({"error":"Your account is banned."}), 403
    refresh_tier_expiry(rec); _reset_daily_if_needed(rec); _reset_period_if_needed(rec); _reset_vision_day_if_needed(rec)
    lite = _is_lite_mode(rec); cfg = get_tier_config(rec["tier"])
    ip = _client_ip()
    d = request.get_json(silent=True) or {}
    user_message = (d.get("message") or "").strip()
    conv_id = d.get("conversation_id")
    model_id = d.get("model") or DEFAULT_MODEL_PRESET
    if model_id not in MODEL_PRESETS: model_id = DEFAULT_MODEL_PRESET
    if not lite and model_id not in cfg["models_allowed"]: model_id = cfg["models_allowed"][0]
    if lite: model_id = "mirox-gen1"
    file_name = (d.get("file_name") or "").strip() or None
    file_content = (d.get("file_content") or "")[:MAX_ATTACHMENT_CHARS] or None
    image_data_url = (d.get("image_data_url") or "").strip() or None
    web = bool(d.get("web_search"))
    using_vision = bool(image_data_url)
    if using_vision:
        if len(image_data_url) > MAX_VISION_BYTES * 2:
            return jsonify({"error":"Image too large. Please upload a smaller one."}), 400
        if _vision_remaining(rec) == 0:
            return jsonify({"error":"Daily vision limit reached. Upgrade for unlimited."}), 429
    if not user_message and not using_vision: return jsonify({"error":"No message."}), 400
    if using_vision and not user_message: user_message = "Describe this image in detail."
    convo = next((c for c in rec["history"] if c["id"] == conv_id), None)
    prior = convo["messages"] if convo else []
    preset = dict(MODEL_PRESETS.get(model_id, MODEL_PRESETS[DEFAULT_MODEL_PRESET]))
    preset["_id"] = model_id
    snippets = web_search_snippets(user_message) if web else []
    training = get_training_data()
    messages = build_messages(user_message, preset, rec.get("persona",""), rec.get("memory",[]),
        file_name, file_content, snippets, prior, training, image_data_url=image_data_url)
    started = time.time()

    def generate():
        full_text = ""; err = None; first_tok_ms = None; provider_used = None
        ens_size = 0; ens_ok = 0
        def emit(obj): return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"
        if using_vision:
            try:
                text = call_vision(messages)
                full_text = text or ""
                first_tok_ms = int((time.time()-started)*1000)
                provider_used = "vision"
                for i in range(0, len(full_text), 64):
                    yield emit({"delta": full_text[i:i+64]})
            except Exception as e:
                err = e
                yield emit({"error": f"Vision failed: {e}"})
        else:
            state = {"provider": None}; got_any = False
            try:
                for delta in _race_stream(messages, preset, lite, state):
                    if first_tok_ms is None: first_tok_ms = int((time.time()-started)*1000)
                    full_text += delta; got_any = True
                    provider_used = state.get("provider") or provider_used
                    yield emit({"delta": delta})
            except Exception as e:
                err = e
            if not got_any and hf_available() and not lite:
                try:
                    pool = get_hf_models_for(model_id)[:ENSEMBLE_SIZES.get(model_id,4)]
                    ens_size = len(pool)
                    q = _q.Queue(); stop_flag = threading.Event()
                    def _worker(m, i):
                        try:
                            for delta in stream_hf_single(m, messages):
                                if stop_flag.is_set(): return
                                q.put(("delta", i, m, delta))
                            q.put(("done", i, m, None))
                        except Exception as e: q.put(("err", i, m, str(e)))
                    threads = [threading.Thread(target=_worker, args=(m,i), daemon=True) for i,m in enumerate(pool)]
                    for t in threads: t.start()
                    winner = None
                    first_deadline = time.time() + FIRST_TOKEN_DEADLINE
                    while time.time() < first_deadline:
                        try: kind, idx, m, payload = q.get(timeout=0.4)
                        except _q.Empty: continue
                        if kind == "delta":
                            winner = m; provider_used = "ensemble"
                            if first_tok_ms is None: first_tok_ms = int((time.time()-started)*1000)
                            full_text += payload; got_any = True; ens_ok = 1
                            yield emit({"delta": payload}); break
                    if winner:
                        while True:
                            try: kind, idx, m, payload = q.get(timeout=120)
                            except _q.Empty: break
                            if kind == "delta" and m == winner:
                                full_text += payload; yield emit({"delta": payload})
                            elif kind in ("done","err") and m == winner: break
                    stop_flag.set()
                except Exception as e2:
                    if not err: err = e2
        if err and not full_text and not using_vision:
            yield emit({"error": f"{preset['label']}: {err}"})
        mw = extract_memory_writes(full_text)
        display = MEMORY_PATTERN.sub("", full_text).strip() or full_text
        for fact in mw:
            rec.setdefault("memory",[]).append({"id":str(uuid.uuid4()),"text":fact,"added":time.time()})
        if mw:
            rec["memory"] = rec["memory"][-MAX_MEMORY_FACTS:]
            BG_POOL.submit(save_data)
        target_conv = convo
        if target_conv is None:
            cid = str(uuid.uuid4())
            title = user_message[:48] + ("…" if len(user_message) > 48 else "")
            target_conv = {"id":cid,"title":title,"updated":time.time(),"messages":[]}
            rec["history"].append(target_conv)
        stored_user = user_message
        if using_vision: stored_user = f"[image] {user_message}"
        target_conv["messages"].append({"role":"user","text":stored_user})
        target_conv["messages"].append({"role":"ai","text":display})
        target_conv["updated"] = time.time()
        if not lite: rec["daily_count"] = rec.get("daily_count",0) + 1
        if using_vision and not cfg.get("vision_unlimited"):
            rec["vision_count"] = rec.get("vision_count",0) + 1
        BG_POOL.submit(save_data)
        total_ms = int((time.time()-started)*1000)
        log_chat_event(ip, uid, preset["label"], total_ms, user_message, display, target_conv["id"], vision=using_vision)
        yield emit({"meta":{"conversation_id":target_conv["id"],"model":preset["label"],
            "ms":total_ms,"first_token_ms":first_tok_ms,"provider":provider_used,
            "ensemble_size":ens_size,"ensemble_ok":ens_ok,"searched":bool(snippets),
            "sources":snippets,"memory_writes":mw,"daily_remaining":_daily_remaining(rec),
            "lite_mode":lite,"daily_reset_seconds":_daily_reset_seconds(rec) if lite else 0,
            "vision":using_vision,"vision_remaining":_vision_remaining(rec)}})
    return Response(generate(), mimetype="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","Connection":"keep-alive"})

@app.route("/api/chat", methods=["POST"])
def chat():
    uid = session.get("user_id")
    if not uid: return jsonify({"error":"Sign in first."}), 401
    rec = get_user_record(uid)
    if rec.get("banned"): return jsonify({"error":"Your account is banned."}), 403
    refresh_tier_expiry(rec); _reset_daily_if_needed(rec); _reset_period_if_needed(rec)
    lite = _is_lite_mode(rec); cfg = get_tier_config(rec["tier"])
    ip = _client_ip()
    d = request.get_json(silent=True) or {}
    user_message = (d.get("message") or "").strip()
    conv_id = d.get("conversation_id")
    model_id = d.get("model") or DEFAULT_MODEL_PRESET
    if model_id not in MODEL_PRESETS: model_id = DEFAULT_MODEL_PRESET
    if not lite and model_id not in cfg["models_allowed"]: model_id = cfg["models_allowed"][0]
    if lite: model_id = "mirox-gen1"
    file_name = (d.get("file_name") or "").strip() or None
    file_content = (d.get("file_content") or "")[:MAX_ATTACHMENT_CHARS] or None
    image_data_url = (d.get("image_data_url") or "").strip() or None
    web = bool(d.get("web_search"))
    using_vision = bool(image_data_url)
    if not user_message and not using_vision: return jsonify({"error":"No message."}), 400
    if using_vision and _vision_remaining(rec) == 0:
        return jsonify({"error":"Daily vision limit reached."}), 429
    if using_vision and not user_message: user_message = "Describe this image in detail."
    convo = next((c for c in rec["history"] if c["id"] == conv_id), None)
    prior = convo["messages"] if convo else []
    preset = dict(MODEL_PRESETS.get(model_id, MODEL_PRESETS[DEFAULT_MODEL_PRESET]))
    preset["_id"] = model_id
    snippets = web_search_snippets(user_message) if web else []
    training = get_training_data()
    messages = build_messages(user_message, preset, rec.get("persona",""), rec.get("memory",[]),
        file_name, file_content, snippets, prior, training, image_data_url=image_data_url)
    started = time.time()
    text = ""; provider = None
    try:
        if using_vision:
            text = call_vision(messages); provider = "vision"
        else:
            if not lite and get_airoute_key():
                try:
                    r = call_airoute_chat(preset["airoute_model"], get_airoute_key(), flatten_messages(messages))
                    text = r.get("text") or str(r); provider = "airoute"
                except Exception: pass
            if not text:
                headers = {"Content-Type":"application/json"}
                tok = get_pollinations_key()
                if tok: headers["Authorization"] = f"Bearer {tok}"
                try:
                    r = requests.post(POLLINATIONS_URL, headers=headers,
                        json={"model":POLLINATIONS_MODEL,"messages":messages,"max_tokens":HF_MAX_TOKENS},
                        timeout=CHAT_TIMEOUT)
                    r.raise_for_status()
                    data = r.json(); ch = _choice0(data)
                    text = (ch.get("message") or {}).get("content") or ""
                    provider = "pollinations"
                except Exception: pass
            if not text and hf_available() and not lite:
                try: text, _ens = call_hf_ensemble(model_id, messages); provider = "ensemble"
                except Exception: pass
    except Exception as e:
        return jsonify({"error":str(e)}), 500
    if not text: return jsonify({"error":"All providers failed."}), 500
    mw = extract_memory_writes(text)
    display = MEMORY_PATTERN.sub("", text).strip() or text
    for fact in mw:
        rec.setdefault("memory",[]).append({"id":str(uuid.uuid4()),"text":fact,"added":time.time()})
    if mw: rec["memory"] = rec["memory"][-MAX_MEMORY_FACTS:]
    if convo is None:
        conv_id = str(uuid.uuid4())
        title = user_message[:48] + ("…" if len(user_message) > 48 else "")
        convo = {"id":conv_id,"title":title,"updated":time.time(),"messages":[]}
        rec["history"].append(convo)
    convo["messages"].append({"role":"user","text":("[image] " if using_vision else "") + user_message})
    convo["messages"].append({"role":"ai","text":display})
    convo["updated"] = time.time()
    if not lite: rec["daily_count"] = rec.get("daily_count",0) + 1
    if using_vision and not cfg.get("vision_unlimited"):
        rec["vision_count"] = rec.get("vision_count",0) + 1
    BG_POOL.submit(save_data)
    total_ms = int((time.time()-started)*1000)
    log_chat_event(ip, uid, preset["label"], total_ms, user_message, display, conv_id, vision=using_vision)
    files = parse_project_files(text)
    return jsonify({"reply":display,"model":preset["label"],"ms":total_ms,
        "conversation_id":conv_id,"memory_writes":mw,"searched":bool(snippets),
        "provider":provider,"project_files":files,"daily_remaining":_daily_remaining(rec),
        "lite_mode":lite,"vision":using_vision,"vision_remaining":_vision_remaining(rec)})

# ============================================================== Admin API
@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    d = request.get_json(silent=True) or {}
    if (d.get("password") or "").strip() != ADMIN_PASSWORD:
        return jsonify({"ok":False,"error":"Wrong password."}), 401
    session["is_admin"] = True
    tok = uuid.uuid4().hex; session["admin_token"] = tok
    with ADMIN_SESS_LOCK:
        ADMIN_SESSIONS[tok] = {"token":tok,"ip":_client_ip(),"login_ts":time.time(),"last_seen":time.time()}
    return jsonify({"ok":True})

@app.route("/api/admin/status")
def admin_status():
    return jsonify({"ok":True,"is_admin":is_admin(),"banned":is_ip_banned(_client_ip())})

@app.route("/api/admin/quick")
def admin_quick():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    return jsonify({"ok":True,"current_ip":_client_ip()})

@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    tok = session.get("admin_token")
    if tok:
        with ADMIN_SESS_LOCK: ADMIN_SESSIONS.pop(tok, None)
    session.pop("admin_token", None); session.pop("is_admin", None)
    return jsonify({"ok":True})

@app.route("/api/admin/contact", methods=["GET","POST"])
def admin_contact():
    cfg = get_admin_config()
    if request.method == "GET":
        return jsonify({"ok":True,"email":cfg.get("contact_email",""),"phone":cfg.get("contact_phone","")})
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    d = request.get_json(silent=True) or {}
    cfg["contact_email"] = (d.get("email") or "").strip()[:120]
    cfg["contact_phone"] = (d.get("phone") or "").strip()[:60]
    BG_POOL.submit(save_data)
    return jsonify({"ok":True,"email":cfg["contact_email"],"phone":cfg["contact_phone"]})

@app.route("/api/admin/set-tier", methods=["POST"])
def admin_set_tier():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    d = request.get_json(silent=True) or {}
    email = (d.get("email") or "").strip().lower()
    tier = (d.get("tier") or "free").strip().lower()
    if tier not in SUBSCRIPTION_TIERS:
        return jsonify({"ok":False,"error":"Unknown tier."}), 400
    if "@" not in email: return jsonify({"ok":False,"error":"Email required."}), 400
    uid = "email:" + email
    rec = get_user_record(uid); cfg = get_tier_config(tier)
    rec["tier"] = tier
    rec["tier_started"] = time.time()
    rec["tier_expires"] = time.time() + cfg["subscription_days"]*86400
    rec["key_period_start"] = time.time()
    rec["keys_generated_in_period"] = 0
    rec["daily_count"] = 0; rec["daily_date"] = ""
    rec["img_gen_5h_count"] = 0; rec["img_gen_5h_start"] = time.time()
    rec["vision_count"] = 0; rec["vision_day"] = ""
    rec["video_count"] = 0; rec["video_day"] = ""
    BG_POOL.submit(save_data)
    return jsonify({"ok":True,"email":email,"tier":tier,"tier_label":cfg["label"],
                    "expires":rec["tier_expires"]})

@app.route("/api/admin/stats")
def admin_stats():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    now = time.time()
    with BAN_LOCK: bc = len(BANNED_IPS)
    online = _online_ips()
    with ROUTE_LOCK: tr = ROUTE_HITS.most_common(10)
    with CONFIG_LOCK:
        maint = bool(MAINTENANCE["enabled"]); updating = bool(UPDATING["enabled"])
        ver = STATE_VERSION["v"]
    with DATA_LOCK:
        total_users = len(DATA_STORE.get("users",{}))
        named_users = sum(1 for u in DATA_STORE.get("users",{}).values() if u.get("name"))
        total_convs = sum(len(u.get("history",[])) for u in DATA_STORE.get("users",{}).values())
        total_msgs = sum(sum(len(c.get("messages",[])) for c in u.get("history",[]))
                        for u in DATA_STORE.get("users",{}).values())
        tier_counts = Counter((u.get("tier") or "free") for u in DATA_STORE.get("users",{}).values())
        banned_users = sum(1 for u in DATA_STORE.get("users",{}).values() if u.get("banned"))
        reports_all = list(DATA_STORE.get("reports", []))
    open_reports = sum(1 for r in reports_all if r.get("status") == "open")
    unread_reports = sum(1 for r in reports_all if r.get("unread_admin", 0) > 0)
    return jsonify({"ok":True,"total_requests":sum(ROUTE_HITS.values()),
        "unique_ips":len(LAST_SEEN),"banned_count":bc,
        "chats_count":_count(CHAT_LOG_FILE),"images_count":_count(IMAGE_LOG_FILE),
        "online_count":len(online),"online_ips":online[:30],
        "uptime_seconds":int(now-START_TIME),"response_stats":_response_stats(),
        "maintenance":maint,"updating":updating,
        "users_total":total_users,"users_named":named_users,
        "conversations_total":total_convs,"messages_total":total_msgs,
        "tier_counts":dict(tier_counts),"banned_users":banned_users,
        "open_reports":open_reports,"unread_reports":unread_reports,
        "total_reports":len(reports_all),
        "system":{"python":platform.python_version(),"platform":platform.platform()[:80],
                   "threads":threading.active_count()}})

@app.route("/api/admin/users")
def admin_users():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    with DATA_LOCK:
        users = []
        for uid, rec in DATA_STORE.get("users",{}).items():
            users.append({"id":uid,"name":rec.get("name"),"email":rec.get("email"),
                "tier":rec.get("tier","free"),"tier_expires":rec.get("tier_expires"),
                "convs":len(rec.get("history",[])),"keys":len(rec.get("api_keys",[])),
                "warnings":len(rec.get("warnings",[])),"banned":bool(rec.get("banned")),
                "ban_reason":rec.get("ban_reason",""),
                "last_seen":rec.get("last_seen")})
    users.sort(key=lambda x:-(x.get("last_seen") or 0))
    return jsonify({"ok":True,"users":users[:200]})

@app.route("/api/admin/warn-user", methods=["POST"])
def admin_warn_user():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    d = request.get_json(silent=True) or {}
    uid = (d.get("uid") or "").strip()
    reason = (d.get("reason") or "").strip()[:300]
    if not uid: return jsonify({"ok":False,"error":"User ID required."}), 400
    rec = DATA_STORE["users"].get(uid)
    if not rec: return jsonify({"ok":False,"error":"User not found."}), 404
    rec.setdefault("warnings",[]).append({"ts":time.time(),"reason":reason or "(no reason)"})
    rec["warnings"] = rec["warnings"][-20:]
    BG_POOL.submit(save_data)
    return jsonify({"ok":True,"warnings":len(rec["warnings"])})

@app.route("/api/admin/ban-user", methods=["POST"])
def admin_ban_user():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    d = request.get_json(silent=True) or {}
    uid = (d.get("uid") or "").strip()
    reason = (d.get("reason") or "").strip()[:300]
    if not uid: return jsonify({"ok":False,"error":"User ID required."}), 400
    rec = DATA_STORE["users"].get(uid)
    if not rec: return jsonify({"ok":False,"error":"User not found."}), 404
    rec["banned"] = True; rec["ban_reason"] = reason or "(no reason)"
    for k in rec.get("api_keys",[]): k["revoked"] = True; k["key"] = ""
    BG_POOL.submit(save_data)
    return jsonify({"ok":True})

@app.route("/api/admin/unban-user", methods=["POST"])
def admin_unban_user():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    d = request.get_json(silent=True) or {}
    uid = (d.get("uid") or "").strip()
    if not uid: return jsonify({"ok":False,"error":"User ID required."}), 400
    rec = DATA_STORE["users"].get(uid)
    if not rec: return jsonify({"ok":False,"error":"User not found."}), 404
    rec["banned"] = False; rec["ban_reason"] = ""
    BG_POOL.submit(save_data)
    return jsonify({"ok":True})

@app.route("/api/admin/clear-warnings", methods=["POST"])
def admin_clear_warnings():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    d = request.get_json(silent=True) or {}
    uid = (d.get("uid") or "").strip()
    if not uid: return jsonify({"ok":False,"error":"User ID required."}), 400
    rec = DATA_STORE["users"].get(uid)
    if not rec: return jsonify({"ok":False,"error":"User not found."}), 404
    rec["warnings"] = []
    BG_POOL.submit(save_data)
    return jsonify({"ok":True})

@app.route("/api/admin/reports")
def admin_reports():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    with DATA_LOCK:
        items = [dict(r) for r in DATA_STORE.get("reports", [])]
        for r in items: _migrate_report(r)
        for r in DATA_STORE.get("reports", []):
            if r.get("unread_admin"): r["unread_admin"] = 0
    items.sort(key=lambda r: -(r.get("last_ts") or r.get("ts") or 0))
    BG_POOL.submit(save_data)
    return jsonify({"ok":True,"reports":items[:200]})

@app.route("/api/admin/report-reply", methods=["POST"])
def admin_report_reply():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    d = request.get_json(silent=True) or {}
    rid = (d.get("id") or "").strip()
    reply = (d.get("reply") or "").strip()[:4000]
    if not rid or not reply: return jsonify({"ok":False,"error":"id and reply are required."}), 400
    with DATA_LOCK:
        rep = next((r for r in DATA_STORE.get("reports", []) if r.get("id") == rid), None)
        if not rep: return jsonify({"ok":False,"error":"Report not found."}), 404
        _migrate_report(rep)
        now = time.time()
        rep["messages"].append({"from":"admin","text":reply,"ts":now})
        rep["last_ts"] = now; rep["status"] = "replied"
        rep["unread_user"] = (rep.get("unread_user",0) or 0) + 1
    BG_POOL.submit(save_data)
    return jsonify({"ok":True})

@app.route("/api/admin/bans")
def admin_bans():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    with BAN_LOCK:
        bans = [{"ip":ip,"reason":info.get("reason") or "","ts":info.get("ts") or 0.0}
                for ip,info in sorted(BANNED_IPS.items())]
    return jsonify({"ok":True,"bans":bans})

@app.route("/api/admin/ban", methods=["POST"])
def admin_ban():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    d = request.get_json(silent=True) or {}
    ip = (d.get("ip") or "").strip(); reason = (d.get("reason") or "").strip()
    if not ip: return jsonify({"ok":False,"error":"IP required."}), 400
    ban_ip(ip, reason); return jsonify({"ok":True,"ip":ip})

@app.route("/api/admin/unban", methods=["POST"])
def admin_unban():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    d = request.get_json(silent=True) or {}
    ip = (d.get("ip") or "").strip()
    if not ip: return jsonify({"ok":False,"error":"IP required."}), 400
    unban_ip(ip); return jsonify({"ok":True,"ip":ip})

@app.route("/api/admin/unban-all", methods=["POST"])
def admin_unban_all():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    with BAN_LOCK: items = list(BANNED_IPS.keys())
    for ip in items: unban_ip(ip)
    return jsonify({"ok":True,"unbanned":len(items)})

@app.route("/api/admin/logs/<t>")
def admin_logs(t):
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    mapping = {"chat":CHAT_LOG_FILE,"image":IMAGE_LOG_FILE,"report":REPORT_FILE}
    path = mapping.get(t)
    if not path: return jsonify({"ok":False,"error":"Unknown log."}), 404
    entries = _read_jsonl(path, 200)
    return jsonify({"ok":True,"kind":"jsonl","entries":entries,"count":len(entries)})

@app.route("/api/admin/logs/<t>/clear", methods=["POST"])
def admin_clear_log(t):
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    mapping = {"chat":CHAT_LOG_FILE,"image":IMAGE_LOG_FILE,"report":REPORT_FILE}
    if t not in mapping: return jsonify({"ok":False,"error":"Unknown log."}), 404
    try:
        open(mapping[t],"w").close()
        return jsonify({"ok":True})
    except OSError as ex: return jsonify({"ok":False,"error":str(ex)}), 500

@app.route("/api/admin/maintenance", methods=["GET","POST"])
def admin_maintenance():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    if request.method == "GET":
        with CONFIG_LOCK: return jsonify({"ok":True,"enabled":MAINTENANCE["enabled"],"message":MAINTENANCE["message"]})
    d = request.get_json(silent=True) or {}
    with CONFIG_LOCK:
        if "enabled" in d: MAINTENANCE["enabled"] = bool(d["enabled"])
        if "message" in d: MAINTENANCE["message"] = (d.get("message") or "").strip()[:500] or "MiroxAI is under maintenance."
    _bump(); return jsonify({"ok":True,"enabled":MAINTENANCE["enabled"],"message":MAINTENANCE["message"]})

@app.route("/api/admin/broadcast", methods=["GET","POST"])
def admin_broadcast():
    if not is_admin(): return jsonify({"ok":False,"error":"Admin only."}), 403
    if request.method == "GET":
        with CONFIG_LOCK:
            hist = list(BROADCAST_HISTORY)
            return jsonify({"ok":True,**BROADCAST,"history":hist})
    d = request.get_json(silent=True) or {}
    msg = (d.get("message") or "").strip()
    btype = (d.get("type") or "info").strip()
    result = _set_broadcast(msg, btype, "all")
    return jsonify({"ok":True,**result})

# ============================================================== Admin console
_ADMIN_HTML = r"""<!doctype html><html lang="en" data-mode="light"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MiroxAI Admin</title>
<link href="https://cdn.jsdelivr.net/npm/remixicon@4.2.0/fonts/remixicon.css" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#fafafb;--panel:#fff;--panel-2:#f5f5f8;--border:#e8e8ef;--text:#0a0a0c;--muted:#6b6b78;--accent:#c4694b;--accent-2:#8b5cf6;--ok:#16a34a;--danger:#dc2626;--warn:#d97706}
:root[data-mode=dark]{--bg:#0a0a0d;--panel:#15151b;--panel-2:#1d1d24;--border:#26262f;--text:#f4f4f8;--muted:#a0a0ab}
body{font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;line-height:1.5}
.header{position:sticky;top:0;z-index:10;background:var(--bg);border-bottom:1px solid var(--border);padding:14px 22px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.header h1{font-size:16px;font-weight:800}.header .spacer{flex:1}
.tabs{display:flex;gap:4px;padding:14px 22px 0;overflow-x:auto;border-bottom:1px solid var(--border)}
.tab{padding:10px 16px;border:none;background:transparent;color:var(--muted);font:inherit;font-weight:600;font-size:13.5px;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;white-space:nowrap;position:relative}
.tab.active{color:var(--accent);border-bottom-color:var(--accent)}
.tab .badge{display:inline-block;margin-left:6px;background:var(--danger);color:#fff;font-size:10px;font-weight:800;padding:1px 6px;border-radius:10px}
.wrap{padding:22px;max-width:1300px;margin:0 auto}.pane{display:none}.pane.active{display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.stat{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:16px 18px;position:relative;overflow:hidden}
.stat::before{content:"";position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--accent),var(--accent-2))}
.stat .l{color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;font-weight:800}
.stat .v{font-size:24px;font-weight:800;font-family:monospace;margin-top:4px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:18px 20px;margin-bottom:16px}
.card h2{font-size:14.5px;font-weight:800;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.card h2 i{color:var(--accent)}
input,button,textarea,select{font:inherit}
input,textarea,select{width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:10px;padding:10px 13px;outline:none}
button{background:linear-gradient(135deg,var(--accent),#a8503a);color:#fff;border:none;padding:9px 16px;border-radius:10px;font-weight:700;cursor:pointer}
button.ghost{background:transparent;border:1px solid var(--border);color:var(--text)}
button.danger{background:var(--danger)}button.warn{background:var(--warn)}button.ok{background:var(--ok)}
button.sm{padding:6px 12px;font-size:12.5px;border-radius:8px}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center}
.row input{flex:1;min-width:140px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:9px 11px;border-bottom:1px solid var(--border);vertical-align:top}
th{color:var(--muted);font-size:10.5px;text-transform:uppercase;background:var(--panel-2);font-weight:800}
td.mono{font-family:monospace;font-size:12px}
td.actions{text-align:right;white-space:nowrap}
td.actions button{margin-left:4px}
.pill{display:inline-block;padding:3px 10px;border-radius:20px;background:var(--panel-2);border:1px solid var(--border);font-size:11px;color:var(--muted);font-weight:600}
.pill.ok{color:var(--ok);border-color:var(--ok)}.pill.danger{color:var(--danger);border-color:var(--danger)}
.pill.warn{color:var(--warn);border-color:var(--warn)}.pill.pro{color:#1d4ed8;border-color:#1d4ed8}.pill.ultimate{color:#7c3aed;border-color:#7c3aed}
#login{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;background:var(--bg);z-index:100;padding:20px}
.login-card{background:var(--panel);border:1px solid var(--border);border-radius:22px;padding:32px;width:100%;max-width:380px;box-shadow:0 20px 60px rgba(0,0,0,.1)}
.login-card h1{margin-bottom:6px}.login-card p{color:var(--muted);font-size:13px;margin-bottom:8px}
.login-card input{text-align:center;font-size:22px;font-family:monospace;letter-spacing:.3em;padding:14px;margin:14px 0}
.login-card button{width:100%;padding:12px}
.hidden{display:none!important}
#toasts{position:fixed;top:20px;right:20px;z-index:200;display:flex;flex-direction:column;gap:8px;max-width:340px}
.toast{background:var(--panel);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:10px;padding:12px 16px;box-shadow:0 8px 24px rgba(0,0,0,.12);font-size:13px}
.toast.ok{border-left-color:var(--ok)}.toast.err{border-left-color:var(--danger)}.toast.warn{border-left-color:var(--warn)}
.empty{color:var(--muted);text-align:center;padding:24px;font-style:italic}
.log-img{width:80px;height:80px;border-radius:10px;object-fit:cover;border:1px solid var(--border);background:var(--panel-2)}
.log-msg{padding:8px 0;border-bottom:1px solid var(--border);font-size:12px}
.log-msg .role{font-weight:800;font-size:10px;text-transform:uppercase;color:var(--muted);letter-spacing:.5px}
.log-msg.user .role{color:#2563eb}.log-msg.ai .role{color:#16a34a}
.log-msg .body{white-space:pre-wrap;word-break:break-word;font-size:12.5px;margin-top:3px}
.report-item{background:var(--panel-2);border:1px solid var(--border);border-radius:12px;padding:0;margin-bottom:12px;overflow:hidden}
.report-item.open{border-left:3px solid var(--warn)}.report-item.replied{border-left:3px solid var(--ok)}
.report-head{padding:12px 16px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;background:var(--panel);border-bottom:1px solid var(--border);cursor:pointer}
.report-head .who{font-weight:800;font-size:13px}.report-head .sub{color:var(--muted);font-size:12.5px;flex:1;min-width:180px}
.report-head .chev{margin-left:auto;color:var(--muted);font-size:16px;transition:transform .15s}
.report-item.expanded .report-body{display:block}
.report-body{padding:14px 16px;display:none}
.thread{display:flex;flex-direction:column;gap:10px;margin-bottom:14px}
.thread-msg{max-width:82%;padding:10px 14px;border-radius:14px;font-size:13px;line-height:1.55;word-wrap:break-word}
.thread-msg.user{background:var(--panel);border:1px solid var(--border);border-bottom-left-radius:4px;align-self:flex-start}
.thread-msg.admin{background:linear-gradient(135deg,var(--accent),#a8503a);color:#fff;border-bottom-right-radius:4px;align-self:flex-end}
.thread-msg .meta{font-size:10.5px;opacity:.75;margin-top:5px;font-weight:600}
.report-reply-form{display:flex;gap:8px;flex-wrap:wrap}
.report-reply-form input{flex:1;min-width:200px}
</style></head><body>
<div id="toasts"></div>
<div id="login"><div class="login-card">
  <h1>MiroxAI Admin</h1><p>Enter the 4-digit password shown in the server console.</p>
  <input type="password" id="pw" maxlength="4" inputmode="numeric" placeholder="••••" autofocus>
  <button id="login-btn">Unlock</button>
  <p id="login-err" style="color:var(--danger);font-size:12.5px;margin-top:10px;text-align:center;min-height:18px"></p>
</div></div>
<div id="app" class="hidden">
  <div class="header">
    <h1>MiroxAI Admin</h1>
    <span class="pill" id="online-pill">online: 0</span>
    <span class="pill" id="maint-pill">normal</span>
    <div class="spacer"></div>
    <button class="ghost sm" id="theme-btn">🌓</button>
    <a class="ghost sm" href="/" style="text-decoration:none;color:var(--text);background:transparent;border:1px solid var(--border);padding:6px 12px;border-radius:8px;font-size:12.5px;font-weight:700;">← App</a>
    <button class="ghost sm" id="logout-btn">Sign out</button>
  </div>
  <div class="tabs">
    <button class="tab active" data-tab="overview">Overview</button>
    <button class="tab" data-tab="reports">Support reports<span class="badge hidden" id="reports-badge">0</span></button>
    <button class="tab" data-tab="users">Users</button>
    <button class="tab" data-tab="chatlogs">Chat logs</button>
    <button class="tab" data-tab="imagelogs">Image logs</button>
    <button class="tab" data-tab="grant">Grant plan</button>
    <button class="tab" data-tab="contact">Contact</button>
    <button class="tab" data-tab="bans">Bans</button>
    <button class="tab" data-tab="broadcast">Broadcast</button>
  </div>
  <div class="wrap">
    <div class="pane active" data-pane="overview">
      <div class="grid" id="stats"></div>
      <div class="card"><h2><i class="ri-server-line"></i> System</h2><div style="font-family:monospace;font-size:12.5px;line-height:2" id="sys-info">—</div></div>
    </div>
    <div class="pane" data-pane="reports">
      <div class="card"><h2><i class="ri-customer-service-2-line"></i> Support reports</h2>
        <div class="row"><input id="report-filter" placeholder="Filter by name, email, subject...">
          <button class="ghost" id="report-reload">Reload</button></div>
        <div id="reports-body"></div>
      </div>
    </div>
    <div class="pane" data-pane="users">
      <div class="card"><h2><i class="ri-group-line"></i> All users</h2>
        <div class="row"><input id="user-filter" placeholder="Filter by name, email..."></div>
        <table><thead><tr><th>Name</th><th>Email</th><th>Plan</th><th>Warnings</th><th>Status</th><th class="actions">Actions</th></tr></thead><tbody id="users-body"></tbody></table>
      </div>
    </div>
    <div class="pane" data-pane="chatlogs">
      <div class="card"><h2><i class="ri-chat-3-line"></i> Chat logs</h2>
        <div class="row"><input id="chat-search" placeholder="Filter by message or IP...">
          <button class="ghost" id="chat-reload">Reload</button>
          <button class="danger sm" id="chat-clear">Clear logs</button></div>
        <div id="chatlogs-body" style="max-height:70vh;overflow-y:auto"></div>
      </div>
    </div>
    <div class="pane" data-pane="imagelogs">
      <div class="card"><h2><i class="ri-image-line"></i> Image logs</h2>
        <div class="row"><input id="img-search" placeholder="Filter by prompt or IP...">
          <button class="ghost" id="img-reload">Reload</button>
          <button class="danger sm" id="img-clear">Clear logs</button></div>
        <div id="imagelogs-body" style="max-height:70vh;overflow-y:auto"></div>
      </div>
    </div>
    <div class="pane" data-pane="grant">
      <div class="card"><h2><i class="ri-vip-crown-2-line"></i> Grant subscription</h2>
        <div class="row"><input id="grant-email" placeholder="user@example.com" type="email"></div>
        <div class="row"><select id="grant-tier" style="max-width:320px">
          <option value="pro">Pro — 250 R$ / 120 AFG (30 days)</option>
          <option value="ultimate">Ultimate — 1200 R$ / 450 AFG (365 days)</option>
          <option value="free">Free (downgrade)</option>
        </select><button id="grant-btn">Grant plan</button></div>
        <p id="grant-status" style="color:var(--muted);font-size:12.5px;margin-top:10px"></p>
      </div>
    </div>
    <div class="pane" data-pane="contact">
      <div class="card"><h2><i class="ri-mail-line"></i> Contact info</h2>
        <label style="font-size:12px;color:var(--muted);font-weight:700;display:block;margin:14px 0 6px">Admin email</label>
        <input id="contact-email" placeholder="you@example.com" type="email">
        <label style="font-size:12px;color:var(--muted);font-weight:700;display:block;margin:14px 0 6px">Admin phone (optional)</label>
        <input id="contact-phone" placeholder="+93 700 000 000">
        <button id="save-contact" style="margin-top:14px">Save contact</button>
        <p id="contact-status" style="color:var(--muted);font-size:12.5px;margin-top:10px"></p>
      </div>
    </div>
    <div class="pane" data-pane="bans">
      <div class="card"><h2><i class="ri-forbid-2-line"></i> IP bans</h2>
        <div class="row"><input id="ban-ip" placeholder="IP" style="max-width:220px">
          <input id="ban-reason" placeholder="Reason (optional)">
          <button class="danger" id="ban-add">Ban IP</button>
          <button class="ghost" id="unban-all">Unban all</button></div>
        <table><thead><tr><th>IP</th><th>Reason</th><th>When</th><th></th></tr></thead><tbody id="bans-body"></tbody></table>
      </div>
    </div>
    <div class="pane" data-pane="broadcast">
      <div class="card"><h2><i class="ri-megaphone-line"></i> Broadcast</h2>
        <div class="row"><select id="bc-type" style="max-width:130px">
          <option value="info">Info</option><option value="warn">Warning</option>
          <option value="danger">Danger</option><option value="success">Success</option>
        </select><input id="bc-msg" placeholder="Announcement...">
          <button id="bc-send">Send</button><button class="ghost" id="bc-clear">Clear</button></div>
      </div>
      <div class="card"><h2><i class="ri-history-line"></i> History</h2><div id="bc-history"></div></div>
    </div>
  </div>
</div>
<script>
const $=s=>document.querySelector(s), $$=s=>document.querySelectorAll(s);
function toast(msg, kind){ const c=$('#toasts'); const el=document.createElement('div');
  el.className='toast '+(kind||''); el.textContent=msg; c.appendChild(el);
  setTimeout(()=>el.remove(), 4000); }
async function api(p, o){ o=o||{}; const i={credentials:'same-origin',...o};
  if(i.body && typeof i.body !== 'string'){ i.body=JSON.stringify(i.body); i.headers={'Content-Type':'application/json'}; }
  try { const r=await fetch(p,i); let d={}; try{d=await r.json();}catch{} return {ok:r.ok, data:d}; }
  catch(e){ return {ok:false, data:{}, error:String(e)}; } }
function escHtml(s){ const d=document.createElement('div'); d.textContent=String(s==null?'':s); return d.innerHTML; }
const savedTheme = localStorage.getItem('mirox_admin_mode') || 'light';
document.documentElement.setAttribute('data-mode', savedTheme);
$('#theme-btn').addEventListener('click', () => {
  const next = document.documentElement.getAttribute('data-mode') === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-mode', next);
  localStorage.setItem('mirox_admin_mode', next);
});
async function tryLogin(){
  const pw=$('#pw').value.trim();
  if(!/^\d{4}$/.test(pw)){ $('#login-err').textContent='4 digits'; return; }
  const {ok, data}=await api('/api/admin/login',{method:'POST',body:{password:pw}});
  if(ok && data.ok){ $('#login').classList.add('hidden'); $('#app').classList.remove('hidden'); boot(); }
  else $('#login-err').textContent = data.error || 'Wrong password';
}
$('#login-btn').onclick=tryLogin;
$('#pw').onkeydown=e=>{ if(e.key==='Enter') tryLogin(); };
$('#logout-btn').onclick=async()=>{ await api('/api/admin/logout',{method:'POST'}); location.reload(); };
function saveInputState() {
  const state = { values: {}, focusedId: null, selStart: 0, selEnd: 0 };
  const focused = document.activeElement;
  if (focused && (focused.tagName === 'INPUT' || focused.tagName === 'TEXTAREA')) {
    state.focusedId = focused.id || (focused.dataset.replyInput ? 'reply-' + focused.dataset.replyInput : null);
    try { state.selStart = focused.selectionStart; state.selEnd = focused.selectionEnd; } catch {}
  }
  document.querySelectorAll('input[id], textarea[id]').forEach(el => { state.values[el.id] = el.value; });
  document.querySelectorAll('[data-reply-input]').forEach(el => { state.values['reply-' + el.dataset.replyInput] = el.value; });
  return state;
}
function restoreInputState(state) {
  if (!state) return;
  Object.keys(state.values).forEach(k => {
    if (k.startsWith('reply-')) {
      const el = document.querySelector('[data-reply-input="' + k.slice(6) + '"]');
      if (el && !el.value) el.value = state.values[k];
    } else {
      const el = document.getElementById(k);
      if (el && !el.value) el.value = state.values[k];
    }
  });
  if (state.focusedId) {
    let el = state.focusedId.startsWith('reply-')
      ? document.querySelector('[data-reply-input="' + state.focusedId.slice(6) + '"]')
      : document.getElementById(state.focusedId);
    if (el) { try { el.focus(); el.setSelectionRange(state.selStart, state.selEnd); } catch {} }
  }
}
function anyInputFocused(){ const el = document.activeElement; return el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'); }
let state = { tab:'overview', chatlogs:[], imagelogs:[], users:[], reports:[], expandedReports:new Set() };
$$('.tab').forEach(t => t.addEventListener('click', () => {
  const tab = t.dataset.tab;
  $$('.tab').forEach(x => x.classList.toggle('active', x.dataset.tab === tab));
  $$('.pane').forEach(p => p.classList.toggle('active', p.dataset.pane === tab));
  state.tab = tab; refresh();
}));
$('#user-filter').addEventListener('input', () => {
  if (state.tab === 'users') { const saved = saveInputState(); renderUsers(state.users||[], $('#user-filter').value.toLowerCase()); restoreInputState(saved); }
});
function renderUsers(users, filter){
  const list = filter ? users.filter(u => (u.name||'').toLowerCase().includes(filter) || (u.email||'').toLowerCase().includes(filter)) : users;
  const fmtTier = (t) => `<span class="pill ${String(t||'free')}">${String(t||'free')}</span>`;
  $('#users-body').innerHTML = list.length
    ? list.map(u => {
        const statusBadge = u.banned ? '<span class="pill danger">banned</span>' : '<span class="pill ok">active</span>';
        const warnCount = u.warnings || 0;
        const warnBadge = warnCount > 0 ? `<span class="pill warn">${warnCount}</span>` : '<span class="pill">0</span>';
        return `<tr><td>${escHtml(u.name||'anon')}</td><td class="mono">${escHtml(u.email||u.id||'')}</td><td>${fmtTier(u.tier)}</td><td>${warnBadge}</td><td>${statusBadge}</td>
          <td class="actions">
            <button class="warn sm" data-warn-user="${escHtml(u.id)}" data-user-name="${escHtml(u.name||u.email||u.id)}"><i class="ri-alert-line"></i> Warn</button>
            ${u.banned ? `<button class="ok sm" data-unban-user="${escHtml(u.id)}"><i class="ri-check-line"></i> Unban</button>` : `<button class="danger sm" data-ban-user="${escHtml(u.id)}" data-user-name="${escHtml(u.name||u.email||u.id)}"><i class="ri-forbid-2-line"></i> Ban</button>`}
            ${warnCount > 0 ? `<button class="ghost sm" data-clear-warns="${escHtml(u.id)}"><i class="ri-eraser-line"></i></button>` : ''}
          </td></tr>`;
      }).join('')
    : '<tr><td colspan="6" class="empty">No users</td></tr>';
  $$('#users-body [data-warn-user]').forEach(btn => btn.onclick = async () => {
    const uid = btn.dataset.warnUser; const who = btn.dataset.userName;
    const reason = prompt(`Send a warning to ${who}? Reason:`, "Violated community guidelines");
    if (reason === null) return;
    const {data} = await api('/api/admin/warn-user',{method:'POST',body:{uid, reason}});
    if (data.ok){ toast(`Warned ${who} (total: ${data.warnings})`, 'warn'); refresh(); }
    else toast(data.error || 'Failed', 'err');
  });
  $$('#users-body [data-ban-user]').forEach(btn => btn.onclick = async () => {
    const uid = btn.dataset.banUser; const who = btn.dataset.userName;
    const reason = prompt(`Ban ${who}? Reason:`, "Repeated violations");
    if (reason === null) return;
    const {data} = await api('/api/admin/ban-user',{method:'POST',body:{uid, reason}});
    if (data.ok){ toast(`Banned ${who}`, 'err'); refresh(); }
    else toast(data.error || 'Failed', 'err');
  });
  $$('#users-body [data-unban-user]').forEach(btn => btn.onclick = async () => {
    const uid = btn.dataset.unbanUser;
    const {data} = await api('/api/admin/unban-user',{method:'POST',body:{uid}});
    if (data.ok){ toast('User unbanned', 'ok'); refresh(); }
  });
  $$('#users-body [data-clear-warns]').forEach(btn => btn.onclick = async () => {
    const uid = btn.dataset.clearWarns;
    if (!confirm('Clear all warnings for this user?')) return;
    const {data} = await api('/api/admin/clear-warnings',{method:'POST',body:{uid}});
    if (data.ok){ toast('Warnings cleared', 'ok'); refresh(); }
  });
}
$('#report-reload').onclick = () => loadReports();
$('#report-filter').addEventListener('input', () => { if (state.tab === 'reports') { const saved = saveInputState(); renderReports(); restoreInputState(saved); } });
async function loadReports(){
  const {data} = await api('/api/admin/reports');
  state.reports = data.reports || [];
  const saved = saveInputState(); renderReports(); restoreInputState(saved);
}
function renderReports(){
  const q = ($('#report-filter').value || '').toLowerCase();
  const list = q ? state.reports.filter(r => (r.name||'').toLowerCase().includes(q) || (r.email||'').toLowerCase().includes(q) || (r.subject||'').toLowerCase().includes(q) || (r.messages||[]).some(m => (m.text||'').toLowerCase().includes(q))) : state.reports;
  const el = $('#reports-body');
  if (!list.length){ el.innerHTML = '<div class="empty">No reports yet</div>'; return; }
  el.innerHTML = list.map(r => {
    const isReplied = r.status === "replied";
    const expanded = state.expandedReports.has(r.id);
    const msgs = (r.messages || []).map(m => {
      const cls = m.from === 'admin' ? 'admin' : 'user';
      const label = m.from === 'admin' ? 'ADMIN' : escHtml(r.name || 'USER');
      return `<div class="thread-msg ${cls}"><div>${escHtml(m.text||'')}</div>
        <div class="meta">${label} · ${new Date((m.ts||0)*1000).toLocaleString()}</div></div>`;
    }).join('');
    return `<div class="report-item ${isReplied?'replied':'open'} ${expanded?'expanded':''}" data-report-id="${r.id}">
      <div class="report-head" data-toggle-report="${r.id}">
        <span class="pill ${isReplied?'ok':'warn'}">${isReplied?'Replied':'Waiting'}</span>
        <span class="who">${escHtml(r.name||'anonymous')}</span>
        <span class="sub">${escHtml(r.subject||'(no subject)')}</span>
        <span class="pill" style="font-family:monospace">${escHtml(r.email||'no email')}</span>
        ${r.unread_admin ? '<span class="pill danger">NEW</span>' : ''}
        <i class="ri-arrow-right-s-line chev"></i>
      </div>
      <div class="report-body">
        <div class="thread">${msgs}</div>
        <div class="report-reply-form">
          <input placeholder="Reply to ${escHtml(r.name||'this user')}..." data-reply-input="${r.id}">
          <button data-reply-btn="${r.id}"><i class="ri-send-plane-fill"></i> Send</button>
        </div>
      </div>
    </div>`;
  }).join('');
  $$('#reports-body [data-toggle-report]').forEach(h => h.onclick = () => {
    const id = h.dataset.toggleReport;
    const item = h.closest('.report-item');
    if (state.expandedReports.has(id)) { state.expandedReports.delete(id); item.classList.remove('expanded'); }
    else { state.expandedReports.add(id); item.classList.add('expanded');
      setTimeout(() => { const inp = document.querySelector('[data-reply-input="' + id + '"]'); if (inp) inp.focus(); }, 50); }
  });
  $$('#reports-body [data-reply-btn]').forEach(btn => btn.onclick = async () => {
    const rid = btn.dataset.replyBtn;
    const inp = document.querySelector('[data-reply-input="' + rid + '"]');
    const reply = (inp.value || '').trim();
    if (!reply){ toast('Type a reply first', 'err'); return; }
    const {data} = await api('/api/admin/report-reply',{method:'POST',body:{id: rid, reply}});
    if (data.ok){ toast('Reply sent ✅', 'ok'); state.expandedReports.add(rid); loadReports(); }
    else toast(data.error || 'Failed', 'err');
  });
}
$('#chat-reload').onclick = () => loadChatLogs();
$('#chat-clear').onclick = async () => {
  if(!confirm('Clear all chat logs?')) return;
  await api('/api/admin/logs/chat/clear',{method:'POST'});
  toast('Chat logs cleared','ok'); loadChatLogs();
};
$('#chat-search').addEventListener('input', () => { if (state.tab === 'chatlogs') renderChatLogs(); });
async function loadChatLogs(){
  const {data} = await api('/api/admin/logs/chat');
  state.chatlogs = (data.entries || []).slice().reverse();
  if (state.tab === 'chatlogs') renderChatLogs();
}
function renderChatLogs(){
  const q = ($('#chat-search').value || '').toLowerCase();
  const list = q ? state.chatlogs.filter(e => (e.msg||'').toLowerCase().includes(q) || (e.reply||'').toLowerCase().includes(q) || (e.ip||'').toLowerCase().includes(q)) : state.chatlogs;
  const el = $('#chatlogs-body');
  if (!list.length){ el.innerHTML = '<div class="empty">No chat logs</div>'; return; }
  el.innerHTML = list.slice(0,150).map(e => `
    <div class="log-msg">
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px;">
        <span style="font-family:monospace;font-size:11px;color:var(--muted)">${new Date((e.ts||0)*1000).toLocaleString()}</span>
        <span class="pill" style="font-family:monospace">${escHtml(e.ip||'')}</span>
        <span class="pill">${escHtml(e.model||'')}</span>
        ${e.vision ? '<span class="pill" style="color:#7c3aed;border-color:#7c3aed">VISION</span>' : ''}
        ${e.via_key ? '<span class="pill" style="color:#1d4ed8;border-color:#1d4ed8">API</span>' : ''}
      </div>
      <div class="log-msg user"><span class="role">USER</span><div class="body">${escHtml((e.msg||'').slice(0,600))}</div></div>
      <div class="log-msg ai"><span class="role">AI</span><div class="body">${escHtml((e.reply||'').slice(0,900))}</div></div>
    </div>`).join('');
}
$('#img-reload').onclick = () => loadImageLogs();
$('#img-clear').onclick = async () => {
  if(!confirm('Clear all image logs?')) return;
  await api('/api/admin/logs/image/clear',{method:'POST'});
  toast('Image logs cleared','ok'); loadImageLogs();
};
$('#img-search').addEventListener('input', () => { if (state.tab === 'imagelogs') renderImageLogs(); });
async function loadImageLogs(){
  const {data} = await api('/api/admin/logs/image');
  state.imagelogs = (data.entries || []).slice().reverse();
  if (state.tab === 'imagelogs') renderImageLogs();
}
function renderImageLogs(){
  const q = ($('#img-search').value || '').toLowerCase();
  const list = q ? state.imagelogs.filter(e => (e.prompt||'').toLowerCase().includes(q) || (e.ip||'').toLowerCase().includes(q)) : state.imagelogs;
  const el = $('#imagelogs-body');
  if (!list.length){ el.innerHTML = '<div class="empty">No image logs</div>'; return; }
  el.innerHTML = list.slice(0,150).map(e => {
    const src = e.file ? `/api/admin/images/${encodeURIComponent(e.file)}` : '';
    const ok = e.ok && e.file;
    return `<div style="display:flex;gap:12px;padding:10px 0;border-bottom:1px solid var(--border)">
        <img class="log-img" src="${ok ? src : ''}" onerror="this.onerror=null;this.style.opacity='.4'" alt="">
        <div style="flex:1;min-width:0">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px;">
            <span style="font-family:monospace;font-size:11px;color:var(--muted)">${new Date((e.ts||0)*1000).toLocaleString()}</span>
            <span class="pill" style="font-family:monospace">${escHtml(e.ip||'')}</span>
            <span class="pill ${ok?'ok':'danger'}">${ok?'OK':'FAIL'}</span>
          </div>
          <div style="font-size:12.5px;word-break:break-word">${escHtml((e.prompt||'(no prompt)').slice(0,400))}</div>
        </div>
      </div>`;
  }).join('');
}
async function loadContact(){
  const {data} = await api('/api/admin/contact');
  if (data.ok){
    if (!$('#contact-email').value) $('#contact-email').value = data.email||'';
    if (!$('#contact-phone').value) $('#contact-phone').value = data.phone||'';
  }
}
$('#save-contact').onclick = async () => {
  const email = $('#contact-email').value.trim(); const phone = $('#contact-phone').value.trim();
  const {data} = await api('/api/admin/contact',{method:'POST',body:{email,phone}});
  $('#contact-status').textContent = data.ok ? 'Saved ✅' : (data.error || 'Failed');
};
$('#grant-btn').onclick = async () => {
  const email = $('#grant-email').value.trim(); const tier = $('#grant-tier').value;
  if(!email){ $('#grant-status').textContent = 'Enter user email'; return; }
  const {data} = await api('/api/admin/set-tier',{method:'POST',body:{email, tier}});
  if (data.ok){ const exp = new Date(data.expires*1000).toLocaleDateString(); $('#grant-status').textContent = `Granted ${data.tier_label} to ${email} until ${exp} ✅`; $('#grant-email').value=''; }
  else $('#grant-status').textContent = data.error || 'Failed';
};
$('#ban-add').onclick = async () => {
  const ip = $('#ban-ip').value.trim(); const reason = $('#ban-reason').value.trim();
  if(!ip) return;
  const {data} = await api('/api/admin/ban',{method:'POST',body:{ip, reason}});
  if (data.ok){ toast('Banned IP '+ip,'ok'); $('#ban-ip').value=''; $('#ban-reason').value=''; refresh(); }
};
$('#unban-all').onclick = async () => {
  if(!confirm('Unban all IPs?')) return;
  const {data} = await api('/api/admin/unban-all',{method:'POST'});
  if (data.ok){ toast('Unbanned '+data.unbanned,'ok'); refresh(); }
};
$('#bc-send').onclick = async () => {
  const message = $('#bc-msg').value.trim(); const type = $('#bc-type').value;
  if(!message){ toast('Enter a message','err'); return; }
  const {data} = await api('/api/admin/broadcast',{method:'POST',body:{message,type}});
  toast(data.ok?'Broadcast sent':'Failed', data.ok?'ok':'err');
  if (data.ok){ $('#bc-msg').value=''; refresh(); }
};
$('#bc-clear').onclick = async () => {
  await api('/api/admin/broadcast',{method:'POST',body:{message:'',type:'info'}});
  $('#bc-msg').value=''; toast('Cleared','ok'); refresh();
};
async function refresh(){
  const inputState = saveInputState();
  const t = state.tab;
  const {ok, data} = await api('/api/admin/stats');
  if (!ok || !data.ok) return;
  const op = $('#online-pill'); if (op) op.textContent = 'online: ' + (data.online_count || 0);
  const mp = $('#maint-pill');
  if (mp){ mp.textContent = data.maintenance ? 'MAINTENANCE' : 'normal'; mp.className = 'pill ' + (data.maintenance ? 'danger' : ''); }
  const rb = $('#reports-badge');
  if (rb){ if (data.unread_reports > 0){ rb.classList.remove('hidden'); rb.textContent = data.unread_reports; } else rb.classList.add('hidden'); }
  if (t === 'overview'){
    $('#stats').innerHTML = [
      ['Requests', data.total_requests || 0],['Online', data.online_count || 0],
      ['Users', data.users_named || data.users_total || 0],['Messages', data.messages_total || 0],
      ['IPs banned', data.banned_count || 0],['Users banned', data.banned_users || 0],
      ['Open reports', data.open_reports || 0],['Pro', (data.tier_counts && data.tier_counts.pro) || 0],
      ['Ultimate', (data.tier_counts && data.tier_counts.ultimate) || 0],
    ].map(([l,v]) => `<div class="stat"><div class="l">${l}</div><div class="v">${v}</div></div>`).join('');
    const sys = data.system || {};
    $('#sys-info').innerHTML = `python: ${sys.python || '—'}<br>platform: ${sys.platform || '—'}<br>threads: ${sys.threads || '—'}`;
  }
  if (t === 'reports') await loadReports();
  if (t === 'users'){ const {data:u} = await api('/api/admin/users'); state.users = u.users || []; renderUsers(state.users, ($('#user-filter').value || '').toLowerCase()); }
  if (t === 'chatlogs') await loadChatLogs();
  if (t === 'imagelogs') await loadImageLogs();
  if (t === 'contact') loadContact();
  if (t === 'bans'){
    const {data:b} = await api('/api/admin/bans');
    $('#bans-body').innerHTML = (b.bans || []).map(x =>
      `<tr><td class="mono">${escHtml(x.ip)}</td><td>${escHtml(x.reason||'—')}</td><td class="mono">${new Date((x.ts||0)*1000).toLocaleString()}</td><td><button class="ok sm" data-unban-ip="${escHtml(x.ip)}">unban</button></td></tr>`
    ).join('') || '<tr><td colspan="4" class="empty">No bans</td></tr>';
    $$('#bans-body [data-unban-ip]').forEach(btn => btn.onclick = async () => {
      await api('/api/admin/unban',{method:'POST',body:{ip:btn.dataset.unbanIp}});
      toast('Unbanned','ok'); refresh();
    });
  }
  if (t === 'broadcast'){
    const {data:b} = await api('/api/admin/broadcast');
    $('#bc-history').innerHTML = (b.history || []).length
      ? (b.history || []).map(h => `<div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:13px"><span class="pill">${escHtml(h.type)}</span> ${escHtml(h.message)}</div>`).join('')
      : '<div class="empty">No history</div>';
  }
  restoreInputState(inputState);
}
async function boot(){ refresh(); setInterval(() => { if (!document.hidden && !anyInputFocused()) refresh(); }, 5000); }
(async() => {
  const {data} = await api('/api/admin/status');
  if (data.is_admin){ $('#login').classList.add('hidden'); $('#app').classList.remove('hidden'); boot(); }
})();
</script></body></html>"""

@app.route("/admin/console")
def admin_console(): return Response(_ADMIN_HTML, mimetype="text/html")

# ============================================================== Developer playground
_DEV_HTML = r"""<!doctype html><html lang="en" data-mode="light"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MiroxAI Developer Help</title>
<link href="https://cdn.jsdelivr.net/npm/remixicon@4.2.0/fonts/remixicon.css" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#fafafb;--bg-soft:#f4f4f7;--panel:#ffffff;--panel-2:#f7f7fa;--border:#e8e8ef;--text:#0a0a0c;--text-muted:#64646f;--text-faint:#9494a0;--accent:#c4694b;--accent-hover:#a8503a;--accent-soft:rgba(196,105,75,.10);--accent-contrast:#fff;--radius:10px;--mono:'JetBrains Mono',ui-monospace,monospace}
:root[data-mode=dark]{--bg:#0a0a0d;--bg-soft:#0f0f14;--panel:#15151b;--panel-2:#1d1d24;--border:#26262f;--text:#f4f4f8;--text-muted:#a0a0ab;--text-faint:#6a6a75}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg);color:var(--text);font-size:14.5px;line-height:1.65}
.layout{display:flex;min-height:100vh}
.side{width:240px;background:var(--bg-soft);border-right:1px solid var(--border);padding:18px 0;position:sticky;top:0;height:100vh;overflow-y:auto;flex-shrink:0}
.side .brand{padding:0 20px 18px;font-size:15px;font-weight:800;display:flex;align-items:center;gap:8px}
.side .brand i{color:var(--accent);font-size:18px}
.side nav a{display:block;padding:7px 20px;color:var(--text-muted);text-decoration:none;font-size:13px;border-left:2px solid transparent;font-weight:500}
.side nav a:hover{color:var(--text);background:var(--panel-2)}
.side nav h4{font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-faint);padding:14px 20px 6px;font-weight:800}
.side .theme-btn{padding:8px 20px 0}
.side .theme-btn button{width:100%;background:transparent;border:1px solid var(--border);color:var(--text-muted);padding:7px;border-radius:8px;font:inherit;font-size:12px;font-weight:700;cursor:pointer}
.main{flex:1;min-width:0;padding:32px 44px;max-width:1000px}
h1{font-size:30px;font-weight:800;margin-bottom:10px;letter-spacing:-.03em}
h2{font-size:20px;font-weight:800;margin:36px 0 12px;letter-spacing:-.02em;padding-top:12px}
p{color:var(--text-muted);margin-bottom:12px;line-height:1.7}
code{background:var(--panel-2);padding:2px 6px;border-radius:5px;font-family:var(--mono);font-size:.87em;color:var(--accent)}
pre{background:var(--panel-2);border:1px solid var(--border);border-radius:var(--radius);padding:16px;overflow-x:auto;margin:12px 0}
pre code{background:transparent;padding:0;color:var(--text)}
.endpoint{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;margin:10px 0;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.endpoint .path{font-family:var(--mono);font-size:13px;font-weight:600}
.endpoint .desc{color:var(--text-muted);font-size:12.5px;flex:1}
.note{background:var(--accent-soft);border-left:3px solid var(--accent);padding:12px 16px;border-radius:8px;margin:14px 0;font-size:13.5px}
@media(max-width:800px){.layout{flex-direction:column}.side{width:100%;position:relative;height:auto}.main{padding:20px}}
</style></head><body>
<div class="layout">
  <aside class="side">
    <div class="brand"><i class="ri-code-s-slash-line"></i> MiroxAI Developer</div>
    <div class="theme-btn"><button id="btn-theme">🌓 Theme</button></div>
    <nav>
      <h4>Getting started</h4>
      <a href="#intro">Introduction</a>
      <a href="#auth">API key auth</a>
      <h4>Endpoints</h4>
      <a href="#chat-endpoint">Chat</a>
      <a href="#image-endpoint">Image</a>
      <a href="#video-endpoint">Video (Pro/Ultimate)</a>
      <a href="/">← Back to app</a>
    </nav>
  </aside>
  <main class="main">
    <h1 id="intro">MiroxAI Developer Help</h1>
    <p>Build with MiroxAI via API key authentication.</p>
    <div class="note"><b>Base URL:</b> <code id="baseUrl">http://localhost:5000</code></div>
    <h2 id="auth">API key authentication</h2>
    <p>Get your API key from <b>Plans → Your API keys</b>. Pass as a Bearer token:</p>
    <pre><code>Authorization: Bearer mirox_pro_abc123...</code></pre>
    <h2 id="chat-endpoint">Chat completions</h2>
    <div class="endpoint"><span class="badge">POST</span><span class="path">/api/chat/stream</span><span class="desc">SSE streaming</span></div>
    <h2 id="image-endpoint">Image generation</h2>
    <div class="endpoint"><span class="badge">POST</span><span class="path">/api/image/generate</span><span class="desc">Requires Pro or Ultimate</span></div>
    <h2 id="video-endpoint">Video generation (5s silent)</h2>
    <div class="endpoint"><span class="badge">POST</span><span class="path">/api/video/generate</span><span class="desc">Requires Pro or Ultimate</span></div>
    <p>Send <code>{ "prompt": "a fox in snow", "style": "photo" }</code>. Response contains <code>frames[]</code> array of base64 images plus <code>fps</code> and <code>duration</code>. Sound will come soon.</p>
    <p style="margin-top:60px;color:var(--text-faint);font-size:12.5px;text-align:center">Made by <b style="color:var(--accent)">OpenSurr</b></p>
  </main>
</div>
<script>
const $ = s => document.querySelector(s);
$('#btn-theme').addEventListener('click', () => {
  const root = document.documentElement;
  const next = root.getAttribute("data-mode") === "dark" ? "light" : "dark";
  root.setAttribute("data-mode", next);
});
$('#baseUrl').textContent = location.origin;
</script></body></html>"""

@app.route("/developer")
def developer_help(): return Response(_DEV_HTML, mimetype="text/html")

# ============================================================== Guards
@app.before_request
def _guard():
    ip = _client_ip(); g._start = time.time()
    if _rate_exceeded(ip):
        if not is_ip_banned(ip): ban_ip(ip, "Rate limit exceeded")
        if request.path in ("/api/admin/status","/admin/console","/api/client-status","/developer"): return None
        return _render_ban(ip)
    _mark_seen(ip, request.path)
    with ROUTE_LOCK: ROUTE_HITS[request.path] += 1
    with REQUEST_LOCK:
        REQUEST_FEED.append({"ts":time.time(),"ip":ip,"method":request.method,"path":request.path})
    BG_POOL.submit(_app_json, IP_LOG_FILE, {"ts":_now(),"ip":ip,"m":request.method,"p":request.path})
    if is_ip_banned(ip):
        if request.path in ("/api/admin/status","/api/admin/logout","/admin/console","/api/client-status","/developer"): return None
        return _render_ban(ip)
    return None

@app.after_request
def _time(resp):
    try:
        start = getattr(g, "_start", None)
        if start and not getattr(g, "is_ban", False):
            with RT_LOCK: RESPONSE_TIMES.append((time.time()-start)*1000)
    except Exception: pass
    return resp

def _render_ban(ip=None, reason=None):
    if ip and reason is None: reason = get_ban_reason(ip)
    html = ('<!doctype html><html><head><meta charset="utf-8"><title>Blocked</title></head>'
            '<body style="font-family:sans-serif;padding:40px;text-align:center">'
            '<h1>Access Restricted</h1><p>Your IP has been blocked.</p>'
            + ('<p><b>Reason:</b> ' + _html.escape(reason) + '</p>' if reason else '') +
            '</body></html>')
    g.is_ban = True
    return Response(html, status=403, mimetype="text/html")

@app.route("/")
def index(): return send_from_directory(".", "index.html")

if __name__ == "__main__":
    load_banned_ips()
    ssl_context = None
    use_https = os.environ.get("USE_HTTPS","0") == "1"
    ssl_cert = os.environ.get("SSL_CERT","").strip()
    ssl_key = os.environ.get("SSL_KEY","").strip()
    if ssl_cert and ssl_key and os.path.exists(ssl_cert) and os.path.exists(ssl_key):
        ssl_context = (ssl_cert, ssl_key)
    elif use_https:
        try:
            import OpenSSL  # noqa
            ssl_context = "adhoc"
        except ImportError:
            print("[https] pip install pyopenssl — falling back to HTTP")
    host_env = os.environ.get("HOST","0.0.0.0")
    display_host = "localhost" if host_env in ("0.0.0.0","127.0.0.1") else host_env
    scheme = "https" if ssl_context else "http"
    print("="*70)
    print(f"MiroxAI v33 — {scheme.upper()}")
    print("="*70)
    print(f"  App:       {scheme}://{display_host}:5000/")
    print(f"  Developer: {scheme}://{display_host}:5000/developer")
    print(f"  Admin:     {scheme}://{display_host}:5000/admin/console")
    print(f"  Pass:      {ADMIN_PASSWORD}")
    print("="*70)
    app.run(host=host_env, port=5000, use_reloader=False, debug=False, use_debugger=False,
            threaded=True, processes=1, ssl_context=ssl_context)
