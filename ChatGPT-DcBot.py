from openai import AsyncOpenAI
import discord
from discord.ext import commands
import json

with open("keys.json","r") as fp:
    secrets = json.load(fp)

client = AsyncOpenAI(
    api_key=secrets["openai.api-key"]
)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot ist bereit! {bot.user.name}')

@bot.command(name="Message")
async def message(ctx, text):
    try:
        async with ctx.typing():
            # MODEL = "gpt-3.5-turbo"
            # response = await client.chat.completions.create(
            #     model=MODEL,
            #     messages=[
            #         {"role": "system", "content": "Fasse dich kurz, duze mich, sei freundlich und hilfsbereit"},
            #         {"role": "user", "content": text},
            #     ],
            #     temperature=0,
            # )
            # print(response)
            # Antwort=response.choices[0].message.content
            Antwort="Test Nachricht"

            print(Antwort)
            await ctx.send(Antwort)
    except Exception as e:
        print(e)

bot.run(secrets["discord-bot.token"])
