import os
import sys
import re
import time
import signal
import subprocess
from fastapi import FastAPI
from threading import Thread
import telebot

app = FastAPI()
bot = telebot.TeleBot("7949052497:AAEZMEUiO7f8ntgZDcCYfVe19vRUKSu7KoQ", parse_mode="MarkdownV2")

running_bots = {}
user_bot_limits = {}
user_sessions = {}
bot_start_times = {}

DEFAULT_BOT_LIMIT = 1
BOT_FOLDER = "BotDeploy_Database"
OWNER_ID = 6067142319

if not os.path.exists(BOT_FOLDER):
    os.makedirs(BOT_FOLDER)

def validate_bot_name(name):
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", name))

def install_requirements(script_path):
    stdlib = set(sys.stdlib_module_names)
    with open(script_path, "r") as f:
        code = f.read()
    imports = [line.split()[1].split(".")[0] for line in code.split("\n") 
              if line.startswith(("import ", "from "))]
    for package in set(imports) - stdlib:
        subprocess.call(["pip", "install", package])

def launch_bot_process(chat_id, script_path, bot_name):
    try:
        install_requirements(script_path)
        process = subprocess.Popen(["python", script_path], 
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 text=True)
        
        if chat_id not in running_bots:
            running_bots[chat_id] = {}
        
        running_bots[chat_id][bot_name] = process
        bot_start_times[bot_name] = time.time()
        
        def monitor_process():
            while True:
                if process.poll() is not None:
                    error_output = process.stderr.read()
                    bot.send_message(chat_id, f"{bot_name} crashed!\n```\n{error_output}\n```")
                    running_bots[chat_id].pop(bot_name, None)
                    break
                time.sleep(5)
        
        Thread(target=monitor_process, daemon=True).start()
    except Exception as e:
        bot.send_message(chat_id, f"Startup failed: {str(e)}")

@bot.message_handler(commands=['start'])
def handle_start(message):
    welcome_msg = """
*Welcome to Bot Hosting Service!*
Host your Telegram bots instantly! Secure, and Reliable.

*Commands:*
/newbot - Create a new bot  
/mybots - View your hosted bots
/deletebot - Remove an existing bot  
/editbot - Modify an existing bot  
/cancel - Cancel any ongoing process

*Example*: (Simple Bot Script)
```py
import telebot
TOKEN = "MY_BOT_TOKEN" 
bot = telebot.TeleBot(TOKEN)
@bot.message_handler(commands=['start']) 
def say_hello(message): 
    bot.reply_to(message, "Hello from Hosting Service!")
bot.polling()
```
For support join @hostingsupport
"""
    bot.send_message(message.chat.id, welcome_msg)

@bot.message_handler(commands=['upgrade'])
def handle_upgrade(message):
    if message.from_user.id != OWNER_ID:
        bot.send_message(message.chat.id, "Unauthorized command.")
        return
    try:
        _, user_id, limit = message.text.split()
        user_bot_limits[int(user_id)] = int(limit)
        bot.send_message(message.chat.id, f"User {user_id} limit set to {limit}.")
    except:
        bot.send_message(message.chat.id, "Use /upgrade user-id number")

@bot.message_handler(commands=['cancel'])
def handle_cancel(message):
    chat_id = message.chat.id
    if chat_id in user_sessions:
        user_sessions.pop(chat_id)
        bot.send_message(chat_id, "Operation cancelled successfully.")
    else:
        bot.send_message(chat_id, "No operation to cancel.")

@bot.message_handler(commands=['newbot'])
def handle_newbot(message):
    chat_id = message.chat.id
    user_sessions[chat_id] = {"action": "newbot"}
    bot.send_message(chat_id, "Choose a name for your bot:")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get("action") == "newbot")
def process_bot_name(message):
    chat_id = message.chat.id
    bot_name = message.text.strip()
    
    if not validate_bot_name(bot_name):
        bot.send_message(chat_id, "Invalid name! Use only letters, numbers, underscores, hyphens.")
        return
    
    if chat_id not in user_bot_limits:
        user_bot_limits[chat_id] = DEFAULT_BOT_LIMIT
    
    if len(running_bots.get(chat_id, {})) >= user_bot_limits[chat_id]:
        bot.send_message(chat_id, "Bot limit reached! Contact for upgrade.")
        return
    
    user_sessions[chat_id] = {"action": "get_code", "bot_name": bot_name}
    bot.send_message(chat_id, f"Send the script for {bot_name} (text or .py file)")

@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    chat_id = message.chat.id
    if user_sessions.get(chat_id, {}).get("action") == "get_code":
        bot_name = user_sessions[chat_id]["bot_name"]
        
        if not message.document.file_name.endswith('.py'):
            bot.send_message(chat_id, "Only .py files accepted.")
            return
        
        file_info = bot.get_file(message.document.file_id)
        file_path = os.path.join(BOT_FOLDER, f"{bot_name}.py")
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(file_path, "wb") as f:
            f.write(downloaded_file)
        
        bot.send_message(chat_id, f"{bot_name} uploaded! Starting...")
        launch_bot_process(chat_id, file_path, bot_name)
        user_sessions.pop(chat_id, None)

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get("action") == "get_code")
def handle_code_input(message):
    chat_id = message.chat.id
    bot_name = user_sessions[chat_id]["bot_name"]
    script_path = os.path.join(BOT_FOLDER, f"{bot_name}.py")
    
    with open(script_path, "w") as f:
        f.write(message.text.strip())
    
    bot.send_message(chat_id, f"{bot_name} created! Starting...")
    launch_bot_process(chat_id, script_path, bot_name)
    user_sessions.pop(chat_id, None)

@bot.message_handler(commands=['mybots'])
def handle_mybots(message):
    chat_id = message.chat.id
    bots = running_bots.get(chat_id, {})
    
    if not bots:
        bot.send_message(chat_id, "No running bots. Create one with /newbot")
        return
    
    bot_list = []
    for name, process in bots.items():
        status = "Online" if process.poll() is None else "Offline"
        uptime = time.time() - bot_start_times.get(name, time.time())
        uptime_str = time.strftime("%H:%M:%S", time.gmtime(uptime))
        bot_list.append(f"**Bot:** {name}\n**Status:** {status}\n**Uptime:** {uptime_str}")
    
    bot.send_message(chat_id, "\n\n".join(bot_list))

@bot.message_handler(commands=['deletebot'])
def handle_deletebot(message):
    chat_id = message.chat.id
    user_sessions[chat_id] = {"action": "deletebot"}
    bot.send_message(chat_id, "Enter bot name to delete:")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get("action") == "deletebot")
def process_bot_deletion(message):
    chat_id = message.chat.id
    bot_name = message.text.strip()
    
    if bot_name not in running_bots.get(chat_id, {}):
        bot.send_message(chat_id, "Bot not found.")
        return
    
    process = running_bots[chat_id].pop(bot_name)
    if process.poll() is None:
        os.kill(process.pid, signal.SIGTERM)
    
    script_path = os.path.join(BOT_FOLDER, f"{bot_name}.py")
    if os.path.exists(script_path):
        os.remove(script_path)
    
    bot.send_message(chat_id, f"Bot {bot_name} deleted.")
    user_sessions.pop(chat_id, None)

@bot.message_handler(commands=['editbot'])
def handle_editbot(message):
    chat_id = message.chat.id
    user_sessions[chat_id] = {"action": "editbot"}
    bot.send_message(chat_id, "Enter bot name to edit:")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get("action") == "editbot")
def process_edit_request(message):
    chat_id = message.chat.id
    bot_name = message.text.strip()
    
    if bot_name not in running_bots.get(chat_id, {}):
        bot.send_message(chat_id, "Bot not found.")
        return
    
    script_path = os.path.join(BOT_FOLDER, f"{bot_name}.py")
    bot.send_document(chat_id, open(script_path, "rb"))
    user_sessions[chat_id] = {"action": "update_code", "bot_name": bot_name}
    bot.send_message(chat_id, f"Send updated code for {bot_name}")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get("action") == "update_code")
def update_bot_script(message):
    chat_id = message.chat.id
    bot_name = user_sessions[chat_id]["bot_name"]
    script_path = os.path.join(BOT_FOLDER, f"{bot_name}.py")
    
    with open(script_path, "w") as f:
        f.write(message.text.strip())
    
    bot.send_message(chat_id, f"{bot_name} updated! Restarting...")
    launch_bot_process(chat_id, script_path, bot_name)
    user_sessions.pop(chat_id, None)

@bot.message_handler(func=lambda msg: True)
def handle_default(message):
    chat_id = message.chat.id
    if chat_id not in user_sessions and not running_bots.get(chat_id, {}):
        handle_start(message)

@app.get("/")
def health_check():
    return {"status": "Bot Hosting Service is running"}

def run_bot():
    bot.infinity_polling()

Thread(target=run_bot).start()
