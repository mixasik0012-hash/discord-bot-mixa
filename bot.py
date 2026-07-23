import discord
from discord import app_commands
import sqlite3
import os
from datetime import datetime, timedelta
import asyncio
import re
import random

ALLOWED_ROLES = ["⚔️Админ состав⚔️"]
BOT_TOKEN = os.getenv("BOT_TOKEN", "ТОКЕН_СЮДА_ЗАМЕНИТЕ")
DB_FILE = "/data/bot_data.db" if os.path.exists("/data") else "bot_data.db"

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
id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT, user_id TEXT,
reason TEXT, moderator TEXT, date TEXT
)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mutes (
guild_id TEXT, user_id TEXT, until TEXT, reason TEXT, moderator TEXT, date TEXT
)''')
    c.execute('''CREATE TABLE IF NOT EXISTS voice_mutes (
guild_id TEXT, user_id TEXT, until TEXT, reason TEXT, moderator TEXT, date TEXT
)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_levels (
guild_id TEXT, user_id TEXT, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
PRIMARY KEY (guild_id, user_id)
)''')
    c.execute('''CREATE TABLE IF NOT EXISTS temp_channels (
guild_id TEXT, channel_id TEXT PRIMARY KEY, owner_id TEXT
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

def get_setting(guild_id, key):
    result = db_execute_one(f"SELECT {key} FROM server_settings WHERE guild_id = ?", (str(guild_id),))
    return result[0] if result else None

def parse_time(time_str: str) -> int:
    time_str = time_str.lower().strip()
    total_minutes = 0
    patterns = {'mo': r'(\d+)\s*mo', 'w': r'(\d+)\s*w', 'd': r'(\d+)\s*d', 'h': r'(\d+)\s*h', 'mi': r'(\d+)\s*mi'}
    for match in re.finditer(patterns['mo'], time_str): total_minutes += int(match.group(1)) * 30 * 24 * 60
    for match in re.finditer(patterns['w'], time_str): total_minutes += int(match.group(1)) * 7 * 24 * 60
    for match in re.finditer(patterns['d'], time_str): total_minutes += int(match.group(1)) * 24 * 60
    for match in re.finditer(patterns['h'], time_str): total_minutes += int(match.group(1)) * 60
    for match in re.finditer(patterns['mi'], time_str): total_minutes += int(match.group(1))
    return total_minutes

def format_time(minutes: int) -> str:
    mo = minutes // (30 * 24 * 60); minutes %= (30 * 24 * 60)
    w = minutes // (7 * 24 * 60); minutes %= (7 * 24 * 60)
    d = minutes // (24 * 60); minutes %= (24 * 60)
    h = minutes // 60; mi = minutes % 60
    parts = []
    if mo: parts.append(f"{mo}mo")
    if w: parts.append(f"{w}w")
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if mi: parts.append(f"{mi}mi")
    return " ".join(parts) if parts else "0mi"

def has_permission(interaction: discord.Interaction) -> bool:
    guild_id = str(interaction.guild.id)
    mod_role_ids = get_setting(guild_id, "moderator_role_ids")
    if mod_role_ids:
        allowed_ids = [rid.strip() for rid in mod_role_ids.split(",") if rid.strip()]
        user_roles = [str(role.id) for role in interaction.user.roles]
        if any(rid in user_roles for rid in allowed_ids):
            return True
    user_roles = [role.name for role in interaction.user.roles]
    return any(role in ALLOWED_ROLES for role in user_roles)

def has_permission_simple(member, guild_id):
    mod_role_ids = get_setting(guild_id, "moderator_role_ids")
    if mod_role_ids:
        allowed_ids = [rid.strip() for rid in mod_role_ids.split(",") if rid.strip()]
        user_roles = [str(role.id) for role in member.roles]
        if any(rid in user_roles for rid in allowed_ids):
            return True
    user_roles = [role.name for role in member.roles]
    return any(role in ALLOWED_ROLES for role in user_roles)

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
    async def setup_hook(self):
        await self.tree.sync()
        print('✅ Команды синхронизированы!')

bot = MyBot()

async def check_mutes():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            now = datetime.now().isoformat()
            expired = db_execute("SELECT guild_id, user_id FROM mutes WHERE until <= ?", (now,), fetch=True)
            for guild_id, user_id in expired:
                try:
                    guild = bot.get_guild(int(guild_id))
                    if guild:
                        member = guild.get_member(int(user_id))
                        if member: await member.timeout(None)
                except: pass
                db_execute("DELETE FROM mutes WHERE guild_id = ? AND user_id = ? AND until <= ?", (guild_id, user_id, now))
        except: pass
        await asyncio.sleep(30)

async def check_voice_mutes():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            now = datetime.now().isoformat()
            expired = db_execute("SELECT guild_id, user_id FROM voice_mutes WHERE until <= ?", (now,), fetch=True)
            for guild_id, user_id in expired:
                try:
                    guild = bot.get_guild(int(guild_id))
                    if guild:
                        member = guild.get_member(int(user_id))
                        if member: await member.edit(mute=False)
                except: pass
                db_execute("DELETE FROM voice_mutes WHERE guild_id = ? AND user_id = ? AND until <= ?", (guild_id, user_id, now))
        except: pass
        await asyncio.sleep(30)

@bot.event
async def on_ready():
    print(f'🚀 Бот {bot.user} готов к работе! 24/7')
    bot.loop.create_task(check_mutes())
    bot.loop.create_task(check_voice_mutes())

@bot.event
async def on_member_join(member):
    guild_id = str(member.guild.id)
    auto_role_id = get_setting(guild_id, "auto_role_id")
    if auto_role_id:
        role = member.guild.get_role(int(auto_role_id))
        if role:
            try: await member.add_roles(role)
            except: pass
    if get_setting(guild_id, "welcome_enabled"):
        ch_id = get_setting(guild_id, "welcome_channel_id")
        text = get_setting(guild_id, "welcome_text") or "👋 Добро пожаловать, {user}!"
        if ch_id:
            channel = member.guild.get_channel(int(ch_id))
            if channel:
                msg = text.replace("{user}", member.mention).replace("{server}", member.guild.name)
                embed = discord.Embed(title="👋 Новый участник!", description=msg, color=0x57F287)
                embed.add_field(name="Всего участников", value=str(member.guild.member_count))
                embed.set_thumbnail(url=member.display_avatar.url)
                await channel.send(embed=embed)
    if get_setting(guild_id, "logging_enabled"):
        log_id = get_setting(guild_id, "log_channel_id")
        if log_id:
            log_ch = member.guild.get_channel(int(log_id))
            if log_ch:
                await log_ch.send(embed=discord.Embed(title="📥 Присоединился", color=0x57F287)
                                 .add_field(name="Пользователь", value=f"{member.mention} ({member.name})")
                                 .set_footer(text=f"ID: {member.id}"))

@bot.event
async def on_member_remove(member):
    guild_id = str(member.guild.id)
    if get_setting(guild_id, "leave_enabled"):
        ch_id = get_setting(guild_id, "leave_channel_id")
        text = get_setting(guild_id, "leave_text") or "😢 {user} покинул нас..."
        if ch_id:
            channel = member.guild.get_channel(int(ch_id))
            if channel:
                msg = text.replace("{user}", member.mention).replace("{server}", member.guild.name)
                await channel.send(embed=discord.Embed(title="😢 Ушёл", description=msg, color=0xED4245))
    if get_setting(guild_id, "logging_enabled"):
        log_id = get_setting(guild_id, "log_channel_id")
        if log_id:
            log_ch = member.guild.get_channel(int(log_id))
            if log_ch:
                await log_ch.send(embed=discord.Embed(title="📤 Вышел", color=0xED4245)
                                 .add_field(name="Пользователь", value=f"{member.mention} ({member.name})")
                                 .set_footer(text=f"ID: {member.id}"))

@bot.event
async def on_message(message):
    if message.author.bot: return
    guild_id = str(message.guild.id)
    if get_setting(guild_id, "automod_enabled"):
        if get_setting(guild_id, "automod_anti_caps"):
            if len(message.content) > 10:
                caps_percent = get_setting(guild_id, "automod_caps_percent") or 70
                caps_count = sum(1 for c in message.content if c.isupper())
                if caps_count / len(message.content) > caps_percent / 100:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention} Слишком много заглавных!", delete_after=5)
                    return
        if get_setting(guild_id, "automod_anti_links"):
            if any(x in message.content for x in ["http://", "https://", "discord.gg/"]):
                if not has_permission_simple(message.author, guild_id):
                    await message.delete()
                    await message.channel.send(f"{message.author.mention} Ссылки запрещены!", delete_after=5)
                    return
        bad_words = get_setting(guild_id, "automod_bad_words")
        if bad_words:
            for word in bad_words.lower().split(","):
                if word.strip() in message.content.lower():
                    await message.delete()
                    await message.channel.send(f"{message.author.mention} Это слово запрещено!", delete_after=5)
                    return
    if get_setting(guild_id, "leveling_enabled"):
        user_id = str(message.author.id)
        xp = random.randint(5, 15)
        result = db_execute_one("SELECT xp, level FROM user_levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        if result:
            current_xp, current_level = result
            new_xp = current_xp + xp
            if new_xp >= current_level * 100:
                new_level = current_level + 1
                db_execute("UPDATE user_levels SET xp = ?, level = ? WHERE guild_id = ? AND user_id = ?", 
                          (new_xp - current_level * 100, new_level, guild_id, user_id))
                await message.channel.send(f"🎉 {message.author.mention} достиг уровня **{new_level}**!")
            else:
                db_execute("UPDATE user_levels SET xp = ? WHERE guild_id = ? AND user_id = ?", (new_xp, guild_id, user_id))
        else:
            db_execute("INSERT INTO user_levels (guild_id, user_id, xp, level) VALUES (?, ?, ?, ?)", (guild_id, user_id, xp, 1))

@bot.event
async def on_voice_state_update(member, before, after):
    guild_id = str(member.guild.id)
    if not get_setting(guild_id, "temp_channels_enabled"): return
    if after.channel:
        creator_name = get_setting(guild_id, "temp_creator_channel_name") or "⚙️Создать канал [+]⚙️"
        if "создать" in after.channel.name.lower() or after.channel.name.lower() == creator_name.lower():
            category_id = get_setting(guild_id, "temp_channel_category_id")
            temp_name = get_setting(guild_id, "temp_channel_name") or "🔊 Временный"
            category = member.guild.get_channel(int(category_id)) if category_id else None
            channel = await member.guild.create_voice_channel(
                name=f"{temp_name} {member.display_name}", category=category)
            await member.move_to(channel)
            db_execute("INSERT INTO temp_channels VALUES (?, ?, ?)", (guild_id, str(channel.id), str(member.id)))
    if before.channel:
        ch_id = str(before.channel.id)
        temp = db_execute_one("SELECT owner_id FROM temp_channels WHERE channel_id = ?", (ch_id,))
        if temp and len(before.channel.members) == 0:
            try:
                await before.channel.delete()
                db_execute("DELETE FROM temp_channels WHERE channel_id = ?", (ch_id,))
            except: pass

# Варны
@bot.tree.command(name="warn", description="Выдать предупреждение")
@app_commands.describe(user="Кому", reason="Причина")
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str = "Не указана"):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return
    guild_id, user_id = str(interaction.guild.id), str(user.id)
    db_execute("INSERT INTO warnings VALUES (NULL, ?, ?, ?, ?, ?)",
              (guild_id, user_id, reason, interaction.user.name, datetime.now().strftime("%d.%m.%Y %H:%M:%S")))
    count = db_execute_one("SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))[0]
    embed = discord.Embed(title="⚠️ Предупреждение", color=0xFFA500)
    embed.add_field(name="Кому", value=user.mention)
    embed.add_field(name="Причина", value=reason)
    embed.add_field(name="Всего", value=str(count))
    await interaction.response.send_message(embed=embed)

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
    warns = db_execute("SELECT reason, moderator, date FROM warnings WHERE guild_id = ? AND user_id = ?",
                       (str(interaction.guild.id), str(user.id)), fetch=True)
    if warns:
        embed = discord.Embed(title=f"⚠️ Варны: {user.display_name}", color=0xFFA500)
        for i, (r, m, d) in enumerate(warns, 1):
            embed.add_field(name=f"#{i} | {d}", value=f"{r}\nМодер: {m}", inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(f"✅ Нет варнов.", ephemeral=True)

# Таймаут
@bot.tree.command(name="timeout", description="Таймаут")
async def timeout(interaction: discord.Interaction, user: discord.Member, time: str, reason: str = "Не указана"):
    if not has_permission(interaction): return
    minutes = parse_time(time)
    if minutes <= 0 or minutes > 40320:
        await interaction.response.send_message("❌ Неверное время.", ephemeral=True)
        return
    await user.timeout(timedelta(minutes=minutes), reason=reason)
    await interaction.response.send_message(f"🔇 {user.mention} таймаут на {format_time(minutes)}")

@bot.tree.command(name="untimeout", description="Снять таймаут")
async def untimeout(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction): return
    await user.timeout(None)
    await interaction.response.send_message(f"🔊 Таймаут снят с {user.mention}")

# Войс мьют
@bot.tree.command(name="vmute", description="Голосовой мьют")
async def vmute(interaction: discord.Interaction, user: discord.Member, time: str, reason: str = "Не указана"):
    if not has_permission(interaction): return
    minutes = parse_time(time)
    if minutes <= 0 or minutes > 40320: return
    await user.edit(mute=True, reason=reason)
    await interaction.response.send_message(f"🎤 {user.mention} мьют на {format_time(minutes)}")

@bot.tree.command(name="vunmute", description="Снять мьют войса")
async def vunmute(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction): return
    await user.edit(mute=False)
    await interaction.response.send_message(f"🎤 Мьют снят с {user.mention}")

# Уровни
@bot.tree.command(name="rank", description="Уровень")
async def rank(interaction: discord.Interaction, user: discord.Member = None):
    if not user: user = interaction.user
    r = db_execute_one("SELECT xp, level FROM user_levels WHERE guild_id = ? AND user_id = ?", 
                       (str(interaction.guild.id), str(user.id)))
    if r:
        xp, lv = r
        await interaction.response.send_message(f"🎖️ {user.display_name}\nУровень: **{lv}**\nОпыт: **{xp}/{lv*100}**")
    else:
        await interaction.response.send_message("Нет уровней.")

@bot.tree.command(name="top", description="Топ")
async def top(interaction: discord.Interaction):
    data = db_execute("SELECT user_id, level, xp FROM user_levels WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 10",
                     (str(interaction.guild.id),), fetch=True)
    if data:
        embed = discord.Embed(title="🏆 Топ", color=0xFFD700)
        for i, (uid, lv, xp) in enumerate(data, 1):
            u = interaction.guild.get_member(int(uid))
            embed.add_field(name=f"#{i} {u.display_name if u else uid}", value=f"Ур: {lv} | XP: {xp}", inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Нет данных.")

@bot.tree.command(name="add_xp", description="Добавить опыт")
async def add_xp(interaction: discord.Interaction, user: discord.Member, amount: int):
    if not has_permission(interaction): return
    gid, uid = str(interaction.guild.id), str(user.id)
    r = db_execute_one("SELECT xp FROM user_levels WHERE guild_id = ? AND user_id = ?", (gid, uid))
    if r: db_execute("UPDATE user_levels SET xp = xp + ? WHERE guild_id = ? AND user_id = ?", (amount, gid, uid))
    else: db_execute("INSERT INTO user_levels VALUES (?, ?, ?, 1)", (gid, uid, amount))
    await interaction.response.send_message(f"✅ +{amount} XP → {user.mention}")

@bot.tree.command(name="remove_xp", description="Убрать опыт")
async def remove_xp(interaction: discord.Interaction, user: discord.Member, amount: int):
    if not has_permission(interaction): return
    gid, uid = str(interaction.guild.id), str(user.id)
    db_execute("UPDATE user_levels SET xp = MAX(0, xp - ?) WHERE guild_id = ? AND user_id = ?", (amount, gid, uid))
    await interaction.response.send_message(f"✅ -{amount} XP у {user.mention}")

@bot.tree.command(name="set_level", description="Установить уровень")
async def set_level(interaction: discord.Interaction, user: discord.Member, level: int):
    if not has_permission(interaction): return
    gid, uid = str(interaction.guild.id), str(user.id)
    db_execute("INSERT OR REPLACE INTO user_levels VALUES (?, ?, 0, ?)", (gid, uid, level))
    await interaction.response.send_message(f"✅ {user.mention} → уровень **{level}**")

bot.run(BOT_TOKEN)
