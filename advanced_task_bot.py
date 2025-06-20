import discord
from discord.ext import commands, tasks
import json
import os
import io
import matplotlib.pyplot as plt
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

# === Keep Alive ===
app = Flask(__name__)
@app.route("/")
def home():
    return "✅ Bot is alive!"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    Thread(target=run).start()

keep_alive()

# === Load Token ===
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# === Setup ===
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

TASKS_FILE = "tasks.json"
tasks = json.load(open(TASKS_FILE)) if os.path.exists(TASKS_FILE) else []

def save_tasks():
    with open(TASKS_FILE, "w") as f:
        json.dump(tasks, f, indent=2)

def create_embed(task):
    status = "✅ Done" if task["done"] else "⏳ Pending"
    embed = discord.Embed(title=f"📋 Task #{task['id']} - {task['name']}", color=0x00ffcc)
    embed.add_field(name="📝 Description", value=task['description'], inline=False)
    embed.add_field(name="🔘 Status", value=status, inline=True)
    embed.add_field(name="👤 Assigned To", value=f"<@{task['assigned_to']}>" if task['assigned_to'] else "Unassigned", inline=True)
    return embed

@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user}")

    # Start the alive message task loop if not running
    if not send_alive_message.is_running():
        send_alive_message.start()

# === Background task to send "I'm alive" every 10 minutes ===
@tasks.loop(minutes=10)
async def send_alive_message():
    # Define the guild and channel names
    GUILD_ID = 1382363476948680754  # Replace with your server ID (int)
    CHANNEL_NAME = "bot-status"     # Channel name you want the bot to send messages in

    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        print("Guild not found. Check GUILD_ID.")
        return

    # Try to get the channel
    channel = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
    if channel is None:
        # Create channel if it doesn't exist
        try:
            channel = await guild.create_text_channel(CHANNEL_NAME)
            print(f"Created channel #{CHANNEL_NAME}")
        except Exception as e:
            print(f"Failed to create channel: {e}")
            return

    try:
        await channel.send("🤖 I'm alive and running 24/7! 🌟")
    except Exception as e:
        print(f"Failed to send alive message: {e}")

# --- Your existing commands here ---

@bot.command()
async def taskcreate(ctx, *, args=None):
    if not args or "--desc" not in args:
        return await ctx.send("❗ Usage: !taskcreate \"Title\" --desc \"short description\"")
    title, desc = args.split("--desc", 1)
    task = {
        "id": len(tasks) + 1,
        "name": title.strip().strip('"'),
        "description": desc.strip().strip('"'),
        "assigned_to": ctx.author.id,
        "done": False
    }
    tasks.append(task)
    save_tasks()
    await ctx.send("📌 Task created:", embed=create_embed(task))

@bot.command()
async def tasklist(ctx):
    if not tasks:
        return await ctx.send("📭 No tasks.")
    for task in tasks:
        await ctx.send(embed=create_embed(task))

@bot.command()
async def taskdone(ctx, task_id: int):
    for task in tasks:
        if task["id"] == task_id:
            if task["assigned_to"] != ctx.author.id:
                return await ctx.send("🚫 Only assigned user can mark done.")
            task["done"] = True
            save_tasks()
            await ctx.send(f"✅ Task #{task_id} marked done!", embed=create_embed(task))
            return
    await ctx.send("❌ Task not found.")

@bot.command()
async def taskdelete(ctx, task_id: int):
    global tasks
    for task in tasks:
        if task["id"] == task_id:
            if task["assigned_to"] != ctx.author.id:
                return await ctx.send("🚫 You can't delete others' tasks.")
            tasks = [t for t in tasks if t["id"] != task_id]
            save_tasks()
            return await ctx.send(f"🗑️ Task #{task_id} deleted.")
    await ctx.send("❌ Task not found.")

@bot.command()
async def taskassign(ctx, task_id: int, user: discord.Member):
    for task in tasks:
        if task["id"] == task_id:
            task["assigned_to"] = user.id
            save_tasks()
            await ctx.send(f"👤 Task #{task_id} assigned to {user.mention}", embed=create_embed(task))
            return
    await ctx.send("❌ Task not found.")

@bot.command()
async def taskchart(ctx):
    done = sum(1 for t in tasks if t["done"])
    pending = len(tasks) - done
    plt.figure(figsize=(5, 5))
    plt.pie([done, pending], labels=["Done", "Pending"], autopct="%1.1f%%", colors=["green", "orange"])
    plt.title("📊 Task Completion")
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    await ctx.send(file=discord.File(buf, "task_chart.png"))
    buf.close()

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="🛠️ Task Bot Help", description="Manage tasks easily.", color=0x00ffcc)
    embed.add_field(name="Create Task", value="!taskcreate \"Title\" --desc \"Description\"", inline=False)
    embed.add_field(name="List Tasks", value="!tasklist", inline=False)
    embed.add_field(name="Mark Done", value="!taskdone <task_id>", inline=False)
    embed.add_field(name="Assign User", value="!taskassign <task_id> @user", inline=False)
    embed.add_field(name="Delete Task", value="!taskdelete <task_id>", inline=False)
    embed.add_field(name="Task Chart", value="!taskchart", inline=False)
    await ctx.send(embed=embed)

bot.run(TOKEN)
