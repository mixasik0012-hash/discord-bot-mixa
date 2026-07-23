from flask import Flask, render_template, request, redirect, url_for, session
from flask_cors import CORS
import requests
import os
import sqlite3

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
CORS(app)

CLIENT_ID = "1529545316003479843"
CLIENT_SECRET = "OZxiSNFpg3-CR7Gyf-NY2H9lXgEz3zg8"
REDIRECT_URI = "http://localhost:5000/callback"
BOT_TOKEN = "MTUyOTU0NTMxNjAwMzQ3OTg0Mw.GGxZtW.c2VakjBQ5qeDpxp_mXac-STp8x31Isgb-0PbEg"
API_BASE = "https://discord.com/api/v10"
DB_FILE = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS server_settings (
guild_id TEXT PRIMARY KEY,
auto_role_id TEXT,
welcome_channel_id TEXT,
welcome_text TEXT DEFAULT '👋 Добро пожаловать, {user}!',
leave_channel_id TEXT,
leave_text TEXT DEFAULT '😢 {user} покинул нас...',
log_channel_id TEXT,
leveling_enabled INTEGER DEFAULT 0,
welcome_enabled INTEGER DEFAULT 1,
leave_enabled INTEGER DEFAULT 1,
logging_enabled INTEGER DEFAULT 1,
automod_enabled INTEGER DEFAULT 0,
temp_channels_enabled INTEGER DEFAULT 0,
temp_channel_category_id TEXT,
temp_channel_name TEXT DEFAULT '🔊 Временный',
automod_anti_spam INTEGER DEFAULT 0,
automod_anti_caps INTEGER DEFAULT 0,
automod_caps_percent INTEGER DEFAULT 70,
automod_anti_links INTEGER DEFAULT 0,
automod_bad_words TEXT DEFAULT '',
moderator_role_ids TEXT DEFAULT '',
temp_creator_channel_name TEXT DEFAULT '⚙️Создать канал [+]⚙️',
welcome_roles TEXT DEFAULT '',
leave_roles TEXT DEFAULT '',
logging_roles TEXT DEFAULT '',
autorole_roles TEXT DEFAULT '',
levels_roles TEXT DEFAULT '',
tempchannels_roles TEXT DEFAULT '',
automod_roles TEXT DEFAULT ''
)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS warnings (
id INTEGER PRIMARY KEY AUTOINCREMENT,
guild_id TEXT,
user_id TEXT,
reason TEXT,
moderator TEXT,
date TEXT
)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS mutes (
guild_id TEXT,
user_id TEXT,
until TEXT,
reason TEXT,
moderator TEXT,
date TEXT
)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS voice_mutes (
guild_id TEXT,
user_id TEXT,
until TEXT,
reason TEXT,
moderator TEXT,
date TEXT
)''')
    
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    result = c.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return result

def db_execute_one(query, params=()):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    result = c.fetchone()
    conn.commit()
    conn.close()
    return result

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def get_user_guilds(token):
    headers = {'Authorization': f'Bearer {token}'}
    r = requests.get(f'{API_BASE}/users/@me/guilds', headers=headers)
    return r.json() if r.ok else []

def get_guild_roles(guild_id):
    headers = {'Authorization': f'Bot {BOT_TOKEN}'}
    r = requests.get(f'{API_BASE}/guilds/{guild_id}/roles', headers=headers)
    return r.json() if r.ok else []

def get_guild_channels(guild_id):
    headers = {'Authorization': f'Bot {BOT_TOKEN}'}
    r = requests.get(f'{API_BASE}/guilds/{guild_id}/channels', headers=headers)
    return r.json() if r.ok else []

def get_user_info(token):
    headers = {'Authorization': f'Bearer {token}'}
    r = requests.get(f'{API_BASE}/users/@me', headers=headers)
    return r.json() if r.ok else None

def exchange_code(code):
    data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    r = requests.post(f'{API_BASE}/oauth2/token', data=data, headers=headers)
    return r.json() if r.ok else None

@app.route('/')
def index():
    return render_template('index.html', bot_name="Mixasik",
                         invite_link=f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&scope=bot%20applications.commands&permissions=8")

@app.route('/login')
def login():
    return redirect(f"{API_BASE}/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds")

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code: return "Ошибка", 400
    td = exchange_code(code)
    if not td: return "Ошибка", 500
    session['access_token'] = td['access_token']
    ui = get_user_info(td['access_token'])
    session['user'] = {'id': ui['id'], 'username': ui['username'],
                       'avatar': f"https://cdn.discordapp.com/avatars/{ui['id']}/{ui['avatar']}.png" if ui.get('avatar') else ""}
    return redirect(url_for('select_server'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/servers')
@login_required
def select_server():
    guilds = get_user_guilds(session['access_token'])
    admin = [g for g in guilds if (int(g['permissions']) & 0x8) == 0x8]
    return render_template('servers.html', user=session['user'], guilds=admin)

@app.route('/dashboard/<guild_id>')
@login_required
def dashboard(guild_id):
    roles = get_guild_roles(guild_id)
    channels = get_guild_channels(guild_id)
    text_channels = [c for c in channels if c.get('type') == 0]
    categories = [c for c in channels if c.get('type') == 4]
    
    warns_count = db_execute_one("SELECT COUNT(*) FROM warnings WHERE guild_id = ?", (guild_id,))
    warns_count = warns_count[0] if warns_count else 0
    mutes_count = db_execute_one("SELECT COUNT(*) FROM mutes WHERE guild_id = ?", (guild_id,))
    mutes_count = mutes_count[0] if mutes_count else 0
    vmutes_count = db_execute_one("SELECT COUNT(*) FROM voice_mutes WHERE guild_id = ?", (guild_id,))
    vmutes_count = vmutes_count[0] if vmutes_count else 0
    
    result = db_execute_one("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
    settings = {}
    if result:
        settings = {
            'auto_role_id': result[1] if len(result) > 1 else '',
            'welcome_channel_id': result[2] if len(result) > 2 else '',
            'welcome_text': result[3] if len(result) > 3 else '👋 Добро пожаловать, {user}!',
            'leave_channel_id': result[4] if len(result) > 4 else '',
            'leave_text': result[5] if len(result) > 5 else '😢 {user} покинул нас...',
            'log_channel_id': result[6] if len(result) > 6 else '',
            'leveling_enabled': result[7] if len(result) > 7 else 0,
            'welcome_enabled': result[8] if len(result) > 8 else 1,
            'leave_enabled': result[9] if len(result) > 9 else 1,
            'logging_enabled': result[10] if len(result) > 10 else 1,
            'automod_enabled': result[11] if len(result) > 11 else 0,
            'temp_channels_enabled': result[12] if len(result) > 12 else 0,
            'temp_channel_category_id': result[13] if len(result) > 13 else '',
            'temp_channel_name': result[14] if len(result) > 14 else '🔊 Временный',
            'automod_anti_spam': result[15] if len(result) > 15 else 0,
            'automod_anti_caps': result[16] if len(result) > 16 else 0,
            'automod_caps_percent': result[17] if len(result) > 17 else 70,
            'automod_anti_links': result[18] if len(result) > 18 else 0,
            'automod_bad_words': result[19] if len(result) > 19 else '',
            'moderator_role_ids': result[20] if len(result) > 20 else '',
            'temp_creator_channel_name': result[21] if len(result) > 21 else '⚙️Создать канал [+]⚙️',
            'welcome_roles': result[22] if len(result) > 22 else '',
            'leave_roles': result[23] if len(result) > 23 else '',
            'logging_roles': result[24] if len(result) > 24 else '',
            'autorole_roles': result[25] if len(result) > 25 else '',
            'levels_roles': result[26] if len(result) > 26 else '',
            'tempchannels_roles': result[27] if len(result) > 27 else '',
            'automod_roles': result[28] if len(result) > 28 else ''
        }
    
    return render_template('dashboard.html', user=session['user'], guild_id=guild_id,
                         roles=roles, channels=text_channels, categories=categories, settings=settings,
                         warns_count=warns_count, mutes_count=mutes_count, vmutes_count=vmutes_count)

@app.route('/save_settings/<guild_id>', methods=['POST'])
@login_required
def save_settings(guild_id):
    db_execute('''INSERT OR REPLACE INTO server_settings 
        (guild_id, auto_role_id, welcome_channel_id, welcome_text, leave_channel_id, leave_text,
         log_channel_id, leveling_enabled, welcome_enabled, leave_enabled, logging_enabled,
         automod_enabled, temp_channels_enabled, temp_channel_category_id, temp_channel_name,
         automod_anti_spam, automod_anti_caps, automod_caps_percent, automod_anti_links, automod_bad_words,
         moderator_role_ids, temp_creator_channel_name, welcome_roles, leave_roles, logging_roles,
         autorole_roles, levels_roles, tempchannels_roles, automod_roles)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (guild_id,
         request.form.get('auto_role_id', ''),
         request.form.get('welcome_channel_id', ''),
         request.form.get('welcome_text', '👋 Добро пожаловать, {user}!'),
         request.form.get('leave_channel_id', ''),
         request.form.get('leave_text', '😢 {user} покинул нас...'),
         request.form.get('log_channel_id', ''),
         request.form.get('leveling_enabled', '0'),
         request.form.get('welcome_enabled', '0'),
         request.form.get('leave_enabled', '0'),
         request.form.get('logging_enabled', '1'),
         request.form.get('automod_enabled', '0'),
         request.form.get('temp_channels_enabled', '0'),
         request.form.get('temp_channel_category_id', ''),
         request.form.get('temp_channel_name', '🔊 Временный'),
         request.form.get('automod_anti_spam', '0'),
         request.form.get('automod_anti_caps', '0'),
         request.form.get('automod_caps_percent', '70'),
         request.form.get('automod_anti_links', '0'),
         request.form.get('automod_bad_words', ''),
         request.form.get('moderator_role_ids', ''),
         request.form.get('temp_creator_channel_name', '⚙️Создать канал [+]⚙️'),
         request.form.get('welcome_roles', ''),
         request.form.get('leave_roles', ''),
         request.form.get('logging_roles', ''),
         request.form.get('autorole_roles', ''),
         request.form.get('levels_roles', ''),
         request.form.get('tempchannels_roles', ''),
         request.form.get('automod_roles', '')))
    return redirect(url_for('dashboard', guild_id=guild_id))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
