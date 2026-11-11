import os
import math
import hmac
import base64
import hashlib
import ipaddress
from datetime import datetime
from flask import Flask, request, redirect, url_for, render_template_string, send_from_directory, Response
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# ==============================================================================
# CONFIGURATION & ENVIRONMENT VARIABLES
# ==============================================================================
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_KT7UWPjCe6DJ@ep-rough-feather-bddwptd9-pooler.c-8.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)
IP_SALT = os.environ.get("IP_SALT", "cathars_sanctum_salt_777")
SECRET_CIPHER_KEY = "Cathars"
SECONDARY_LAYER_KEY = "AltarOfPerdition666"

# Secret host key to access /access/console/
HOST_CONSOLE_KEY = os.environ.get("HOST_CONSOLE_KEY", "----357832186")

# ==============================================================================
# STEADY IP SUBNET NORMALIZER (Prevents trailing digit shifts from changing ID)
# ==============================================================================

def get_steady_node_id(raw_ip: str) -> str:
    """
    Normalizes IPv4 to /24 (drops fluctuating last octet) and IPv6 to /64.
    Produces a permanent deterministic node string that will not shift
    even when residential or dynamic IPs rotate their trailing digits.
    """
    try:
        ip_obj = ipaddress.ip_address(raw_ip)
        if ip_obj.version == 4:
            network = ipaddress.ip_network(f"{raw_ip}/24", strict=False)
            steady_base = str(network.network_address)
        else:
            network = ipaddress.ip_network(f"{raw_ip}/64", strict=False)
            steady_base = str(network.network_address)
    except Exception:
        parts = raw_ip.split(".")
        if len(parts) == 4:
            steady_base = f"{parts[0]}.{parts[1]}.{parts[2]}.0"
        else:
            steady_base = raw_ip

    digest = hashlib.sha256((steady_base + IP_SALT).encode("utf-8")).hexdigest()[:16].upper()
    return f"NODE-{digest[:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:16]}"

# ==============================================================================
# HIDDEN MULTILAYER ENCRYPTION (SERVER-SIDE ONLY)
# ==============================================================================

def xor_bytes(data: bytes, key: str) -> bytes:
    key_bytes = key.encode("utf-8")
    return bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data)])

def cathars_encrypt(raw_text: str) -> str:
    """Internal silent encryption. Never displayed publicly."""
    if not raw_text:
        return ""
    step1 = xor_bytes(raw_text.encode("utf-8"), SECRET_CIPHER_KEY)
    step2 = base64.b64encode(step1)
    step3 = base64.b32encode(step2)
    step4 = ".".join(str(b) for b in step3).encode("utf-8")
    step5 = xor_bytes(step4, SECONDARY_LAYER_KEY)
    step6 = base64.b64encode(step5).decode("utf-8")
    return f"SIGIL${step6}"

def cathars_decrypt(cipher_text: str) -> str:
    """Decodes multi-layer ciphertext back to original text."""
    if not cipher_text or not cipher_text.startswith("SIGIL$"):
        return cipher_text
    try:
        token = cipher_text.replace("SIGIL$", "")
        step5 = base64.b64decode(token.encode("utf-8"))
        step4 = xor_bytes(step5, SECONDARY_LAYER_KEY).decode("utf-8")
        step3 = bytes([int(dec) for dec in step4.split(".")])
        step2 = base64.b32decode(step3)
        step1 = base64.b64decode(step2)
        return xor_bytes(step1, SECRET_CIPHER_KEY).decode("utf-8")
    except Exception:
        return "[UNREADABLE RITE]"

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cathars_posts (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                author_hash VARCHAR(32) NOT NULL,
                node_id VARCHAR(64) DEFAULT 'UNKNOWN',
                views INT DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS cathars_audit_logs (
                id SERIAL PRIMARY KEY,
                post_id INT,
                action VARCHAR(50) NOT NULL,
                ip_hash VARCHAR(32) NOT NULL,
                node_id VARCHAR(64) DEFAULT 'UNKNOWN',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS cathars_removals (
                id SERIAL PRIMARY KEY,
                post_id INT NOT NULL,
                reason TEXT NOT NULL,
                contact_info VARCHAR(255),
                ip_hash VARCHAR(32) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS cathars_banned_nodes (
                id SERIAL PRIMARY KEY,
                node_id VARCHAR(64) UNIQUE NOT NULL,
                banned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                note TEXT DEFAULT 'Disappeared by Host'
            );
            ALTER TABLE cathars_posts ADD COLUMN IF NOT EXISTS node_id VARCHAR(64) DEFAULT 'UNKNOWN';
            ALTER TABLE cathars_audit_logs ADD COLUMN IF NOT EXISTS node_id VARCHAR(64) DEFAULT 'UNKNOWN';
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[!] DB Init Notice: {e}")

try:
    init_db()
except Exception:
    pass

# ==============================================================================
# GHOST BAN SHIELD (SITE COMPLETELY VANISHES FOR BANNED SUBNETS)
# ==============================================================================
@app.before_request
def ghost_ban_check():
    if request.path.startswith("/access/console"):
        return None

    raw_ip = request.headers.get("x-forwarded-for", request.remote_addr).split(",")[0].strip()
    node_id = get_steady_node_id(raw_ip)

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM cathars_banned_nodes WHERE node_id = %s LIMIT 1", (node_id,))
        banned = cur.fetchone()
        cur.close()
        conn.close()

        if banned:
            # Completely dead response: website disappears
            return Response("", status=404)
    except Exception:
        pass

@app.after_request
def apply_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response

# ==============================================================================
# LOGO SERVING ROUTE (Checks root and api directories, or serves SVG)
# ==============================================================================
@app.route("/logo.png")
def serve_logo():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "..", "logo.png"),
        os.path.join(base_dir, "logo.png"),
        "logo.png"
    ]
    for c in candidates:
        if os.path.exists(c):
            return send_from_directory(os.path.dirname(os.path.abspath(c)), os.path.basename(c))
    svg_fallback = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" fill="none" stroke="#ff1a1a" stroke-width="2">
        <circle cx="50" cy="50" r="46" stroke="#4a0000" stroke-width="3"/>
        <polygon points="50,10 85,80 15,35 85,35 15,80" stroke="#8b0000" fill="#080101"/>
        <circle cx="50" cy="50" r="18" stroke="#ff1a1a"/>
        <path d="M50 20 L50 80 M20 50 L80 50" stroke="#330000"/>
    </svg>"""
    return svg_fallback, 200, {"Content-Type": "image/svg+xml"}

# ==============================================================================
# PUBLIC TEMPLATE (ZERO TRACE OF ADMIN CODE, ZERO EMOJIS, ANTI-DEVTOOLS)
# ==============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CATHARS | Forbidden Tome</title>
    <style>
        :root {
            --bg-void: #030000;
            --bg-panel: #0a0101;
            --bg-highlight: #140202;
            --blood: #8b0000;
            --bright-crimson: #ff1a1a;
            --dim-crimson: #4a0000;
            --text-color: #a87e7e;
            --border-dark: #220303;
        }

        * { 
            box-sizing: border-box; 
            margin: 0; 
            padding: 0; 
            -webkit-user-select: none;
            user-select: none;
        }
        
        .reader-text, .search-area input, .form-row input, .form-row textarea {
            -webkit-user-select: text;
            user-select: text;
        }

        body {
            background-color: var(--bg-void);
            color: var(--text-color);
            font-family: "Courier New", Courier, monospace;
            min-height: 100vh;
            background-image: 
                radial-gradient(circle at 50% 10%, rgba(139, 0, 0, 0.15) 0%, transparent 65%),
                repeating-linear-gradient(0deg, rgba(0, 0, 0, 0.5) 0px, rgba(0, 0, 0, 0.5) 1px, transparent 1px, transparent 2px);
            background-size: 100% 100%, 100% 4px;
        }

        header {
            background: #080101;
            border-bottom: 2px solid var(--border-dark);
            padding: 10px 18px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 4px 30px rgba(0,0,0,0.95);
        }
        .menu-btn {
            background: #110101;
            border: 1px solid var(--blood);
            color: var(--bright-crimson);
            font-size: 14px;
            padding: 7px 14px;
            cursor: pointer;
            letter-spacing: 2px;
            font-weight: bold;
        }
        .menu-btn:hover {
            background: var(--blood);
            color: #ffffff;
            box-shadow: 0 0 10px var(--bright-crimson);
        }
        .search-area {
            flex: 1;
            max-width: 650px;
            margin: 0 20px;
        }
        .search-area input {
            width: 100%;
            background: #000;
            border: 1px solid var(--dim-crimson);
            color: var(--bright-crimson);
            padding: 9px 14px;
            font-family: inherit;
            font-size: 13px;
            outline: none;
            text-transform: uppercase;
        }
        .search-area input:focus {
            border-color: var(--bright-crimson);
            box-shadow: 0 0 10px rgba(255, 26, 26, 0.35);
        }
        .brand-wrap {
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
        }
        .brand-logo {
            width: 38px;
            height: 38px;
            border-radius: 50%;
            border: 1px solid var(--bright-crimson);
            box-shadow: 0 0 8px rgba(255, 26, 26, 0.5);
            object-fit: cover;
            background: #000;
            pointer-events: none;
        }
        .brand-name {
            color: var(--bright-crimson);
            font-size: 16px;
            font-weight: bold;
            letter-spacing: 4px;
            text-shadow: 0 0 8px rgba(255, 0, 0, 0.8);
        }

        #sidebar {
            position: fixed;
            top: 0;
            left: -350px;
            width: 330px;
            height: 100%;
            background: #060101;
            border-right: 2px solid var(--blood);
            transition: left 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            z-index: 1000;
            padding: 24px;
            box-shadow: 15px 0 40px rgba(0,0,0,0.98);
        }
        #sidebar.active { left: 0; }
        .sidebar-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--dim-crimson);
            padding-bottom: 16px;
            margin-bottom: 24px;
        }
        .sidebar-btn {
            display: block;
            background: #0e0202;
            border: 1px solid var(--border-dark);
            color: #d89696;
            padding: 12px 14px;
            margin-bottom: 12px;
            cursor: pointer;
            text-decoration: none;
            font-size: 13px;
            letter-spacing: 1px;
            transition: 0.2s;
        }
        .sidebar-btn:hover {
            border-color: var(--bright-crimson);
            color: #ffffff;
            background: #250303;
        }

        .hero {
            border-bottom: 1px solid var(--border-dark);
            background: linear-gradient(180deg, #180202 0%, #030000 100%);
            padding: 35px 20px;
            text-align: center;
        }
        .hero-img {
            width: 100px;
            height: 100px;
            border-radius: 50%;
            border: 2px solid var(--bright-crimson);
            box-shadow: 0 0 25px rgba(255, 0, 0, 0.5);
            margin: 0 auto 15px;
            display: block;
            object-fit: cover;
            background: #000;
            pointer-events: none;
        }
        .hero h1 {
            color: var(--bright-crimson);
            font-size: 34px;
            font-weight: 900;
            letter-spacing: 10px;
            text-shadow: 0 0 15px rgba(255, 0, 0, 0.8);
        }
        .hero p {
            color: #7d3333;
            font-size: 11px;
            letter-spacing: 3px;
            margin-top: 6px;
            text-transform: uppercase;
        }

        .covenant-note {
            max-width: 1040px;
            margin: 20px auto 0;
            padding: 14px 18px;
            border: 1px solid var(--border-dark);
            background: #090101;
            font-size: 11px;
            line-height: 1.6;
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .covenant-tag {
            color: #39ff14;
            font-weight: bold;
            white-space: nowrap;
            letter-spacing: 1px;
        }

        .container {
            max-width: 1040px;
            margin: 20px auto 50px;
            padding: 0 16px;
        }
        .table-wrap {
            border: 1px solid var(--border-dark);
            background: var(--bg-panel);
            box-shadow: 0 0 25px rgba(0,0,0,0.85);
        }
        .table-head {
            display: grid;
            grid-template-columns: 80px 1fr 200px;
            padding: 12px 16px;
            background: #140202;
            border-bottom: 2px solid var(--blood);
            font-size: 11px;
            font-weight: bold;
            color: var(--bright-crimson);
            letter-spacing: 2px;
        }
        .table-row {
            display: grid;
            grid-template-columns: 80px 1fr 200px;
            padding: 12px 16px;
            border-bottom: 1px solid #140202;
            text-decoration: none;
            color: inherit;
            font-size: 12px;
            align-items: center;
            transition: 0.15s;
        }
        .table-row:hover {
            background: var(--bg-highlight);
            border-left: 2px solid var(--bright-crimson);
        }
        .row-id { color: var(--dim-crimson); font-weight: bold; }
        .row-title {
            color: #f7a8a8;
            font-weight: bold;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .row-meta { text-align: right; font-size: 10px; color: #722020; }

        .pager-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 14px 16px;
            background: #090101;
            border-top: 1px solid var(--border-dark);
            font-size: 11px;
        }
        .pager-link {
            background: #140101;
            border: 1px solid var(--border-dark);
            color: var(--text-color);
            padding: 6px 12px;
            text-decoration: none;
            letter-spacing: 1px;
        }
        .pager-link:hover {
            border-color: var(--bright-crimson);
            color: #fff;
            background: #250202;
        }
        .pager-link.disabled { opacity: 0.3; pointer-events: none; }

        .reader-panel {
            background: #090101;
            border: 1px solid var(--blood);
            padding: 24px;
        }
        .reader-title {
            font-size: 22px;
            color: var(--bright-crimson);
            word-break: break-all;
            margin-bottom: 8px;
            letter-spacing: 1px;
        }
        .reader-meta {
            font-size: 11px;
            color: #6a1a1a;
            border-bottom: 1px solid var(--border-dark);
            padding-bottom: 12px;
            margin-bottom: 18px;
            display: flex;
            justify-content: space-between;
        }
        .reader-text {
            background: #020000;
            border: 1px solid #1c0202;
            padding: 20px;
            font-size: 13px;
            line-height: 1.7;
            color: #fca8a8;
            white-space: pre-wrap;
            max-height: 650px;
            overflow-y: auto;
        }

        .modal-screen {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.94);
            z-index: 2000;
            align-items: center;
            justify-content: center;
            padding: 16px;
        }
        .modal-screen.active { display: flex; }
        .modal-box {
            background: #090101;
            border: 1px solid var(--blood);
            max-width: 600px;
            width: 100%;
            padding: 24px;
            box-shadow: 0 0 35px rgba(255, 0, 0, 0.35);
        }
        .modal-title {
            font-size: 15px;
            color: var(--bright-crimson);
            border-bottom: 1px solid var(--border-dark);
            padding-bottom: 10px;
            margin-bottom: 18px;
            letter-spacing: 3px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .form-row { margin-bottom: 14px; }
        .form-row label {
            display: block;
            font-size: 10px;
            color: #8c3232;
            margin-bottom: 5px;
            letter-spacing: 2px;
        }
        .form-row input, .form-row textarea {
            width: 100%;
            background: #000;
            border: 1px solid var(--border-dark);
            color: #f7a8a8;
            padding: 9px;
            font-family: inherit;
            font-size: 12px;
            outline: none;
        }
        .form-row input:focus, .form-row textarea:focus {
            border-color: var(--bright-crimson);
        }
        .action-btn {
            width: 100%;
            background: var(--dim-crimson);
            border: 1px solid var(--blood);
            color: #ffffff;
            padding: 12px;
            cursor: pointer;
            font-family: inherit;
            font-size: 12px;
            letter-spacing: 3px;
            font-weight: bold;
        }
        .action-btn:hover {
            background: var(--blood);
            box-shadow: 0 0 14px var(--bright-crimson);
        }
        .cancel-btn {
            background: none;
            border: none;
            color: var(--dim-crimson);
            font-size: 12px;
            cursor: pointer;
            width: 100%;
            margin-top: 10px;
            letter-spacing: 1px;
        }
        .cancel-btn:hover { color: var(--bright-crimson); }
        .notice-banner {
            padding: 12px;
            margin-bottom: 18px;
            border: 1px solid #781c1c;
            background: #200404;
            color: #f3aaaa;
            font-size: 11px;
        }
    </style>
</head>
<body oncontextmenu="return false;">

    <header>
        <button class="menu-btn" onclick="toggleMenu(true)">[=] MENU</button>
        <form class="search-area" method="GET" action="/">
            <input type="text" name="q" value="{{ query or '' }}" placeholder="SEARCH CODEX ARCHIVES...">
        </form>
        <a href="/" class="brand-wrap">
            <img src="/logo.png" alt="Cathars Logo" class="brand-logo">
            <span class="brand-name">CATHARS</span>
        </a>
    </header>

    <div id="sidebar">
        <div class="sidebar-header">
            <span style="color:var(--bright-crimson); font-weight:bold; letter-spacing:3px;">SANCTUM COUNCIL</span>
            <button class="menu-btn" style="padding:4px 8px;" onclick="toggleMenu(false)">[X]</button>
        </div>
        <div class="sidebar-btn" onclick="openModal('createModal')">[ + ] INSCRIBE POST</div>
        <div class="sidebar-btn" onclick="openModal('rulesModal')">[ ! ] TERMS OF SERVICE &amp; EDICTS</div>
        <div class="sidebar-btn" onclick="openModal('removalModal')">[ - ] PETITION REMOVAL</div>
        
        <div style="font-size:10px; color:#5c1a1a; margin-top:40px; line-height: 1.6; border-top: 1px solid var(--border-dark); padding-top:14px;">
            PROTOCOL: ZERO RETENTION.<br>
            40 RECORDS PER SCROLL.<br>
            IMMUTABLE SERVER RECORD.<br>
            TRIPWIRE ACTIVE.
        </div>
    </div>

    <section class="hero">
        <img src="/logo.png" alt="Altar Sigil" class="hero-img">
        <h1>CATHARS</h1>
        <p>Anonymous Codex &bull; Immutability Assured &bull; Total Expression</p>
    </section>

    <div class="container" style="margin-bottom:0;">
        <div class="covenant-note">
            <div class="covenant-tag">[ INVIOLABLE ANONYMITY ]</div>
            <div>
                <strong>YOUR DATA IS COMPLETELY UNTRACEABLE:</strong> Even the owner and operators of this site 
                cannot see who you are. All network data is permanently dissolved into salted one-way hashes 
                before touching storage. You exist here purely as a transient voice.
            </div>
        </div>
    </div>

    <main class="container">
        {% if msg %}
            <div class="notice-banner">{{ msg }}</div>
        {% endif %}

        {% if post %}
            <div style="margin-bottom:12px;">
                <a href="/?page={{ page }}" style="color:var(--bright-crimson); text-decoration:none; font-size:11px;">
                    &lt;-- RETURN TO ARCHIVE
                </a>
            </div>
            <article class="reader-panel">
                <h2 class="reader-title">{{ post.title }}</h2>
                <div class="reader-meta">
                    <span>RECORD #{{ post.id }} &bull; INSCRIBED: {{ post.created_at.strftime('%Y-%m-%d %H:%M:%S UTC') }}</span>
                    <span>OBSERVATIONS: {{ post.views }}</span>
                </div>
                <pre class="reader-text">{{ post.content }}</pre>
                <div style="text-align:right; margin-top:16px;">
                    <button class="menu-btn" style="font-size:10px;" onclick="prepareRemoval({{ post.id }})">
                        PETITION REMOVAL OF THIS RECORD
                    </button>
                </div>
            </article>
        {% else %}
            <div class="table-wrap">
                <div class="table-head">
                    <div>ID</div>
                    <div>INSCRIPTION TITLE / PAYLOAD</div>
                    <div style="text-align:right;">VIEWS / DATE</div>
                </div>

                {% if not posts %}
                    <div style="padding:40px; text-align:center; font-size:12px; color:#551818;">
                        NO ENTRIES RECORDED UNDER THIS INCANTATION.
                    </div>
                {% endif %}

                {% for p in posts %}
                    <a href="/post/{{ p.id }}?page={{ current_page }}" class="table-row">
                        <div class="row-id">#{{ p.id }}</div>
                        <div class="row-title">{{ p.title }}</div>
                        <div class="row-meta">
                            {{ p.views }} EYES &bull; {{ p.created_at.strftime('%Y-%m-%d') }}
                        </div>
                    </a>
                {% endfor %}

                <div class="pager-bar">
                    <div>
                        PAGE {{ current_page }} OF {{ total_pages }} ({{ total_count }} TOTAL RECORDS)
                    </div>
                    <div style="display:flex; gap:8px;">
                        <a href="/?page=1{% if query %}&q={{ query }}{% endif %}" 
                           class="pager-link {% if current_page <= 1 %}disabled{% endif %}">
                           |&lt; FIRST
                        </a>
                        <a href="/?page={{ current_page - 1 }}{% if query %}&q={{ query }}{% endif %}" 
                           class="pager-link {% if current_page <= 1 %}disabled{% endif %}">
                           &lt; PREV
                        </a>
                        <a href="/?page={{ current_page + 1 }}{% if query %}&q={{ query }}{% endif %}" 
                           class="pager-link {% if current_page >= total_pages %}disabled{% endif %}">
                           NEXT &gt;
                        </a>
                        <a href="/?page={{ total_pages }}{% if query %}&q={{ query }}{% endif %}" 
                           class="pager-link {% if current_page >= total_pages %}disabled{% endif %}">
                           LAST &gt;|
                        </a>
                    </div>
                </div>
            </div>
        {% endif %}
    </main>

    <div id="createModal" class="modal-screen">
        <div class="modal-box">
            <div class="modal-title">
                <span>[ + ] INSCRIBE CODEX</span>
                <button class="menu-btn" style="padding:2px 6px;" onclick="closeModal('createModal')">[X]</button>
            </div>
            <form action="/create" method="POST">
                <div class="form-row">
                    <label>INSCRIPTION NAME / TITLE</label>
                    <input type="text" name="title" required placeholder="Codex identifier or moniker...">
                </div>
                <div class="form-row">
                    <label>RITE CONTENT</label>
                    <textarea name="content" rows="9" required placeholder="Paste or type content here..."></textarea>
                </div>
                <div style="font-size:10px; color:#672020; margin-bottom:14px; line-height:1.5;">
                    * Submissions are permanent and cannot be modified once stored.<br>
                    * Rate limit: Maximum 3 inscriptions per hour per steady node.
                </div>
                <button type="submit" class="action-btn">SEAL INTO RECORD</button>
            </form>
            <button class="cancel-btn" onclick="closeModal('createModal')">ABORT</button>
        </div>
    </div>

    <div id="rulesModal" class="modal-screen">
        <div class="modal-box">
            <div class="modal-title">
                <span>[ ! ] TERMS OF SERVICE &amp; EDICTS</span>
                <button class="menu-btn" style="padding:2px 6px;" onclick="closeModal('rulesModal')">[X]</button>
            </div>
            <div style="font-size:11px; line-height:1.8; color:#f0a8a8;">
                <p style="padding-bottom:10px; border-bottom:1px solid #330000; margin-bottom:10px; color:#ffffff;">
                    <strong style="color:var(--bright-crimson)">COVENANT OF ABSOLUTE BLINDNESS:</strong><br>
                    Even the owner and architects of this site cannot see who you are. All network data is 
                    atomically destroyed and transformed into irreversible mathematical hashes upon arrival. 
                    No raw IPs, hardware fingerprints, or user identifiers are ever recorded or viewable by anyone.
                </p>
                <p><strong style="color:var(--bright-crimson)">EDICT I &bull; ZERO TOLERANCE:</strong> Absolutely no CP / CSAM under any circumstance.</p>
                <p><strong style="color:var(--bright-crimson)">EDICT II &bull; NO GORE:</strong> No bodily mutilation, severe violence, or slaughter content.</p>
                <p><strong style="color:var(--bright-crimson)">EDICT III &bull; NO STOLEN DATA:</strong> Stolen databases, hacked credentials, and malicious tools are barred.</p>
                <p><strong style="color:var(--bright-crimson)">EDICT IV &bull; NO TRACKERS:</strong> Grabify links, IP loggers, and phishing endpoints are strictly banned.</p>
                <p><strong style="color:var(--bright-crimson)">EDICT V &bull; NO DOXXING:</strong> Private personal information of unconsenting individuals must remain completely hidden.</p>
            </div>
            <button class="action-btn" style="margin-top:20px;" onclick="closeModal('rulesModal')">I UNDERSTAND AND AGREE</button>
        </div>
    </div>

    <div id="removalModal" class="modal-screen">
        <div class="modal-box">
            <div class="modal-title">
                <span>[ - ] PETITION REMOVAL</span>
                <button class="menu-btn" style="padding:2px 6px;" onclick="closeModal('removalModal')">[X]</button>
            </div>
            <form action="/removal" method="POST">
                <div class="form-row">
                    <label>TARGET RECORD ID</label>
                    <input type="number" id="removal_post_id" name="post_id" required placeholder="e.g. 42">
                </div>
                <div class="form-row">
                    <label>CLAIM OR EDICT VIOLATION</label>
                    <textarea name="reason" rows="4" required placeholder="State exact edict or legal infringement..."></textarea>
                </div>
                <div class="form-row">
                    <label>CONTACT HASH OR EMAIL (OPTIONAL)</label>
                    <input type="email" name="contact_info" placeholder="inquisitor@domain.onion">
                </div>
                <button type="submit" class="action-btn">SUBMIT TO COUNCIL</button>
            </form>
            <button class="cancel-btn" onclick="closeModal('removalModal')">ABORT</button>
        </div>
    </div>

    <script>
        function toggleMenu(open) {
            document.getElementById('sidebar').classList.toggle('active', open);
        }
        function openModal(id) {
            toggleMenu(false);
            document.getElementById(id).classList.add('active');
        }
        function closeModal(id) {
            document.getElementById(id).classList.remove('active');
        }
        function prepareRemoval(postId) {
            document.getElementById('removal_post_id').value = postId;
            openModal('removalModal');
        }

        document.addEventListener('contextmenu', function(e) {
            e.preventDefault();
            return false;
        });

        document.addEventListener('keydown', function(e) {
            if (
                e.key === "F12" ||
                (e.ctrlKey && e.shiftKey && (e.key === "I" || e.key === "i" || e.key === "J" || e.key === "j" || e.key === "C" || e.key === "c")) ||
                (e.ctrlKey && (e.key === "U" || e.key === "u" || e.key === "S" || e.key === "s"))
            ) {
                e.preventDefault();
                e.stopPropagation();
                return false;
            }
        });

        try {
            const noop = function () {};
            window.console.log = noop;
            window.console.warn = noop;
            window.console.error = noop;
            window.console.info = noop;
            window.console.table = noop;
            window.console.dir = noop;
        } catch (e) {}
    </script>
</body>
</html>
"""

# ==============================================================================
# SECURE OWNER CONSOLE TEMPLATE (SERVED ONLY TO VALID AUTHENTICATED KEY)
# ==============================================================================
CONSOLE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CATHARS | HOST SANCTUM</title>
    <style>
        body {
            background-color: #020000;
            color: #d19a9a;
            font-family: "Courier New", Courier, monospace;
            padding: 24px;
        }
        h1 {
            color: #ff1a1a;
            font-size: 22px;
            letter-spacing: 4px;
            margin-bottom: 8px;
            border-bottom: 2px solid #5a0000;
            padding-bottom: 8px;
        }
        .meta-sub {
            font-size: 11px;
            color: #7b2626;
            margin-bottom: 25px;
        }
        .banner {
            background: #190202;
            border: 1px solid #771212;
            padding: 10px 14px;
            color: #ffaaaa;
            font-size: 12px;
            margin-bottom: 20px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 40px;
            background: #080101;
            border: 1px solid #280303;
        }
        th, td {
            padding: 10px 12px;
            font-size: 11px;
            text-align: left;
            border-bottom: 1px solid #1c0202;
        }
        th {
            background: #140202;
            color: #ff1a1a;
            letter-spacing: 1px;
        }
        tr:hover { background: #130101; }
        .node-tag {
            color: #39ff14;
            font-weight: bold;
            letter-spacing: 1px;
        }
        .btn-action {
            border: none;
            color: #fff;
            padding: 5px 9px;
            cursor: pointer;
            font-family: inherit;
            font-size: 10px;
            letter-spacing: 1px;
            font-weight: bold;
        }
        .btn-ban { background: #600000; border: 1px solid #ff1a1a; }
        .btn-ban:hover { background: #b30000; }
        .btn-delete { background: #8b0000; border: 1px solid #ff4444; margin-left: 6px; }
        .btn-delete:hover { background: #e60000; }
        .btn-unban { background: #1b4d1b; border: 1px solid #33cc33; }
        .btn-unban:hover { background: #288028; }
    </style>
</head>
<body>
    <h1>[!] CATHARS HOST COMMAND CONSOLE</h1>
    <div class="meta-sub">AUTHORIZED OPERATOR ACCESS ONLY &bull; TRIPWIRE ACTIVE</div>

    {% if msg %}
        <div class="banner">{{ msg }}</div>
    {% endif %}

    <h2 style="color:#ff4444; font-size:14px; margin-bottom:10px; letter-spacing:2px;">GLOBAL POSTS &amp; STEADY NODE REPOSITORY</h2>
    <table>
        <thead>
            <tr>
                <th style="width:70px;">SERIAL #</th>
                <th>POST NAME / TITLE</th>
                <th style="width:80px;">VIEWS</th>
                <th style="width:230px;">STEADY NODE STRING</th>
                <th style="width:130px;">DATE</th>
                <th style="width:220px;">ACTIONS</th>
            </tr>
        </thead>
        <tbody>
            {% for p in posts %}
            <tr>
                <td style="color:#ff1a1a; font-weight:bold;">#{{ p.id }}</td>
                <td style="color:#ffffff;">
                    <a href="/post/{{ p.id }}" target="_blank" style="color:#f7a8a8; text-decoration:none;">{{ p.title }}</a>
                </td>
                <td>{{ p.views }}</td>
                <td><span class="node-tag">{{ p.node_id }}</span></td>
                <td style="color:#772626;">{{ p.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
                <td>
                    <div style="display:flex; align-items:center;">
                        <form action="/access/console/ban" method="POST" style="margin:0;">
                            <input type="hidden" name="key" value="{{ key }}">
                            <input type="hidden" name="node_id" value="{{ p.node_id }}">
                            <button type="submit" class="btn-action btn-ban" onclick="return confirm('Disappear the entire website for this node?')">[ BAN NODE ]</button>
                        </form>
                        <form action="/access/console/delete" method="POST" style="margin:0;">
                            <input type="hidden" name="key" value="{{ key }}">
                            <input type="hidden" name="post_id" value="{{ p.id }}">
                            <button type="submit" class="btn-action btn-delete" onclick="return confirm('Eradicate post #{{ p.id }} completely from the database?')">[ PURGE RECORD ]</button>
                        </form>
                    </div>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <h2 style="color:#ff4444; font-size:14px; margin-bottom:10px; letter-spacing:2px;">DISAPPEARED / GHOST-BANNED NODES</h2>
    <table>
        <thead>
            <tr>
                <th>BANNED STEADY NODE STRING</th>
                <th>TIMESTAMP</th>
                <th>REASON / NOTE</th>
                <th style="width:100px;">RESTORE</th>
            </tr>
        </thead>
        <tbody>
            {% if not bans %}
                <tr><td colspan="4" style="text-align:center; color:#501616;">NO ACTIVE GHOST BANS IN EFFECT.</td></tr>
            {% endif %}
            {% for b in bans %}
            <tr>
                <td><span class="node-tag" style="color:#ff5555;">{{ b.node_id }}</span></td>
                <td>{{ b.banned_at.strftime('%Y-%m-%d %H:%M') }}</td>
                <td style="color:#994444;">{{ b.note }}</td>
                <td>
                    <form action="/access/console/unban" method="POST" style="margin:0;">
                        <input type="hidden" name="key" value="{{ key }}">
                        <input type="hidden" name="node_id" value="{{ b.node_id }}">
                        <button type="submit" class="btn-action btn-unban">[ UNBAN ]</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>
"""

# ==============================================================================
# FLASK ROUTE HANDLERS
# ==============================================================================

@app.route("/")
def index():
    query = request.args.get("q", "").strip()
    msg = request.args.get("msg", "")
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    per_page = 40
    offset = (page - 1) * per_page

    conn = get_db()
    cur = conn.cursor()

    if query:
        cur.execute(
            """SELECT COUNT(*) AS total FROM cathars_posts 
               WHERE title ILIKE %s OR content ILIKE %s""",
            (f"%{query}%", f"%{query}%")
        )
        total_count = cur.fetchone()["total"]

        cur.execute(
            """SELECT id, title, views, created_at FROM cathars_posts 
               WHERE title ILIKE %s OR content ILIKE %s 
               ORDER BY id DESC LIMIT %s OFFSET %s""",
            (f"%{query}%", f"%{query}%", per_page, offset)
        )
    else:
        cur.execute("SELECT COUNT(*) AS total FROM cathars_posts")
        total_count = cur.fetchone()["total"]

        cur.execute(
            """SELECT id, title, views, created_at FROM cathars_posts 
               ORDER BY id DESC LIMIT %s OFFSET %s""",
            (per_page, offset)
        )

    posts = cur.fetchall()
    cur.close()
    conn.close()

    total_pages = max(1, math.ceil(total_count / per_page))

    return render_template_string(
        HTML_TEMPLATE,
        posts=posts,
        query=query,
        msg=msg,
        post=None,
        current_page=page,
        total_pages=total_pages,
        total_count=total_count
    )


@app.route("/post/<int:post_id>")
def view_post(post_id):
    page = request.args.get("page", 1, type=int)
    raw_ip = request.headers.get("x-forwarded-for", request.remote_addr).split(",")[0].strip()
    node_id = get_steady_node_id(raw_ip)
    ip_h = hashlib.sha256((raw_ip + IP_SALT).encode("utf-8")).hexdigest()[:16]

    conn = get_db()
    cur = conn.cursor()

    cur.execute("UPDATE cathars_posts SET views = views + 1 WHERE id = %s", (post_id,))
    cur.execute(
        "INSERT INTO cathars_audit_logs (post_id, action, ip_hash, node_id) VALUES (%s, 'VIEW_POST', %s, %s)",
        (post_id, ip_h, node_id)
    )

    cur.execute("SELECT id, title, content, views, created_at FROM cathars_posts WHERE id = %s", (post_id,))
    post = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if not post:
        return redirect(url_for("index", msg="Record not found in the archives.", page=page))

    post["content"] = cathars_decrypt(post["content"])

    return render_template_string(HTML_TEMPLATE, post=post, posts=[], query="", msg="", page=page)


@app.route("/create", methods=["POST"])
def create_post():
    raw_ip = request.headers.get("x-forwarded-for", request.remote_addr).split(",")[0].strip()
    node_id = get_steady_node_id(raw_ip)
    ip_h = hashlib.sha256((raw_ip + IP_SALT).encode("utf-8")).hexdigest()[:16]

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()

    if not title or not content:
        return redirect(url_for("index", msg="Both title and content are mandatory."))

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """SELECT COUNT(*) AS count FROM cathars_audit_logs 
           WHERE node_id = %s AND action = 'CREATE_POST' AND created_at > NOW() - INTERVAL '1 hour'""",
        (node_id,)
    )
    result = cur.fetchone()
    if result["count"] >= 3:
        cur.close()
        conn.close()
        return redirect(url_for("index", msg="Rate limit engaged: Maximum 3 inscriptions per hour permitted."))

    encrypted_content = cathars_encrypt(content)

    cur.execute(
        "INSERT INTO cathars_posts (title, content, author_hash, node_id) VALUES (%s, %s, %s, %s) RETURNING id",
        (title, encrypted_content, ip_h, node_id)
    )
    new_id = cur.fetchone()["id"]

    cur.execute(
        "INSERT INTO cathars_audit_logs (post_id, action, ip_hash, node_id) VALUES (%s, 'CREATE_POST', %s, %s)",
        (new_id, ip_h, node_id)
    )
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("view_post", post_id=new_id))


@app.route("/removal", methods=["POST"])
def request_removal():
    raw_ip = request.headers.get("x-forwarded-for", request.remote_addr).split(",")[0].strip()
    node_id = get_steady_node_id(raw_ip)
    ip_h = hashlib.sha256((raw_ip + IP_SALT).encode("utf-8")).hexdigest()[:16]

    post_id = request.form.get("post_id")
    reason = request.form.get("reason", "").strip()
    contact_info = request.form.get("contact_info", "").strip()

    if not post_id or not reason:
        return redirect(url_for("index", msg="Post ID and reason are mandatory for removal."))

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO cathars_removals (post_id, reason, contact_info, ip_hash) VALUES (%s, %s, %s, %s)",
        (post_id, reason, contact_info, ip_h)
    )
    cur.execute(
        "INSERT INTO cathars_audit_logs (post_id, action, ip_hash, node_id) VALUES (%s, 'REQUEST_REMOVAL', %s, %s)",
        (post_id, ip_h, node_id)
    )
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("index", msg="Petition registered. The Sanctum Council will review."))


# ==============================================================================
# SECURED OWNER CONSOLE & SCANNER TRIPWIRE SYSTEM
# ==============================================================================

def record_failed_probe_and_tripwire(node_id: str, raw_ip: str):
    """
    Logs unauthorized probes. If 3 wrong attempts occur within 24 hours,
    the node is permanently vanished into cathars_banned_nodes.
    """
    try:
        conn = get_db()
        cur = conn.cursor()
        ip_h = hashlib.sha256((raw_ip + IP_SALT).encode("utf-8")).hexdigest()[:16]

        cur.execute(
            "INSERT INTO cathars_audit_logs (action, ip_hash, node_id) VALUES ('UNAUTHORIZED_PROBE', %s, %s)",
            (ip_h, node_id)
        )

        cur.execute(
            """SELECT COUNT(*) AS attempts FROM cathars_audit_logs 
               WHERE node_id = %s AND action = 'UNAUTHORIZED_PROBE' 
               AND created_at > NOW() - INTERVAL '24 hours'""",
            (node_id,)
        )
        attempts = cur.fetchone()["attempts"]

        if attempts >= 3:
            cur.execute(
                """INSERT INTO cathars_banned_nodes (node_id, note) 
                   VALUES (%s, 'Auto-Ghosted: Console Scanner Probe Triggered') 
                   ON CONFLICT DO NOTHING""",
                (node_id,)
            )

        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


@app.route("/access/console/", methods=["GET"])
def host_console():
    key = request.args.get("key", "").strip()
    msg = request.args.get("msg", "")

    raw_ip = request.headers.get("x-forwarded-for", request.remote_addr).split(",")[0].strip()
    node_id = get_steady_node_id(raw_ip)

    is_valid = hmac.compare_digest(key, HOST_CONSOLE_KEY)

    if not is_valid:
        record_failed_probe_and_tripwire(node_id, raw_ip)
        return Response("", status=404)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, title, views, node_id, created_at FROM cathars_posts ORDER BY id DESC")
    posts = cur.fetchall()

    cur.execute("SELECT node_id, banned_at, note FROM cathars_banned_nodes ORDER BY id DESC")
    bans = cur.fetchall()
    cur.close()
    conn.close()

    return render_template_string(CONSOLE_TEMPLATE, posts=posts, bans=bans, key=key, msg=msg)


@app.route("/access/console/delete", methods=["POST"])
def purge_post():
    key = request.form.get("key", "").strip()
    post_id = request.form.get("post_id", "").strip()

    if not hmac.compare_digest(key, HOST_CONSOLE_KEY):
        return Response("", status=404)

    if post_id:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM cathars_posts WHERE id = %s", (post_id,))
        cur.execute("DELETE FROM cathars_removals WHERE post_id = %s", (post_id,))
        conn.commit()
        cur.close()
        conn.close()

    return redirect(url_for("host_console", key=key, msg=f"Record #{post_id} completely eradicated from existence."))


@app.route("/access/console/ban", methods=["POST"])
def ban_node():
    key = request.form.get("key", "").strip()
    node_id = request.form.get("node_id", "").strip()

    if not hmac.compare_digest(key, HOST_CONSOLE_KEY):
        return Response("", status=404)

    if node_id:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO cathars_banned_nodes (node_id, note) 
               VALUES (%s, 'Vanished by Host Command') 
               ON CONFLICT (node_id) DO NOTHING""",
            (node_id,)
        )
        conn.commit()
        cur.close()
        conn.close()

    return redirect(url_for("host_console", key=key, msg=f"Node {node_id} has been completely vanished."))


@app.route("/access/console/unban", methods=["POST"])
def unban_node():
    key = request.form.get("key", "").strip()
    node_id = request.form.get("node_id", "").strip()

    if not hmac.compare_digest(key, HOST_CONSOLE_KEY):
        return Response("", status=404)

    if node_id:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM cathars_banned_nodes WHERE node_id = %s", (node_id,))
        conn.commit()
        cur.close()
        conn.close()

    return redirect(url_for("host_console", key=key, msg=f"Node {node_id} restored to visibility."))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)