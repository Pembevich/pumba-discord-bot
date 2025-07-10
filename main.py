import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
from discord.ui import Modal, TextInput, View, Button
from discord import TextStyle
from discord import app_commands, Interaction
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
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

conn.commit()


# --- Привилегированные пользователи для !dm ---
ALLOWED_DM_USERS = [123456789012345678]  # Укажи здесь свой Discord ID или список ID


# --- Модальные окна для базы данных ---
class PasswordModal(Modal, title="Введите пароль"):
    password = TextInput(label="Пароль", style=TextStyle.short)

    def __init__(self):
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        if self.password.value == "1234":
            await interaction.response.send_modal(EntryModal())
        else:
            await interaction.response.send_message("Неверный пароль.", ephemeral=True)


class EntryModal(Modal, title="Добавить запись"):
    title = TextInput(label="Заголовок", style=TextStyle.short)
    description = TextInput(label="Описание", style=TextStyle.paragraph)

    def __init__(self):
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        c.execute("INSERT INTO entries (title, description) VALUES (?, ?)", (self.title.value, self.description.value))
        conn.commit()
        await interaction.response.send_message("Запись добавлена.", ephemeral=True)

@bot.tree.command(name="data_base", description="Открыть интерфейс базы данных")
async def data_base(interaction: Interaction):
    await interaction.response.send_modal(PasswordModal(interaction))

# --- Приватные чаты ---
class ChatPasswordModal(Modal, title="Установить пароль для чата"):
    password = TextInput(label="Пароль", required=False)

    def __init__(self, requester, partner):
        super().__init__()
        self.requester = requester
        self.partner = partner

    async def on_submit(self, interaction: discord.Interaction):
        c.execute("INSERT INTO private_chats (user1_id, user2_id, password) VALUES (?, ?, ?)",
                  (self.requester.id, self.partner.id, self.password.value))
        conn.commit()
        await interaction.response.send_message(f"Приватный чат с {self.partner.display_name} создан.", ephemeral=True)
        try:
            await self.partner.send(f"{self.requester.display_name} хочет начать с вами приватный чат.")
        except:
            pass


@bot.command(name='chat')
async def start_private_chat(ctx, member_identifier: str):
    if member == ctx.author:
        await ctx.send("Вы не можете начать чат с самим собой.")
        return
    await ctx.send("Открываю настройки чата...", delete_after=1)
    await ctx.author.send_modal(ChatPasswordModal(ctx.author, member))


@bot.command()
async def chats(ctx):
    user_id = ctx.author.id
    c.execute("SELECT * FROM private_chats WHERE user1_id = ? OR user2_id = ?", (user_id, user_id))
    chats = c.fetchall()
    if not chats:
        await ctx.send("У вас нет активных приватных чатов.")
        return

    embed = discord.Embed(title="Ваши чаты", color=discord.Color.green())
    for chat in chats:
        uid = chat[1] if chat[1] != user_id else chat[2]
        user = await bot.fetch_user(uid)
        embed.add_field(name=f"С {user.display_name}", value=f"ID чата: {chat[0]}", inline=False)

    await ctx.send(embed=embed)


# --- !message: отправка от имени пользователя ---
@bot.command()
async def message(ctx, member: discord.Member, *, msg: str = None):
    files = [await attachment.to_file() for attachment in ctx.message.attachments]
    if msg is None and not files:
        await ctx.send("Нужно ввести сообщение или приложить файл.")
        return
    try:
        content = f"Сообщение от **{ctx.author.display_name}**:\n{msg or ''}"
        await member.send(content, files=files)
        await ctx.send("Сообщение отправлено.")
    except:
        await ctx.send("Не удалось отправить сообщение пользователю.")


# --- !dm: анонимная отправка (только для админов) ---
@bot.command()
async def dm(ctx, member: discord.Member, *, msg: str = None):
    if ctx.author.id not in 968698192411652176:
        await ctx.send("У вас нет доступа к этой команде.")
        return

    files = [await attachment.to_file() for attachment in ctx.message.attachments]
    if msg is None and not files:
        await ctx.send("Нужно ввести сообщение или приложить файл.")
        return
    try:
        await member.send(msg or "", files=files)
        await ctx.send("Анонимное сообщение отправлено.")
    except:
        await ctx.send("Не удалось отправить сообщение пользователю.")


# --- Команда !add и !info из базы данных ---
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

    embed = discord.Embed(title="Информация из базы данных", color=discord.Color.blue())
    for title, description in entries:
        embed.add_field(name=title, value=description, inline=False)

    await ctx.send(embed=embed)


# --- Запуск ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Бот запущен как {bot.user}")

bot.run(os.getenv("DISCORD_TOKEN"))