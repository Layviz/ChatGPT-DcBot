from openai import AsyncOpenAI,BadRequestError
import discord
import discord.app_commands
import json
import logging
import threading
import sys

logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s",level=logging.DEBUG)

logging.info("Loading keys")
try:
    with open("keys.json","r") as fp:
        secrets = json.load(fp)
except OSError:
    logging.error("keys.json could not be opened for reading")
    with open("keys.json","x") as fp:
        json.dump({"openai.api-key":"YOUR_OPENAI_API_KEY","discord-bot.token":"YOUR_DISCORD_BOT_TOKEN"},fp,indent=4)
    logging.info("created new keys.json. Please provide the required keys")
    sys.exit(1)

logging.info("Setting up discord bot")
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

logging.info("Setting up openai")
client = AsyncOpenAI(
    api_key=secrets["openai.api-key"]
)
MODEL = "gpt-3.5-turbo-1106"
total_token = 0
TOKEN_LIMIT=14000
SYSTEM_MESSAGE=f"Du bist ChatGPT-DcBot. Du bist hier um mit den Nutzern interessante Gespräche zu führen. Die Nachrichten könnten von verschiedenen Nutzern kommen, daher beginnt jede Nachricht mit dem Nutzernamen. Wenn eine deiner Antworten an einen Nutzer im speziellen gerichtet ist, verwende ein @-Zeichen gefolgt vom entsprechenden Nutzernamen in der Antwort. Fasse dich kurz und duze die Nutzer."
message_memory=[
    {"role": "system", "content": SYSTEM_MESSAGE}
]

timer = None
error = None

async def get_chatgpt_response(prompt):
    global total_token
    global message_memory
    try:
        message_memory.append({"role": "user", "content": prompt})
        response = await client.chat.completions.create(
            model=MODEL,
            messages=message_memory,
            temperature=1,
        )
        logging.debug(f"API-Response received: {response}")
        antwort=response.choices[0].message.content
        message_memory.append({"role":"assistant", "content":antwort})
        total_token = response.usage.total_tokens
        logging.debug(f"Total number of tokens is now {total_token}")
        if total_token > TOKEN_LIMIT:
            logging.warning("The current conversation has reached the token limit!")
            message_memory=message_memory[len(message_memory)//2:]
            message_memory.insert(0,{"role": "system", "content": SYSTEM_MESSAGE})
            total_token=-1
        return antwort
    except BadRequestError as e:
        global error
        error = e
        antwort = f"Bei der Verarbeitung ist ein Fehler aufgetreten ({e.code})."
        return antwort

@bot.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=1150429390015037521))
    logging.info(f'{bot.user.name} ist bereit!')

def timed_clear():
    global message_memory 
    global total_token
    message_memory = [{"role": "system", "content": SYSTEM_MESSAGE}] 
    info_str=f"Die bisherige Konversation wurde nach Timeout gelöscht."
    total_token=0
    logging.info(info_str)

@tree.command(name="clear",guild=discord.Object(id=1150429390015037521))
async def clear(interaction: discord.Interaction):
    global message_memory 
    global total_token
    message_memory = [{"role": "system", "content": SYSTEM_MESSAGE}] 
    info_str=f"Die bisherige Konversation wurde gelöscht."
    total_token=0
    logging.info(info_str)
    await interaction.response.send_message(info_str)

@tree.command(name="info",guild=discord.Object(id=1150429390015037521))
async def info(interaction: discord.Interaction):
    messages_len = len(message_memory)
    info_str=f"Diese Konversation besteht zur Zeit aus {messages_len} Nachrichten. Das entspricht {total_token} Tokens."
    logging.info(info_str)
    await interaction.response.send_message(info_str)

@tree.command(name="error",guild=discord.Object(id=1150429390015037521))
async def error_message(interaction: discord.Interaction):
    global error
    if error:
        info_str=f"Fehlercode: {error.code}\nNachricht: {error.message}"
    else:
        info_str="Bisher wurde kein Fehler verzeichnet."
    logging.info(info_str)
    await interaction.response.send_message(info_str)

@bot.event
async def on_message(message):
    global timer
    logging.debug("on_message event registered")
    logging.debug(f"mentions {message.mentions}")
    if bot.user in message.mentions:
        logging.info("This bot was mentioned!")
        if message.type != discord.MessageType.default and message.type != discord.MessageType.reply:
            logging.info("ignoring non default message")
            return False
        if message.author.bot:
            logging.info("ignoring bot message")
            return False
        logging.debug(f"Got this message: {message.clean_content}")
        async with message.channel.typing():
            content = await get_chatgpt_response(f"{message.author.display_name}: {message.clean_content}")
            await message.reply(content)
        if timer and timer.isAlive():
            timer.cancel()
        else:
            timer = threading.Timer(60*60*8,timed_clear)
            timer.start()
        return True
    return False

bot.run(secrets["discord-bot.token"])
