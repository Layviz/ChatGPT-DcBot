from openai import AsyncOpenAI
import discord
import discord.app_commands
import json
import logging
import threading

logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s",level=logging.DEBUG)

logging.info("Loading keys")
with open("keys.json","r") as fp:
    secrets = json.load(fp)

logging.info("Setting up discord bot")
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

logging.info("Setting up openai")
client = AsyncOpenAI(
    api_key=secrets["openai.api-key"]
)
MODEL = "gpt-3.5-turbo"
total_token = 0
TOKEN_LIMIT=22222
SYSTEM_MESSAGE=f"Du bist ChatGPT-DcBot. Du bist hier um mit den Nutzern interessante Gespräche zu führen. Die Nachrichten könnten von verschiedenen Nutzern kommen, daher beginnt jede Nachricht mit dem Nutzernamen. Wenn eine deiner Antworten an einen Nutzer im speziellen gerichtet ist, verwende ein @-Zeichen gefolgt vom entsprechenden Nutzernamen in der Antwort. Fasse dich kurz und duze die Nutzer."
message_memory=[
    {"role": "system", "content": SYSTEM_MESSAGE}
]

timer = None

async def get_chatgpt_response(prompt):
    global total_token
    global message_memory
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
    return antwort

@bot.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=1150429390015037521))
    logging.info(f'{bot.user.name} ist bereit!')

def timed_clear():
    global message_memory 
    message_memory = [{"role": "system", "content": SYSTEM_MESSAGE}] 
    info_str=f"Die bisherige Konversation wurde nach Timeout gelöscht."
    logging.info(info_str)


@tree.command(name="clear",guild=discord.Object(id=1150429390015037521))
async def clear(interaction: discord.Interaction):
    global message_memory 
    message_memory = [{"role": "system", "content": SYSTEM_MESSAGE}] 
    info_str=f"Die bisherige Konversation wurde gelöscht."
    logging.info(info_str)
    await interaction.response.send_message(info_str)

@tree.command(name="info",guild=discord.Object(id=1150429390015037521))
async def info(interaction: discord.Interaction):
    messages_len = len(message_memory)
    info_str=f"Diese Konversation besteht zur Zeit aus {messages_len} Nachrichten. Das entspricht {total_token} Tokens."
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

