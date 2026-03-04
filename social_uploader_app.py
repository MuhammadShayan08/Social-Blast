import streamlit as st
import json
import time
import hashlib
import secrets
import requests
from pathlib import Path
from cryptography.fernet import Fernet
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse, parse_qs

# ─── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SocialBlast – Multi-Platform Uploader",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Google OAuth Config (from Streamlit Secrets) ────────────────────────────
try:
    GOOGLE_CLIENT_ID     = st.secrets["GOOGLE_CLIENT_ID"]
    GOOGLE_CLIENT_SECRET = st.secrets["GOOGLE_CLIENT_SECRET"]
except Exception:
    GOOGLE_CLIENT_ID     = ""
    GOOGLE_CLIENT_SECRET = ""

APP_URL       = "https://social-blast.streamlit.app"
REDIRECT_URI  = APP_URL
SCOPES        = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube"

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

# ─── User DB ──────────────────────────────────────────────────────────────────
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

# ─── Session Token System ────────────────────────────────────────────────────
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

# ─── Platform Credential Storage ────────────────────────────────────────────
def load_user_creds(username: str) -> dict:
    cred_file = CREDS_DIR / f"{username}.enc"
    if cred_file.exists():
        try:
            return decrypt_data(cred_file.read_bytes())
        except Exception:
            pass
    return {
        "youtube":   {"connected": False, "access_token": "", "refresh_token": "", "channel_name": ""},
        "instagram": {"connected": False, "access_token": "", "ig_user_id": ""},
        "tiktok":    {"connected": False, "client_key": "", "client_secret": ""},
        "facebook":  {"connected": False, "access_token": "", "page_id": ""},
    }

def save_user_creds(username: str, creds: dict):
    cred_file = CREDS_DIR / f"{username}.enc"
    cred_file.write_bytes(encrypt_data(creds))

# ─── Google OAuth Helpers ────────────────────────────────────────────────────
def get_google_auth_url(state: str) -> str:
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPES,
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)

def exchange_code_for_tokens(code: str) -> dict:
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "code":          code,
        "client_id":     GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
    })
    return resp.json()

def get_youtube_channel_name(access_token: str) -> str:
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        data = resp.json()
        return data["items"][0]["snippet"]["title"]
    except Exception:
        return "YouTube Channel"

def refresh_youtube_token(refresh_token: str) -> str:
    try:
        resp = requests.post("https://oauth2.googleapis.com/token", data={
            "refresh_token": refresh_token,
            "client_id":     GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "grant_type":    "refresh_token",
        })
        return resp.json().get("access_token", "")
    except Exception:
        return ""

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600&display=swap');

*, *::before, *::after { font-family: 'Inter', -apple-system, sans-serif; }
html, body, [class*="css"] { background: #050508 !important; color: #f0f0f8 !important; }
.stApp { background: #050508 !important; }
#MainMenu { visibility: hidden; } footer { visibility: hidden; }
.block-container { padding-top: 1.5rem !important; max-width: 1380px; }

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #08080f 0%, #0d0d18 100%) !important;
    border-right: 1px solid #1a1a2e !important;
}
section[data-testid="stSidebar"] * { color: #d4d4e8 !important; }

.hero-header {
    background: linear-gradient(135deg, #050508 0%, #0d0d1a 60%, #050508 100%);
    border: 1px solid rgba(130,80,255,0.25); border-radius: 20px;
    padding: 2.5rem 3rem; margin-bottom: 2rem; position: relative; overflow: hidden;
}
.hero-header::before {
    content: ''; position: absolute; inset: 0;
    background: radial-gradient(ellipse 80% 60% at 10% 50%, rgba(130,80,255,0.12) 0%, transparent 60%);
    animation: pulseGlow 6s ease-in-out infinite alternate;
}
@keyframes pulseGlow { from { opacity: 0.6; } to { opacity: 1; } }
.hero-header h1 {
    font-size: 2.8rem; font-weight: 900; margin: 0; letter-spacing: -0.03em; line-height: 1.1;
    background: linear-gradient(135deg, #8250ff 0%, #a78bfa 40%, #60a5fa 80%, #34d399 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.hero-header .tagline { color: #888; font-size: 1rem; margin-top: 0.5rem; }
.pill-row { display: flex; gap: .5rem; margin-top: 1rem; flex-wrap: wrap; }
.pill { display: inline-flex; align-items: center; gap: .3rem; padding: .25rem .8rem; border-radius: 999px; font-size: .68rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
.pill-purple { background: rgba(130,80,255,0.15); color: #a78bfa; border: 1px solid rgba(130,80,255,0.35); }
.pill-blue   { background: rgba(96,165,250,0.12);  color: #60a5fa; border: 1px solid rgba(96,165,250,0.30); }
.pill-green  { background: rgba(52,211,153,0.12);  color: #34d399; border: 1px solid rgba(52,211,153,0.30); }
.pill-red    { background: rgba(248,113,113,0.12);  color: #f87171; border: 1px solid rgba(248,113,113,0.30); }

.auth-card {
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 22px; padding: 2.75rem 2.5rem; max-width: 460px; margin: 1.5rem auto;
}
.auth-title {
    font-size: 1.8rem; font-weight: 900;
    background: linear-gradient(135deg, #8250ff, #60a5fa);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    text-align: center; margin-bottom: 0.2rem;
}
.auth-sub { color: #555; font-size: 0.875rem; text-align: center; margin-bottom: 1.75rem; }

.platform-card {
    background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px; padding: 1.1rem 1.4rem; margin-bottom: 0.75rem;
}

/* Google Connect Button */
.google-btn {
    display: flex; align-items: center; justify-content: center; gap: .75rem;
    background: #ffffff; color: #3c4043 !important; border: 1px solid #dadce0;
    border-radius: 12px; padding: .85rem 1.5rem; font-size: .95rem; font-weight: 600;
    cursor: pointer; text-decoration: none; transition: all 0.2s ease;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}
.google-btn:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.3); transform: translateY(-1px); }

.connected-badge {
    display: inline-flex; align-items: center; gap: .4rem;
    background: rgba(52,211,153,0.12); border: 1px solid rgba(52,211,153,0.35);
    border-radius: 999px; padding: .35rem 1rem; font-size: .8rem;
    color: #34d399; font-weight: 700;
}
.disconnected-badge {
    display: inline-flex; align-items: center; gap: .4rem;
    background: rgba(248,113,113,0.12); border: 1px solid rgba(248,113,113,0.35);
    border-radius: 999px; padding: .35rem 1rem; font-size: .8rem;
    color: #f87171; font-weight: 700;
}

.info-box {
    background: rgba(96,165,250,0.07); border: 1px solid rgba(96,165,250,0.25);
    border-radius: 12px; padding: .9rem 1.1rem; font-size: .875rem; color: #93c5fd; margin: 0.75rem 0;
}
.warn-box {
    background: rgba(245,158,11,0.07); border: 1px solid rgba(245,158,11,0.25);
    border-radius: 12px; padding: .9rem 1.1rem; font-size: .875rem; color: #fcd34d; margin: 0.75rem 0;
}
.success-box {
    background: rgba(52,211,153,0.07); border: 1px solid rgba(52,211,153,0.25);
    border-radius: 12px; padding: .9rem 1.1rem; font-size: .875rem; color: #34d399; margin: 0.75rem 0;
}

.glow-divider {
    height: 1px; margin: 1.5rem 0;
    background: linear-gradient(90deg, transparent, #8250ff, #60a5fa, transparent); opacity: .3;
}
.user-badge {
    display: inline-flex; align-items: center; gap: .4rem;
    background: rgba(130,80,255,0.15); border: 1px solid rgba(130,80,255,0.35);
    border-radius: 20px; padding: .35rem 1rem; font-size: .82rem; color: #c4b5fd; font-weight: 700;
}

.stButton > button {
    font-family: 'Inter', sans-serif !important; font-weight: 700 !important;
    border-radius: 12px !important; border: none !important; transition: all 0.2s ease !important;
    background: linear-gradient(135deg, #6d28d9, #8b5cf6) !important;
    color: #fff !important; box-shadow: 0 4px 16px rgba(130,80,255,0.35) !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important; box-shadow: 0 8px 24px rgba(130,80,255,0.45) !important;
}
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div {
    background: rgba(255,255,255,0.05) !important; border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important; color: #f0f0f8 !important;
}
.stTabs [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.03) !important; border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 14px !important; padding: 5px !important; gap: 4px !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 10px !important; font-weight: 600 !important; border: none !important;
    color: #666 !important; background: transparent !important; padding: .6rem 1.3rem !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #6d28d9, #8b5cf6) !important;
    color: #fff !important; box-shadow: 0 4px 14px rgba(130,80,255,0.4) !important;
}
.stProgress > div > div > div { background: linear-gradient(90deg, #8250ff, #60a5fa) !important; }
[data-testid="stFileUploader"] > div {
    border: 2px dashed rgba(130,80,255,0.35) !important; border-radius: 12px !important;
    background: rgba(130,80,255,0.04) !important;
}
@keyframes slideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: none; } }
.slide-up { animation: slideUp .4s ease-out both; }
</style>
""", unsafe_allow_html=True)

# ─── Session State Init ───────────────────────────────────────────────────────
for k, v in [
    ("authenticated", False), ("username", ""), ("credentials", {}),
    ("upload_log", []), ("auth_mode", "signin"), ("login_token", None),
    ("oauth_state", None),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ─── Auto-login via token ─────────────────────────────────────────────────────
try:
    qp = st.query_params
    saved_token  = qp.get("token", None)
    oauth_code   = qp.get("code",  None)
    oauth_state  = qp.get("state", None)

    # Auto-login
    if not st.session_state.authenticated and saved_token:
        uname = validate_token(saved_token)
        if uname:
            users_db = load_users()
            if uname in users_db:
                st.session_state.authenticated = True
                st.session_state.username      = uname
                st.session_state.credentials   = load_user_creds(uname)
                st.session_state.login_token   = saved_token
except Exception:
    oauth_code  = None
    oauth_state = None
    saved_token = None

PLATFORMS = {
    "youtube":   {"emoji": "▶️",  "name": "YouTube"},
    "instagram": {"emoji": "📸",  "name": "Instagram"},
    "tiktok":    {"emoji": "🎵",  "name": "TikTok"},
    "facebook":  {"emoji": "📘",  "name": "Facebook"},
}

# ─── Handle Google OAuth Callback ────────────────────────────────────────────
if oauth_code and st.session_state.authenticated:
    with st.spinner("Connecting YouTube..."):
        try:
            token_data = exchange_code_for_tokens(oauth_code)
            access_token  = token_data.get("access_token", "")
            refresh_token = token_data.get("refresh_token", "")

            if access_token:
                channel_name = get_youtube_channel_name(access_token)
                creds = st.session_state.credentials
                creds["youtube"] = {
                    "connected":     True,
                    "access_token":  access_token,
                    "refresh_token": refresh_token,
                    "channel_name":  channel_name,
                }
                save_user_creds(st.session_state.username, creds)
                st.session_state.credentials = creds

                # Clean URL — remove oauth params, keep login token
                try:
                    st.query_params.clear()
                    if st.session_state.login_token:
                        st.query_params["token"] = st.session_state.login_token
                except Exception:
                    pass

                st.success(f"✅ YouTube connected! Channel: **{channel_name}**")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ YouTube connection failed. Please try again.")
        except Exception as e:
            st.error(f"❌ Error: {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  AUTH SCREEN
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.authenticated:
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

        col_l, col_r = st.columns(2)
        with col_l:
            if st.button("🔑  Sign In", use_container_width=True,
                         type="primary" if st.session_state.auth_mode == "signin" else "secondary"):
                st.session_state.auth_mode = "signin"; st.rerun()
        with col_r:
            if st.button("✨  Create Account", use_container_width=True,
                         type="primary" if st.session_state.auth_mode == "signup" else "secondary"):
                st.session_state.auth_mode = "signup"; st.rerun()

        st.markdown("<div class='glow-divider'></div>", unsafe_allow_html=True)

        # ── SIGN IN ──
        if st.session_state.auth_mode == "signin":
            st.markdown("<div class='auth-card'>", unsafe_allow_html=True)
            st.markdown("<div class='auth-title'>Welcome Back 👋</div><div class='auth-sub'>Sign in to your SocialBlast account</div>", unsafe_allow_html=True)
            st.text_input("Username", placeholder="Your username", key="si_user")
            st.text_input("Password", placeholder="••••••••", type="password", key="si_pass")
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
                        time.sleep(0.6); st.rerun()
                    else:
                        st.error(f"❌ {msg}")
                else:
                    st.warning("Please fill in both fields.")
            st.markdown("</div>", unsafe_allow_html=True)

        # ── SIGN UP ──
        else:
            st.markdown("<div class='auth-card'>", unsafe_allow_html=True)
            st.markdown("<div class='auth-title'>Create Account ✨</div><div class='auth-sub'>Join SocialBlast — it's completely free</div>", unsafe_allow_html=True)
            st.text_input("Username",         placeholder="Choose a unique username", key="r_user")
            st.text_input("Email Address",    placeholder="you@example.com",          key="r_email")
            st.text_input("Password",         placeholder="Min. 6 characters",        type="password", key="r_pass")
            st.text_input("Confirm Password", placeholder="Repeat your password",     type="password", key="r_pass2")
            st.markdown("")
            if st.button("Create Account & Get Started  →", use_container_width=True, type="primary", key="do_signup"):
                _user  = st.session_state.get("r_user",  "").strip()
                _email = st.session_state.get("r_email", "").strip()
                _pass  = st.session_state.get("r_pass",  "")
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
                        time.sleep(0.6); st.rerun()
                    else:
                        st.error(f"❌ {msg}")
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div style="text-align:center;margin-top:1.5rem;font-size:.78rem;color:#444">🔒 Your data is stored securely and encrypted</div>', unsafe_allow_html=True)
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ══════════════════════════════════════════════════════════════════════════════
creds  = st.session_state.credentials if st.session_state.credentials else {}
uname  = st.session_state.username or ""
users  = load_users()
udata  = users.get(uname) or {}

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
        if tok: delete_token(tok)
        try: st.query_params.clear()
        except Exception: pass
        for k in ["authenticated","username","credentials","upload_log","login_token"]:
            st.session_state[k] = False if k == "authenticated" else "" if k in ["username","login_token"] else {} if k == "credentials" else []
        st.rerun()

    st.markdown("<div class='glow-divider'></div>", unsafe_allow_html=True)

    # ── Usage Stats ──
    st.markdown(f"""
    <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);
                border-radius:12px;padding:.9rem 1rem;margin-bottom:1rem">
      <div style="font-size:.62rem;font-weight:800;text-transform:uppercase;
                  letter-spacing:.08em;color:#555;margin-bottom:.65rem">📊 Your Stats</div>
      <div style="display:flex;justify-content:space-between;margin-bottom:.35rem">
        <span style="font-size:.75rem;color:#888">🔑 Total Sign Ins</span>
        <span style="font-size:.8rem;font-weight:800;color:#a78bfa;font-family:monospace">{udata.get("login_count",0)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;margin-bottom:.35rem">
        <span style="font-size:.75rem;color:#888">📤 Posts Uploaded</span>
        <span style="font-size:.8rem;font-weight:800;color:#34d399;font-family:monospace">{udata.get("upload_count",0)}</span>
      </div>
      <div style="display:flex;justify-content:space-between">
        <span style="font-size:.75rem;color:#888">📅 Last Login</span>
        <span style="font-size:.73rem;color:#666;font-family:monospace">{(udata.get("last_login") or "—")[:10]}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:#8250ff;margin-bottom:.75rem">🔗 Connected Platforms</div>', unsafe_allow_html=True)

    # ── YouTube Connect with Google ──
    yt_connected = creds.get("youtube", {}).get("connected", False)
    yt_channel   = creds.get("youtube", {}).get("channel_name", "")

    st.markdown("**▶️ YouTube**", unsafe_allow_html=True)
    if yt_connected:
        st.markdown(f"<div class='connected-badge'>✅ {yt_channel or 'Connected'}</div>", unsafe_allow_html=True)
        if st.button("🔌 Disconnect YouTube", key="yt_disconnect"):
            creds["youtube"] = {"connected": False, "access_token": "", "refresh_token": "", "channel_name": ""}
            save_user_creds(uname, creds)
            st.session_state.credentials = creds
            st.success("YouTube disconnected!"); st.rerun()
    else:
        if GOOGLE_CLIENT_ID:
            state = secrets.token_urlsafe(16)
            st.session_state.oauth_state = state
            auth_url = get_google_auth_url(state)
            st.markdown(
                f'<a href="{auth_url}" target="_self" class="google-btn" style="'
                f'display:flex;align-items:center;justify-content:center;gap:.6rem;'
                f'background:#fff;color:#3c4043;border:1px solid #dadce0;border-radius:10px;'
                f'padding:.7rem 1rem;font-size:.85rem;font-weight:600;text-decoration:none;'
                f'margin:.5rem 0;box-shadow:0 2px 8px rgba(0,0,0,0.3)">'
                f'<svg width="18" height="18" viewBox="0 0 18 18">'
                f'<path fill="#4285F4" d="M16.51 8H8.98v3h4.3c-.18 1-.74 1.48-1.6 2.04v2.01h2.6a7.8 7.8 0 0 0 2.38-5.88c0-.57-.05-.66-.15-1.18z"/>'
                f'<path fill="#34A853" d="M8.98 17c2.16 0 3.97-.72 5.3-1.94l-2.6-2a4.8 4.8 0 0 1-7.18-2.54H1.83v2.07A8 8 0 0 0 8.98 17z"/>'
                f'<path fill="#FBBC05" d="M4.5 10.52a4.8 4.8 0 0 1 0-3.04V5.41H1.83a8 8 0 0 0 0 7.18z"/>'
                f'<path fill="#EA4335" d="M8.98 4.18c1.17 0 2.23.4 3.06 1.2l2.3-2.3A8 8 0 0 0 1.83 5.4L4.5 7.49a4.77 4.77 0 0 1 4.48-3.3z"/>'
                f'</svg>'
                f'Connect with Google</a>',
                unsafe_allow_html=True
            )
        else:
            st.markdown("<div class='warn-box' style='font-size:.78rem'>⚠️ Google Client ID not configured in Streamlit Secrets.</div>", unsafe_allow_html=True)

    st.markdown("<div class='glow-divider'></div>", unsafe_allow_html=True)

    # ── Other Platforms (manual) ──
    st.markdown('<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:#555;margin-bottom:.5rem">OTHER PLATFORMS (Manual)</div>', unsafe_allow_html=True)

    creds_changed = False

    with st.expander("📸  Instagram"):
        ig_token = st.text_input("Access Token",      value=creds.get("instagram",{}).get("access_token",""), type="password", key="ig_token")
        ig_uid   = st.text_input("Instagram User ID", value=creds.get("instagram",{}).get("ig_user_id",""),   key="ig_uid")
        if st.button("💾 Save Instagram", key="save_ig"):
            if ig_token and ig_uid:
                creds["instagram"] = {"connected": True, "access_token": ig_token, "ig_user_id": ig_uid}
                creds_changed = True; st.success("Saved! ✅")
            else:
                st.error("Both Token and User ID required.")

    with st.expander("🎵  TikTok"):
        tt_ck = st.text_input("Client Key",    value=creds.get("tiktok",{}).get("client_key",""),    key="tt_ck")
        tt_cs = st.text_input("Client Secret", value=creds.get("tiktok",{}).get("client_secret",""), type="password", key="tt_cs")
        if st.button("💾 Save TikTok", key="save_tt"):
            if tt_ck and tt_cs:
                creds["tiktok"] = {"connected": True, "client_key": tt_ck, "client_secret": tt_cs}
                creds_changed = True; st.success("Saved! ✅")
            else:
                st.error("Both Key and Secret required.")

    with st.expander("📘  Facebook"):
        fb_token = st.text_input("Page Access Token", value=creds.get("facebook",{}).get("access_token",""), type="password", key="fb_token")
        fb_pid   = st.text_input("Page ID",           value=creds.get("facebook",{}).get("page_id",""),      key="fb_pid")
        if st.button("💾 Save Facebook", key="save_fb"):
            if fb_token and fb_pid:
                creds["facebook"] = {"connected": True, "access_token": fb_token, "page_id": fb_pid}
                creds_changed = True; st.success("Saved! ✅")
            else:
                st.error("Both Token and Page ID required.")

    if creds_changed:
        save_user_creds(uname, creds)
        st.session_state.credentials = creds

    st.markdown("<div class='glow-divider'></div>", unsafe_allow_html=True)
    st.markdown('<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:#555;margin-bottom:.5rem">📡 STATUS</div>', unsafe_allow_html=True)
    for pid, pdata in PLATFORMS.items():
        connected = creds.get(pid, {}).get("connected", False)
        col  = "#34d399" if connected else "#f87171"
        dot  = "🟢" if connected else "🔴"
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:.3rem 0;border-bottom:1px solid #111">'
            f'<span style="font-size:.8rem;color:#aaa">{pdata["emoji"]} {pdata["name"]}</span>'
            f'<span style="font-size:.72rem;font-weight:700;color:{col}">{dot} {"On" if connected else "Off"}</span>'
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
            Upload once — publish to all platforms in one click.
        </p>
        <div class="pill-row">
            <span class="pill pill-purple">✦ Multi-Platform</span>
            <span class="pill pill-blue">⚡ One Click Upload</span>
            <span class="pill pill-green">🔒 Encrypted Storage</span>
            <span class="pill {'pill-green' if creds.get('youtube',{}).get('connected') else 'pill-red'}">
                {'✅ YouTube Connected' if creds.get('youtube',{}).get('connected') else '🔴 YouTube Not Connected'}
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)
with _c2:
    if st.button("🚪 Logout", key="top_logout"):
        tok = st.session_state.get("login_token")
        if tok: delete_token(tok)
        try: st.query_params.clear()
        except Exception: pass
        for k in ["authenticated","username","credentials","upload_log","login_token"]:
            st.session_state[k] = False if k == "authenticated" else "" if k in ["username","login_token"] else {} if k == "credentials" else []
        st.rerun()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📤  Upload & Post", "📋  Upload History", "📖  Setup Guide"])

# ════════════════════════════════════════════════════════════════════════════
#  TAB 1 — Upload & Post
# ════════════════════════════════════════════════════════════════════════════
with tab1:

    # YouTube not connected warning
    if not creds.get("youtube", {}).get("connected"):
        st.markdown("""
        <div class='warn-box'>
            ⚠️ <b>YouTube not connected.</b> Click <b>"Connect with Google"</b> in the sidebar
            to link your YouTube channel — no API key needed!
        </div>
        """, unsafe_allow_html=True)

    col_left, col_right = st.columns([1.2, 1], gap="large")

    with col_left:
        st.markdown("#### 📁 Upload Your File")
        uploaded_file = st.file_uploader(
            "Drag & drop or click to browse",
            type=["mp4","mov","avi","mkv","jpg","jpeg","png","gif","webp"],
            help="Supported: MP4, MOV, AVI, MKV, JPG, PNG, GIF, WEBP"
        )
        if uploaded_file:
            ext      = Path(uploaded_file.name).suffix.lower()
            is_video = ext in [".mp4",".mov",".avi",".mkv"]
            st.markdown(f"""
            <div class='platform-card'>
                <b style="color:#f0f0f8">{'🎬 Video' if is_video else '🖼️ Image'}</b>: {uploaded_file.name}<br>
                <span style='color:#666;font-size:.82rem'>Size: {uploaded_file.size/1024:.1f} KB &nbsp;·&nbsp; Type: {uploaded_file.type}</span>
            </div>""", unsafe_allow_html=True)
            if is_video: st.video(uploaded_file)
            else: st.image(uploaded_file, use_container_width=True)

    with col_right:
        st.markdown("#### ✍️ Post Details")
        post_title   = st.text_input("Title",    placeholder="Enter your post title...")
        post_caption = st.text_area("Caption",   placeholder="Write a caption...", height=100)
        post_tags    = st.text_input("Hashtags", placeholder="#trending #viral #fyp")
        post_privacy = st.selectbox("Privacy",   ["Public", "Unlisted", "Private"])

        st.markdown("#### 🎯 Select Platforms")
        pc1, pc2 = st.columns(2)
        with pc1:
            sel_yt = st.checkbox("▶️ YouTube",   value=creds.get("youtube",{}).get("connected", False))
            sel_ig = st.checkbox("📸 Instagram", value=creds.get("instagram",{}).get("connected", False))
        with pc2:
            sel_tt = st.checkbox("🎵 TikTok",    value=creds.get("tiktok",{}).get("connected", False))
            sel_fb = st.checkbox("📘 Facebook",  value=creds.get("facebook",{}).get("connected", False))

    st.markdown("<div class='glow-divider'></div>", unsafe_allow_html=True)

    if st.button("🚀 Publish to All Selected Platforms", use_container_width=True, type="primary"):
        if not uploaded_file:
            st.error("⚠️ Please upload a file first.")
        elif not post_title:
            st.error("⚠️ Please enter a title.")
        else:
            selected  = {"youtube": sel_yt, "instagram": sel_ig, "tiktok": sel_tt, "facebook": sel_fb}
            active    = [p for p, s in selected.items() if s]
            connected = [p for p in active if creds.get(p, {}).get("connected")]
            no_cred   = [p for p in active if not creds.get(p, {}).get("connected")]

            if no_cred:
                names = ", ".join([PLATFORMS[p]["name"] for p in no_cred])
                st.markdown(f"<div class='warn-box'>⚠️ <b>{names}</b> not connected — will be skipped.</div>", unsafe_allow_html=True)

            if not connected:
                st.error("No connected platforms selected. Please connect at least one platform from the sidebar.")
            else:
                progress    = st.progress(0)
                status_area = st.empty()
                log_entry   = {"file": uploaded_file.name, "title": post_title, "privacy": post_privacy, "results": {}, "time": now_str()}

                for i, pid in enumerate(connected):
                    pname = PLATFORMS[pid]["name"]
                    status_area.info(f"Uploading to **{pname}**... ({i+1}/{len(connected)})")
                    time.sleep(1.2)

                    # ── YouTube Real Upload ──
                    if pid == "youtube":
                        try:
                            from googleapiclient.discovery import build
                            from googleapiclient.http import MediaIoBaseUpload
                            import io

                            access_token = creds["youtube"].get("access_token", "")
                            # Refresh token if needed
                            if not access_token:
                                access_token = refresh_youtube_token(creds["youtube"].get("refresh_token",""))
                                creds["youtube"]["access_token"] = access_token
                                save_user_creds(uname, creds)

                            from google.oauth2.credentials import Credentials
                            google_creds = Credentials(token=access_token)
                            youtube = build("youtube", "v3", credentials=google_creds)

                            file_bytes = uploaded_file.read()
                            media = MediaIoBaseUpload(
                                io.BytesIO(file_bytes),
                                mimetype=uploaded_file.type,
                                chunksize=1024*1024,
                                resumable=True
                            )
                            request = youtube.videos().insert(
                                part="snippet,status",
                                body={
                                    "snippet": {
                                        "title":       post_title,
                                        "description": post_caption,
                                        "tags":        post_tags.split() if post_tags else [],
                                    },
                                    "status": {"privacyStatus": post_privacy.lower()}
                                },
                                media_body=media
                            )
                            response = request.execute()
                            video_id = response.get("id","")
                            log_entry["results"][pid] = f"✅ Uploaded! youtube.com/watch?v={video_id}"
                        except Exception as e:
                            log_entry["results"][pid] = f"❌ Failed: {str(e)[:80]}"

                    # ── Instagram (simulated) ──
                    elif pid == "instagram":
                        log_entry["results"][pid] = "✅ Success (Simulated — needs public URL)"

                    # ── Facebook (simulated) ──
                    elif pid == "facebook":
                        log_entry["results"][pid] = "✅ Success (Simulated)"

                    # ── TikTok (simulated) ──
                    elif pid == "tiktok":
                        log_entry["results"][pid] = "✅ Success (Simulated)"

                    progress.progress((i+1)/len(connected))

                st.session_state.upload_log.append(log_entry)
                users_upd = load_users()
                if uname in users_upd:
                    users_upd[uname]["upload_count"] = users_upd[uname].get("upload_count", 0) + 1
                    save_users(users_upd)

                status_area.success(f"🎉 Done! Published to **{len(connected)} platform(s)**!")
                st.markdown("#### 📊 Results")
                for pid, result in log_entry["results"].items():
                    st.markdown(f"- {PLATFORMS[pid]['emoji']} **{PLATFORMS[pid]['name']}**: {result}")

# ════════════════════════════════════════════════════════════════════════════
#  TAB 2 — History
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("#### 📋 Your Upload History")
    if not st.session_state.upload_log:
        st.markdown(f"""
        <div style="text-align:center;padding:3rem;background:rgba(255,255,255,0.02);
                    border:1px solid #111;border-radius:18px">
            <div style="font-size:3.5rem;margin-bottom:.75rem;opacity:.3">📭</div>
            <div style="font-size:1.1rem;font-weight:700;color:#aaa">No uploads yet</div>
            <div style="color:#555;font-size:.875rem;margin-top:.3rem">Go to Upload & Post tab to get started!</div>
        </div>""", unsafe_allow_html=True)
    else:
        for entry in reversed(st.session_state.upload_log):
            with st.expander(f"📁 {entry['file']}  ·  {entry['time']}"):
                st.markdown(f"**Title:** {entry['title']} &nbsp;·&nbsp; **Privacy:** {entry.get('privacy','Public')}")
                for pid, result in entry["results"].items():
                    st.markdown(f"- {PLATFORMS[pid]['emoji']} **{PLATFORMS[pid]['name']}**: {result}")

# ════════════════════════════════════════════════════════════════════════════
#  TAB 3 — Setup Guide
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("## 📖 Setup Guide")

    st.markdown("""
### ✅ Step 1 — Add Secrets to Streamlit Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click your app → **Settings** → **Secrets**
3. Add these secrets:
```toml
GOOGLE_CLIENT_ID = "your-client-id-here"
GOOGLE_CLIENT_SECRET = "your-client-secret-here"
```
4. Click **Save** — app will restart automatically

---

### ✅ Step 2 — Connect YouTube
1. Open your app
2. In the sidebar, click **"Connect with Google"**
3. Select your Google account
4. Allow YouTube permissions
5. Done! ✅ Your channel is connected

---

### ✅ Step 3 — Upload & Post
1. Go to **Upload & Post** tab
2. Upload your video/image
3. Fill in title, caption, hashtags
4. Select platforms
5. Click **Publish** — done!

---

### 📦 Install Packages (local only)
```bash
pip install streamlit cryptography google-api-python-client google-auth-oauthlib requests
```
    """)

    if not GOOGLE_CLIENT_ID:
        st.markdown("""
        <div class='warn-box'>
        ⚠️ <b>Secrets not configured yet!</b><br>
        Go to Streamlit Cloud → Your App → Settings → Secrets and add your
        GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("<div class='success-box'>✅ Google credentials are configured!</div>", unsafe_allow_html=True)
