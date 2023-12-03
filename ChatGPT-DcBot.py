from openai import AsyncOpenAI
import discord
from discord.ext import commands
import json
import logging

logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s",level=logging.DEBUG)

logging.info("Loading keys")
with open("keys.json","r") as fp:
    secrets = json.load(fp)

logging.info("Setting up openai")
client = AsyncOpenAI(
    api_key=secrets["openai.api-key"]
)
MODEL = "gpt-3.5-turbo"
SYSTEM_MESSAGE="Fasse dich kurz, duze mich, sei freundlich und hilfsbereit"

message_memory=[
    {"role": "system", "content": SYSTEM_MESSAGE}
]
total_token = 0

logging.info("Setting up discord bot")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

async def get_chatgpt_response(prompt):
    global total_token
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
    return antwort

@bot.event
async def on_ready():
    logging.info(f'{bot.user.name} ist bereit!')


@bot.hybrid_command(name="clear")
async def clear(ctx):
    global message_memory 
    message_memory = [{"role": "system", "content": SYSTEM_MESSAGE}] 
    info_str=f"Die bisherige Konversation wurde gelöscht"
    logging.info(info_str)
    async with ctx.typing():
        await ctx.send(info_str)

@bot.hybrid_command(name="info")
async def info(ctx):
    messages_len = len(message_memory)
    info_str=f"Diese Konversation besteht zur Zeit aus {messages_len} Nachrichten"
    logging.info(info_str)
    async with ctx.typing():
        await ctx.send(info_str)


@bot.event
async def on_message(message):
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
            content = await get_chatgpt_response(message.clean_content)
            await message.reply(content)
        return True
    # this isn't needed anymore because its covered by the previous check for mentions
    # elif message.type == discord.MessageType.reply:
    #     if message.reference and message.reference.message_id:
    #         orignal_message = await message.channel.fetch_message(message.reference.message_id)
    #         if orignal_message.author == bot.user:
    #             logging.debug(f"Got this message: {message.clean_content}")
    #             async with message.channel.typing():
    #                 content = "Beispiel Antwort"
    #                 # content = get_chatgpt_response(message.clean_content)
    #                 await message.reply(content)
    #             return True
    return False

bot.run(secrets["discord-bot.token"])
