import discord
from discord.ext import commands
import sqlite3
import asyncio
from discord import app_commands
from discord.ui import Modal, InputText, View, Button

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Подключение к базе данных
conn = sqlite3.connect('bot_database.db')
c = conn.cursor()

# Создание таблиц
def setup_database():
    c.execute('''
        CREATE TABLE IF NOT EXISTS info (
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

setup_database()

# --- Modal для добавления записи в базу данных ---
class AddDataModal(Modal):
    def __init__(self):
        super().__init__(title="Добавить запись")
        self.add_item(InputText(label="Заголовок", placeholder="Введите заголовок"))
        self.add_item(InputText(label="Описание", placeholder="Введите описание"))

    async def callback(self, interaction: discord.Interaction):
        title = self.children[0].value
        description = self.children[1].value
        c.execute("INSERT INTO info (title, description) VALUES (?, ?)", (title, description))
        conn.commit()
        await interaction.response.send_message(f"Запись добавлена:\n**{title}** - {description}", ephemeral=True)

# --- Modal для авторизации перед работой с базой данных ---
class AuthModal(Modal):
    def __init__(self):
        super().__init__(title="Авторизация")
        self.add_item(InputText(label="Введите пароль"))

    async def callback(self, interaction: discord.Interaction):
        password = self.children[0].value
        if password == "1234":
            await interaction.response.send_modal(AddDataModal())
        else:
            await interaction.response.send_message("Неверный пароль!", ephemeral=True)

# --- Команда для вызова интерфейса базы данных ---
@bot.command()
async def data_base(ctx):
    class DataBaseView(View):
        @discord.ui.button(label="Добавить запись", style=discord.ButtonStyle.green)
        async def add_button(self, interaction: discord.Interaction, button: Button):
            await interaction.response.send_modal(AuthModal())

        @discord.ui.button(label="Показать записи", style=discord.ButtonStyle.blurple)
        async def show_button(self, interaction: discord.Interaction, button: Button):
            c.execute("SELECT * FROM info ORDER BY id DESC LIMIT 5")
            data = c.fetchall()
            if not data:
                await interaction.response.send_message("Записей нет.", ephemeral=True)
                return
            msg = "\n".join([f"**{row[1]}** — {row[2]}" for row in data])
            await interaction.response.send_message(msg, ephemeral=True)

    await ctx.send("Выберите действие:", view=DataBaseView())

# --- Приватные чаты ---
class ChatRequestModal(Modal):
    def __init__(self, requester_id, recipient_id):
        super().__init__(title="Создать приватный чат")
        self.requester_id = requester_id
        self.recipient_id = recipient_id
        self.add_item(InputText(label="Установить пароль (по желанию)", required=False))

    async def callback(self, interaction: discord.Interaction):
        password = self.children[0].value or ""
        c.execute("INSERT INTO private_chats (user1_id, user2_id, password) VALUES (?, ?, ?)", 
                  (self.requester_id, self.recipient_id, password))
        conn.commit()
        await interaction.response.send_message("Приватный чат создан.", ephemeral=True)

@bot.command()
async def chat(ctx, member: discord.Member):
    requester = ctx.author
    await member.send(f"{requester.name} хочет начать приватный чат с вами.")

    class AcceptDeclineView(View):
        @discord.ui.button(label="Принять", style=discord.ButtonStyle.green)
        async def accept(self, interaction: discord.Interaction, button: Button):
            await interaction.response.send_modal(ChatRequestModal(requester.id, member.id))

        @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.red)
        async def decline(self, interaction: discord.Interaction, button: Button):
            await interaction.response.send_message("Запрос отклонён.", ephemeral=True)

    await member.send("Вы принимаете запрос?", view=AcceptDeclineView())

@bot.command()
async def chats(ctx):
    user_id = ctx.author.id
    c.execute("SELECT * FROM private_chats WHERE user1_id=? OR user2_id=?", (user_id, user_id))
    rows = c.fetchall()
    if not rows:
        await ctx.send("У вас нет активных чатов.")
    else:
        result = ""
        for chat in rows:
            partner_id = chat[1] if chat[2] == user_id else chat[2]
            user = await bot.fetch_user(partner_id)
            result += f"Чат с {user.name}\n"
        await ctx.send(result)

# --- Простые команды ---
@bot.command()
async def add(ctx, title: str, *, description: str):
    c.execute("INSERT INTO info (title, description) VALUES (?, ?)", (title, description))
    conn.commit()
    await ctx.send(f"Запись добавлена: **{title}** — {description}")

@bot.command()
async def info(ctx):
    c.execute("SELECT * FROM info ORDER BY id DESC LIMIT 5")
    rows = c.fetchall()
    if not rows:
        await ctx.send("Нет записей.")
    else:
        for row in rows:
            await ctx.send(f"**{row[1]}** — {row[2]}")

# Запуск бота
bot.run('YOUR_TOKEN_HERE')