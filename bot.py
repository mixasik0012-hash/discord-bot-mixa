import discord
from discord import app_commands
import sqlite3
import os
from datetime import datetime, timedelta
import asyncio
import re
import random

# =============================================
# НАСТРОЙКИ
# =============================================
ALLOWED_ROLES = ["⚔️Админ состав⚔️"]
BOT_TOKEN = os.getenv("BOT_TOKEN", "ТОКЕН_СЮДА_ЗАМЕНИТЕ")

DB_FILE = "/data/bot_data.db" if os.path.exists("/data") else "bot_data.db"

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
        automod_anti_links INTEGER DEFAULT 0,
        automod_bad_words TEXT DEFAULT ''
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
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_levels (
        guild_id TEXT,
        user_id TEXT,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        PRIMARY KEY (guild_id, user_id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS temp_channels (
        guild_id TEXT,
        channel_id TEXT PRIMARY KEY,
        owner_id TEXT
    )''')
    
    conn.commit()
    conn.close()

init_db()

# =============================================
# ФУНКЦИИ БД
# =============================================
def db_execute(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    if fetch:
        result = c.fetchall()
    else:
        result = None
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
    user_roles = [role.name for role in interaction.user.roles]
    return any(role in ALLOWED_ROLES for role in user_roles)

# =============================================
# БОТ
# =============================================
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

# =============================================
# ПРИВЕТСТВИЯ / ПРОЩАНИЯ / ЛОГИ / АВТО-РОЛЬ
# =============================================
@bot.event
async def on_member_join(member):
    guild_id = str(member.guild.id)
    
    # Авто-роль
    auto_role_id = get_setting(guild_id, "auto_role_id")
    if auto_role_id:
        role = member.guild.get_role(int(auto_role_id))
        if role:
            try: await member.add_roles(role)
            except: pass
    
    # Приветствие
    if get_setting(guild_id, "welcome_enabled"):
        welcome_channel_id = get_setting(guild_id, "welcome_channel_id")
        welcome_text = get_setting(guild_id, "welcome_text") or "👋 Добро пожаловать, {user}!"
        if welcome_channel_id:
            channel = member.guild.get_channel(int(welcome_channel_id))
            if channel:
                text = welcome_text.replace("{user}", member.mention).replace("{server}", member.guild.name)
                embed = discord.Embed(title="👋 Новый участник!", description=text, color=0x57F287)
                embed.add_field(name="Всего участников", value=str(member.guild.member_count))
                embed.set_thumbnail(url=member.display_avatar.url)
                await channel.send(embed=embed)
    
    # Лог
    if get_setting(guild_id, "logging_enabled"):
        log_channel_id = get_setting(guild_id, "log_channel_id")
        if log_channel_id:
            log_channel = member.guild.get_channel(int(log_channel_id))
            if log_channel:
                embed = discord.Embed(title="📥 Участник присоединился", color=0x57F287)
                embed.add_field(name="Пользователь", value=f"{member.mention} ({member.name})")
                embed.set_footer(text=f"ID: {member.id}")
                await log_channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    guild_id = str(member.guild.id)
    
    # Прощание
    if get_setting(guild_id, "leave_enabled"):
        leave_channel_id = get_setting(guild_id, "leave_channel_id")
        leave_text = get_setting(guild_id, "leave_text") or "😢 {user} покинул нас..."
        if leave_channel_id:
            channel = member.guild.get_channel(int(leave_channel_id))
            if channel:
                text = leave_text.replace("{user}", member.mention).replace("{server}", member.guild.name)
                await channel.send(embed=discord.Embed(title="😢 Участник ушёл", description=text, color=0xED4245))
    
    # Лог
    if get_setting(guild_id, "logging_enabled"):
        log_channel_id = get_setting(guild_id, "log_channel_id")
        if log_channel_id:
            log_channel = member.guild.get_channel(int(log_channel_id))
            if log_channel:
                embed = discord.Embed(title="📤 Участник вышел", color=0xED4245)
                embed.add_field(name="Пользователь", value=f"{member.mention} ({member.name})")
                embed.set_footer(text=f"ID: {member.id}")
                await log_channel.send(embed=embed)

# =============================================
# АВТО-МОДЕРАЦИЯ
# =============================================
@bot.event
async def on_message(message):
    if message.author.bot: return
    
    guild_id = str(message.guild.id)
    automod_enabled = get_setting(guild_id, "automod_enabled")
    
    if automod_enabled:
        # Анти-спам (больше 5 сообщений за 5 секунд)
        # Упрощённая версия — проверка капса и ссылок
        
        # Анти-капс (больше 70% заглавных)
        if get_setting(guild_id, "automod_anti_caps"):
            if len(message.content) > 10:
                caps_count = sum(1 for c in message.content if c.isupper())
                if caps_count / len(message.content) > 0.7:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention} Не злоупотребляй капсом!", delete_after=5)
                    return
        
        # Анти-ссылки
        if get_setting(guild_id, "automod_anti_links"):
            if "http://" in message.content or "https://" in message.content or "discord.gg/" in message.content:
                if not has_permission_simple(message.author, guild_id):
                    await message.delete()
                    await message.channel.send(f"{message.author.mention} Ссылки запрещены!", delete_after=5)
                    return
        
        # Плохие слова
        bad_words = get_setting(guild_id, "automod_bad_words")
        if bad_words:
            words_list = bad_words.lower().split(",")
            for word in words_list:
                if word.strip() in message.content.lower():
                    await message.delete()
                    await message.channel.send(f"{message.author.mention} Это слово запрещено!", delete_after=5)
                    return
    
    # Уровни
    if get_setting(guild_id, "leveling_enabled"):
        user_id = str(message.author.id)
        xp = random.randint(5, 15)
        result = db_execute_one("SELECT xp, level FROM user_levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        
        if result:
            current_xp, current_level = result
            new_xp = current_xp + xp
            xp_needed = current_level * 100
            if new_xp >= xp_needed:
                new_level = current_level + 1
                db_execute("UPDATE user_levels SET xp = ?, level = ? WHERE guild_id = ? AND user_id = ?", 
                          (new_xp - xp_needed, new_level, guild_id, user_id))
                await message.channel.send(f"🎉 {message.author.mention} достиг уровня **{new_level}**!")
            else:
                db_execute("UPDATE user_levels SET xp = ? WHERE guild_id = ? AND user_id = ?", (new_xp, guild_id, user_id))
        else:
            db_execute("INSERT INTO user_levels (guild_id, user_id, xp, level) VALUES (?, ?, ?, ?)", (guild_id, user_id, xp, 1))

def has_permission_simple(member, guild_id):
    user_roles = [role.name for role in member.roles]
    return any(role in ALLOWED_ROLES for role in user_roles)

# =============================================
# ВРЕМЕННЫЕ ГОЛОСОВЫЕ КАНАЛЫ
# =============================================
@bot.event
async def on_voice_state_update(member, before, after):
    guild_id = str(member.guild.id)
    
    if not get_setting(guild_id, "temp_channels_enabled"):
        return
    
    # Если зашёл в специальный канал — создать временный
    if after.channel:
        category_id = get_setting(guild_id, "temp_channel_category_id")
        temp_name = get_setting(guild_id, "temp_channel_name") or "🔊 Временный"
        
        # Создаём канал если зашли в "создатель"
        if after.channel.name.lower() == "➕ создать канал":
            category = member.guild.get_channel(int(category_id)) if category_id else None
            if category:
                channel = await member.guild.create_voice_channel(
                    name=f"{temp_name} {member.display_name}",
                    category=category
                )
                await member.move_to(channel)
                db_execute("INSERT INTO temp_channels (guild_id, channel_id, owner_id) VALUES (?, ?, ?)",
                          (guild_id, str(channel.id), str(member.id)))
    
    # Удалить пустой временный канал
    if before.channel:
        channel_id = str(before.channel.id)
        temp_channel = db_execute_one("SELECT owner_id FROM temp_channels WHERE channel_id = ?", (channel_id,))
        if temp_channel and len(before.channel.members) == 0:
            try:
                await before.channel.delete()
                db_execute("DELETE FROM temp_channels WHERE channel_id = ?", (channel_id,))
            except: pass

# =============================================
# ВАРНЫ
# =============================================
@bot.tree.command(name="warn", description="Выдать предупреждение")
@app_commands.describe(user="Кому", reason="Причина")
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str = "Не указана"):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return
    
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    date = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    db_execute("INSERT INTO warnings (guild_id, user_id, reason, moderator, date) VALUES (?, ?, ?, ?, ?)",
              (guild_id, user_id, reason, interaction.user.name, date))
    
    count = db_execute_one("SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))[0]
    
    embed = discord.Embed(title="⚠️ Предупреждение выдано", color=0xFFA500)
    embed.add_field(name="Пользователь", value=user.mention)
    embed.add_field(name="Причина", value=reason)
    embed.add_field(name="Всего варнов", value=str(count))
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="warn_remove", description="Снять варн")
async def warn_remove(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction): return
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    db_execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ? AND id = (SELECT id FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1)",
              (guild_id, user_id, guild_id, user_id))
    await interaction.response.send_message(f"✅ Последний варн снят с {user.mention}")

@bot.tree.command(name="warnings", description="Список варнов")
async def warnings_list(interaction: discord.Interaction, user: discord.Member = None):
    if not user: user = interaction.user
    guild_id = str(interaction.guild.id)
    warns = db_execute("SELECT reason, moderator, date FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC", 
                       (guild_id, str(user.id)), fetch=True)
    if warns:
        embed = discord.Embed(title=f"⚠️ Варны: {user.display_name}", color=0xFFA500)
        for i, (reason, moderator, date) in enumerate(warns, 1):
            embed.add_field(name=f"#{i} | {date}", value=f"Причина: {reason}\nМодератор: {moderator}", inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(f"✅ У {user.mention} нет варнов.", ephemeral=True)

# =============================================
# ТАЙМАУТ
# =============================================
@bot.tree.command(name="timeout", description="Таймаут")
async def timeout(interaction: discord.Interaction, user: discord.Member, time: str, reason: str = "Не указана"):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return
    minutes = parse_time(time)
    if minutes <= 0 or minutes > 40320:
        await interaction.response.send_message("❌ Неверное время.", ephemeral=True)
        return
    await user.timeout(timedelta(minutes=minutes), reason=reason)
    
    guild_id = str(interaction.guild.id)
    until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    db_execute("INSERT INTO mutes (guild_id, user_id, until, reason, moderator, date) VALUES (?, ?, ?, ?, ?, ?)",
              (guild_id, str(user.id), until, reason, interaction.user.name, datetime.now().strftime("%d.%m.%Y %H:%M:%S")))
    
    await interaction.response.send_message(f"🔇 {user.mention} таймаут на {format_time(minutes)}")

@bot.tree.command(name="untimeout", description="Снять таймаут")
async def untimeout(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction): return
    await user.timeout(None)
    await interaction.response.send_message(f"🔊 Таймаут снят с {user.mention}")

# =============================================
# ГОЛОСОВОЙ МЬЮТ
# =============================================
@bot.tree.command(name="vmute", description="Голосовой мьют")
async def vmute(interaction: discord.Interaction, user: discord.Member, time: str, reason: str = "Не указана"):
    if not has_permission(interaction): return
    minutes = parse_time(time)
    if minutes <= 0 or minutes > 40320:
        await interaction.response.send_message("❌ Неверное время.", ephemeral=True)
        return
    await user.edit(mute=True, reason=reason)
    
    guild_id = str(interaction.guild.id)
    until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    db_execute("INSERT INTO voice_mutes (guild_id, user_id, until, reason, moderator, date) VALUES (?, ?, ?, ?, ?, ?)",
              (guild_id, str(user.id), until, reason, interaction.user.name, datetime.now().strftime("%d.%m.%Y %H:%M:%S")))
    
    await interaction.response.send_message(f"🎤 {user.mention} мьют войса на {format_time(minutes)}")

@bot.tree.command(name="vunmute", description="Снять мьют войса")
async def vunmute(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction): return
    await user.edit(mute=False)
    await interaction.response.send_message(f"🎤 Мьют снят с {user.mention}")

# =============================================
# УРОВНИ (ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ)
# =============================================
@bot.tree.command(name="rank", description="Уровень")
async def rank(interaction: discord.Interaction, user: discord.Member = None):
    if not user: user = interaction.user
    guild_id = str(interaction.guild.id)
    result = db_execute_one("SELECT xp, level FROM user_levels WHERE guild_id = ? AND user_id = ?", (guild_id, str(user.id)))
    if result:
        xp, level = result
        await interaction.response.send_message(f"🎖️ **{user.display_name}**\nУровень: **{level}**\nОпыт: **{xp}/{level * 100}**")
    else:
        await interaction.response.send_message(f"{user.display_name} ещё не имеет уровней.")

@bot.tree.command(name="top", description="Топ по уровням")
async def top(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    top_users = db_execute("SELECT user_id, level, xp FROM user_levels WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 10", (guild_id,), fetch=True)
    if top_users:
        embed = discord.Embed(title="🏆 Топ участников", color=0xFFD700)
        for i, (user_id, level, xp) in enumerate(top_users, 1):
            user = interaction.guild.get_member(int(user_id))
            name = user.display_name if user else f"ID: {user_id}"
            embed.add_field(name=f"#{i} {name}", value=f"Уровень: {level} | Опыт: {xp}", inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Нет данных.")

@bot.tree.command(name="add_xp", description="Добавить опыт")
@app_commands.describe(user="Кому", amount="Сколько опыта")
async def add_xp(interaction: discord.Interaction, user: discord.Member, amount: int):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    result = db_execute_one("SELECT xp FROM user_levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    if result:
        db_execute("UPDATE user_levels SET xp = xp + ? WHERE guild_id = ? AND user_id = ?", (amount, guild_id, user_id))
    else:
        db_execute("INSERT INTO user_levels (guild_id, user_id, xp, level) VALUES (?, ?, ?, 1)", (guild_id, user_id, amount))
    await interaction.response.send_message(f"✅ Добавлено {amount} XP для {user.mention}")

@bot.tree.command(name="remove_xp", description="Убрать опыт")
async def remove_xp(interaction: discord.Interaction, user: discord.Member, amount: int):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    db_execute("UPDATE user_levels SET xp = MAX(0, xp - ?) WHERE guild_id = ? AND user_id = ?", (amount, guild_id, user_id))
    await interaction.response.send_message(f"✅ Убрано {amount} XP у {user.mention}")

@bot.tree.command(name="set_level", description="Установить уровень")
async def set_level(interaction: discord.Interaction, user: discord.Member, level: int):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    db_execute("INSERT OR REPLACE INTO user_levels (guild_id, user_id, xp, level) VALUES (?, ?, 0, ?)", (guild_id, user_id, level))
    await interaction.response.send_message(f"✅ Уровень {user.mention} установлен на **{level}**")

bot.run(BOT_TOKEN)
