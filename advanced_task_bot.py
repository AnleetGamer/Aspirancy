from keep_alive import keep_alive
keep_alive()

import discord
from discord.ext import commands
import json
import os
import matplotlib.pyplot as plt
import io
from keep_alive import keep_alive
keep_alive()

# === Settings ===
DISCORD_TOKEN = "YOUR_BOT_TOKEN_HERE"
TASKS_FILE = "tasks.json"

# === Load Tasks ===
if os.path.exists(TASKS_FILE):
    with open(TASKS_FILE, "r") as f:
        tasks = json.load(f)
else:
    tasks = []

def save_tasks():
    with open(TASKS_FILE, "w") as f:
        json.dump(tasks, f, indent=2)

# === Bot Setup ===
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

def create_task_embed(task):
    status = "✅ Done" if task["done"] else "⏳ Pending"
    assigned = f"<@{task['assigned_to']}>" if task["assigned_to"] else "Unassigned"
    embed = discord.Embed(title=f"📋 Task #{task['id']}", color=0x00ffcc)
    embed.add_field(name="Name", value=task["name"], inline=False)
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Assigned To", value=assigned, inline=True)
    embed.set_footer(text="Task Manager Bot")
    return embed

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user.name}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.lower()

    if content.startswith("taskcreate"):
        task_name = message.content[len("taskcreate"):].strip()
        task = {
            "id": len(tasks) + 1,
            "name": task_name,
            "assigned_to": message.author.id,
            "done": False,
            "creator": message.author.id
        }
        tasks.append(task)
        save_tasks()
        embed = create_task_embed(task)
        await message.channel.send(f"📌 Task created and assigned to {message.author.mention}!", embed=embed)
        try:
            await message.author.send("📥 You created a new task:", embed=embed)
        except:
            pass

    elif content.startswith("tasklist"):
        if not tasks:
            await message.channel.send("📭 No tasks available.")
            return
        for task in tasks:
            embed = create_task_embed(task)
            await message.channel.send(embed=embed)

    elif content.startswith("taskassign"):
        try:
            parts = message.content.split()
            task_id = int(parts[1])
            user = message.mentions[0]
        except:
            await message.channel.send("⚠️ Usage: taskassign <task_id> @user")
            return

        for task in tasks:
            if task["id"] == task_id:
                task["assigned_to"] = user.id
                save_tasks()
                embed = create_task_embed(task)
                await message.channel.send(f"👤 Task #{task_id} assigned to {user.mention}", embed=embed)
                try:
                    await user.send("📥 A task was assigned to you:", embed=embed)
                except:
                    pass
                return
        await message.channel.send("❌ Task ID not found.")

    elif content.startswith("taskdone"):
        try:
            task_id = int(message.content.split()[1])
        except:
            await message.channel.send("⚠️ Usage: taskdone <task_id>")
            return

        for task in tasks:
            if task["id"] == task_id:
                if task["assigned_to"] != message.author.id and task["creator"] != message.author.id:
                    await message.channel.send("🚫 You can't mark this task done.")
                    return
                task["done"] = True
                save_tasks()
                embed = create_task_embed(task)
                await message.channel.send(f"✅ Task #{task_id} marked as done!", embed=embed)
                try:
                    await message.author.send("🎉 You marked a task as done:", embed=embed)
                except:
                    pass
                return
        await message.channel.send("❌ Task ID not found.")

    elif content.startswith("taskchart"):
        done = sum(1 for t in tasks if t["done"])
        pending = len(tasks) - done

        plt.figure(figsize=(5, 5))
        plt.pie([done, pending], labels=["Done", "Pending"], autopct="%1.1f%%", colors=["green", "orange"])
        plt.title("📊 Task Completion Chart")

        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        await message.channel.send("Here is the task chart:", file=discord.File(buf, "task_chart.png"))
        buf.close()

    await bot.process_commands(message)

from dotenv import load_dotenv
import os

load_dotenv()  # Works locally
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

