import os
import io
import discord
import aiohttp
import aiosqlite
from PIL import Image
from discord.ext import commands
from moviepy.editor import VideoFileClip
from dotenv import load_dotenv
import yt_dlp
import uuid
import imageio.v2 as imageio
from discord.ui import Button, View
import sqlite3

conn = sqlite3.connect("data.db")
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS data (title TEXT, info TEXT)")
conn.commit()
conn.close()
# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Создание папки для видео, если не существует
if not os.path.exists("downloads"):
    os.makedirs("downloads")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user}")
    async with aiosqlite.connect("data.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT,
                info TEXT
            )
        """)
        await db.commit()

# !add - добавление информации о пользователе
@bot.command()
async def add(ctx, user: discord.Member, *, info):
    async with aiosqlite.connect("data.db") as db:
        await db.execute("INSERT OR REPLACE INTO users (id, name, info) VALUES (?, ?, ?)",
                         (user.id, user.name, info))
        await db.commit()
    await ctx.send(f"Информация о {user.name} сохранена.")

# !info - получение информации о пользователе
@bot.command()
async def info(ctx, user: discord.Member):
    async with aiosqlite.connect("data.db") as db:
        async with db.execute("SELECT info FROM users WHERE id = ?", (user.id,)) as cursor:
            row = await cursor.fetchone()
    if row:
        await ctx.send(f"Информация о {user.name}: {row[0]}")
    else:
        await ctx.send("Нет данных.")

# !message - сообщение с указанием отправителя
@bot.command()
async def message(ctx, user_id: int, *, message_content: str):
    try:
        # Если передан не числовой user_id — пробуем распознать как ник
        if not str(user_id).isdigit():
            username_tag = str(user_id).strip()

            # Ищем пользователя по тегу (имя#тег)
            for member in ctx.guild.members:
                if str(member) == username_tag:
                    user = member
                    break
            else:
                await ctx.send("❌ Пользователь с таким ником не найден.")
                return
        else:
            user = await bot.fetch_user(user_id)
        sender_name = ctx.author.name

        full_message = f"📨 Сообщение от **{sender_name}**:\n{message_content}"

        files = []
        for attachment in ctx.message.attachments:
            file_bytes = await attachment.read()
            discord_file = discord.File(io.BytesIO(file_bytes), filename=attachment.filename)
            files.append(discord_file)

        await user.send(content=full_message, files=files)
        await ctx.send(f"✅ Сообщение отправлено пользователю с ID {user_id}.")

    except discord.NotFound:
        await ctx.send("❌ Пользователь не найден.")
    except discord.Forbidden:
        await ctx.send("❌ Невозможно отправить сообщение — пользователь запретил ЛС.")
    except Exception as e:
        await ctx.send(f"⚠️ Ошибка: {e}")

# !dm - анонимное сообщение (только для авторизованных пользователей)
@bot.command(name="dm")
async def dm(ctx, user_id: int, *, message_content: str):
    allowed_users = [968698192411652176]  # Замени на свои Discord ID

    if ctx.author.id not in allowed_users:
        await ctx.send("❌ У вас нет прав на использование этой команды.")
        return

    try:
        user = await bot.fetch_user(user_id)

        files = []
        for attachment in ctx.message.attachments:
            file_bytes = await attachment.read()
            discord_file = discord.File(io.BytesIO(file_bytes), filename=attachment.filename)
            files.append(discord_file)

        await user.send(content=message_content, files=files)
        await ctx.send(f"✅ Сообщение отправлено пользователю с ID {user_id}.")

    except discord.NotFound:
        await ctx.send("❌ Пользователь не найден.")
    except discord.Forbidden:
        await ctx.send("❌ Невозможно отправить сообщение — пользователь запретил ЛС.")
    except Exception as e:
        await ctx.send(f"⚠️ Ошибка: {e}")

# !gif - генерация GIF из картинки или видео
@bot.command()
async def gif(ctx):
    """Создаёт GIF из изображений или видео"""
    if not ctx.message.attachments:
        await ctx.send("❌ Пожалуйста, прикрепи изображение или видео к сообщению.")
        return

    attachment = ctx.message.attachments[0]
    file_url = attachment.url
    file_name = attachment.filename.lower()

    # Обработка видео
    if file_name.endswith(('.mp4', '.mov', '.webm')):
        await ctx.send("⏳ Обрабатываю видео, это может занять несколько секунд...")
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    await ctx.send("❌ Не удалось скачать видео.")
                    return
                video_bytes = await resp.read()

        # Сохраняем видео во временный файл
        temp_video_path = "temp_video.mp4"
        with open(temp_video_path, "wb") as f:
            f.write(video_bytes)

        try:
            clip = VideoFileClip(temp_video_path).subclip(0, min(5, VideoFileClip(temp_video_path).duration))
            gif_path = "output.gif"
            clip.write_gif(gif_path, fps=10)

            await ctx.send("🎞️ Вот твоя GIF из видео:", file=discord.File(gif_path))
        except Exception as e:
            await ctx.send(f"⚠️ Ошибка при обработке видео: {e}")
        finally:
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            if os.path.exists("output.gif"):
                os.remove("output.gif")
        return

    # Обработка изображений
    images = []
    for attachment in ctx.message.attachments:
        if attachment.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as resp:
                    if resp.status != 200:
                        continue
                    data = io.BytesIO(await resp.read())
                    img = Image.open(data).convert("RGBA")
                    images.append(img)

    if len(images) == 0:
        await ctx.send("❌ Поддерживаются только изображения и видео.")
        return

    # Создание GIF из одного или нескольких изображений
    gif_bytes = io.BytesIO()
    images[0].save(gif_bytes, format='GIF', save_all=True, append_images=images[1:] if len(images) > 1 else [images[0]]*3, duration=500, loop=0)
    gif_bytes.seek(0)

    await ctx.send("🎞️ Вот твоя GIF:", file=discord.File(gif_bytes, filename="result.gif"))
@bot.command()
async def data_base(ctx):
    await ctx.send("```\n[ВВЕДИТЕ_ПАРОЛЬ]\n———————————-\n[ENTER_PASSWORD]\n\n>...\n```")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
        if msg.content != "TEST_PASSWORD":
            await ctx.send("```\n[...]\n\n[НЕВЕРНЫЙ_ПАРОЛЬ]\n———————————-\n[WRONG_PASSWORD]\n```")
            return
    except asyncio.TimeoutError:
        await ctx.send("```\n[...]\n\n[ОТКЛЮЧЕНИЕ(ВРЕМЯ ОЖИДАНИЯ ИСТЕКЛО)]\n———————————-\n[INCONNECTING(TIME IS UP)]\n```")
        return

    # Добро пожаловать
    await ctx.send("```\n[...]\n\n[ДОБРО_ПОЖАЛОВАТЬ_В_БАЗУ_ДАННЫХ]\n———————————\n[WELCOME_TO_DATA_BASE]\n\n———————————\n\n[ОЖИДАНИЕ_КОМАНДЫ _ОТ_КОНСОЛИ]\n———————————\n[WAITING_FOR_COMMAND_OF_CONSOLE]\n\n>...\n```")

    # Создание кнопок
    view = View()

    async def view_data_callback(interaction):
        if interaction.user != ctx.author:
            await interaction.response.send_message("```\n[...]\n\n[ACCESS_GRUNTED]\n```", ephemeral=True)
            return

        conn = sqlite3.connect("data.db")
        cursor = conn.cursor()
        cursor.execute("SELECT title, info FROM data")
        rows = cursor.fetchall()
        conn.close()

        if rows:
            content = "\n\n".join([f">... \n{title} — {info}" for title, info in rows])
        else:
            content = "```\n[...]\n\n[ЗАПИСИ_ОТСУТСТВУЮТ]\n———————————\n[THERE_ARE_NO_RECORDS]\n\n>...\n```"

        await interaction.response.send_message(f"```\n{content}\n\n[…]```", ephemeral=True)

    async def add_data_callback(interaction):
        if interaction.user != ctx.author:
            await interaction.response.send_message("```\n[...]\n\n[ACCESS_GRUNTED]\n```", ephemeral=True)
            return

        await interaction.response.send_message("```\n[...]\n\n[НОВАЯ_ЗАПИСЬ]\n———————————\n[NEW_ENTRY]\n\n[ВВЕДИТЕ_НАЗВАНИЕ/ЗАГОЛОВОК]\n—————————\n[ENTER_TITLE/HEADLINE]\n\n>...\n```", ephemeral=True)
        try:
            title_msg = await bot.wait_for("message", check=check, timeout=30.0)
            await ctx.send("```\n[...]\n\n[ВВЕДИТЕ_ОПИСАНИЕ/СОДЕРЖАНИЕ]\n———————————\n[ENTER_DISCRIPTION/CONTENT]\n\n>...\n```")
            info_msg = await bot.wait_for("message", check=check, timeout=30.0)

            conn = sqlite3.connect("data.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO data (title, info) VALUES (?, ?)", (title_msg.content, info_msg.content))
            conn.commit()
            conn.close()

            await ctx.send("```[…]\n\n[ДАННЫЕ_ЗАПИСАНЫ]\n—————————\n[DATA_IS_RECORDED]\n```")

        except asyncio.TimeoutError:
            await ctx.send("```\n[...]\n\n[ОТКЛЮЧЕНИЕ(ВРЕМЯ ОЖИДАНИЯ ИСТЕКЛО)]\n———————————-\n[INCONNECTING(TIME IS UP)]\n```")

    # Добавляем кнопки
    view.add_item(Button(label="[ПРОСМОТР_ДАННЫХ]", style=discord.ButtonStyle.grey, custom_id="view"))
    view.add_item(Button(label="[ВНЕСТИ_ДАННЫЕ]", style=discord.ButtonStyle.grey, custom_id="add"))

    # Назначаем обработчики
    view.children[0].callback = view_data_callback
    view.children[1].callback = add_data_callback

    # Отправка интерфейса
    await ctx.send("```[КОМАНДЫ_КОНСОЛИ]:```", view=view)
# (весь предыдущий код оставлен без изменений вплоть до конца data_base)

# Таблицы для приватных чатов
@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user}")
    async with aiosqlite.connect("data.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT,
                info TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS private_chats (
                chat_id TEXT PRIMARY KEY,
                user1_id INTEGER,
                user2_id INTEGER,
                password TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                sender_id INTEGER,
                message TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

# Команда !chat для создания чата
@bot.command()
async def chat(ctx, target: discord.User):
    sender = ctx.author

    # Проверка: уже существует чат?
    async with aiosqlite.connect("data.db") as db:
        async with db.execute("""
            SELECT chat_id FROM private_chats
            WHERE (user1_id = ? AND user2_id = ?)
               OR (user1_id = ? AND user2_id = ?)
        """, (sender.id, target.id, target.id, sender.id)) as cursor:
            existing = await cursor.fetchone()

        if existing:
            await ctx.send("❗ Чат уже существует.")
            return

    # Отправка запроса получателю
    try:
        view = View()
        accept_button = Button(label="Принять чат", style=discord.ButtonStyle.green)

        async def accept_callback(interaction):
            if interaction.user.id != target.id:
                await interaction.response.send_message("⛔ Не для вас!", ephemeral=True)
                return

            chat_id = str(uuid.uuid4())
            async with aiosqlite.connect("data.db") as db:
                await db.execute("""
                    INSERT INTO private_chats (chat_id, user1_id, user2_id, password)
                    VALUES (?, ?, ?, ?)
                """, (chat_id, sender.id, target.id, None))
                await db.commit()

            await interaction.response.send_message("✅ Чат создан. Используйте `!chats`, чтобы просматривать чаты.", ephemeral=True)

        accept_button.callback = accept_callback
        view.add_item(accept_button)

        await target.send(f"🔔 Пользователь **{sender}** хочет начать с вами приватный чат.", view=view)
        await ctx.send("✅ Запрос на чат отправлен.")

    except discord.Forbidden:
        await ctx.send("❌ Не удалось отправить запрос: пользователь закрыл личные сообщения.")

# Команда !chats для просмотра чатов
@bot.command()
async def chats(ctx):
    user_id = ctx.author.id
    async with aiosqlite.connect("data.db") as db:
        async with db.execute("""
            SELECT chat_id, user1_id, user2_id FROM private_chats
            WHERE user1_id = ? OR user2_id = ?
        """, (user_id, user_id)) as cursor:
            chats = await cursor.fetchall()

    if not chats:
        await ctx.send("❌ У вас нет активных чатов.")
        return

    view = View(timeout=120)
    for chat in chats:
        chat_id, user1, user2 = chat
        partner_id = user2 if user1 == user_id else user1
        partner = await bot.fetch_user(partner_id)
        btn = Button(label=f"Чат с {partner.name}", style=discord.ButtonStyle.primary)

        async def make_modal(chat_id_inner):
            class ChatModal(discord.ui.Modal, title="🔒 Приватный чат"):
                message = discord.ui.TextInput(label="Сообщение", style=discord.TextStyle.paragraph, required=True)

                async def on_submit(self, interaction: discord.Interaction):
                    async with aiosqlite.connect("data.db") as db:
                        await db.execute("""
                            INSERT INTO chat_messages (chat_id, sender_id, message)
                            VALUES (?, ?, ?)
                        """, (chat_id_inner, interaction.user.id, self.message.value))
                        await db.commit()
                    await interaction.response.send_message("✅ Сообщение отправлено.", ephemeral=True)

            return ChatModal()

        async def callback(interaction, chat_id_inner=chat_id):
            # Проверка пароля (если установлен)
            async with aiosqlite.connect("data.db") as db:
                async with db.execute("SELECT password FROM private_chats WHERE chat_id = ?", (chat_id_inner,)) as c:
                    row = await c.fetchone()
            if row and row[0]:
                await interaction.response.send_modal(PasswordModal(chat_id_inner))
            else:
                await interaction.response.send_modal(await make_modal(chat_id_inner))

        btn.callback = callback
        view.add_item(btn)

    await ctx.send("📬 Ваши чаты:", view=view)

# Modal для ввода пароля
class PasswordModal(discord.ui.Modal, title="🔑 Введите пароль"):
    password = discord.ui.TextInput(label="Пароль", style=discord.TextStyle.short, required=True)

    def __init__(self, chat_id):
        super().__init__()
        self.chat_id = chat_id

    async def on_submit(self, interaction: discord.Interaction):
        async with aiosqlite.connect("data.db") as db:
            async with db.execute("SELECT password FROM private_chats WHERE chat_id = ?", (self.chat_id,)) as cursor:
                row = await cursor.fetchone()

        if row and self.password.value == row[0]:
            await interaction.response.send_modal(await make_chat_modal(self.chat_id))
        else:
            await interaction.response.send_message("❌ Неверный пароль.", ephemeral=True)

# Modal для ввода сообщения
async def make_chat_modal(chat_id):
    class ChatModal(discord.ui.Modal, title="✉️ Сообщение в чат"):
        message = discord.ui.TextInput(label="Сообщение", style=discord.TextStyle.paragraph, required=True)

        async def on_submit(self, interaction: discord.Interaction):
            async with aiosqlite.connect("data.db") as db:
                await db.execute("""
                    INSERT INTO chat_messages (chat_id, sender_id, message)
                    VALUES (?, ?, ?)
                """, (chat_id, interaction.user.id, self.message.value))
                await db.commit()
            await interaction.response.send_message("✅ Сообщение отправлено.", ephemeral=True)

    return ChatModal()

# Запуск бота
bot.run(TOKEN)