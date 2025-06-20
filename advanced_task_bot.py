import discord
from discord.ext import commands, tasks
import json, os, io, re
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from typing import Optional, Union

# ———————————— SETUP ————————————
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
PREFIXES = ("!", "t?", "/")  # Multiple command prefixes
STATUS_CHANNEL = "bot-commands"

# ———————————— DISCORD BOT ————————————
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIXES, intents=intents, case_insensitive=True)

# ———————————— DATA STORAGE ————————————
os.makedirs("data", exist_ok=True)
TASKS_FILE = "data/tasks.json"
TEAMS_FILE = "data/teams.json"

def load_data(file):
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump([] if "tasks" in file else {}, f)
    with open(file, "r") as f:
        return json.load(f)

def save_data(data, file):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

# ———————————— TASK & TEAM FUNCTIONS ————————————
def get_next_task_id():
    tasks = load_data(TASKS_FILE)
    return max([t["id"] for t in tasks] or [0]) + 1

def create_task_embed(task):
    status = "✅ Done" if task["done"] else "⏳ Pending"
    priority_colors = {"high": 0xff0000, "medium": 0xffa500, "low": 0x00ff00}
    
    embed = discord.Embed(
        title=f"📋 Task #{task['id']} – {task['name']}",
        description=task["description"],
        color=priority_colors.get(task.get("priority", "medium"), 0x00ffcc),
        timestamp=datetime.strptime(task["created_at"], "%Y-%m-%d %H:%M:%S") if "created_at" in task else None
    )
    
    embed.add_field(name="🔘 Status", value=status, inline=True)
    embed.add_field(name="🔝 Priority", value=task.get("priority", "medium").capitalize(), inline=True)
    embed.add_field(name="👤 Assigned", value=f"<@{task['assigned_to']}>", inline=True)
    
    if "deadline" in task:
        embed.add_field(name="⏰ Deadline", value=task["deadline"], inline=True)
    
    if "team" in task:
        embed.add_field(name="👥 Team", value=task["team"], inline=True)
    
    embed.set_footer(text=f"Created by {task.get('created_by', 'Unknown')}")
    return embed

def create_team_embed(team_name, team_data):
    embed = discord.Embed(
        title=f"👥 Team: {team_name}",
        color=0x7289da
    )
    
    leader = f"<@{team_data['leader']}>" if "leader" in team_data else "Not assigned"
    embed.add_field(name="👑 Leader", value=leader, inline=False)
    
    members = "\n".join([f"<@{member_id}>" for member_id in team_data.get("members", [])])
    embed.add_field(name="👤 Members", value=members or "No members", inline=False)
    
    if "description" in team_data:
        embed.add_field(name="📝 Description", value=team_data["description"], inline=False)
    
    return embed

# ———————————— BOT EVENTS ————————————
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"your tasks | {PREFIXES[0]}help"))

    if not alive_loop.is_running():
        alive_loop.start()
    if not daily_task_report.is_running():
        daily_task_report.start()

# ———————————— BACKGROUND TASKS ————————————
@tasks.loop(minutes=10)
async def alive_loop():
    """Regular status update to show the bot is alive"""
    guild = bot.get_guild(GUILD_ID)
    if not guild: return
    
    channel = discord.utils.get(guild.text_channels, name=STATUS_CHANNEL)
    if not channel:
        channel = await guild.create_text_channel(STATUS_CHANNEL)
    await channel.send("🤖 I'm alive and running 24/7! 🌟")

@tasks.loop(hours=24)
async def daily_task_report():
    """Daily report of pending tasks"""
    guild = bot.get_guild(GUILD_ID)
    if not guild: return
    
    tasks = load_data(TASKS_FILE)
    pending_tasks = [t for t in tasks if not t["done"]]
    
    if not pending_tasks: return
    
    # Group tasks by assigned user
    tasks_by_user = {}
    for task in pending_tasks:
        user_id = task["assigned_to"]
        if user_id not in tasks_by_user:
            tasks_by_user[user_id] = []
        tasks_by_user[user_id].append(task)
    
    # Send DM reminders
    for user_id, user_tasks in tasks_by_user.items():
        embed = discord.Embed(
            title="📅 Daily Task Reminder",
            description=f"You have {len(user_tasks)} pending task(s)",
            color=0xffa500
        )
        
        for task in user_tasks[:5]:  # Show up to 5 tasks
            deadline = f" (⏰ {task['deadline']})" if "deadline" in task else ""
            embed.add_field(
                name=f"#{task['id']} - {task['name']}{deadline}",
                value=task["description"][:100] + ("..." if len(task["description"]) > 100 else ""),
                inline=False
            )
        
        if len(user_tasks) > 5:
            embed.set_footer(text=f"+ {len(user_tasks) - 5} more tasks...")
        
        try:
            member = await guild.fetch_member(user_id)
            await member.send(embed=embed)
        except:
            continue  # Skip if user can't be DM'd

# ———————————— TASK COMMANDS ————————————
@bot.command(name="taskcreate", aliases=["createtask", "addtask", "newtask"])
async def task_create(ctx, *, args: str = None):
    """
    Create a new task
    Usage: !taskcreate "Title" --desc "Description" [--priority high/medium/low] [--deadline YYYY-MM-DD] [--team TeamName]
    """
    if not args or "--desc" not in args:
        embed = discord.Embed(
            title="❌ Invalid Syntax",
            description=f"Usage: `{ctx.prefix}taskcreate \"Title\" --desc \"Description\" [--priority high/medium/low] [--deadline YYYY-MM-DD] [--team TeamName]`",
            color=0xff0000
        )
        return await ctx.send(embed=embed)
    
    # Parse arguments
    parts = args.split("--")
    title_part = parts[0].strip().strip('"')
    
    # Extract parameters
    params = {}
    for part in parts[1:]:
        if " " in part:
            key, value = part.split(" ", 1)
            params[key.strip()] = value.strip().strip('"')
    
    # Validate required fields
    if "desc" not in params:
        return await ctx.send("❌ Description is required (use --desc)")
    
    # Set default values
    priority = params.get("priority", "medium").lower()
    if priority not in ["high", "medium", "low"]:
        priority = "medium"
    
    # Create task object
    task = {
        "id": get_next_task_id(),
        "name": title_part,
        "description": params["desc"],
        "assigned_to": ctx.author.id,
        "done": False,
        "priority": priority,
        "created_by": str(ctx.author),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Optional fields
    if "deadline" in params:
        task["deadline"] = params["deadline"]
    
    if "team" in params:
        teams = load_data(TEAMS_FILE)
        if params["team"] in teams:
            task["team"] = params["team"]
            # Auto-assign to team leader if exists
            if "leader" in teams[params["team"]]:
                task["assigned_to"] = teams[params["team"]]["leader"]
    
    # Save task
    tasks = load_data(TASKS_FILE)
    tasks.append(task)
    save_data(tasks, TASKS_FILE)
    
    await ctx.send(f"📌 Task created:", embed=create_task_embed(task))

@bot.command(name="tasklist", aliases=["listtasks", "tasks", "mytasks"])
async def task_list(ctx, filter: Optional[str] = None):
    """
    List all tasks or filter by status/team
    Usage: !tasklist [all/done/pending/team:TeamName]
    """
    tasks = load_data(TASKS_FILE)
    
    if not tasks:
        return await ctx.send("📭 No tasks found.")
    
    # Apply filters
    if filter:
        filter = filter.lower()
        if filter == "done":
            tasks = [t for t in tasks if t["done"]]
        elif filter == "pending":
            tasks = [t for t in tasks if not t["done"]]
        elif filter.startswith("team:"):
            team_name = filter[5:]
            tasks = [t for t in tasks if t.get("team") == team_name]
        elif filter == "all":
            pass  # Show all tasks
        else:
            tasks = [t for t in tasks if t["assigned_to"] == ctx.author.id or filter in t["name"].lower()]
    
    # Paginate if too many tasks
    if len(tasks) > 10:
        chunks = [tasks[i:i + 10] for i in range(0, len(tasks), 10)]
        for chunk in chunks:
            for task in chunk:
                await ctx.send(embed=create_task_embed(task))
            await ctx.send(f"📄 Page {chunks.index(chunk) + 1}/{len(chunks)}")
    else:
        for task in tasks:
            await ctx.send(embed=create_task_embed(task))

@bot.command(name="taskdone", aliases=["donetask", "completetask", "finishtask"])
async def task_done(ctx, task_id: int):
    """Mark a task as done"""
    tasks = load_data(TASKS_FILE)
    
    for task in tasks:
        if task["id"] == task_id:
            if task["assigned_to"] == ctx.author.id or ctx.author.guild_permissions.manage_messages:
                task["done"] = True
                task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                save_data(tasks, TASKS_FILE)
                
                # Send notification to task creator if different from completer
                if str(task.get("created_by", "")) != str(ctx.author):
                    try:
                        creator = await ctx.guild.fetch_member(int(re.search(r'\d+', task["created_by"]).group()))
                        await creator.send(f"🎉 Your task #{task_id} '{task['name']}' was completed by {ctx.author.mention}!")
                    except:
                        pass
                
                return await ctx.send(f"✅ Task marked as done!", embed=create_task_embed(task))
            else:
                return await ctx.send("❌ You can only mark your own tasks as done.")
    
    await ctx.send("❌ Task not found.")

@bot.command(name="taskassign", aliases=["assigntask", "reassigntask"])
async def task_assign(ctx, task_id: int, user: discord.Member):
    """Reassign a task to another user"""
    tasks = load_data(TASKS_FILE)
    
    for task in tasks:
        if task["id"] == task_id:
            # Check permissions: original assignee, task creator, or admin
            if (task["assigned_to"] == ctx.author.id or 
                str(task.get("created_by", "")) == str(ctx.author) or 
                ctx.author.guild_permissions.manage_messages):
                
                task["assigned_to"] = user.id
                save_data(tasks, TASKS_FILE)
                
                # Notify the new assignee
                try:
                    await user.send(f"📌 You've been assigned a new task: #{task_id} '{task['name']}'")
                except:
                    pass
                
                return await ctx.send(f"👤 Task reassigned to {user.mention}", embed=create_task_embed(task))
            else:
                return await ctx.send("❌ You don't have permission to reassign this task.")
    
    await ctx.send("❌ Task not found.")

@bot.command(name="taskdelete", aliases=["deletetask", "removetask"])
async def task_delete(ctx, task_id: int):
    """Delete a task"""
    tasks = load_data(TASKS_FILE)
    
    for task in tasks:
        if task["id"] == task_id:
            # Check permissions: task creator or admin
            if str(task.get("created_by", "")) == str(ctx.author) or ctx.author.guild_permissions.manage_messages:
                tasks = [t for t in tasks if t["id"] != task_id]
                save_data(tasks, TASKS_FILE)
                return await ctx.send(f"🗑️ Task #{task_id} deleted.")
            else:
                return await ctx.send("❌ You can only delete tasks you created.")
    
    await ctx.send("❌ Task not found.")

@bot.command(name="taskupdate", aliases=["updatetask", "modifytask"])
async def task_update(ctx, task_id: int, *, args: str):
    """
    Update task details
    Usage: !taskupdate <id> --name "New Name" --desc "New Desc" --priority high --deadline 2023-12-31
    """
    tasks = load_data(TASKS_FILE)
    
    for task in tasks:
        if task["id"] == task_id:
            # Check permissions
            if not (task["assigned_to"] == ctx.author.id or 
                   str(task.get("created_by", "")) == str(ctx.author) or 
                   ctx.author.guild_permissions.manage_messages):
                return await ctx.send("❌ You don't have permission to modify this task.")
            
            # Parse update parameters
            parts = args.split("--")
            updates = {}
            for part in parts[1:]:
                if " " in part:
                    key, value = part.split(" ", 1)
                    updates[key.strip()] = value.strip().strip('"')
            
            # Apply updates
            if "name" in updates:
                task["name"] = updates["name"]
            if "desc" in updates:
                task["description"] = updates["desc"]
            if "priority" in updates:
                if updates["priority"].lower() in ["high", "medium", "low"]:
                    task["priority"] = updates["priority"].lower()
            if "deadline" in updates:
                task["deadline"] = updates["deadline"]
            if "team" in updates:
                teams = load_data(TEAMS_FILE)
                if updates["team"] in teams:
                    task["team"] = updates["team"]
            
            task["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_data(tasks, TASKS_FILE)
            
            return await ctx.send(f"🔄 Task updated:", embed=create_task_embed(task))
    
    await ctx.send("❌ Task not found.")

@bot.command(name="taskchart", aliases=["taskstats", "taskreport"])
async def task_chart(ctx, timeframe: str = "all"):
    """Generate a visual report of task completion"""
    tasks = load_data(TASKS_FILE)
    
    # Filter by timeframe if specified
    if timeframe != "all":
        now = datetime.now()
        if timeframe == "week":
            cutoff = now - timedelta(weeks=1)
        elif timeframe == "month":
            cutoff = now - timedelta(days=30)
        elif timeframe == "year":
            cutoff = now - timedelta(days=365)
        else:
            return await ctx.send("❌ Invalid timeframe. Use week/month/year/all")
        
        tasks = [t for t in tasks if 
                datetime.strptime(t["created_at"], "%Y-%m-%d %H:%M:%S") > cutoff or
                ("completed_at" in t and datetime.strptime(t["completed_at"], "%Y-%m-%d %H:%M:%S") > cutoff)]
    
    if not tasks:
        return await ctx.send("📭 No tasks to display.")
    
    # Calculate statistics
    done = sum(1 for t in tasks if t["done"])
    pending = len(tasks) - done
    
    # Priority breakdown
    priorities = {"high": 0, "medium": 0, "low": 0}
    for t in tasks:
        priorities[t.get("priority", "medium")] += 1
    
    # Create figure with multiple subplots
    plt.figure(figsize=(12, 8))
    
    # Task completion pie chart
    plt.subplot(2, 2, 1)
    plt.pie([done, pending], 
            labels=["Done", "Pending"], 
            autopct="%1.1f%%",
            colors=["#4CAF50", "#FF9800"])
    plt.title("Task Completion")
    
    # Priority distribution pie chart
    plt.subplot(2, 2, 2)
    plt.pie([priorities["high"], priorities["medium"], priorities["low"]],
            labels=["High", "Medium", "Low"],
            autopct="%1.1f%%",
            colors=["#F44336", "#FFC107", "#8BC34A"])
    plt.title("Priority Distribution")
    
    # Completion over time (if enough data)
    if len(tasks) > 5 and any("completed_at" in t for t in tasks):
        plt.subplot(2, 1, 2)
        dates = []
        completed = []
        for t in tasks:
            if "completed_at" in t:
                date = datetime.strptime(t["completed_at"], "%Y-%m-%d %H:%M:%S").date()
                dates.append(date)
                completed.append(1)
        
        if dates and completed:
            unique_dates = sorted(list(set(dates)))
            daily_completed = [completed.count(d) for d in unique_dates]
            plt.plot(unique_dates, daily_completed, marker="o")
            plt.title("Completion Over Time")
            plt.xlabel("Date")
            plt.ylabel("Tasks Completed")
            plt.grid(True)
    
    plt.tight_layout()
    
    # Save to buffer and send
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100)
    buf.seek(0)
    await ctx.send(file=discord.File(buf, "task_report.png"))
    plt.close()

# ———————————— TEAM COMMANDS ————————————
@bot.command(name="teamcreate", aliases=["createteam", "addteam"])
async def team_create(ctx, team_name: str, *, description: str = None):
    """Create a new team"""
    teams = load_data(TEAMS_FILE)
    
    if team_name in teams:
        return await ctx.send("❌ A team with that name already exists.")
    
    teams[team_name] = {
        "leader": ctx.author.id,
        "members": [ctx.author.id],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "created_by": str(ctx.author)
    }
    
    if description:
        teams[team_name]["description"] = description
    
    save_data(teams, TEAMS_FILE)
    await ctx.send(f"👥 Team '{team_name}' created!", embed=create_team_embed(team_name, teams[team_name]))

@bot.command(name="teamadd", aliases=["addmember", "teaminvite"])
async def team_add(ctx, team_name: str, member: discord.Member):
    """Add a member to a team"""
    teams = load_data(TEAMS_FILE)
    
    if team_name not in teams:
        return await ctx.send("❌ Team not found.")
    
    # Check if user is team leader or admin
    if teams[team_name]["leader"] != ctx.author.id and not ctx.author.guild_permissions.manage_messages:
        return await ctx.send("❌ Only the team leader can add members.")
    
    if member.id in teams[team_name]["members"]:
        return await ctx.send("❌ Member is already in the team.")
    
    teams[team_name]["members"].append(member.id)
    save_data(teams, TEAMS_FILE)
    
    # Notify the new member
    try:
        await member.send(f"🎉 You've been added to team '{team_name}'!")
    except:
        pass
    
    await ctx.send(f"👤 {member.mention} added to team '{team_name}'!", 
                  embed=create_team_embed(team_name, teams[team_name]))

@bot.command(name="teamremove", aliases=["removemember", "teamkick"])
async def team_remove(ctx, team_name: str, member: discord.Member):
    """Remove a member from a team"""
    teams = load_data(TEAMS_FILE)
    
    if team_name not in teams:
        return await ctx.send("❌ Team not found.")
    
    # Check if user is team leader or admin
    if teams[team_name]["leader"] != ctx.author.id and not ctx.author.guild_permissions.manage_messages:
        return await ctx.send("❌ Only the team leader can remove members.")
    
    if member.id not in teams[team_name]["members"]:
        return await ctx.send("❌ Member is not in this team.")
    
    # Prevent removing the leader
    if member.id == teams[team_name]["leader"]:
        return await ctx.send("❌ Use !teamleader to transfer leadership first.")
    
    teams[team_name]["members"].remove(member.id)
    save_data(teams, TEAMS_FILE)
    
    # Notify the removed member
    try:
        await member.send(f"ℹ️ You've been removed from team '{team_name}'")
    except:
        pass
    
    await ctx.send(f"👤 {member.mention} removed from team '{team_name}'", 
                  embed=create_team_embed(team_name, teams[team_name]))

@bot.command(name="teamleader", aliases=["setleader", "transferleadership"])
async def team_leader(ctx, team_name: str, new_leader: discord.Member):
    """Transfer team leadership"""
    teams = load_data(TEAMS_FILE)
    
    if team_name not in teams:
        return await ctx.send("❌ Team not found.")
    
    # Check if user is current team leader or admin
    if teams[team_name]["leader"] != ctx.author.id and not ctx.author.guild_permissions.manage_messages:
        return await ctx.send("❌ Only the current team leader can transfer leadership.")
    
    if new_leader.id not in teams[team_name]["members"]:
        return await ctx.send("❌ New leader must be a team member.")
    
    teams[team_name]["leader"] = new_leader.id
    save_data(teams, TEAMS_FILE)
    
    # Notify the new leader
    try:
        await new_leader.send(f"👑 You are now the leader of team '{team_name}'!")
    except:
        pass
    
    await ctx.send(f"👑 Team leadership transferred to {new_leader.mention}!", 
                  embed=create_team_embed(team_name, teams[team_name]))

@bot.command(name="teamdelete", aliases=["deleteteam", "removeteam"])
async def team_delete(ctx, team_name: str):
    """Delete a team"""
    teams = load_data(TEAMS_FILE)
    
    if team_name not in teams:
        return await ctx.send("❌ Team not found.")
    
    # Check if user is team leader or admin
    if teams[team_name]["leader"] != ctx.author.id and not ctx.author.guild_permissions.manage_messages:
        return await ctx.send("❌ Only the team leader can delete the team.")
    
    # Confirm deletion
    confirm_embed = discord.Embed(
        title="⚠️ Confirm Team Deletion",
        description=f"Are you sure you want to delete the team '{team_name}'? This action cannot be undone.",
        color=0xffcc00
    )
    confirm_embed.set_footer(text="Type 'confirm' to proceed or anything else to cancel.")
    
    await ctx.send(embed=confirm_embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
    except:
        return await ctx.send("🕒 Deletion timed out.")
    
    if msg.content.lower() != "confirm":
        return await ctx.send("❌ Team deletion cancelled.")
    
    # Remove team and reassign any team tasks
    tasks = load_data(TASKS_FILE)
    for task in tasks:
        if task.get("team") == team_name:
            task["team"] = None
    
    del teams[team_name]
    save_data(teams, TEAMS_FILE)
    save_data(tasks, TASKS_FILE)
    
    await ctx.send(f"🗑️ Team '{team_name}' has been deleted.")

@bot.command(name="teaminfo", aliases=["teamview", "showteam"])
async def team_info(ctx, team_name: str):
    """Show information about a team"""
    teams = load_data(TEAMS_FILE)
    
    if team_name not in teams:
        return await ctx.send("❌ Team not found.")
    
    await ctx.send(embed=create_team_embed(team_name, teams[team_name]))

@bot.command(name="teamlist", aliases=["listteams", "teams"])
async def team_list(ctx):
    """List all teams"""
    teams = load_data(TEAMS_FILE)
    
    if not teams:
        return await ctx.send("📭 No teams found.")
    
    embed = discord.Embed(
        title="👥 All Teams",
        description=f"Total teams: {len(teams)}",
        color=0x7289da
    )
    
    for team_name, team_data in teams.items():
        leader = f"<@{team_data['leader']}>" if "leader" in team_data else "Not assigned"
        members = len(team_data.get("members", []))
        embed.add_field(
            name=team_name,
            value=f"👑 Leader: {leader}\n👤 Members: {members}",
            inline=True
        )
    
    await ctx.send(embed=embed)

# ———————————— USER COMMANDS ————————————
@bot.command(name="userprofile", aliases=["profile", "myprofile"])
async def user_profile(ctx, user: Optional[discord.Member] = None):
    """Show a user's profile and task statistics"""
    user = user or ctx.author
    tasks = load_data(TASKS_FILE)
    
    user_tasks = [t for t in tasks if t["assigned_to"] == user.id]
    completed = sum(1 for t in user_tasks if t["done"])
    pending = len(user_tasks) - completed
    
    # Calculate completion rate (avoid division by zero)
    completion_rate = (completed / len(user_tasks)) * 100 if user_tasks else 0
    
    embed = discord.Embed(
        title=f"👤 {user.display_name}'s Profile",
        color=user.color
    )
    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
    
    embed.add_field(name="📊 Task Stats", 
                   value=f"✅ Completed: {completed}\n⏳ Pending: {pending}\n📈 Completion: {completion_rate:.1f}%", 
                   inline=True)
    
    # Show teams the user is in
    teams = load_data(TEAMS_FILE)
    user_teams = []
    leader_teams = []
    
    for team_name, team_data in teams.items():
        if user.id in team_data.get("members", []):
            user_teams.append(team_name)
        if team_data.get("leader") == user.id:
            leader_teams.append(team_name)
    
    if user_teams:
        embed.add_field(name="👥 Member of", value="\n".join(user_teams), inline=True)
    if leader_teams:
        embed.add_field(name="👑 Leader of", value="\n".join(leader_teams), inline=True)
    
    # Show recent tasks if any
    if user_tasks:
        recent_tasks = sorted(user_tasks, key=lambda x: x.get("created_at", ""), reverse=True)[:3]
        task_list = []
        for t in recent_tasks:
            status = "✅" if t["done"] else "⏳"
            task_list.append(f"{status} #{t['id']} - {t['name']}")
        
        embed.add_field(name="📋 Recent Tasks", value="\n".join(task_list), inline=False)
    
    await ctx.send(embed=embed)

# ———————————— HELP COMMAND ————————————
@bot.command(name="taskhelp", aliases=["commands", "bothelp"])
async def help_command(ctx, command: str = None):
    """Show help information"""
    if command:
        # Show specific command help
        cmd = bot.get_command(command.lower())
        if not cmd:
            return await ctx.send(f"❌ Command '{command}' not found.")
        
        embed = discord.Embed(
            title=f"🛠️ {cmd.name.capitalize()} Command",
            description=cmd.help or "No description available",
            color=0x00ffcc
        )
        
        if cmd.aliases:
            embed.add_field(name="🔤 Aliases", value=", ".join(cmd.aliases), inline=False)
        
        await ctx.send(embed=embed)
    else:
        # Show general help
        embed = discord.Embed(
            title="🛠️ Task Manager Bot Help",
            description=f"Prefixes: {', '.join(PREFIXES)}\nUse `{ctx.prefix}taskhelp <command>` for more info",
            color=0x00ffcc
        )
        
        # Task commands
        task_commands = [
            ("📋 Task Management", [
                f"`{ctx.prefix}taskcreate \"Title\" --desc \"Description\"` - Create new task",
                f"`{ctx.prefix}tasklist [filter]` - List tasks (all/done/pending/team:name)",
                f"`{ctx.prefix}taskdone <id>` - Mark task as done",
                f"`{ctx.prefix}taskassign <id> @user` - Reassign task",
                f"`{ctx.prefix}taskupdate <id> --param value` - Update task details",
                f"`{ctx.prefix}taskdelete <id>` - Delete task",
                f"`{ctx.prefix}taskchart [timeframe]` - Generate task statistics"
            ]),
            ("👥 Team Management", [
                f"`{ctx.prefix}teamcreate <name> [desc]` - Create new team",
                f"`{ctx.prefix}teamadd <team> @user` - Add member to team",
                f"`{ctx.prefix}teamremove <team> @user` - Remove member",
                f"`{ctx.prefix}teamleader <team> @user` - Transfer leadership",
                f"`{ctx.prefix}teaminfo <team>` - View team info",
                f"`{ctx.prefix}teamlist` - List all teams",
                f"`{ctx.prefix}teamdelete <team>` - Delete team"
            ]),
            ("👤 User Commands", [
                f"`{ctx.prefix}profile [@user]` - View user profile",
                f"`{ctx.prefix}taskhelp [command]` - Show this help"
            ])
        ]
        
        for category, commands_list in task_commands:
            embed.add_field(
                name=category,
                value="\n".join(commands_list),
                inline=False
            )
        
        await ctx.send(embed=embed)

# ———————————— ERROR HANDLING ————————————
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Command not found. Use `{ctx.prefix}taskhelp` for available commands.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param.name}\nUse `{ctx.prefix}taskhelp {ctx.command.name}` for usage.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Invalid argument: {str(error)}\nUse `{ctx.prefix}taskhelp {ctx.command.name}` for usage.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    else:
        await ctx.send(f"⚠️ An error occurred: {str(error)}")
        raise error  # Re-raise the error for logging

# ———————————— RUN THE BOT ————————————
if __name__ == "__main__":
    bot.run(TOKEN)
