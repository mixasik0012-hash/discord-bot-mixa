import discord
from discord import app_commands
import sqlite3
import os
from datetime import datetime, timedelta
import asyncio
import re
import random
import threading
from flask import Flask, render_template, request, redirect, url_for, session
from flask_cors import CORS

# =============================================
# НАСТРОЙКИ БОТА
# =============================================
ALLOWED_ROLES = ["⚔️Админ состав⚔️"]
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_FILE = "bot_data.db"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

# =============================================
# БАЗА ДАННЫХ
# =============================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS server_settings (
guild_id TEXT PRIMARY KEY, auto_role_id TEXT, welcome_channel_id TEXT,
welcome_text TEXT DEFAULT '👋 Добро пожаловать, {user}!', leave_channel_id TEXT,
leave_text TEXT DEFAULT '😢 {user} покинул нас...', log_channel_id TEXT,
leveling_enabled INTEGER DEFAULT 0, welcome_enabled INTEGER DEFAULT 0,
leave_enabled INTEGER DEFAULT 0, logging_enabled INTEGER DEFAULT 0,
automod_enabled INTEGER DEFAULT 0, temp_channels_enabled INTEGER DEFAULT 0,
temp_channel_category_id TEXT, temp_channel_name TEXT DEFAULT '🔊 Временный',
automod_anti_caps INTEGER DEFAULT 0, automod_caps_percent INTEGER DEFAULT 70,
automod_anti_links INTEGER DEFAULT 0, automod_bad_words TEXT DEFAULT '',
moderator_role_ids TEXT DEFAULT '', temp_creator_channel_name TEXT DEFAULT 'test')''')
    c.execute('''CREATE TABLE IF NOT EXISTS warnings (
id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT, user_id TEXT,
reason TEXT, moderator TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mutes (guild_id TEXT, user_id TEXT, until TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS voice_mutes (guild_id TEXT, user_id TEXT, until TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_levels (
guild_id TEXT, user_id TEXT, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS temp_channels (
guild_id TEXT, channel_id TEXT, owner_id TEXT)''')
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=()):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def db_execute_one(query, params=()):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    result = c.fetchone()
    conn.commit()
    conn.close()
    return result

def get_setting(guild_id, key):
    result = db_execute_one(f"SELECT {key} FROM server_settings WHERE guild_id = ?", (str(guild_id),))
    return result[0] if result else None

def parse_time(time_str: str) -> int:
    time_str = time_str.lower().strip()
    total = 0
    for unit, mins in [('mo', 43200), ('w', 10080), ('d', 1440), ('h', 60), ('mi', 1)]:
        match = re.search(rf'(\d+)\s*{unit}', time_str)
        if match: total += int(match.group(1)) * mins
    return total

def format_time(minutes: int) -> str:
    mo, m = divmod(minutes, 43200)
    w, m = divmod(m, 10080)
    d, m = divmod(m, 1440)
    h, mi = divmod(m, 60)
    parts = []
    if mo: parts.append(f"{mo}mo")
    if w: parts.append(f"{w}w")
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if mi: parts.append(f"{mi}mi")
    return " ".join(parts) if parts else "0mi"

def has_permission(interaction: discord.Interaction) -> bool:
    guild_id = str(interaction.guild.id)
    mod_ids = get_setting(guild_id, "moderator_role_ids")
    if mod_ids:
        allowed = [rid.strip() for rid in mod_ids.split(",") if rid.strip()]
        user_roles = [str(r.id) for r in interaction.user.roles]
        if any(rid in user_roles for rid in allowed):
            return True
    user_names = [r.name for r in interaction.user.roles]
    return any(role in ALLOWED_ROLES for role in user_names)

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
    async def setup_hook(self):
        await self.tree.sync()
        print('✅ Команды синхронизированы!')

bot = MyBot()

# =============================================
# БОТ: СОБЫТИЯ
# =============================================
@bot.event
async def on_ready():
    print(f'🚀 Бот {bot.user} готов!')

@bot.event
async def on_voice_state_update(member, before, after):
    guild_id = str(member.guild.id)
    if not get_setting(guild_id, "temp_channels_enabled"): return
    if after.channel:
        creator = get_setting(guild_id, "temp_creator_channel_name") or "test"
        if after.channel.name.lower() == creator.lower():
            try:
                cat_id = get_setting(guild_id, "temp_channel_category_id")
                cat = member.guild.get_channel(int(cat_id)) if cat_id else None
                tname = get_setting(guild_id, "temp_channel_name") or "канал"
                ch = await member.guild.create_voice_channel(f"{tname} {member.display_name}", category=cat)
                await member.move_to(ch)
                db_execute("INSERT INTO temp_channels VALUES (?, ?, ?)", (guild_id, str(ch.id), str(member.id)))
            except Exception as e:
                print(f"Ошибка: {e}")
    if before.channel:
        ch_id = str(before.channel.id)
        row = db_execute_one("SELECT owner_id FROM temp_channels WHERE channel_id = ?", (ch_id,))
        if row and len(before.channel.members) == 0:
            try:
                await before.channel.delete()
                db_execute("DELETE FROM temp_channels WHERE channel_id = ?", (ch_id,))
            except: pass

# =============================================
# БОТ: КОМАНДЫ
# =============================================
@bot.tree.command(name="warn", description="Выдать предупреждение")
@app_commands.describe(user="Кому", reason="Причина")
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str = "Не указана"):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return
    gid, uid = str(interaction.guild.id), str(user.id)
    db_execute("INSERT INTO warnings VALUES (NULL, ?, ?, ?, ?, ?)",
              (gid, uid, reason, interaction.user.name, datetime.now().strftime("%d.%m.%Y %H:%M:%S")))
    await interaction.response.send_message(f"⚠️ Варн выдан {user.mention}: {reason}")
    try:
        embed = discord.Embed(title="⚠️ Предупреждение", color=0xFFA500)
        embed.add_field(name="Сервер", value=interaction.guild.name)
        embed.add_field(name="Модератор", value=interaction.user.display_name)
        embed.add_field(name="Причина", value=reason)
        await user.send(embed=embed)
    except: pass

@bot.tree.command(name="warn_remove", description="Снять варн")
async def warn_remove(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction): return
    gid, uid = str(interaction.guild.id), str(user.id)
    db_execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ? AND id = (SELECT id FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1)",
              (gid, uid, gid, uid))
    await interaction.response.send_message(f"✅ Варн снят с {user.mention}")

@bot.tree.command(name="warnings", description="Список варнов")
async def warnings_list(interaction: discord.Interaction, user: discord.Member = None):
    if not user: user = interaction.user
    await interaction.response.send_message(f"📋 Варны {user.mention}: команда в разработке")

@bot.tree.command(name="timeout", description="Таймаут")
async def timeout(interaction: discord.Interaction, user: discord.Member, time: str, reason: str = ""):
    if not has_permission(interaction): return
    minutes = parse_time(time)
    if minutes <= 0 or minutes > 40320:
        await interaction.response.send_message("❌ Неверное время.", ephemeral=True)
        return
    await user.timeout(timedelta(minutes=minutes), reason=reason)
    await interaction.response.send_message(f"🔇 {user.mention} таймаут на {format_time(minutes)}")
    try:
        embed = discord.Embed(title="🔇 Таймаут", color=0xFF6600)
        embed.add_field(name="Сервер", value=interaction.guild.name)
        embed.add_field(name="Длительность", value=format_time(minutes))
        if reason: embed.add_field(name="Причина", value=reason)
        await user.send(embed=embed)
    except: pass

@bot.tree.command(name="untimeout", description="Снять таймаут")
async def untimeout(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction): return
    await user.timeout(None)
    await interaction.response.send_message(f"🔊 Таймаут снят с {user.mention}")

@bot.tree.command(name="vmute", description="Голосовой мьют")
async def vmute(interaction: discord.Interaction, user: discord.Member, time: str):
    if not has_permission(interaction): return
    minutes = parse_time(time)
    if minutes <= 0: return
    await user.edit(mute=True)
    await interaction.response.send_message(f"🎤 {user.mention} мьют на {format_time(minutes)}")
    try:
        embed = discord.Embed(title="🎤 Голосовой мьют", color=0x9933FF)
        embed.add_field(name="Сервер", value=interaction.guild.name)
        embed.add_field(name="Длительность", value=format_time(minutes))
        await user.send(embed=embed)
    except: pass

@bot.tree.command(name="vunmute", description="Снять мьют")
async def vunmute(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction): return
    await user.edit(mute=False)
    await interaction.response.send_message(f"🎤 Мьют снят с {user.mention}")

@bot.tree.command(name="rank", description="Уровень")
async def rank(interaction: discord.Interaction):
    await interaction.response.send_message("🎖️ Система уровней активирована!")

@bot.tree.command(name="top", description="Топ")
async def top(interaction: discord.Interaction):
    await interaction.response.send_message("🏆 Топ пока пуст.")

# =============================================
# САЙТ
# =============================================
CLIENT_ID = "1529545316003479843"
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:5000/callback")
API_BASE = "https://discord.com/api/v10"

site_app = Flask(__name__)
site_app.secret_key = os.urandom(24).hex()
CORS(site_app)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def get_user_guilds(token):
    import requests as req
    r = req.get(f'{API_BASE}/users/@me/guilds', headers={'Authorization': f'Bearer {token}'}, timeout=10)
    return r.json() if r.ok else []

def get_guild_roles(guild_id):
    import requests as req
    r = req.get(f'{API_BASE}/guilds/{guild_id}/roles', headers={'Authorization': f'Bot {BOT_TOKEN}'}, timeout=10)
    return r.json() if r.ok else []

def get_guild_channels(guild_id):
    import requests as req
    r = req.get(f'{API_BASE}/guilds/{guild_id}/channels', headers={'Authorization': f'Bot {BOT_TOKEN}'}, timeout=10)
    return r.json() if r.ok else []

def get_user_info(token):
    import requests as req
    r = req.get(f'{API_BASE}/users/@me', headers={'Authorization': f'Bearer {token}'}, timeout=10)
    return r.json() if r.ok else None

def exchange_code(code):
    import requests as req
    data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
    r = req.post(f'{API_BASE}/oauth2/token', data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=10)
    return r.json() if r.ok else None

@site_app.route('/')
def index():
    return f'''
    <!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Mixasik</title>
    <style>body{{font-family:sans-serif;background:#1a1a2e;color:#fff;display:flex;justify-content:center;align-items:center;min-height:100vh;text-align:center;}}
    .btn{{background:#5865F2;color:white;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;margin:10px;}}</style></head>
    <body><div><h1>🤖 Mixasik</h1><p>Панель управления ботом</p>
    <a href="/login" class="btn">🔐 Войти через Discord</a></div></body></html>'''

@site_app.route('/login')
def login():
    return redirect(f"{API_BASE}/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds")

@site_app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code: return "Ошибка", 400
    td = exchange_code(code)
    if not td: return "Ошибка", 500
    session['access_token'] = td['access_token']
    ui = get_user_info(td['access_token'])
    session['user'] = {'id': ui['id'], 'username': ui['username']}
    return redirect(url_for('servers'))

@site_app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@site_app.route('/servers')
@login_required
def servers():
    guilds = get_user_guilds(session['access_token'])
    html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Сервера</title><style>body{{font-family:sans-serif;background:#0f0f1a;color:#fff;}}a{{color:#5865F2;display:block;padding:10px;}}</style></head><body><h1>📋 Выберите сервер</h1>'
    for g in guilds:
        html += f'<a href="/dashboard/{g["id"]}">{g["name"]}</a>'
    html += '</body></html>'
    return html

@site_app.route('/dashboard/<guild_id>')
@login_required
def dashboard(guild_id):
    roles = get_guild_roles(guild_id)
    result = db_execute_one("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
    settings = {}
    if result:
        cols = ['auto_role_id','welcome_channel_id','welcome_text','leave_channel_id','leave_text',
                'log_channel_id','leveling_enabled','welcome_enabled','leave_enabled','logging_enabled',
                'automod_enabled','temp_channels_enabled','temp_channel_category_id','temp_channel_name',
                'automod_anti_caps','automod_caps_percent','automod_anti_links','automod_bad_words',
                'moderator_role_ids','temp_creator_channel_name']
        for i, col in enumerate(cols):
            settings[col] = result[i+1] if len(result) > i+1 else ''
    
    html = '''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Панель</title>
    <style>body{font-family:sans-serif;background:#0f0f1a;color:#fff;padding:20px;}
    .card{background:rgba(255,255,255,0.05);padding:20px;border-radius:12px;margin:10px 0;}
    select,input,textarea{width:100%;padding:10px;margin:5px 0;background:rgba(0,0,0,0.3);color:white;border:1px solid rgba(255,255,255,0.1);border-radius:8px;}
    .btn{background:#5865F2;color:white;padding:14px;border:none;border-radius:8px;cursor:pointer;font-size:16px;}
    .toggle{display:flex;align-items:center;gap:10px;}
    .toggle input{{width:20px;height:20px;}}</style></head><body>
    <h1>⚙️ Панель управления</h1>
    <form action="/save/''' + guild_id + '''" method="POST">
    <div class="card"><h3>👑 Права доступа</h3>
    <label>Роли модераторов (ID через запятую)</label>
    <input type="text" name="moderator_role_ids" value="''' + settings.get('moderator_role_ids','') + '''">
    </div>
    <div class="card"><h3>👋 Приветствия</h3>
    <div class="toggle"><input type="checkbox" name="welcome_enabled" value="1" ''' + ('checked' if settings.get('welcome_enabled') else '') + '''> Включить</div>
    <label>Текст</label><textarea name="welcome_text">''' + settings.get('welcome_text','👋 Добро пожаловать!') + '''</textarea>
    </div>
    <div class="card"><h3>🔄 Авто-роль</h3>
    <select name="auto_role_id"><option value="">Не выбрана</option>'''
    for r in roles:
        if r['name'] != '@everyone':
            sel = 'selected' if settings.get('auto_role_id') == r['id'] else ''
            html += f'<option value="{r["id"]}" {sel}>{r["name"]}</option>'
    html += '''</select></div>
    <div class="card"><h3>🔊 Временные каналы</h3>
    <div class="toggle"><input type="checkbox" name="temp_channels_enabled" value="1" ''' + ('checked' if settings.get('temp_channels_enabled') else '') + '''> Включить</div>
    <label>Канал-создатель</label><input type="text" name="temp_creator_channel_name" value="''' + settings.get('temp_creator_channel_name','test') + '''">
    </div>
    <button type="submit" class="btn">💾 Сохранить</button></form></body></html>'''
    return html

@site_app.route('/save/<guild_id>', methods=['POST'])
@login_required
def save(guild_id):
    db_execute('''INSERT OR REPLACE INTO server_settings 
        (guild_id, auto_role_id, welcome_text, welcome_enabled, temp_channels_enabled, 
         temp_creator_channel_name, moderator_role_ids)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (guild_id,
         request.form.get('auto_role_id', ''),
         request.form.get('welcome_text', ''),
         request.form.get('welcome_enabled', '0'),
         request.form.get('temp_channels_enabled', '0'),
         request.form.get('temp_creator_channel_name', 'test'),
         request.form.get('moderator_role_ids', '')))
    return redirect(url_for('dashboard', guild_id=guild_id))

def run_site():
    site_app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_site, daemon=True).start()
print("🌐 Сайт запущен на порту 8080")

# =============================================
# ЗАПУСК БОТА
# =============================================
bot.run(BOT_TOKEN)
