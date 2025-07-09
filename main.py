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

# Полный сброс: удалим файл, если это не папка
if os.path.exists("downloads"):
    if os.path.isfile("downloads"):
        os.remove("downloads")
        print("❗ Файл 'downloads' удалён.")
    elif not os.path.isdir("downloads"):
        raise Exception("'downloads' существует, но это не директория.")

# Создаём директорию заново
if not os.path.exists("downloads"):
    os.makedirs("downloads")
    print("✅ Папка 'downloads' создана.")
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
    await ctx.send("⏳ Обрабатываю видео...")

    try:
        # Проверяем сообщение, на которое ответили
        reference = ctx.message.reference
        if reference:
            replied_message = await ctx.channel.fetch_message(reference.message_id)
            attachments = replied_message.attachments
        else:
            attachments = ctx.message.attachments

        video_path = None

        # Ищем видео среди вложений
        for attachment in attachments:
            if attachment.filename.lower().endswith((".mp4", ".webm", ".mov")):
                filename = f"{uuid.uuid4().hex}_{attachment.filename}"
                video_path = os.path.join("downloads", filename)

                # Скачиваем видео
                async with aiohttp.ClientSession() as session:
                    async with session.get(attachment.url) as resp:
                        if resp.status == 200:
                            with open(video_path, "wb") as f:
                                f.write(await resp.read())

        if not video_path:
            await ctx.send("⚠️ Нет доступных видео для обработки.")
            return

        # Обрабатываем видео
        clip = VideoFileClip(video_path).subclip(0, min(5, VideoFileClip(video_path).duration))
        clip_resized = clip.resize(height=360)

        frames = []
        for frame in clip_resized.iter_frames(fps=10):
            img = Image.fromarray(frame).convert("RGB")
            frames.append(img)

        gif_path = os.path.join("downloads", f"{uuid.uuid4().hex}.gif")
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:],
            loop=0,
            duration=int(1000 / 10),
            optimize=True,
            disposal=2
        )

        await ctx.send("✅ Гифка готова!", file=discord.File(gif_path))

        # Удаление временных файлов
        os.remove(video_path)
        os.remove(gif_path)

    except Exception as e:
        await ctx.send(f"⚠️ Ошибка при обработке: {e}")

    # Обработка изображений (как и раньше)
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

    if images:
        gif_bytes = io.BytesIO()
        images[0].save(
            gif_bytes,
            format='GIF',
            save_all=True,
            append_images=images[1:] if len(images) > 1 else [images[0]]*3,
            duration=500,
            loop=0
        )
        gif_bytes.seek(0)
        await ctx.send("🎞️ Вот твоя GIF:", file=discord.File(gif_bytes, filename="result.gif"))

# !youtube - скачивание видео
@bot.command()
async def youtube(ctx, url: str):
    await ctx.send("📥 Загружаю видео...")

    ydl_opts = {
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'format': 'mp4[height<=360]',
        'quiet': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        await ctx.send(f"✅ Видео загружено и сохранено как:\n`{filename}`")
    except Exception as e:
        await ctx.send(f"❌ Ошибка при загрузке: {e}")

# !videos — список загруженных видео
@bot.command()
async def videos(ctx):
    folder_path = "downloads"

    # Проверяем, существует ли папка
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)  # создаём, если её нет
        await ctx.send("📁 Папка `downloads` была создана, но пока в ней нет видео.")
        return

    # Получаем список файлов
    files = os.listdir(folder_path)
    video_files = [f for f in files if f.lower().endswith(('.mp4', '.mkv', '.webm', '.mov'))]

    if not video_files:
        await ctx.send("📭 В папке `downloads` пока нет видео.")
        return

    # Формируем сообщение
    message = "**🎬 Список загруженных видео:**\n"
    for i, name in enumerate(video_files, start=1):
        message += f"{i}. `{name}`\n"

    # Discord ограничивает длину сообщений 2000 символами
    if len(message) > 2000:
        await ctx.send("📄 Слишком много видео для отображения. Уточни вручную в папке `downloads`.")
    else:
        await ctx.send(message)
# Запуск бота
bot.run(TOKEN)