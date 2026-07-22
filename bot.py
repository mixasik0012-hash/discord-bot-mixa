import discord
from discord import app_commands
import json
import os
from datetime import datetime, timedelta
import asyncio
import re

# =============================================
# НАСТРОЙКИ
# =============================================
ALLOWED_ROLES = ["⚔️Админ состав⚔️"]

# =============================================
# ИНТЕНТЫ И ФАЙЛЫ
# =============================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

WARNINGS_FILE = "warnings.json"
MUTES_FILE = "mutes.json"
VOICE_MUTES_FILE = "voice_mutes.json"

def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def parse_time(time_str: str) -> int:
    time_str = time_str.lower().strip()
    total_minutes = 0
    patterns = {
        'mo': r'(\d+)\s*mo',
        'w': r'(\d+)\s*w',
        'd': r'(\d+)\s*d',
        'h': r'(\d+)\s*h',
        'mi': r'(\d+)\s*mi'
    }
    for match in re.finditer(patterns['mo'], time_str):
        total_minutes += int(match.group(1)) * 30 * 24 * 60
    for match in re.finditer(patterns['w'], time_str):
        total_minutes += int(match.group(1)) * 7 * 24 * 60
    for match in re.finditer(patterns['d'], time_str):
        total_minutes += int(match.group(1)) * 24 * 60
    for match in re.finditer(patterns['h'], time_str):
        total_minutes += int(match.group(1)) * 60
    for match in re.finditer(patterns['mi'], time_str):
        total_minutes += int(match.group(1))
    return total_minutes

def format_time(minutes: int) -> str:
    mo = minutes // (30 * 24 * 60)
    minutes %= (30 * 24 * 60)
    w = minutes // (7 * 24 * 60)
    minutes %= (7 * 24 * 60)
    d = minutes // (24 * 60)
    minutes %= (24 * 60)
    h = minutes // 60
    mi = minutes % 60
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

# Свой декоратор проверки прав — без зависаний
def check_perms():
    def decorator(func):
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if has_permission(interaction):
                return await func(interaction, *args, **kwargs)
            await interaction.response.send_message(
                f"❌ Нет прав. Нужны роли: {', '.join(ALLOWED_ROLES)}",
                ephemeral=True
            )
        return wrapper
    return decorator

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print(f'✅ Команды синхронизированы!')

bot = MyBot()
warnings = load_json(WARNINGS_FILE)
mutes = load_json(MUTES_FILE)
voice_mutes = load_json(VOICE_MUTES_FILE)

async def check_timeouts():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            now = datetime.now().isoformat()
            to_remove = []
            for guild_id in list(mutes.keys()):
                for user_id, mute_data in list(mutes[guild_id].items()):
                    if mute_data["until"] <= now:
                        try:
                            guild = bot.get_guild(int(guild_id))
                            if guild:
                                member = guild.get_member(int(user_id))
                                if member:
                                    await member.timeout(None)
                        except:
                            pass
                        to_remove.append((guild_id, user_id))
            for guild_id, user_id in to_remove:
                if guild_id in mutes and user_id in mutes[guild_id]:
                    del mutes[guild_id][user_id]
                if guild_id in mutes and len(mutes[guild_id]) == 0:
                    del mutes[guild_id]
            if to_remove:
                save_json(MUTES_FILE, mutes)
        except:
            pass
        await asyncio.sleep(30)

async def check_voice_mutes():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            now = datetime.now().isoformat()
            to_remove = []
            for guild_id in list(voice_mutes.keys()):
                for user_id, vmute_data in list(voice_mutes[guild_id].items()):
                    if vmute_data["until"] <= now:
                        try:
                            guild = bot.get_guild(int(guild_id))
                            if guild:
                                member = guild.get_member(int(user_id))
                                if member:
                                    await member.edit(mute=False)
                        except:
                            pass
                        to_remove.append((guild_id, user_id))
            for guild_id, user_id in to_remove:
                if guild_id in voice_mutes and user_id in voice_mutes[guild_id]:
                    del voice_mutes[guild_id][user_id]
                if guild_id in voice_mutes and len(voice_mutes[guild_id]) == 0:
                    del voice_mutes[guild_id]
            if to_remove:
                save_json(VOICE_MUTES_FILE, voice_mutes)
        except:
            pass
        await asyncio.sleep(30)

@bot.event
async def on_ready():
    print(f'🚀 Бот {bot.user} готов к работе!')
    print(f'👮 Разрешённые роли: {ALLOWED_ROLES}')
    bot.loop.create_task(check_timeouts())
    bot.loop.create_task(check_voice_mutes())

# =============================================
# ВАРНЫ
# =============================================

@bot.tree.command(name="warn", description="Выдать предупреждение")
@app_commands.describe(user="Кому", reason="Причина")
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str = "Не указана"):
    if not has_permission(interaction):
        await interaction.response.send_message(f"❌ Нет прав. Нужны роли: {', '.join(ALLOWED_ROLES)}", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id not in warnings:
        warnings[guild_id] = {}
    if user_id not in warnings[guild_id]:
        warnings[guild_id][user_id] = []

    warn_entry = {
        "reason": reason,
        "moderator": interaction.user.name,
        "date": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "id": len(warnings[guild_id][user_id]) + 1
    }
    warnings[guild_id][user_id].append(warn_entry)
    save_json(WARNINGS_FILE, warnings)

    embed = discord.Embed(title="⚠️ Предупреждение выдано", color=0xFFA500)
    embed.add_field(name="Пользователь", value=user.mention, inline=True)
    embed.add_field(name="Причина", value=reason, inline=False)
    embed.add_field(name="Всего варнов", value=str(len(warnings[guild_id][user_id])), inline=True)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="warn_remove", description="Снять предупреждение")
@app_commands.describe(user="С кого")
async def warn_remove(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction):
        await interaction.response.send_message(f"❌ Нет прав. Нужны роли: {', '.join(ALLOWED_ROLES)}", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id not in warnings or user_id not in warnings[guild_id] or len(warnings[guild_id][user_id]) == 0:
        await interaction.response.send_message(f"✅ У {user.mention} нет предупреждений.", ephemeral=True)
        return

    removed = warnings[guild_id][user_id].pop()
    save_json(WARNINGS_FILE, warnings)

    embed = discord.Embed(title="✅ Предупреждение снято", color=0x00FF00)
    embed.add_field(name="Пользователь", value=user.mention, inline=True)
    embed.add_field(name="Снятый варн", value=f"Причина: {removed['reason']}", inline=False)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="warnings", description="Посмотреть предупреждения")
@app_commands.describe(user="Чьи")
async def warnings_list(interaction: discord.Interaction, user: discord.Member = None):
    if user is None:
        user = interaction.user
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id not in warnings or user_id not in warnings[guild_id] or len(warnings[guild_id][user_id]) == 0:
        await interaction.response.send_message(f"✅ У {user.mention} нет предупреждений.", ephemeral=True)
        return

    warns = warnings[guild_id][user_id]
    embed = discord.Embed(title=f"⚠️ Предупреждения: {user.display_name}", color=0xFFA500)
    for w in warns:
        embed.add_field(name=f"Варн #{w['id']} | {w['date']}", value=f"Причина: {w['reason']}\nМодератор: {w['moderator']}", inline=False)
    embed.set_footer(text=f"Всего: {len(warns)}")
    await interaction.response.send_message(embed=embed)

# =============================================
# TIMEOUT
# =============================================

@bot.tree.command(name="timeout", description="Запретить писать в чат")
@app_commands.describe(user="Кому", time="Время (30mi, 2h, 1d, 1w, 1mo)", reason="Причина")
async def timeout(interaction: discord.Interaction, user: discord.Member, time: str, reason: str = "Не указана"):
    if not has_permission(interaction):
        await interaction.response.send_message(f"❌ Нет прав. Нужны роли: {', '.join(ALLOWED_ROLES)}", ephemeral=True)
        return

    minutes = parse_time(time)
    if minutes <= 0 or minutes > 40320:
        await interaction.response.send_message("❌ Неверное время. Примеры: 30mi, 2h, 1d, 1w, 1mo", ephemeral=True)
        return

    await user.timeout(timedelta(minutes=minutes), reason=reason)

    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id not in mutes:
        mutes[guild_id] = {}
    mutes[guild_id][user_id] = {
        "until": (datetime.now() + timedelta(minutes=minutes)).isoformat(),
        "reason": reason,
        "moderator": interaction.user.name,
        "date": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    }
    save_json(MUTES_FILE, mutes)

    embed = discord.Embed(title="🔇 Таймаут выдан", color=0xFF6600)
    embed.add_field(name="Пользователь", value=user.mention, inline=True)
    embed.add_field(name="Длительность", value=format_time(minutes), inline=True)
    embed.add_field(name="Причина", value=reason, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="untimeout", description="Снять таймаут")
@app_commands.describe(user="С кого")
async def untimeout(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction):
        await interaction.response.send_message(f"❌ Нет прав. Нужны роли: {', '.join(ALLOWED_ROLES)}", ephemeral=True)
        return

    await user.timeout(None)
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id in mutes and user_id in mutes[guild_id]:
        del mutes[guild_id][user_id]
        if len(mutes[guild_id]) == 0:
            del mutes[guild_id]
        save_json(MUTES_FILE, mutes)

    await interaction.response.send_message(f"🔊 Таймаут снят с {user.mention}")

@bot.tree.command(name="timeouts", description="Список таймаутов")
async def timeouts_list(interaction: discord.Interaction):
    if not has_permission(interaction):
        await interaction.response.send_message(f"❌ Нет прав. Нужны роли: {', '.join(ALLOWED_ROLES)}", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    if guild_id not in mutes or len(mutes[guild_id]) == 0:
        await interaction.response.send_message("✅ Нет таймаутов.", ephemeral=True)
        return

    embed = discord.Embed(title="🔇 Таймауты", color=0xFF6600)
    for user_id, data in mutes[guild_id].items():
        user = interaction.guild.get_member(int(user_id))
        name = user.mention if user else f"<@{user_id}>"
        until = datetime.fromisoformat(data["until"]).strftime("%d.%m.%Y %H:%M:%S")
        embed.add_field(name=name, value=f"До: {until}\nПричина: {data['reason']}", inline=False)
    await interaction.response.send_message(embed=embed)

# =============================================
# VOICE MUTE
# =============================================

@bot.tree.command(name="vmute", description="Запретить говорить в войсе")
@app_commands.describe(user="Кому", time="Время (30mi, 2h, 1d, 1w, 1mo)", reason="Причина")
async def vmute(interaction: discord.Interaction, user: discord.Member, time: str, reason: str = "Не указана"):
    if not has_permission(interaction):
        await interaction.response.send_message(f"❌ Нет прав. Нужны роли: {', '.join(ALLOWED_ROLES)}", ephemeral=True)
        return

    minutes = parse_time(time)
    if minutes <= 0 or minutes > 40320:
        await interaction.response.send_message("❌ Неверное время. Примеры: 30mi, 2h, 1d, 1w, 1mo", ephemeral=True)
        return

    await user.edit(mute=True, reason=reason)

    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id not in voice_mutes:
        voice_mutes[guild_id] = {}
    voice_mutes[guild_id][user_id] = {
        "until": (datetime.now() + timedelta(minutes=minutes)).isoformat(),
        "reason": reason,
        "moderator": interaction.user.name,
        "date": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    }
    save_json(VOICE_MUTES_FILE, voice_mutes)

    embed = discord.Embed(title="🎤 Голосовой мьют выдан", color=0x9933FF)
    embed.add_field(name="Пользователь", value=user.mention, inline=True)
    embed.add_field(name="Длительность", value=format_time(minutes), inline=True)
    embed.add_field(name="Причина", value=reason, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="vunmute", description="Снять голосовой мьют")
@app_commands.describe(user="С кого")
async def vunmute(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction):
        await interaction.response.send_message(f"❌ Нет прав. Нужны роли: {', '.join(ALLOWED_ROLES)}", ephemeral=True)
        return

    await user.edit(mute=False)
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id in voice_mutes and user_id in voice_mutes[guild_id]:
        del voice_mutes[guild_id][user_id]
        if len(voice_mutes[guild_id]) == 0:
            del voice_mutes[guild_id]
        save_json(VOICE_MUTES_FILE, voice_mutes)

    await interaction.response.send_message(f"🎤 Голосовой мьют снят с {user.mention}")

@bot.tree.command(name="vmutes", description="Список голосовых мьютов")
async def vmutes_list(interaction: discord.Interaction):
    if not has_permission(interaction):
        await interaction.response.send_message(f"❌ Нет прав. Нужны роли: {', '.join(ALLOWED_ROLES)}", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    if guild_id not in voice_mutes or len(voice_mutes[guild_id]) == 0:
        await interaction.response.send_message("✅ Нет голосовых мьютов.", ephemeral=True)
        return

    embed = discord.Embed(title="🎤 Голосовые мьюты", color=0x9933FF)
    for user_id, data in voice_mutes[guild_id].items():
        user = interaction.guild.get_member(int(user_id))
        name = user.mention if user else f"<@{user_id}>"
        until = datetime.fromisoformat(data["until"]).strftime("%d.%m.%Y %H:%M:%S")
        embed.add_field(name=name, value=f"До: {until}\nПричина: {data['reason']}", inline=False)
    await interaction.response.send_message(embed=embed)

# =============================================
# ЗАПУСК
# =============================================
bot.run('MTUyOTU0NTMxNjAwMzQ3OTg0Mw.G0XDKC._Xq_b2UAhOeEk7ywaPpyTegO4P5smm7IQkFn3Q')
