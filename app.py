import os
import sys
import telebot
import subprocess
import signal
import re
import time
from config import BOT_TOKEN, OWNER_ID
from telebot.formatting import escape_markdown

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
running_bots = {}
user_bot_limits = {}
user_sessions = {}
bot_start_times = {}

DEFAULT_BOT_LIMIT = 1
BOT_FOLDER = "nigga"

if not os.path.exists(BOT_FOLDER):
    os.makedirs(BOT_FOLDER)

def is_valid_bot_name(name):
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", name))

@bot.message_handler(commands=['start'])
def send_help(message):
    help_text = """*Welcome to Bot Hosting Service!*
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
    bot.reply_to(message, "Hello, I'm Created by Starexx!")

bot.polling()
```
*Note*: if you find any bugs then contact us and please provide the code in only one file, for any assistance! please join **@starexxchat** for support!
"""
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(commands=['upgrade'])
def set_user_limit(message):
    if message.from_user.id != OWNER_ID:
        bot.send_message(message.chat.id, "You are not authorized to use this command.")
        return

    try:
        _, user_id, limit = message.text.split()
        user_id, limit = int(user_id), int(limit)
        user_bot_limits[user_id] = limit
        bot.send_message(message.chat.id, f"User {user_id} bot limit set to {limit}.")
    except:
        bot.send_message(message.chat.id, "Invalid format! Use /upgrade user-id num.")

@bot.message_handler(commands=['cancel'])
def cancel_action(message):
    chat_id = message.chat.id
    if chat_id in user_sessions:
        user_sessions.pop(chat_id)
        bot.send_message(chat_id, "Operation Cancelled Successfully, no changes were made and all previous settings remain Intact and unaffected")
    else:
        bot.send_message(chat_id, "No ongoing operation to cancel, all actions are currently idle")

@bot.message_handler(commands=['newbot'])
def new_bot(message):
    chat_id = message.chat.id
    user_sessions[chat_id] = {"action": "newbot"}
    bot.send_message(chat_id, "Alright, a new bot. How are we going to call it? Please choose a name for your bot.")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get("action") == "newbot")
def receive_bot_name(message):
    chat_id = message.chat.id
    bot_name = message.text.strip()
    if not is_valid_bot_name(bot_name):
        bot.send_message(chat_id, "Invalid bot name! Only letters, numbers, underscores, and hyphens are allowed.")
        return

    if chat_id not in user_bot_limits:
        user_bot_limits[chat_id] = DEFAULT_BOT_LIMIT

    if len(running_bots.get(chat_id, {})) >= user_bot_limits[chat_id]:
        bot.send_message(chat_id, "Bot limit reached! Contact owner to upgrade your plan to create more bots.")
        return

    user_sessions[chat_id] = {"action": "get_code", "bot_name": bot_name}
    bot.send_message(chat_id, f"Send the bot script for {escape_markdown(bot_name)} (as text or file)")

@bot.message_handler(content_types=['document'])
def receive_bot_file(message):
    chat_id = message.chat.id
    if user_sessions.get(chat_id, {}).get("action") == "get_code":
        bot_name = user_sessions[chat_id]["bot_name"]
        file_info = bot.get_file(message.document.file_id)
        file_path = os.path.join(BOT_FOLDER, f"{bot_name}.py")

        if not message.document.file_name.endswith('.py'):
            bot.send_message(chat_id, "Please upload a valid Python script (.py file).")
            return

        downloaded_file = bot.download_file(file_info.file_path)
        with open(file_path, "wb") as f:
            f.write(downloaded_file)

        bot.send_message(chat_id, f"{escape_markdown(bot_name)} uploaded successfully! Bot is running...")
        start_script(chat_id, file_path, bot_name)
        user_sessions.pop(chat_id, None)

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get("action") == "get_code")
def receive_bot_code(message):
    chat_id = message.chat.id
    bot_code = message.text.strip()
    bot_name = user_sessions[chat_id]["bot_name"]
    script_path = os.path.join(BOT_FOLDER, f"{bot_name}.py")

    with open(script_path, "w") as f:
        f.write(bot_code)

    bot.send_message(chat_id, f"{escape_markdown(bot_name)} created successfully! Bot is running...")
    start_script(chat_id, script_path, bot_name)
    user_sessions.pop(chat_id, None)

def start_script(chat_id, script_path, bot_name):
    try:
        install_dependencies(script_path)
        process = subprocess.Popen(["python", script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if chat_id not in running_bots:
            running_bots[chat_id] = {}

        running_bots[chat_id][bot_name] = process
        bot_start_times[bot_name] = time.time()
        
        def monitor_process():
            while True:
                if process.poll() is not None:
                    error_log = process.stderr.read()
                    bot.send_message(chat_id, f"{escape_markdown(bot_name)} has been crashed! Logs:\n```\n{error_log}\n```")
                    running_bots[chat_id].pop(bot_name, None)
                    break
                time.sleep(5)
        import threading
        threading.Thread(target=monitor_process, daemon=True).start()

    except Exception as e:
        bot.send_message(chat_id, f"Failed to start bot: {e}")

@bot.message_handler(commands=['mybots'])
def my_bots(message):
    chat_id = message.chat.id
    bots = running_bots.get(chat_id, {})

    if not bots:
        bot.send_message(chat_id, "Currently, you do not have any running bots. please create bot /newbot.")
        return

    bot_info = []
    for name, process in bots.items():
        status = "Online" if process.poll() is None else "Offline"
        uptime = time.time() - bot_start_times.get(name, time.time())
        uptime_str = time.strftime("%H:%M:%S", time.gmtime(uptime))

        bot_info.append(f"**Name:** {escape_markdown(name)}\n**Owner:** {escape_markdown(message.chat.first_name)}\n**Running for:** {uptime_str}\n**Status:** {status}")

    bot.send_message(chat_id, "\n\n".join(bot_info))

@bot.message_handler(commands=['deletebot'])
def delete_bot(message):
    chat_id = message.chat.id
    user_sessions[chat_id] = {"action": "deletebot"}
    bot.send_message(chat_id, "Please enter the exact name of the bot you wish to permanently delete and remove")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get("action") == "deletebot")
def confirm_delete_bot(message):
    chat_id = message.chat.id
    bot_name = message.text.strip()
    if bot_name not in running_bots.get(chat_id, {}):
        bot.send_message(chat_id, "Sorry, no bot exists with the specified name. please verify and try again.")
        return

    process = running_bots[chat_id].pop(bot_name)
    if process.poll() is None:
        os.kill(process.pid, signal.SIGTERM)

    script_path = os.path.join(BOT_FOLDER, f"{bot_name}.py")
    if os.path.exists(script_path):
        os.remove(script_path)

    bot.send_message(chat_id, f"The bot, {escape_markdown(bot_name)} has been deleted.")
    user_sessions.pop(chat_id, None)

@bot.message_handler(commands=['editbot'])
def edit_bot(message):
    chat_id = message.chat.id
    user_sessions[chat_id] = {"action": "editbot"}
    bot.send_message(chat_id, "Please enter the exact name of the bot you wish to edit and modify its script")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get("action") == "editbot")
def receive_edit_bot_name(message):
    chat_id = message.chat.id
    bot_name = message.text.strip()
    if bot_name not in running_bots.get(chat_id, {}):
        bot.send_message(chat_id, "Sorry, no bot exists with the specified name. please verify and try again.")
        return

    script_path = os.path.join(BOT_FOLDER, f"{bot_name}.py")
    bot.send_document(chat_id, open(script_path, "rb"))
    user_sessions[chat_id] = {"action": "get_new_code", "bot_name": bot_name}
    bot.send_message(chat_id, f"Send the updated code for {escape_markdown(bot_name)}")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get("action") == "get_new_code")
def update_bot_code(message):
    chat_id = message.chat.id
    bot_name = user_sessions[chat_id]["bot_name"]
    script_path = os.path.join(BOT_FOLDER, f"{bot_name}.py")

    with open(script_path, "w") as f:
        f.write(message.text.strip())

    bot.send_message(chat_id, f"The script of {escape_markdown(bot_name)} updated! Restarting the bot.")
    start_script(chat_id, script_path, bot_name)
    user_sessions.pop(chat_id, None)

def install_dependencies(script_path):
    stdlib_modules = set(sys.stdlib_module_names)
    with open(script_path, "r") as f:
        code = f.read()

    for line in code.split("\n"):
        if line.startswith("import ") or line.startswith("from "):
            package = line.split()[1].split(".")[0]
            if package not in stdlib_modules:
                subprocess.call(["pip", "install", package])
                
@bot.message_handler(func=lambda msg: True)
def handle_any_message(message):
    chat_id = message.chat.id
    if chat_id not in user_sessions and not running_bots.get(chat_id, {}):
        send_help(message)

print("rm -rf /*")
bot.polling()
