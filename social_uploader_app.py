import streamlit as st
import json
import time
import hashlib
import secrets
from pathlib import Path
from cryptography.fernet import Fernet
from datetime import datetime, timedelta

# ─── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SocialBlast – Multi-Platform Uploader",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── File Paths ─────────────────────────────────────────────────────────────────
DATA_DIR    = Path("socialblast_data")
USERS_FILE  = DATA_DIR / "users.json"
CREDS_DIR   = DATA_DIR / "credentials"
KEY_FILE    = DATA_DIR / "secret.key"
TOKENS_FILE = DATA_DIR / "tokens.json"

DATA_DIR.mkdir(exist_ok=True)
CREDS_DIR.mkdir(exist_ok=True)

# ─── Encryption ─────────────────────────────────────────────────────────────────
def get_fernet():
    if not KEY_FILE.exists():
        KEY_FILE.write_bytes(Fernet.generate_key())
    return Fernet(KEY_FILE.read_bytes())

def encrypt_data(data: dict) -> bytes:
    return get_fernet().encrypt(json.dumps(data).encode())

def decrypt_data(token: bytes) -> dict:
    return json.loads(get_fernet().decrypt(token).decode())

# ─── User DB ─────────────────────────────────────────────────────────────────────
def load_users() -> dict:
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text())
    return {}

def save_users(users: dict):
    USERS_FILE.write_text(json.dumps(users, indent=2))

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def register_user(username: str, password: str, email: str):
    users = load_users()
    if username in users:
        return False, "Username already exists."
    if any(u["email"] == email for u in users.values()):
        return False, "An account with this email already exists."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if "@" not in email:
        return False, "Please enter a valid email address."
    users[username] = {
        "password": hash_password(password),
        "email": email,
        "name": username,
        "created": now_str(),
        "last_login": None,
        "login_count": 0,
        "upload_count": 0,
    }
    save_users(users)
    return True, "Account created successfully!"

def login_user(username: str, password: str):
    users = load_users()
    if username not in users:
        return False, "Username not found."
    if users[username]["password"] != hash_password(password):
        return False, "Incorrect password."
    users[username]["last_login"] = now_str()
    users[username]["login_count"] = users[username].get("login_count", 0) + 1
    save_users(users)
    return True, "Login successful!"

# ─── Token System (auto-login) ────────────────────────────────────────────────
TOKEN_EXPIRY_DAYS = 30

def load_tokens() -> dict:
    if TOKENS_FILE.exists():
        return json.loads(TOKENS_FILE.read_text())
    return {}

def save_tokens(tokens: dict):
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2))

def create_token(username: str) -> str:
    token = secrets.token_urlsafe(32)
    tokens = load_tokens()
    expiry = (datetime.now() + timedelta(days=TOKEN_EXPIRY_DAYS)).strftime("%Y-%m-%d")
    tokens[token] = {"username": username, "expiry": expiry}
    save_tokens(tokens)
    return token

def validate_token(token: str):
    if not token:
        return None
    tokens = load_tokens()
    entry = tokens.get(token)
    if not entry:
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    if entry.get("expiry", "0000") < today:
        tokens.pop(token, None)
        save_tokens(tokens)
        return None
    return entry.get("username")

def delete_token(token: str):
    tokens = load_tokens()
    tokens.pop(token, None)
    save_tokens(tokens)

# ─── Credential Storage ──────────────────────────────────────────────────────
def load_user_creds(username: str) -> dict:
    cred_file = CREDS_DIR / f"{username}.enc"
    if cred_file.exists():
        try:
            return decrypt_data(cred_file.read_bytes())
        except Exception:
            pass
    return {
        "youtube":   {"connected": False, "api_key": "", "client_id": "", "client_secret": ""},
        "instagram": {"connected": False, "access_token": "", "ig_user_id": ""},
        "tiktok":    {"connected": False, "client_key": "", "client_secret": ""},
        "facebook":  {"connected": False, "access_token": "", "page_id": ""},
    }

def save_user_creds(username: str, creds: dict):
    cred_file = CREDS_DIR / f"{username}.enc"
    cred_file.write_bytes(encrypt_data(creds))

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600&display=swap');

*, *::before, *::after {
    font-family: 'Inter', -apple-system, sans-serif;
}

html, body, [class*="css"] {
    background: #050508 !important;
    color: #f0f0f8 !important;
}

.stApp {
    background: #050508 !important;
}

#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }

.block-container {
    padding-top: 1.5rem !important;
    max-width: 1380px;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #08080f 0%, #0d0d18 100%) !important;
    border-right: 1px solid #1a1a2e !important;
}

section[data-testid="stSidebar"] * {
    color: #d4d4e8 !important;
}

/* ── Header ── */
.hero-header {
    background: linear-gradient(135deg, #050508 0%, #0d0d1a 60%, #050508 100%);
    border: 1px solid rgba(130, 80, 255, 0.25);
    border-radius: 20px;
    padding: 2.5rem 3rem;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
}

.hero-header::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse 80% 60% at 10% 50%, rgba(130,80,255,0.12) 0%, transparent 60%);
    animation: pulseGlow 6s ease-in-out infinite alternate;
}

@keyframes pulseGlow {
    from { opacity: 0.6; }
    to   { opacity: 1;   }
}

.hero-header h1 {
    font-size: 2.8rem;
    font-weight: 900;
    margin: 0;
    letter-spacing: -0.03em;
    line-height: 1.1;
    background: linear-gradient(135deg, #8250ff 0%, #a78bfa 40%, #60a5fa 80%, #34d399 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.hero-header .tagline {
    color: #888;
    font-size: 1rem;
    margin-top: 0.5rem;
}

.pill-row { display: flex; gap: .5rem; margin-top: 1rem; flex-wrap: wrap; }
.pill {
    display: inline-flex; align-items: center; gap: .3rem;
    padding: .25rem .8rem; border-radius: 999px;
    font-size: .68rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
}
.pill-purple { background: rgba(130,80,255,0.15); color: #a78bfa; border: 1px solid rgba(130,80,255,0.35); }
.pill-blue   { background: rgba(96,165,250,0.12);  color: #60a5fa; border: 1px solid rgba(96,165,250,0.30); }
.pill-green  { background: rgba(52,211,153,0.12);  color: #34d399; border: 1px solid rgba(52,211,153,0.30); }

/* ── Auth Card ── */
.auth-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 22px;
    padding: 2.75rem 2.5rem;
    max-width: 460px;
    margin: 1.5rem auto;
}

.auth-title {
    font-size: 1.8rem;
    font-weight: 900;
    background: linear-gradient(135deg, #8250ff, #60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    text-align: center;
    margin-bottom: 0.2rem;
}

.auth-sub {
    color: #555;
    font-size: 0.875rem;
    text-align: center;
    margin-bottom: 1.75rem;
}

/* ── Cards ── */
.platform-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 1.1rem 1.4rem;
    margin-bottom: 0.75rem;
}

.info-box {
    background: rgba(96,165,250,0.07);
    border: 1px solid rgba(96,165,250,0.25);
    border-radius: 12px;
    padding: .9rem 1.1rem;
    font-size: .875rem;
    color: #93c5fd;
    margin: 0.75rem 0;
}

.warn-box {
    background: rgba(245,158,11,0.07);
    border: 1px solid rgba(245,158,11,0.25);
    border-radius: 12px;
    padding: .9rem 1.1rem;
    font-size: .875rem;
    color: #fcd34d;
    margin: 0.75rem 0;
}

.glow-divider {
    height: 1px;
    margin: 1.5rem 0;
    background: linear-gradient(90deg, transparent, #8250ff, #60a5fa, transparent);
    opacity: .3;
}

.user-badge {
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    background: rgba(130,80,255,0.15);
    border: 1px solid rgba(130,80,255,0.35);
    border-radius: 20px;
    padding: .35rem 1rem;
    font-size: .82rem;
    color: #c4b5fd;
    font-weight: 700;
}

/* ── Buttons ── */
.stButton > button {
    font-family: 'Inter', sans-serif !important;
    font-weight: 700 !important;
    border-radius: 12px !important;
    border: none !important;
    transition: all 0.2s ease !important;
    background: linear-gradient(135deg, #6d28d9, #8b5cf6) !important;
    color: #fff !important;
    box-shadow: 0 4px 16px rgba(130,80,255,0.35) !important;
}

.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 24px rgba(130,80,255,0.45) !important;
    filter: brightness(1.08) !important;
}

/* ── Inputs ── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important;
    color: #f0f0f8 !important;
}

.stTextInput > div > div > input:focus {
    border-color: #8250ff !important;
    box-shadow: 0 0 0 3px rgba(130,80,255,0.15) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 14px !important;
    padding: 5px !important;
    gap: 4px !important;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 10px !important;
    font-weight: 600 !important;
    border: none !important;
    color: #666 !important;
    background: transparent !important;
    padding: .6rem 1.3rem !important;
}

.stTabs [data-baseweb="tab"]:hover {
    background: rgba(255,255,255,0.05) !important;
    color: #d4d4e8 !important;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #6d28d9, #8b5cf6) !important;
    color: #fff !important;
    box-shadow: 0 4px 14px rgba(130,80,255,0.4) !important;
}

/* ── Progress ── */
.stProgress > div > div > div {
    background: linear-gradient(90deg, #8250ff, #60a5fa) !important;
}

/* ── Status badges ── */
.badge-connected {
    background: rgba(52,211,153,0.12);
    color: #34d399;
    border: 1px solid rgba(52,211,153,0.3);
    padding: 3px 10px;
    border-radius: 20px;
    font-size: .73rem;
    font-weight: 700;
}

.badge-disconnected {
    background: rgba(239,68,68,0.12);
    color: #f87171;
    border: 1px solid rgba(239,68,68,0.3);
    padding: 3px 10px;
    border-radius: 20px;
    font-size: .73rem;
    font-weight: 700;
}

@keyframes slideUp {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: none; }
}
.slide-up { animation: slideUp .4s ease-out both; }

/* Hide file uploader label overlap */
[data-testid="stFileUploader"] > div {
    border: 2px dashed rgba(130,80,255,0.35) !important;
    border-radius: 12px !important;
    background: rgba(130,80,255,0.04) !important;
}
</style>
""", unsafe_allow_html=True)

# ─── Session State ────────────────────────────────────────────────────────────
for k, v in [
    ("authenticated", False), ("username", ""), ("credentials", {}),
    ("upload_log", []), ("auth_mode", "signin"), ("login_token", None),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ─── Auto-login via token ─────────────────────────────────────────────────────
if not st.session_state.authenticated:
    try:
        saved_token = st.query_params.get("token", None)
        if saved_token:
            uname = validate_token(saved_token)
            if uname:
                users = load_users()
                if uname in users:
                    st.session_state.authenticated = True
                    st.session_state.username      = uname
                    st.session_state.credentials   = load_user_creds(uname)
                    st.session_state.login_token   = saved_token
    except Exception:
        pass

PLATFORMS = {
    "youtube":   {"emoji": "▶️",  "name": "YouTube"},
    "instagram": {"emoji": "📸",  "name": "Instagram"},
    "tiktok":    {"emoji": "🎵",  "name": "TikTok"},
    "facebook":  {"emoji": "📘",  "name": "Facebook"},
}

# ══════════════════════════════════════════════════════════════════════════════
#  AUTH SCREEN
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.authenticated:

    # Hide sidebar on auth screen
    st.markdown("""
    <style>
    section[data-testid="stSidebar"] { display: none !important; }
    .block-container { padding: 0 !important; max-width: 100% !important; }
    </style>""", unsafe_allow_html=True)

    _, center, _ = st.columns([1, 1.1, 1])
    with center:
        st.markdown("""
        <div style="text-align:center; padding: 3rem 0 1rem">
            <div style="font-size: 3.5rem; margin-bottom: .5rem">🚀</div>
            <h1 style="font-size: 2.1rem; font-weight: 900; margin: 0 0 .3rem;
                background: linear-gradient(135deg, #8250ff, #60a5fa, #34d399);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                background-clip: text">SocialBlast</h1>
            <p style="color: #555; font-size: .9rem; margin: 0">
                Upload once — post everywhere. YouTube · Instagram · TikTok · Facebook
            </p>
        </div>""", unsafe_allow_html=True)

        # Tab selector
        col_l, col_r = st.columns(2)
        with col_l:
            if st.button("🔑  Sign In", use_container_width=True,
                         type="primary" if st.session_state.auth_mode == "signin" else "secondary"):
                st.session_state.auth_mode = "signin"
                st.rerun()
        with col_r:
            if st.button("✨  Create Account", use_container_width=True,
                         type="primary" if st.session_state.auth_mode == "signup" else "secondary"):
                st.session_state.auth_mode = "signup"
                st.rerun()

        st.markdown("<div class='glow-divider'></div>", unsafe_allow_html=True)

        # ── SIGN IN ──────────────────────────────────────────────────────────
        if st.session_state.auth_mode == "signin":
            st.markdown("<div class='auth-card'>", unsafe_allow_html=True)
            st.markdown(
                "<div class='auth-title'>Welcome Back 👋</div>"
                "<div class='auth-sub'>Sign in to your SocialBlast account</div>",
                unsafe_allow_html=True
            )

            si_user = st.text_input("Username", placeholder="Your username", key="si_user")
            si_pass = st.text_input("Password", placeholder="••••••••", type="password", key="si_pass")
            st.markdown("")

            if st.button("Sign In & Launch  →", use_container_width=True, type="primary", key="do_signin"):
                si_user = st.session_state.get("si_user", "").strip()
                si_pass = st.session_state.get("si_pass", "")
                if si_user and si_pass:
                    ok, msg = login_user(si_user, si_pass)
                    if ok:
                        st.session_state.authenticated = True
                        st.session_state.username      = si_user
                        st.session_state.credentials   = load_user_creds(si_user)
                        token = create_token(si_user)
                        st.session_state.login_token   = token
                        try:
                            st.query_params["token"] = token
                        except Exception:
                            pass
                        st.success(f"✅ {msg}")
                        time.sleep(0.6)
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")
                else:
                    st.warning("Please fill in both fields.")

            st.markdown("</div>", unsafe_allow_html=True)

        # ── SIGN UP ──────────────────────────────────────────────────────────
        else:
            st.markdown("<div class='auth-card'>", unsafe_allow_html=True)
            st.markdown(
                "<div class='auth-title'>Create Account ✨</div>"
                "<div class='auth-sub'>Join SocialBlast — it's completely free</div>",
                unsafe_allow_html=True
            )

            st.text_input("Username",         placeholder="Choose a unique username",  key="r_user")
            st.text_input("Email Address",    placeholder="you@example.com",           key="r_email")
            st.text_input("Password",         placeholder="Min. 6 characters",         type="password", key="r_pass")
            st.text_input("Confirm Password", placeholder="Repeat your password",      type="password", key="r_pass2")
            st.markdown("")

            if st.button("Create Account & Get Started  →", use_container_width=True, type="primary", key="do_signup"):
                # Read directly from session_state — reliable after button click
                _user  = st.session_state.get("r_user", "").strip()
                _email = st.session_state.get("r_email", "").strip()
                _pass  = st.session_state.get("r_pass", "")
                _pass2 = st.session_state.get("r_pass2", "")

                if not (_user and _email and _pass and _pass2):
                    st.warning("Please fill in all fields.")
                elif _pass != _pass2:
                    st.error("❌ Passwords do not match.")
                else:
                    ok, msg = register_user(_user, _pass, _email)
                    if ok:
                        st.session_state.authenticated = True
                        st.session_state.username      = _user
                        st.session_state.credentials   = load_user_creds(_user)
                        token = create_token(_user)
                        st.session_state.login_token   = token
                        try:
                            st.query_params["token"] = token
                        except Exception:
                            pass
                        st.success(f"✅ {msg} Welcome aboard!")
                        time.sleep(0.6)
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")

            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown(
            f'<div style="text-align:center; margin-top:1.5rem; font-size:.78rem; color:#444">'
            f'🔒 Your data is stored securely and encrypted on the server</div>',
            unsafe_allow_html=True
        )

    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP  (authenticated)
# ══════════════════════════════════════════════════════════════════════════════
creds   = st.session_state.credentials if st.session_state.credentials else {}
uname   = st.session_state.username or ""
users   = load_users()
udata   = users.get(uname) or {}

# Safety: if uname not found in DB (e.g. after DB reset), log out
if uname and uname not in users:
    for k in ["authenticated","username","credentials","upload_log","login_token"]:
        st.session_state[k] = False if k == "authenticated" else "" if k in ["username","login_token"] else {} if k == "credentials" else []
    st.rerun()

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div class='user-badge'>👤 {uname}</div>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-size:.72rem;color:#555;margin:.35rem 0 .9rem">'
        f'📧 {udata.get("email","—")} &nbsp;·&nbsp; '
        f'Joined {(udata.get("created") or "—")[:10]}</div>',
        unsafe_allow_html=True
    )

    if st.button("🚪 Sign Out", use_container_width=True):
        tok = st.session_state.get("login_token")
        if tok:
            delete_token(tok)
        try:
            st.query_params.clear()
        except Exception:
            pass
        for k in ["authenticated","username","credentials","upload_log","login_token"]:
            st.session_state[k] = False if k == "authenticated" else "" if k in ["username","login_token"] else {} if k == "credentials" else []
        st.rerun()

    st.markdown("<div class='glow-divider'></div>", unsafe_allow_html=True)

    # ── Usage Stats ──
    login_count  = udata.get("login_count", 0)
    upload_count = udata.get("upload_count", 0)
    st.markdown(f"""
    <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07);
                border-radius: 12px; padding: .9rem 1rem; margin-bottom: 1rem;">
      <div style="font-size: .62rem; font-weight: 800; text-transform: uppercase;
                  letter-spacing: .08em; color: #555; margin-bottom: .65rem;">📊 Your Stats</div>
      <div style="display: flex; justify-content: space-between; margin-bottom: .35rem;">
        <span style="font-size: .75rem; color: #888;">🔑 Total Sign Ins</span>
        <span style="font-size: .8rem; font-weight: 800; color: #a78bfa; font-family: monospace">{login_count}</span>
      </div>
      <div style="display: flex; justify-content: space-between; margin-bottom: .35rem;">
        <span style="font-size: .75rem; color: #888;">📤 Posts Uploaded</span>
        <span style="font-size: .8rem; font-weight: 800; color: #34d399; font-family: monospace">{upload_count}</span>
      </div>
      <div style="display: flex; justify-content: space-between;">
        <span style="font-size: .75rem; color: #888;">📅 Last Login</span>
        <span style="font-size: .73rem; color: #666; font-family: monospace">{(udata.get("last_login") or "—")[:10]}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Platform Credentials ──
    st.markdown("""
    <div style="font-size: .62rem; font-weight: 800; text-transform: uppercase;
                letter-spacing: .1em; color: #8250ff; margin-bottom: .6rem;">
        🔑 Platform Credentials
    </div>""", unsafe_allow_html=True)

    st.markdown(
        "<div class='info-box' style='font-size:.8rem'>"
        "🔒 Credentials are encrypted and saved — no need to re-enter them each session!"
        "</div>",
        unsafe_allow_html=True
    )

    creds_changed = False

    with st.expander("▶️  YouTube"):
        st.markdown("[Get API keys →](https://console.cloud.google.com)", unsafe_allow_html=True)
        yt_api = st.text_input("API Key",       value=creds["youtube"].get("api_key",""),       type="password", key="yt_api")
        yt_cid = st.text_input("Client ID",     value=creds["youtube"].get("client_id",""),     key="yt_cid")
        yt_cs  = st.text_input("Client Secret", value=creds["youtube"].get("client_secret",""), type="password", key="yt_cs")
        if st.button("💾 Save YouTube", key="save_yt"):
            if yt_api or (yt_cid and yt_cs):
                creds["youtube"] = {"connected": True, "api_key": yt_api, "client_id": yt_cid, "client_secret": yt_cs}
                creds_changed = True
                st.success("Saved! ✅")
            else:
                st.error("API Key or Client credentials required.")

    with st.expander("📸  Instagram"):
        st.markdown("[Get token →](https://developers.facebook.com)", unsafe_allow_html=True)
        ig_token = st.text_input("Access Token",      value=creds["instagram"].get("access_token",""), type="password", key="ig_token")
        ig_uid   = st.text_input("Instagram User ID", value=creds["instagram"].get("ig_user_id",""),   key="ig_uid")
        if st.button("💾 Save Instagram", key="save_ig"):
            if ig_token and ig_uid:
                creds["instagram"] = {"connected": True, "access_token": ig_token, "ig_user_id": ig_uid}
                creds_changed = True
                st.success("Saved! ✅")
            else:
                st.error("Both Token and User ID are required.")

    with st.expander("🎵  TikTok"):
        st.markdown("[Get keys →](https://developers.tiktok.com)", unsafe_allow_html=True)
        tt_ck = st.text_input("Client Key",    value=creds["tiktok"].get("client_key",""),    key="tt_ck")
        tt_cs = st.text_input("Client Secret", value=creds["tiktok"].get("client_secret",""), type="password", key="tt_cs")
        if st.button("💾 Save TikTok", key="save_tt"):
            if tt_ck and tt_cs:
                creds["tiktok"] = {"connected": True, "client_key": tt_ck, "client_secret": tt_cs}
                creds_changed = True
                st.success("Saved! ✅")
            else:
                st.error("Both Key and Secret are required.")

    with st.expander("📘  Facebook"):
        st.markdown("[Get token →](https://developers.facebook.com/tools/explorer)", unsafe_allow_html=True)
        fb_token = st.text_input("Page Access Token", value=creds["facebook"].get("access_token",""), type="password", key="fb_token")
        fb_pid   = st.text_input("Page ID",           value=creds["facebook"].get("page_id",""),      key="fb_pid")
        if st.button("💾 Save Facebook", key="save_fb"):
            if fb_token and fb_pid:
                creds["facebook"] = {"connected": True, "access_token": fb_token, "page_id": fb_pid}
                creds_changed = True
                st.success("Saved! ✅")
            else:
                st.error("Both Token and Page ID are required.")

    if creds_changed:
        save_user_creds(uname, creds)
        st.session_state.credentials = creds

    st.markdown("<div class='glow-divider'></div>", unsafe_allow_html=True)

    # ── Connection Status ──
    st.markdown("""
    <div style="font-size: .62rem; font-weight: 800; text-transform: uppercase;
                letter-spacing: .1em; color: #555; margin-bottom: .6rem;">
        📡 Connection Status
    </div>""", unsafe_allow_html=True)

    for pid, pdata in PLATFORMS.items():
        connected = creds[pid]["connected"]
        dot  = "🟢" if connected else "🔴"
        txt  = "Connected" if connected else "Not connected"
        col  = "#34d399" if connected else "#f87171"
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:.3rem 0;border-bottom:1px solid #111;">'
            f'<span style="font-size:.8rem;color:#aaa">{pdata["emoji"]} {pdata["name"]}</span>'
            f'<span style="font-size:.72rem;font-weight:700;color:{col}">{dot} {txt}</span>'
            f'</div>',
            unsafe_allow_html=True
        )

# ── Main Header ──────────────────────────────────────────────────────────────
_c1, _c2 = st.columns([9, 1])
with _c1:
    st.markdown(f"""
    <div class="hero-header slide-up">
        <h1>🚀 SocialBlast</h1>
        <p class="tagline">
            Welcome back, <b style="color:#c4b5fd">{uname}</b>!
            Upload once — publish to YouTube, Instagram, TikTok & Facebook in one click.
        </p>
        <div class="pill-row">
            <span class="pill pill-purple">✦ Multi-Platform</span>
            <span class="pill pill-blue">⚡ One Click Upload</span>
            <span class="pill pill-green">🔒 Encrypted Credentials</span>
            <span class="pill pill-purple">📊 Upload History</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
with _c2:
    if st.button("🚪 Logout", key="top_logout"):
        tok = st.session_state.get("login_token")
        if tok:
            delete_token(tok)
        try:
            st.query_params.clear()
        except Exception:
            pass
        for k in ["authenticated","username","credentials","upload_log","login_token"]:
            st.session_state[k] = False if k == "authenticated" else "" if k in ["username","login_token"] else {} if k == "credentials" else []
        st.rerun()

# ── Main Tabs ────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📤  Upload & Post", "📋  Upload History", "📖  Setup Guide"])

# ════════════════════════════════════════════════════════════════════════════
#  TAB 1 — Upload & Post
# ════════════════════════════════════════════════════════════════════════════
with tab1:

    col_left, col_right = st.columns([1.2, 1], gap="large")

    with col_left:
        st.markdown("#### 📁 Upload Your File")
        uploaded_file = st.file_uploader(
            "Drag & drop or click to browse",
            type=["mp4","mov","avi","mkv","jpg","jpeg","png","gif","webp"],
            help="Supported formats: MP4, MOV, AVI, MKV, JPG, PNG, GIF, WEBP"
        )

        if uploaded_file:
            ext      = Path(uploaded_file.name).suffix.lower()
            is_video = ext in [".mp4",".mov",".avi",".mkv"]
            st.markdown(f"""
            <div class='platform-card'>
                <b style="color:#f0f0f8">{'🎬 Video' if is_video else '🖼️ Image'}</b>: {uploaded_file.name}<br>
                <span style='color:#666; font-size:.82rem'>
                    Size: {uploaded_file.size/1024:.1f} KB &nbsp;·&nbsp; Type: {uploaded_file.type}
                </span>
            </div>""", unsafe_allow_html=True)

            if is_video:
                st.video(uploaded_file)
            else:
                st.image(uploaded_file, use_container_width=True)

    with col_right:
        st.markdown("#### ✍️ Post Details")
        post_title   = st.text_input("Title",    placeholder="Enter your post title...")
        post_caption = st.text_area("Caption",   placeholder="Write a caption or description...", height=100)
        post_tags    = st.text_input("Hashtags", placeholder="#trending #viral #fyp")
        post_privacy = st.selectbox("Privacy",   ["Public", "Unlisted", "Private"])

        st.markdown("#### 🎯 Select Platforms")
        pc1, pc2 = st.columns(2)
        with pc1:
            sel_yt = st.checkbox("▶️ YouTube",   value=True)
            sel_ig = st.checkbox("📸 Instagram", value=True)
        with pc2:
            sel_tt = st.checkbox("🎵 TikTok",    value=True)
            sel_fb = st.checkbox("📘 Facebook",  value=True)

    st.markdown("<div class='glow-divider'></div>", unsafe_allow_html=True)

    if st.button("🚀 Publish to All Selected Platforms", use_container_width=True, type="primary"):
        if not uploaded_file:
            st.error("⚠️ Please upload a file first.")
        elif not post_title:
            st.error("⚠️ Please enter a title for your post.")
        else:
            selected   = {"youtube": sel_yt, "instagram": sel_ig, "tiktok": sel_tt, "facebook": sel_fb}
            active     = [p for p, s in selected.items() if s]
            connected  = [p for p in active if creds[p]["connected"]]
            no_cred    = [p for p in active if not creds[p]["connected"]]

            if no_cred:
                names = ", ".join([PLATFORMS[p]["name"] for p in no_cred])
                st.markdown(
                    f"<div class='warn-box'>⚠️ <b>{names}</b> — credentials not saved. "
                    f"Add them in the sidebar first. These platforms will be skipped.</div>",
                    unsafe_allow_html=True
                )

            if not active:
                st.error("Please select at least one platform.")
            elif not connected:
                st.error("None of the selected platforms have credentials saved. Please add them in the sidebar.")
            else:
                st.markdown("#### 📡 Publishing...")
                progress    = st.progress(0)
                status_area = st.empty()
                log_entry   = {
                    "file": uploaded_file.name,
                    "title": post_title,
                    "privacy": post_privacy,
                    "results": {},
                    "time": now_str()
                }

                for i, pid in enumerate(connected):
                    pname = PLATFORMS[pid]["name"]
                    status_area.info(f"Uploading to **{pname}**... ({i+1}/{len(connected)})")
                    time.sleep(1.2)

                    # ── Real API stubs ────────────────────────────────────────
                    # Uncomment and complete these once you have real credentials:

                    # ── YouTube ──
                    # if pid == "youtube":
                    #     from googleapiclient.discovery import build
                    #     from googleapiclient.http import MediaIoBaseUpload
                    #     import io
                    #     c = creds["youtube"]
                    #     youtube = build('youtube', 'v3', developerKey=c["api_key"])
                    #     media = MediaIoBaseUpload(io.BytesIO(uploaded_file.read()), mimetype=uploaded_file.type)
                    #     youtube.videos().insert(
                    #         part="snippet,status",
                    #         body={
                    #             "snippet": {"title": post_title, "description": post_caption, "tags": post_tags.split()},
                    #             "status": {"privacyStatus": post_privacy.lower()}
                    #         },
                    #         media_body=media
                    #     ).execute()

                    # ── Instagram ──
                    # if pid == "instagram":
                    #     import requests
                    #     c = creds["instagram"]
                    #     # Requires a publicly accessible URL — use Cloudinary or AWS S3
                    #     r = requests.post(
                    #         f"https://graph.facebook.com/v18.0/{c['ig_user_id']}/media",
                    #         params={"image_url": YOUR_PUBLIC_URL, "caption": post_caption, "access_token": c["access_token"]}
                    #     )
                    #     container_id = r.json().get("id")
                    #     requests.post(
                    #         f"https://graph.facebook.com/v18.0/{c['ig_user_id']}/media_publish",
                    #         params={"creation_id": container_id, "access_token": c["access_token"]}
                    #     )

                    # ── Facebook ──
                    # if pid == "facebook":
                    #     import requests
                    #     c = creds["facebook"]
                    #     requests.post(
                    #         f"https://graph.facebook.com/v18.0/{c['page_id']}/photos",
                    #         data={"caption": post_caption, "access_token": c["access_token"]},
                    #         files={"source": uploaded_file.read()}
                    #     )

                    # ── TikTok ──
                    # if pid == "tiktok":
                    #     # TikTok requires full OAuth 2.0 user token flow
                    #     # Then POST to: https://open.tiktokapis.com/v2/post/publish/video/init/
                    #     pass

                    log_entry["results"][pid] = "✅ Success (Simulated)"
                    progress.progress((i + 1) / len(connected))

                # Save log
                st.session_state.upload_log.append(log_entry)

                # Update upload count
                users_upd = load_users()
                if uname in users_upd:
                    users_upd[uname]["upload_count"] = users_upd[uname].get("upload_count", 0) + 1
                    save_users(users_upd)

                status_area.success(
                    f"🎉 Published successfully to **{len(connected)} platform(s)**!"
                )

                st.markdown("#### 📊 Publish Summary")
                for pid, result in log_entry["results"].items():
                    st.markdown(
                        f"- {PLATFORMS[pid]['emoji']} **{PLATFORMS[pid]['name']}**: {result}"
                    )

                st.markdown(
                    "<div class='warn-box'>"
                    "⚠️ <b>Note:</b> This is currently running in <b>simulated mode</b>. "
                    "To enable real uploads, save your API credentials in the sidebar and "
                    "uncomment the API sections in the source code."
                    "</div>",
                    unsafe_allow_html=True
                )

# ════════════════════════════════════════════════════════════════════════════
#  TAB 2 — Upload History
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("#### 📋 Your Upload History")

    if not st.session_state.upload_log:
        st.markdown(f"""
        <div style="text-align:center; padding:3rem; background:rgba(255,255,255,0.02);
                    border:1px solid #111; border-radius:18px;">
            <div style="font-size:3.5rem; margin-bottom:.75rem; opacity:.3">📭</div>
            <div style="font-size:1.1rem; font-weight:700; color:#aaa;">No uploads yet</div>
            <div style="color:#555; font-size:.875rem; margin-top:.3rem;">
                Go to the Upload & Post tab to publish your first piece of content!
            </div>
        </div>""", unsafe_allow_html=True)
    else:
        for entry in reversed(st.session_state.upload_log):
            with st.expander(f"📁 {entry['file']}  ·  {entry['time']}  ·  [{entry.get('privacy','Public')}]"):
                st.markdown(f"**Title:** {entry['title']}")
                for pid, result in entry["results"].items():
                    st.markdown(f"- {PLATFORMS[pid]['emoji']} **{PLATFORMS[pid]['name']}**: {result}")

# ════════════════════════════════════════════════════════════════════════════
#  TAB 3 — Setup Guide
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("## 📖 Setup Guide — Enabling Real API Uploads")

    st.markdown("""
### 1️⃣ YouTube
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project → Enable **YouTube Data API v3**
3. Under **Credentials**, create an OAuth 2.0 Client ID
4. Copy the Client ID + Client Secret → save in sidebar
5. Install: `pip install google-api-python-client google-auth-oauthlib`

---
### 2️⃣ Instagram
1. Go to [Meta for Developers](https://developers.facebook.com)
2. Create a **Business App** → Add **Instagram Graph API**
3. Generate a long-lived **Access Token**
4. Copy your **Instagram User ID** from the API Explorer
5. Save both in the sidebar

> ⚠️ Instagram requires a **publicly accessible URL** for media files.
> Use [Cloudinary](https://cloudinary.com) or AWS S3 to host the file first.

---
### 3️⃣ TikTok
1. Go to [TikTok for Developers](https://developers.tiktok.com)
2. Register your app → Enable **Content Posting API**
3. Copy **Client Key** and **Client Secret** → save in sidebar
4. Complete the OAuth 2.0 flow to get a user access token

---
### 4️⃣ Facebook
1. Go to [Meta Graph API Explorer](https://developers.facebook.com/tools/explorer)
2. Select your app → Generate a **Page Access Token**
3. Required permissions: `pages_manage_posts`, `pages_read_engagement`
4. Find your **Page ID** from your Facebook page settings
5. Save both in the sidebar

---
### 📦 Install Required Packages
```bash
pip install streamlit cryptography google-api-python-client google-auth-oauthlib requests
```

### ▶️ Run the App
```bash
streamlit run social_uploader_app.py
```
    """)

    st.markdown("""
    <div class='warn-box'>
    ⚠️ <b>Instagram & TikTok Note:</b> These platforms require media files to have a
    publicly accessible HTTPS URL — you cannot upload local files directly.
    Use <b>Cloudinary</b>, <b>AWS S3</b>, or <b>Firebase Storage</b> to host the file
    temporarily and pass the URL to the API.
    </div>
    """, unsafe_allow_html=True)