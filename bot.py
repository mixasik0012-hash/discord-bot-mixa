import discord
from discord import app_commands
import sqlite3
import os
from datetime import datetime, timedelta
import asyncio
import re
import random

ALLOWED_ROLES = [⚔️Админ состав⚔️"]
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_FILE = "bot_data.db"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

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
welcome_enabled INTEGER DEFAULT 0,
leave_enabled INTEGER DEFAULT 0,
logging_enabled INTEGER DEFAULT 0,
automod_enabled INTEGER DEFAULT 0,
temp_channels_enabled INTEGER DEFAULT 0,
temp_channel_category_id TEXT,
temp_channel_name TEXT DEFAULT '🔊 Временный',
automod_anti_caps INTEGER DEFAULT 0,
automod_caps_percent INTEGER DEFAULT 70,
automod_anti_links INTEGER DEFAULT 0,
automod_bad_words TEXT DEFAULT '',
moderator_role_ids TEXT DEFAULT '',
temp_creator_channel_name TEXT DEFAULT 'test'
)''')
    c.execute('''CREATE TABLE IF NOT EXISTS warnings (
id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT, user_id TEXT,
reason TEXT, moderator TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mutes (
guild_id TEXT, user_id TEXT, until TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS voice_mutes (
guild_id TEXT, user_id TEXT, until TEXT)''')
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

@bot.event
async def on_ready():
    print(f'🚀 Бот {bot.user} готов!')

@bot.event
async def on_voice_state_update(member, before, after):
    print(f"🎤 {member.name}: {before.channel} -> {after.channel}")
    guild_id = str(member.guild.id)
    if not get_setting(guild_id, "temp_channels_enabled"):
        return
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
                print(f"❌ Ошибка: {e}")
    if before.channel:
        ch_id = str(before.channel.id)
        row = db_execute_one("SELECT owner_id FROM temp_channels WHERE channel_id = ?", (ch_id,))
        if row and len(before.channel.members) == 0:
            try:
                await before.channel.delete()
                db_execute("DELETE FROM temp_channels WHERE channel_id = ?", (ch_id,))
            except:
                pass

# ВАРНЫ
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
    except:
        pass

@bot.tree.command(name="warn_remove", description="Снять варн")
async def warn_remove(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction): return
    gid, uid = str(interaction.guild.id), str(user.id)
    db_execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ? AND id = (SELECT id FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1)",
              (gid, uid, gid, uid))
    await interaction.response.send_message(f"✅ Варн снят с {user.mention}")
    try:
        await user.send(f"✅ С вас снято предупреждение на сервере **{interaction.guild.name}**")
    except:
        pass

@bot.tree.command(name="warnings", description="Список варнов")
async def warnings_list(interaction: discord.Interaction, user: discord.Member = None):
    if not user: user = interaction.user
    await interaction.response.send_message(f"📋 Варны {user.mention}: команда в разработке")

# ТАЙМАУТ
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
    except:
        pass

@bot.tree.command(name="untimeout", description="Снять таймаут")
async def untimeout(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction): return
    await user.timeout(None)
    await interaction.response.send_message(f"🔊 Таймаут снят с {user.mention}")
    try:
        await user.send(f"🔊 С вас снят таймаут на сервере **{interaction.guild.name}**")
    except:
        pass

# ГОЛОСОВОЙ МЬЮТ
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
    except:
        pass

@bot.tree.command(name="vunmute", description="Снять мьют")
async def vunmute(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction): return
    await user.edit(mute=False)
    await interaction.response.send_message(f"🎤 Мьют снят с {user.mention}")
    try:
        await user.send(f"🎤 С вас снят голосовой мьют на сервере **{interaction.guild.name}**")
    except:
        pass

# УРОВНИ
@bot.tree.command(name="rank", description="Уровень")
async def rank(interaction: discord.Interaction):
    await interaction.response.send_message("🎖️ Система уровней активирована!")

@bot.tree.command(name="top", description="Топ")
async def top(interaction: discord.Interaction):
    await interaction.response.send_message("🏆 Топ пока пуст.")

bot.run(BOT_TOKEN)
