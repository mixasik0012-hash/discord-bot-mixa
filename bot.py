import discord
from discord import app_commands
import json
import os
from datetime import datetime, timedelta
import asyncio
import re

# Настройки
ALLOWED_ROLES = ["Модератор", "Админ", "Главный"]

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ Ошибка: BOT_TOKEN не найден!")
    exit(1)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

WARNINGS_FILE = "/data/warnings.json"
MUTES_FILE = "/data/mutes.json"
VOICE_MUTES_FILE = "/data/voice_mutes.json"
SETTINGS_FILE = "/data/server_settings.json"

def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(file, data):
    os.makedirs(os.path.dirname(file), exist_ok=True)
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

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

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
    async def setup_hook(self):
        await self.tree.sync()
        print('✅ Команды синхронизированы!')

bot = MyBot()
warnings = load_json(WARNINGS_FILE)
mutes = load_json(MUTES_FILE)
voice_mutes = load_json(VOICE_MUTES_FILE)
server_settings = load_json(SETTINGS_FILE)

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
                                if member: await member.timeout(None)
                        except: pass
                        to_remove.append((guild_id, user_id))
            for guild_id, user_id in to_remove:
                if guild_id in mutes and user_id in mutes[guild_id]: del mutes[guild_id][user_id]
                if guild_id in mutes and len(mutes[guild_id]) == 0: del mutes[guild_id]
            if to_remove: save_json(MUTES_FILE, mutes)
        except: pass
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
                                if member: await member.edit(mute=False)
                        except: pass
                        to_remove.append((guild_id, user_id))
            for guild_id, user_id in to_remove:
                if guild_id in voice_mutes and user_id in voice_mutes[guild_id]: del voice_mutes[guild_id][user_id]
                if guild_id in voice_mutes and len(voice_mutes[guild_id]) == 0: del voice_mutes[guild_id]
            if to_remove: save_json(VOICE_MUTES_FILE, voice_mutes)
        except: pass
        await asyncio.sleep(30)

@bot.event
async def on_ready():
    print(f'🚀 Бот {bot.user} готов к работе! 24/7')
    bot.loop.create_task(check_timeouts())
    bot.loop.create_task(check_voice_mutes())

@bot.event
async def on_member_join(member):
    guild_id = str(member.guild.id)
    if guild_id in server_settings:
        auto_role_id = server_settings[guild_id].get("auto_role")
        if auto_role_id:
            role = member.guild.get_role(int(auto_role_id))
            if role:
                try:
                    await member.add_roles(role)
                except: pass

# ВАРНЫ
@bot.tree.command(name="warn", description="Выдать предупреждение")
@app_commands.describe(user="Кому", reason="Причина")
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str = "Не указана"):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id not in warnings: warnings[guild_id] = {}
    if user_id not in warnings[guild_id]: warnings[guild_id][user_id] = []
    warn_entry = {"reason": reason, "moderator": interaction.user.name, "date": datetime.now().strftime("%d.%m.%Y %H:%M:%S"), "id": len(warnings[guild_id][user_id]) + 1}
    warnings[guild_id][user_id].append(warn_entry)
    save_json(WARNINGS_FILE, warnings)
    embed = discord.Embed(title="⚠️ Предупреждение выдано", color=0xFFA500)
    embed.add_field(name="Пользователь", value=user.mention)
    embed.add_field(name="Причина", value=reason)
    embed.add_field(name="Всего варнов", value=str(len(warnings[guild_id][user_id])))
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="warn_remove", description="Снять предупреждение")
@app_commands.describe(user="С кого")
async def warn_remove(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id in warnings and user_id in warnings[guild_id] and len(warnings[guild_id][user_id]) > 0:
        warnings[guild_id][user_id].pop()
        save_json(WARNINGS_FILE, warnings)
        await interaction.response.send_message(f"✅ Варн снят с {user.mention}")
    else:
        await interaction.response.send_message(f"✅ Нет варнов.", ephemeral=True)

@bot.tree.command(name="warnings", description="Посмотреть предупреждения")
@app_commands.describe(user="Чьи")
async def warnings_list(interaction: discord.Interaction, user: discord.Member = None):
    if user is None: user = interaction.user
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id in warnings and user_id in warnings[guild_id]:
        warns = warnings[guild_id][user_id]
        embed = discord.Embed(title=f"⚠️ Варны: {user.display_name}", color=0xFFA500)
        for w in warns:
            embed.add_field(name=f"#{w['id']} | {w['date']}", value=f"Причина: {w['reason']}", inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(f"✅ У {user.mention} нет варнов.", ephemeral=True)

# ТАЙМАУТ
@bot.tree.command(name="timeout", description="Запретить писать в чат")
@app_commands.describe(user="Кому", time="Время (30mi, 2h, 1d, 1w, 1mo)", reason="Причина")
async def timeout(interaction: discord.Interaction, user: discord.Member, time: str, reason: str = "Не указана"):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return
    minutes = parse_time(time)
    if minutes <= 0 or minutes > 40320:
        await interaction.response.send_message("❌ Неверное время.", ephemeral=True)
        return
    await user.timeout(timedelta(minutes=minutes), reason=reason)
    embed = discord.Embed(title="🔇 Таймаут выдан", color=0xFF6600)
    embed.add_field(name="Пользователь", value=user.mention)
    embed.add_field(name="Длительность", value=format_time(minutes))
    embed.add_field(name="Причина", value=reason)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="untimeout", description="Снять таймаут")
@app_commands.describe(user="С кого")
async def untimeout(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return
    await user.timeout(None)
    await interaction.response.send_message(f"🔊 Таймаут снят с {user.mention}")

# ГОЛОСОВОЙ МЬЮТ
@bot.tree.command(name="vmute", description="Запретить говорить в войсе")
@app_commands.describe(user="Кому", time="Время (30mi, 2h, 1d, 1w, 1mo)", reason="Причина")
async def vmute(interaction: discord.Interaction, user: discord.Member, time: str, reason: str = "Не указана"):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return
    minutes = parse_time(time)
    if minutes <= 0 or minutes > 40320:
        await interaction.response.send_message("❌ Неверное время.", ephemeral=True)
        return
    await user.edit(mute=True, reason=reason)
    embed = discord.Embed(title="🎤 Голосовой мьют выдан", color=0x9933FF)
    embed.add_field(name="Пользователь", value=user.mention)
    embed.add_field(name="Длительность", value=format_time(minutes))
    embed.add_field(name="Причина", value=reason)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="vunmute", description="Снять голосовой мьют")
@app_commands.describe(user="С кого")
async def vunmute(interaction: discord.Interaction, user: discord.Member):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return
    await user.edit(mute=False)
    await interaction.response.send_message(f"🎤 Голосовой мьют снят с {user.mention}")

bot.run(BOT_TOKEN)
