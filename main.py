import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
from discord.ui import Modal, TextInput, View, Button
from discord import TextStyle, Interaction

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

# --- /data_base (Modal интерфейс с паролем) ---
class PasswordModal(Modal, title="Введите пароль"):
    password = TextInput(label="Пароль", style=TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        if self.password.value == "1234":
            view = EntryModalButtonView()
            await interaction.response.send_message("Пароль верен. Нажмите кнопку ниже, чтобы добавить запись:", view=view, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Неверный пароль.", ephemeral=True)

class EntryModalButtonView(View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Добавить запись", style=discord.ButtonStyle.primary)
    async def open_entry_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EntryModal())

class EntryModal(Modal, title="Добавить запись"):
    title = TextInput(label="Заголовок", style=TextStyle.short)
    description = TextInput(label="Описание", style=TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        c.execute("INSERT INTO entries (title, description) VALUES (?, ?)", (self.title.value, self.description.value))
        conn.commit()
        await interaction.response.send_message("✅ Запись добавлена!", ephemeral=True)

@bot.tree.command(name="data_base", description="Открыть интерфейс базы данных")
async def data_base(interaction: Interaction):
    await interaction.response.send_modal(PasswordModal())

# --- Приватные чаты (Modal интерфейс) ---
class ChatRequestModal(Modal, title="Создать приватный чат"):
    password = TextInput(label="Установите пароль (необязательно)", required=False)

    def __init__(self, requester, partner):
        super().__init__()
        self.requester = requester
        self.partner = partner

    async def on_submit(self, interaction: discord.Interaction):
        # Проверка на уже существующий чат
        c.execute('''SELECT id FROM private_chats 
                     WHERE (user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)''',
                  (self.requester.id, self.partner.id, self.partner.id, self.requester.id))
        if c.fetchone():
            await interaction.response.send_message("Чат с этим пользователем уже существует.", ephemeral=True)
            return

        c.execute("INSERT INTO private_chats (user1_id, user2_id, password) VALUES (?, ?, ?)",
                  (self.requester.id, self.partner.id, self.password.value))
        conn.commit()
        await interaction.response.send_message("✅ Приватный чат создан!", ephemeral=True)
        try:
            await self.partner.send(f"{self.requester.display_name} хочет с вами начать приватный чат. Используйте команду `/chats` для просмотра.")
        except:
            pass

@bot.tree.command(name="chat", description="Создать приватный чат с пользователем")
@app_commands.describe(member="Пользователь")
async def chat(interaction: Interaction, member: discord.Member):
    if member.id == interaction.user.id:
        await interaction.response.send_message("❌ Нельзя создать чат с самим собой.", ephemeral=True)
        return

    modal = ChatRequestModal(interaction.user, member)
    await interaction.response.send_modal(modal)

@bot.tree.command(name="chats", description="Посмотреть ваши чаты")
async def chats(interaction: Interaction):
    user_id = interaction.user.id
    c.execute("SELECT * FROM private_chats WHERE user1_id = ? OR user2_id = ?", (user_id, user_id))
    chats = c.fetchall()

    if not chats:
        await interaction.response.send_message("У вас нет активных чатов.", ephemeral=True)
        return

    embed = discord.Embed(title="Ваши приватные чаты", color=discord.Color.green())
    for chat in chats:
        other_id = chat[1] if chat[2] == user_id else chat[2]
        try:
            other_user = await bot.fetch_user(other_id)
            embed.add_field(name=other_user.display_name, value=f"`!open_chat {chat[0]}`", inline=False)
        except:
            continue

    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Открытие чата и отправка сообщений через Modal ---
class ChatMessageModal(Modal, title="Отправить сообщение"):
    content = TextInput(label="Сообщение", style=TextStyle.paragraph, required=False)

    def __init__(self, chat_id, sender):
        super().__init__()
        self.chat_id = chat_id
        self.sender = sender

    async def on_submit(self, interaction: discord.Interaction):
        file_data = None
        if interaction.message and interaction.message.attachments:
            file_data = await interaction.message.attachments[0].read()

        c.execute("INSERT INTO chat_messages (chat_id, sender_id, message, file) VALUES (?, ?, ?, ?)",
                  (self.chat_id, self.sender.id, self.content.value, file_data))
        conn.commit()
        await interaction.response.send_message("Сообщение отправлено!", ephemeral=True)

class OpenChatView(View):
    def __init__(self, chat_id, user):
        super().__init__(timeout=300)
        self.chat_id = chat_id
        self.user = user

    @discord.ui.button(label="✉️ Написать", style=discord.ButtonStyle.primary)
    async def send_message(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ChatMessageModal(self.chat_id, self.user))

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

    view = OpenChatView(chat_id, ctx.author)
    await ctx.send(embed=embed, view=view)

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

# --- Запуск ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Бот запущен как {bot.user}")

bot.run(os.getenv("DISCORD_TOKEN"))