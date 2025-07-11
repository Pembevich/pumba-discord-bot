import discord
from discord.ext import commands
import sqlite3
import os
import io
from PIL import Image
import moviepy.editor as mp
import uuid
from discord import app_commands
import re
import asyncio
from discord import Embed, Color
from datetime import datetime

allowed_guild_ids = [1392735009957347419]  # Укажи нужные ID серверов
sbor_channels = {}  # guild_id -> channel_id

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- База данных ---
conn = sqlite3.connect("bot_data.db")
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    description TEXT
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS private_chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user1_id INTEGER,
    user2_id INTEGER,
    password TEXT
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    sender_id INTEGER,
    message TEXT,
    file BLOB,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

conn.commit()

# --- Приватные чаты ---
@bot.command()
async def open_chat(ctx, chat_id: int):
    user_id = ctx.author.id
    c.execute("SELECT * FROM private_chats WHERE id = ?", (chat_id,))
    chat = c.fetchone()
    if not chat or (user_id != chat[1] and user_id != chat[2]):
        await ctx.send("❌ Чат не найден или у вас нет доступа.")
        return

    embed = discord.Embed(title="Мини-мессенджер", description=f"ID: {chat_id}", color=discord.Color.blurple())
    c.execute("SELECT * FROM chat_messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 5", (chat_id,))
    messages = c.fetchall()
    for msg in reversed(messages):
        sender = await bot.fetch_user(msg[2])
        embed.add_field(name=sender.display_name, value=msg[3] or "[вложение]", inline=False)

    await ctx.send(embed=embed)

# --- Стандартные команды ---
@bot.command()
async def message(ctx, member: discord.Member, *, msg: str = None):
    files = [await a.to_file() for a in ctx.message.attachments]
    if not msg and not files:
        await ctx.send("Введите сообщение или приложите файл.")
        return
    try:
        await member.send(f"Сообщение от **{ctx.author.display_name}**:\n{msg or ''}", files=files)
        await ctx.send("✅ Сообщение отправлено.")
    except:
        await ctx.send("❌ Не удалось отправить сообщение.")

@bot.command()
async def dm(ctx, member: discord.Member, *, msg: str = None):
    if ctx.author.id != 968698192411652176:
        await ctx.send("Нет доступа.")
        return
    files = [await a.to_file() for a in ctx.message.attachments]
    if not msg and not files:
        await ctx.send("Введите сообщение или приложите файл.")
        return
    try:
        await member.send(msg or "", files=files)
        await ctx.send("✅ Анонимное сообщение отправлено.")
    except:
        await ctx.send("❌ Не удалось отправить сообщение.")

@bot.command()
async def add(ctx, title, *, description):
    c.execute("INSERT INTO entries (title, description) VALUES (?, ?)", (title, description))
    conn.commit()
    await ctx.send("Информация добавлена.")

@bot.command()
async def info(ctx):
    c.execute("SELECT title, description FROM entries")
    entries = c.fetchall()
    if not entries:
        await ctx.send("База данных пуста.")
        return

    embed = discord.Embed(title="Информация", color=discord.Color.blue())
    for title, description in entries:
        embed.add_field(name=title, value=description, inline=False)
    await ctx.send(embed=embed)

# --- Команда !gif ---
@bot.command()
async def gif(ctx):
    attachments = ctx.message.attachments

    if not attachments:
        await ctx.send("❌ Прикрепи изображения или видео для создания GIF.")
        return

    files = []
    for a in attachments:
        filename = a.filename.lower()
        if filename.endswith((".jpg", ".jpeg", ".png")):
            files.append(("image", await a.read()))
        elif filename.endswith((".mp4", ".mov", ".webm")):
            files.append(("video", await a.read()))
        else:
            continue

    if not files:
        await ctx.send("❌ Поддерживаются только изображения и видео.")
        return

    if files[0][0] == "video":
        video_data = io.BytesIO(files[0][1])
        unique_id = str(uuid.uuid4())
        temp_video_path = f"{unique_id}.mp4"
        temp_gif_path = f"{unique_id}.gif"

        with open(temp_video_path, "wb") as f:
            f.write(video_data.read())

        try:
            clip = mp.VideoFileClip(temp_video_path).subclip(0, 5)
            clip = clip.resize(width=320)
            clip.write_gif(temp_gif_path)
            await ctx.send(file=discord.File(temp_gif_path))
        except Exception as e:
            await ctx.send(f"❌ Ошибка при создании GIF: {e}")
        finally:
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            if os.path.exists(temp_gif_path):
                os.remove(temp_gif_path)
    else:
        images = [Image.open(io.BytesIO(img[1])).convert("RGBA") for img in files]
        if len(images) == 1:
            images[0].save("output.gif", save_all=True, append_images=[images[0]] * 10, duration=100, loop=0)
        else:
            images[0].save("output.gif", save_all=True, append_images=images[1:], duration=300, loop=0)
        await ctx.send(file=discord.File("output.gif"))
        os.remove("output.gif")

# --- /sbor ---
@bot.tree.command(name="sbor", description="Начать сбор: создаёт голосовой канал и пингует роль")
@app_commands.describe(role="Роль, которую нужно пинговать")
async def sbor(interaction: discord.Interaction, role: discord.Role):
    if interaction.guild.id not in allowed_guild_ids:
        await interaction.response.send_message("❌ Команда недоступна на этом сервере.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    existing = discord.utils.get(interaction.guild.voice_channels, name="сбор")
    if existing:
        await interaction.followup.send("❗ Канал 'сбор' уже существует.")
        return

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(connect=False),
        role: discord.PermissionOverwrite(connect=True, view_channel=True)
    }

    category = interaction.channel.category  # Получаем категорию текущего текстового канала

    voice_channel = await interaction.guild.create_voice_channel(
        "Сбор",
        overwrites=overwrites,
        category=category  # Устанавливаем категорию
    )

    sbor_channels[interaction.guild.id] = voice_channel.id

    webhook = await interaction.channel.create_webhook(name="Сбор")
    await webhook.send(
        content=f"**Сбор! {role.mention}. Заходите в <#{voice_channel.id}>!**",
        username="Сбор",
        avatar_url=bot.user.avatar.url if bot.user.avatar else None
    )
    await webhook.delete()

    await interaction.followup.send("✅ Сбор создан!")
    
# --- /sbor_end ---
@bot.tree.command(name="sbor_end", description="Завершить сбор и удалить голосовой канал")
async def sbor_end(interaction: discord.Interaction):
    if interaction.guild.id not in allowed_guild_ids:
        await interaction.response.send_message("❌ Команда недоступна на этом сервере.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    channel_id = sbor_channels.get(interaction.guild.id)
    if not channel_id:
        await interaction.followup.send("❗ Канал 'сбор' не найден.")
        return

    channel = interaction.guild.get_channel(channel_id)
    if channel:
        await channel.delete()

    webhook = await interaction.channel.create_webhook(name="Сбор")
    await webhook.send(
        content="*Сбор окончен!*",
        username="Сбор",
        avatar_url=bot.user.avatar.url if bot.user.avatar else None
    )
    await webhook.delete()

    sbor_channels.pop(interaction.guild.id, None)
    await interaction.followup.send("✅ Сбор завершён.")

# --- Запуск ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Бот запущен как {bot.user}")

target_channel_id = 1393342266503987270  # Канал, где бот проверяет шаблон

async def send_error_embed(channel, author, error_text, example_template):
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S МСК")
    
    embed = Embed(
        title="❌ Ошибка отправки отчёта",
        description=error_text,
        color=Color.red()
    )
    embed.add_field(name="📝 Как оформить правильно", value=f"```{example_template}```", inline=False)
    embed.set_footer(text=f"Вызвал: {author.name} | ID: {author.id} | {now}")
    
    await channel.send(embed=embed)

@bot.event
async def on_message(message):
    if message.channel.id != target_channel_id or message.author.bot:
        return

    # Проверка структуры
    lines = message.content.strip().split("\n")
    if len(lines) != 5:
        template = (
            "Никнейм: TSergey2008\n"
            "Дс айди: 123456789012345678\n"
            "Время: 1h 30min\n"
            "Причина: FEARRP+NONRP\n"
            "Док-ва: https://example.com"
        )

        await send_error_embed(
            message.channel,
            message.author,
            "Неверное количество строк. Ожидается 5 строк (Никнейм, Дс айди, Время, Причина, Док-ва).",
            template
        )
        return

    nickname_line, id_line, time_line, reason_line, evidence_line = lines

    # Проверка каждой строки
    if not nickname_line.lower().startswith("никнейм:"):
        await message.reply(f"❌ Строка 1 должна начинаться с `Никнейм:`\n```{template}```")
        return

    if not id_line.lower().startswith("дс айди:"):
        await message.reply(f"❌ Строка 2 должна начинаться с `Дс айди:`\n```{template}```")
        return

    if not time_line.lower().startswith("время:"):
        await message.reply(f"❌ Строка 3 должна начинаться с `Время:`\n```{template}```")
        return

    if not reason_line.lower().startswith("причина:"):
        await message.reply(f"❌ Строка 4 должна начинаться с `Причина:`\n```{template}```")
        return

    if not evidence_line.lower().startswith("док-ва:"):
        await message.reply(f"❌ Строка 5 должна начинаться с `Док-ва:`\n```{template}```")
        return

    # Извлечение данных
    try:
        user_id = int(id_line.split(":", 1)[1].strip())
    except ValueError:
        await message.reply(f"❌ `Дс айди` должен быть числом.\n```{template}```")
        return

    time_text = time_line.split(":", 1)[1].strip()
    h_match = re.search(r"(\d+)\s*h", time_text)
    m_match = re.search(r"(\d+)\s*min", time_text)

    total_seconds = 0
    if h_match:
        total_seconds += int(h_match.group(1)) * 3600
    if m_match:
        total_seconds += int(m_match.group(1)) * 60

    if total_seconds == 0:
        await message.reply(f"❌ Указано некорректное время. Примеры: `1h`, `30min`, `1h 15min`.\n```{template}```")
        return

    # Бан
    try:
        member = await message.guild.fetch_member(user_id)
        reason = reason_line.split(":", 1)[1].strip()
        await message.guild.ban(member, reason=reason)
        await message.add_reaction("✅")

        async def unban_later():
            await asyncio.sleep(total_seconds)
            await message.guild.unban(discord.Object(id=user_id), reason="Время бана истекло")

        bot.loop.create_task(unban_later())

    except Exception as e:
        await message.reply(f"❌ Не удалось забанить пользователя: {e}")

    await bot.process_commands(message)

bot.run(os.getenv("DISCORD_TOKEN"))