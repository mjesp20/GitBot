import discord
from discord.ext import commands, tasks
import os
import requests
import json
from dotenv import load_dotenv

# New imports
import threading
import pystray
from PIL import Image, ImageDraw
import win32gui
import win32con

# Store console window handle
CONSOLE_HWND = win32gui.GetForegroundWindow()

def hide_console():
    """Hide the console window."""
    win32gui.ShowWindow(CONSOLE_HWND, win32con.SW_HIDE)

def show_console():
    """Show the console window again."""
    win32gui.ShowWindow(CONSOLE_HWND, win32con.SW_SHOW)


def create_image():
    """Create a simple icon for tray."""
    img = Image.new('RGB', (64, 64), (40, 40, 40))
    d = ImageDraw.Draw(img)
    d.rectangle((16, 16, 48, 48), fill=(114, 137, 218))  # Discord-like purple
    return img

def setup_tray(bot_thread):
    def on_quit(icon, item):
        print("Shutting down bot...")
        os._exit(0)  # Force exit entire script

    def on_hide(icon, item):
        hide_console()

    def on_show(icon, item):
        show_console()

    icon = pystray.Icon("discord_bot")
    icon.icon = create_image()
    icon.title = "Discord Bot"
    icon.menu = pystray.Menu(
        pystray.MenuItem("Hide Console", on_hide),
        pystray.MenuItem("Show Console", on_show),
        pystray.MenuItem("Quit", on_quit)
    )

    icon.run()


load_dotenv()

# Configuration
TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OWNER =
REPO = 

# Channel IDs
ISSUES_CHANNEL_ID = 
PRS_CHANNEL_ID = 
BUILD_CHANNEL_ID= # todo maybe just do webhook?

# Storage file
STORAGE_FILE = "github_tracking.json"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def load_data():
    """Load tracking data from file"""
    try:
        with open(STORAGE_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"issues": {}, "prs": {}}

def save_data(data):
    """Save tracking data to file"""
    with open(STORAGE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_github_items(item_type):
    """Fetch issues or PRs from GitHub"""
    if item_type == "issues":
        # For issues, get from /issues endpoint and filter out PRs
        url = f"https://api.github.com/repos/{OWNER}/{REPO}/issues"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        
        try:
            response = requests.get(url, headers=headers, params={"state": "open"})
            if response.status_code == 200:
                items = response.json()
                # Filter out pull requests (they have a 'pull_request' key)
                return [item for item in items if 'pull_request' not in item]
            return []
        except Exception as e:
            print(f"Error fetching issues: {e}")
            return []
    else:
        # For PRs, use the /pulls endpoint
        url = f"https://api.github.com/repos/{OWNER}/{REPO}/pulls"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        
        try:
            response = requests.get(url, headers=headers, params={"state": "open"})
            return response.json() if response.status_code == 200 else []
        except Exception as e:
            print(f"Error fetching PRs: {e}")
            return []

def create_embed(item, item_type):
    """Create embed for issue or PR"""
    color = 0x28a745 if item_type == "issue" else 0x0366d6
    
    embed = discord.Embed(
        title=f"#{item['number']}: {item['title']}",
        url=item['html_url'],
        color=color,
        description=(item['body'][:200] + "...") if item['body'] and len(item['body']) > 200 else item['body']
    )
    
    embed.add_field(name="Author", value=item['user']['login'], inline=True)
    embed.add_field(name="Created", value=item['created_at'][:10], inline=True)
    
    if item.get('labels'):
        labels = [label['name'] for label in item['labels']]
        embed.add_field(name="Labels", value=", ".join(labels[:3]), inline=True)
    
    return embed

@bot.event
async def on_ready():
    print(f"Bot online as {bot.user}")
    update_channels.start()

@tasks.loop(minutes=5)
async def update_channels():
    """Update both channels with current open items"""
    print("Updating channels...")
    
    try:
        data = load_data()
        
        # Get channels
        issues_channel = bot.get_channel(ISSUES_CHANNEL_ID)
        prs_channel = bot.get_channel(PRS_CHANNEL_ID)
        
        if not issues_channel or not prs_channel:
            print("Could not find channels")
            return
        
        # Update issues
        await update_channel(issues_channel, "issues", data)
        
        # Update PRs  
        await update_channel(prs_channel, "prs", data)
        
        save_data(data)
        
    except Exception as e:
        print(f"Error updating channels: {e}")

async def update_channel(channel, item_type, data):
    """Update a single channel with current items"""
    # Get current items from GitHub
    github_items = get_github_items(item_type)
    current_numbers = {item['number'] for item in github_items}
    
    # Get tracked items
    tracked = data[item_type]
    tracked_numbers = set(map(int, tracked.keys()))
    
    # Remove closed items
    for num in tracked_numbers - current_numbers:
        message_id = tracked.pop(str(num))
        try:
            message = await channel.fetch_message(message_id)
            await message.delete()
            print(f"Removed closed {item_type[:-1]} #{num}")
        except:
            pass
    
    # Add new items
    for item in github_items:
        if str(item['number']) not in tracked:
            embed = create_embed(item, item_type[:-1])
            try:
                message = await channel.send(embed=embed)
                tracked[str(item['number'])] = message.id
                print(f"Added new {item_type[:-1]} #{item['number']}")
            except Exception as e:
                print(f"Error posting {item_type[:-1]} #{item['number']}: {e}")

@bot.command()
async def status(ctx):
    """Show current status"""
    data = load_data()
    embed = discord.Embed(title="GitHub Monitor Status", color=0x7289da)
    embed.add_field(name="Tracked Issues", value=len(data["issues"]), inline=True)
    embed.add_field(name="Tracked PRs", value=len(data["prs"]), inline=True)
    embed.add_field(name="Repository", value=f"{OWNER}/{REPO}", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def refresh(ctx):
    """Manually refresh channels"""
    await ctx.send("🔄 Refreshing channels...")
    await update_channels()
    await ctx.send("✅ Channels refreshed!")

@bot.command()
async def clear_tracking(ctx):
    """Clear all tracking data (useful for debugging)"""
    data = {"issues": {}, "prs": {}}
    save_data(data)
    await ctx.send("🗑️ Cleared all tracking data!")

if __name__ == "__main__":
    # Start bot in background thread
    def run_bot():
        bot.run(TOKEN)

    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # (Optional) hide console automatically at start
    hide_console()

    # Start tray
    setup_tray(bot_thread)
