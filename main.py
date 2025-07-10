import discord
from discord.ext import commands
from discord import app_commands
import sqlite3

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Создание/подключение к БД
conn = sqlite3.connect("bot_data.db")
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL
)''')
conn.commit()

# ========== MODAL С ПАРОЛЕМ ==========

ADMIN_PASSWORD = "1234"  # можно вынести в ENV

class PasswordModal(discord.ui.Modal, title="Авторизация"):
    password = discord.ui.TextInput(label="Введите пароль", style=discord.TextStyle.short, min_length=1)

    def __init__(self, interaction: discord.Interaction):
        super().__init__()
        self.interaction = interaction

    async def on_submit(self, interaction: discord.Interaction):
        if self.password.value == ADMIN_PASSWORD:
            await interaction.response.send_message("Доступ разрешён.", ephemeral=True, view=DatabaseView())
        else:
            await interaction.response.send_message("Неверный пароль.", ephemeral=True)

# ========== VIEW С КНОПКАМИ ==========

class DatabaseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Добавить запись", style=discord.ButtonStyle.green)
    async def add_data(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddDataModal())

    @discord.ui.button(label="Показать все", style=discord.ButtonStyle.blurple)
    async def show_data(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor.execute("SELECT title, description FROM data")
        rows = cursor.fetchall()
        if not rows:
            await interaction.response.send_message("База данных пуста.", ephemeral=True)
        else:
            msg = "\n\n".join([f"**{title}**\n{desc}" for title, desc in rows])
            await interaction.response.send_message(msg[:2000], ephemeral=True)

# ========== MODAL ДОБАВЛЕНИЯ ДАННЫХ ==========

class AddDataModal(discord.ui.Modal, title="Новая запись"):
    title = discord.ui.TextInput(label="Заголовок", max_length=100)
    description = discord.ui.TextInput(label="Описание", style=discord.TextStyle.paragraph, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        cursor.execute("INSERT INTO data (title, description) VALUES (?, ?)", (self.title.value, self.description.value))
        conn.commit()
        await interaction.response.send_message("Запись добавлена!", ephemeral=True)

# ========== КОМАНДА ДЛЯ ДОСТУПА К ИНТЕРФЕЙСУ ==========

@tree.command(name="data_base", description="Открыть базу данных")
async def open_data_base(interaction: discord.Interaction):
    await interaction.response.send_modal(PasswordModal(interaction))

# ========== СТАРЫЕ КОМАНДЫ ==========

@bot.command()
async def add(ctx, *, content):
    with open("data.txt", "a") as file:
        file.write(content + "\n")
    await ctx.send("Информация добавлена.")

@bot.command()
async def info(ctx):
    try:
        with open("data.txt", "r") as file:
            content = file.read()
        await ctx.send(content if content else "Нет данных.")
    except FileNotFoundError:
        await ctx.send("Файл не найден.")

@bot.command()
async def message(ctx, user: discord.User, *, msg):
    await user.send(msg)
    await ctx.send("Сообщение отправлено.")

@bot.command()
async def dm(ctx, user: discord.User):
    await user.send("Привет! Это личное сообщение.")
    await ctx.send("Личное сообщение отправлено.")

# ========== ОН РЕДИ ==========

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Бот запущен как {bot.user}")

bot.run(TOKEN)