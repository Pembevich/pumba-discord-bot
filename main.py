import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
from discord.ui import Modal, TextInput, Button, View
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
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

conn.commit()

# --- Модальные окна для базы данных ---
class PasswordModal(Modal, title="Введите пароль"):
    password = TextInput(label="Пароль", style=TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        if self.password.value == "1234":
            view = EntryModalButtonView()
            await interaction.response.send_message("Пароль верен. Нажмите кнопку ниже, чтобы добавить запись:", view=view, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Неверный пароль. Попробуйте снова.", ephemeral=True)

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

# --- Приватные чаты ---
class ChatPasswordModal(Modal):
    def __init__(self):
        super().__init__(title="Установить пароль для чата")
        self.password = TextInput(label="Пароль", required=False)
        self.add_item(self.password)

        self.requester = None
        self.partner = None

    async def on_submit(self, interaction: discord.Interaction):
        c.execute("INSERT INTO private_chats (user1_id, user2_id, password) VALUES (?, ?, ?)",
                  (self.requester.id, self.partner.id, self.password.value))
        conn.commit()
        await interaction.response.send_message(f"Приватный чат с {self.partner.display_name} создан.", ephemeral=True)
        try:
            await self.partner.send(f"{self.requester.display_name} хочет начать с вами приватный чат.")
        except:
            pass

@bot.tree.command(name="chat", description="Создать приватный чат с пользователем")
@app_commands.describe(member="Пользователь, с которым хотите начать чат")
async def chat(interaction: Interaction, member: discord.Member):
    if member == interaction.user:
        await interaction.response.send_message("Нельзя создать чат с самим собой.", ephemeral=True)
        return

    modal = ChatPasswordModal()
    modal.requester = interaction.user
    modal.partner = member
    await interaction.response.send_modal(modal)

@bot.tree.command(name="chats", description="Показать список ваших приватных чатов")
async def chats(interaction: Interaction):
    user_id = interaction.user.id
    c.execute("SELECT * FROM private_chats WHERE user1_id = ? OR user2_id = ?", (user_id, user_id))
    chats = c.fetchall()

    if not chats:
        await interaction.response.send_message("У вас нет активных приватных чатов.", ephemeral=True)
        return

    embed = discord.Embed(title="Ваши чаты", color=discord.Color.green())
    for chat in chats:
        uid = chat[1] if chat[1] != user_id else chat[2]
        try:
            user = await bot.fetch_user(uid)
            embed.add_field(name=f"С {user.display_name}", value=f"ID чата: {chat[0]}", inline=False)
        except:
            continue

    await interaction.response.send_message(embed=embed, ephemeral=True)

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
    if ctx.author.id != 968698192411652176:
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

# --- !add и !info из базы данных ---
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