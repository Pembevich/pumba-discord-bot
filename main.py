import discord
from discord.ext import commands
import aiosqlite
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Бот запущен как {bot.user}")
    async with aiosqlite.connect("data.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT,
                info TEXT
            )
        """)
        await db.commit()

@bot.command()
async def add(ctx, user: discord.Member, *, info):
    async with aiosqlite.connect("data.db") as db:
        await db.execute("INSERT OR REPLACE INTO users (id, name, info) VALUES (?, ?, ?)",
                         (user.id, user.name, info))
        await db.commit()
    await ctx.send(f"Информация о {user.name} сохранена.")

@bot.command()
async def info(ctx, user: discord.Member):
    async with aiosqlite.connect("data.db") as db:
        async with db.execute("SELECT info FROM users WHERE id = ?", (user.id,)) as cursor:
            row = await cursor.fetchone()
    if row:
        await ctx.send(f"Информация о {user.name}: {row[0]}")
    else:
        await ctx.send("Нет данных.")

@bot.command()
async def message(ctx, user: discord.Member, *, text):
    try:
        await user.send(f"Сообщение от {ctx.author.name}: {text}")
        await ctx.send("Сообщение отправлено.")
    except discord.Forbidden:
        await ctx.send("Не удалось отправить сообщение. Возможно, пользователь отключил ЛС.")

import discord
from discord.ext import commands
import sqlite3  # <-- вот это важно
intents = discord.Intents.default()
intents.message_content = True  # обязательно, чтобы бот видел сообщения

bot = commands.Bot(command_prefix='!', intents=intents)
# Подключение к базе
conn = sqlite3.connect('database.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS information (
    title TEXT PRIMARY KEY,
    content TEXT
)''')
conn.commit()

# Команда для добавления информации
@bot.command()
async def add(ctx, title: str, *, content: str):
    try:
        c.execute("INSERT OR REPLACE INTO information (title, content) VALUES (?, ?)", (title.lower(), content))
        conn.commit()
        await ctx.send(f"✅ Информация с заголовком `{title}` добавлена.")
    except Exception as e:
        await ctx.send(f"❌ Ошибка при добавлении: {e}")

# Команда для получения информации
@bot.command()
async def info(ctx, title: str):
    c.execute("SELECT content FROM information WHERE title = ?", (title.lower(),))
    result = c.fetchone()
    if result:
        await ctx.send(f"📌 **{title}**:\n{result[0]}")
    else:
        await ctx.send("❗ Информация не найдена.")
bot.run(TOKEN)
