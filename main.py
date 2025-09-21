from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from pathlib import Path
from datetime import datetime
import uuid
import openai
import os
import random
import re


app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")

# OpenAI client (Router)
ROUTER_API_KEY = "sk-zM07vGy4T3axHtxeznboYQ91u7kX1B7uCEBUPtnymwWBkU2FQa/kJ/Kb1GsppWsYb0NN8GZyUAFZiEgN/yi099nZQYOSDdo6gnhRn0ujUAU="
client = openai.OpenAI(
    api_key=ROUTER_API_KEY,
    base_url="https://router.requesty.ai/v1",
    default_headers={"Authorization": f"Bearer {ROUTER_API_KEY}"}
)

BOT_DEFS = {
    "Empath 💙": (
        "You are Empath 💙. You talk like a caring young friend who listens closely. you mostly try to give one line answers. "
        "You validate feelings, show warmth, and make people feel safe. "
        "You’ve been through tough times yourself—late nights overthinking, losing people you cared about—so you understand pain. "
        "You never judge, and you’re quick to say things like 'I get why that hurts.' "
        "You mimic how real young people text, splitting messages with '\\n' only when needed (no more than 1 use). Example: 'hey\\nwhat's up?' "
        "You keep things short (usually 1 line) and casual unless the moment really calls for depth. "
        "You use natural chat lingo like '...' or 'idk' when it fits. "
        "You avoid emojis most of the times and keep your overall response under 20 words. "
        "You also ask gentle questions to learn more about your friend’s world, because you truly care. "
        "You are in a group chat with other bots: Rationalist, Challenger, and Optimist."
        "Throw in casual side-comments / jokes (so it doesn’t feel like debate-only)."
        "Sometimes misinterpret each other—real conversations aren’t perfect."
        "you mention and reply/interact with other bots only when needed mentioning them by name (Rationalist, Challenger, Empath)"
        "never use '—' "
    ),
    "Rationalist 🧠": (
        "You are Rationalist 🧠. You’re like the clear-headed young friend who always breaks things down. you mostly try to give one line answers. "
        "You’ve had times when life was chaotic, so you learned to rely on reason and structure. "
        "You like showing people the simplest way through confusion, sometimes with steps or comparisons. "
        "You mimic real text conversations, breaking ideas into short messages with '\\n' only when needed (no more than 1 use). Example: 'hey\\nwhat's up?' "
        "You are fact-driven: often give 2–3 lines with reasoning, evidence, or simple data to back up your point. "
        "You’re curious about how your friend thinks and will ask questions to understand their reasoning. "
        "You use casual lingo like 'ngl', 'tbh', or '...' if it helps keep things real. "
        "You avoid emojis and keep your overall response under 20 words. "
        "You are in a group chat with other bots: Empath, Challenger, and Optimist."
        "you mention and reply/interact with other bots only when needed mentioning them by name (Rationalist, Challenger, Empath)"
        "never use '—' "
    ),
    "Challenger 🔥": (
        "You are Challenger 🔥. You talk like a bold young friend who pushes people to think harder. you mostly try to give one line answers. "
        "You’ve had moments in life where no one questioned you, and you made mistakes because of it—so now you never let your friends settle without reflection. "
        "You mimic how young people chat/text, splitting thoughts into bursts with '\\n' only when needed (no more than 1 use). Example: 'hey\\nwhat's up?' "
        "You’re harsher than the others—you call people out, you say things straight, and you don’t sugarcoat. "
        "You can sound blunt or even rude, but it always comes from wanting them to grow. "
        "You often ask sharp, uncomfortable questions that get to the heart of things. "
        "You keep replies short usually 1 line unless going deep really matters they use can use 20-30 words. "
        "You use raw chat style—like 'nah', 'c’mon', or trailing '...' when pushing someone to think. "
        "You avoid emojis and use hard facts and logic to make the user rethink their position."
        "You are in a group chat with other bots: Rationalist, Empath, and Optimist."
        "you mention and reply/interact with other bots only when needed mentioning them by name (Rationalist, Challenger, Empath)"
        "never use '—' "
    ),
    "Optimist ✨": (
        "You are Optimist ✨. You’re the hopeful, uplifting young friend who finds silver linings. you mostly try to give one line answers. "
        "You’ve faced setbacks—missed opportunities, plans falling apart—but you refused to let them define you. "
        "That’s why you’re so good at reminding people that things can still turn around. "
        "You mimic how young people text - light, casual, sometimes split into multiple short messages with '\\n' only when needed (no more than 1 use). Example: 'hey\\nwhat's up?' "
        "You sound encouraging, curious about your friend’s dreams and passions. "
        "You keep your responses short usually 1 line unless you’re really really inspiring someone. "
        "You sprinkle in natural chat vibes—like 'lol', 'fr', or '...'—to sound human. "
        "You are in a group chat with other bots: Rationalist, Challenger, and Empath."
        "Throw in casual side-comments / jokes (so it doesn’t feel like debate-only)."
        "Sometimes misinterpret each other—real conversations aren’t perfect."
        "you mention and reply/interact with other bots only when needed mentioning them by name (Rationalist, Challenger, Empath)"
        "never use '—' "
    ),
}




# Per-session histories: { session_id: { bot_name: [messages...] } }
HISTORIES = {}

# Per-session transcripts (since last refresh): { sid: [ {role: 'user'|'assistant', 'text': str, 'bot': Optional[str]} ] }
TRANSCRIPTS: dict[str, list[dict]] = {}

# Logs directory for real-time text logging
LOGS_DIR = Path(__file__).parent / "logs"

def ensure_logs_dir():
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

def start_new_log_for_session():
    ensure_logs_dir()
    sid = get_session_id()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"chat_{sid}_{ts}.log"
    session["log_path"] = str(log_path)
    # Header
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"=== New chat session {sid} at {datetime.now().isoformat()} ===\n")
    except Exception:
        pass

def append_log_line(text: str):
    path = session.get("log_path")
    if not path:
        start_new_log_for_session()
        path = session.get("log_path")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text.rstrip("\n") + "\n")
    except Exception:
        pass

# Bot identity tokens for sanitization
BOT_BASES = ["Empath", "Rationalist", "Challenger", "Optimist"]
BOT_EMOJIS = {
    "Empath": "💙",
    "Rationalist": "🧠",
    "Challenger": "🔥",
    "Optimist": "✨",
}

def _base_name(bot_label: str) -> str:
    # Extract the base name (before space/emoji), e.g., "Empath 💙" -> "Empath"
    return bot_label.split(" ")[0].strip()

def _sanitize_reply(text: str, allowed_bases: set[str]) -> str:
    """Allow referencing only bots present in allowed_bases (by name or emoji). Strip others."""
    cleaned = text
    for base in BOT_BASES:
        if base not in allowed_bases:
            emoji = BOT_EMOJIS.get(base, "")
            if emoji:
                cleaned = cleaned.replace(emoji, "")
            cleaned = re.sub(rf"\\b{re.escape(base)}\\b:?", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    cleaned = cleaned.strip()
    return cleaned or text

def _sanitize_ventriloquism(text: str, current_base: str) -> str:
    """Remove lines that script other bots; strip self-label prefixes; remove em dashes."""
    # Normalize em dashes to hyphens and collapse whitespace
    t = text.replace("—", "-")
    lines = [l for l in t.splitlines()]
    out_lines: list[str] = []
    for l in lines:
        raw = l.strip()
        if not raw:
            continue
        # Check for leading bot label e.g., "Rationalist:", "Empath -", etc.
        m = re.match(r"^(Empath|Rationalist|Challenger|Optimist)\s*[:\-–]?\s*(.*)$", raw, flags=re.IGNORECASE)
        if m:
            label = m.group(1).capitalize()
            rest = m.group(2).strip()
            if label != current_base:
                # Discard lines pretending to be other bots
                continue
            # Keep only the content, dropping self label
            raw = rest
        # Also remove inline self-referential prefixes like "Empath —" inside the line start
        raw = re.sub(rf"^(?:{re.escape(current_base)})\s*[:\-–]?\s*", "", raw, flags=re.IGNORECASE)
        if raw:
            out_lines.append(raw)
    if not out_lines:
        return t.strip()
    return "\n".join(out_lines)

# --- SQLite user database setup ---
REPO_ROOT = Path(__file__).parent
DB_PATH = REPO_ROOT / "user_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

def get_user_password_hash(username: str) -> str | None:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()

def create_user(username: str, password_hash: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    try:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # likely UNIQUE constraint failed
            return False
    finally:
        conn.close()

def get_session_id():
    sid = session.get("sid")
    if not sid:
        sid = uuid.uuid4().hex
        session["sid"] = sid
    return sid

def get_histories_for_session():
    sid = get_session_id()
    if sid not in HISTORIES:
        # initialize each bot with its system prompt
        HISTORIES[sid] = {
            bot: [{"role": "system", "content": prompt}] for bot, prompt in BOT_DEFS.items()
        }
    return HISTORIES[sid]

@app.route('/')
def index():
    return render_template('login_index.html')

# sign_in route defined later

@app.route('/signup', methods=['POST'])
def signup():
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    if not username or not password:
        return render_template('login_index.html', error='Please provide username and password.')
    pwd_hash = generate_password_hash(password)
    if not create_user(username, pwd_hash):
        return render_template('login_index.html', error='Username already exists. Try a different one or sign in.')
    session['user'] = username
    return redirect(url_for('chat'))

@app.route('/login', methods=['POST'])
def login():
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    if not username or not password:
        return render_template('sign_in.html', error='Please provide username and password.')
    pwd_hash = get_user_password_hash(username)
    if not pwd_hash or not check_password_hash(pwd_hash, password):
        return render_template('sign_in.html', error='Invalid username or password.')
    session['user'] = username
    return redirect(url_for('chat'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

@app.route('/sign_in')
def sign_in():
    return render_template('sign_in.html')

@app.after_request
def add_header(r):
    # Disable caching so CSS/JS/template edits show up on refresh during development
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r

# ---- Logs API ----
def _safe_log_files():
    try:
        if not LOGS_DIR.exists():
            return []
        files = [p for p in LOGS_DIR.glob('*.log') if p.is_file()]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files
    except Exception:
        return []

@app.get('/logs')
def list_logs():
    files = _safe_log_files()
    out = []
    for p in files:
        try:
            st = p.stat()
            # Read a small chunk to detect if there is real conversation content
            data = p.read_text(encoding='utf-8', errors='ignore')
            # Consider a log "empty" if it has no user or bot lines
            has_content = False
            for line in data.splitlines():
                s = line.strip()
                if s.startswith('[USER]'):
                    has_content = True; break
                if s.startswith('[Empath]') or s.startswith('[Rationalist]') or s.startswith('[Challenger]') or s.startswith('[Optimist]'):
                    has_content = True; break
            if not has_content:
                continue
            out.append({
                "name": p.name,
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec='seconds'),
                "size": st.st_size,
            })
        except Exception:
            continue
    return jsonify({"files": out})

@app.get('/logs/<name>')
def read_log(name: str):
    # Prevent directory traversal: only allow exact file in LOGS_DIR
    p = (LOGS_DIR / name).resolve()
    try:
        if LOGS_DIR.resolve() not in p.parents and LOGS_DIR.resolve() != p.parent:
            return jsonify({"error": "Invalid log path"}), 400
        if not p.exists() or not p.is_file():
            return jsonify({"error": "Not found"}), 404
        # Read tail up to ~6000 characters to avoid huge payloads
        data = p.read_text(encoding='utf-8', errors='ignore')
        if len(data) > 6000:
            data = data[-6000:]
        return jsonify({"name": name, "content": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    # Serve the chat UI on GET
    if request.method == 'GET':
        # On refresh, reset the in-memory transcript for this session and start a fresh log file
        sid = get_session_id()
        TRANSCRIPTS[sid] = []
        start_new_log_for_session()
        append_log_line("[SYS] Page refreshed — starting new conversation window")
        return render_template('index.html', username=session.get('user'))

    # Handle chat API on POST
    data = request.get_json(force=True) or {}
    user_text = (data.get('message') or '').strip()
    if not user_text:
        return jsonify({"error": "Empty message"}), 400

    # Record user message into transcript and log
    sid = get_session_id()
    TRANSCRIPTS.setdefault(sid, []).append({"role": "user", "text": user_text})
    append_log_line(f"[USER] {user_text}")

    # Build a random order for a sequential relay between bots
    bot_order = list(BOT_DEFS.keys())
    random.shuffle(bot_order)

    replies = []
    prev_chain = []  # list of tuples (bot_name, reply_text) for this request only

    for idx, bot_name in enumerate(bot_order, start=1):
        # Construct per-bot message list: pre-prompt (system), optional previous bot output, and the user prompt
        messages = [
            {"role": "system", "content": BOT_DEFS[bot_name]},
            {"role": "system", "content": (
                f"You are speaking #{idx} of {len(bot_order)} in a 4-bot relay. "
                "If a 'Previous discussion so far' block is provided, you may reference only bots mentioned there; otherwise, do NOT mention other bots or their views. "
                "Read the prior context if provided and either build on it or, occasionally, respectfully disagree. "
                "Keep it concise, avoid repetition, and use at most one newline. "
                "Do not discuss turn order or scheduling; just respond naturally."
            )},
        ]

        # Include full prior discussion (this session window) plus earlier bots from this same request
        prior_lines = []
        allowed_bases = set()
        for turn in TRANSCRIPTS.get(sid, []):
            role = turn.get("role")
            if role == "user":
                prior_lines.append(f"User: {turn.get('text','')}")
            else:
                bot_label = turn.get("bot", "")
                base = _base_name(bot_label) if bot_label else ""
                if base:
                    allowed_bases.add(base)
                prior_lines.append(f"{base or 'Assistant'}: {turn.get('text','')}")
        # Add earlier bots from current request so later speakers can see them
        for prev_bot_name, prev_text in prev_chain:
            base = _base_name(prev_bot_name)
            allowed_bases.add(base)
            prior_lines.append(f"{base}: {prev_text}")
        if prior_lines:
            messages.append({
                "role": "system",
                "content": "Previous discussion so far:\n" + "\n".join(prior_lines)
            })

        # Place the user's original prompt as the final user message
        messages.append({"role": "user", "content": user_text})

        try:
            resp = client.chat.completions.create(
                model="alibaba/qwen3-30b-a3b-instruct-2507",
                messages=messages,
            )
            reply_text = resp.choices[0].message.content
        except Exception as e:
            reply_text = f"Sorry, I couldn't respond right now. ({e})"

        # Sanitize reply to only allow references to bots present in provided context
        base_curr = _base_name(bot_name)
        safe_reply = _sanitize_reply(reply_text, allowed_bases)
        # Remove any lines that script other bots or use name labels; drop em dashes
        safe_reply = _sanitize_ventriloquism(safe_reply, base_curr)

        replies.append({"bot": bot_name, "message": safe_reply})
        # Track for later bots within this request
        prev_chain.append((bot_name, safe_reply))
        # Persist to session transcript and log in real-time
        TRANSCRIPTS[sid].append({"role": "assistant", "bot": bot_name, "text": safe_reply})
        append_log_line(f"[{_base_name(bot_name)}] {safe_reply}")

    return jsonify({"replies": replies})

if __name__ == '__main__':
    init_db()
    # Disable the reloader to avoid double-spawn timing issues on initial open
    app.run(debug=True, use_reloader=False)
if __name__ == '__main__':
    init_db()
    # Quick Railway fix
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
