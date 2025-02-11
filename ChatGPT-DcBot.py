from openai import AsyncOpenAI,BadRequestError
import discord
import discord.app_commands
import json
import logging
import threading
import sys
import asyncio,os,shutil
import string
from typing import Literal
from ffmpeg import FFmpeg
from datetime import datetime
import random,re
import traceback

log_filename="ChatGPT-DcBot.log"
if(os.path.isfile(log_filename)):
    shutil.copy(log_filename,f"old_{log_filename}")
logging.basicConfig(filename=log_filename,filemode="w",format="%(asctime)s %(levelname)s: %(message)s",level=logging.DEBUG)

logging.info("Loading keys")
try:
    with open("keys.json","r") as fp:
        secrets = json.load(fp)
except OSError:
    logging.error("keys.json could not be opened for reading")
    with open("keys.json","x") as fp:
        json.dump({
            "openai.api-key":"YOUR_OPENAI_API_KEY",
            "discord-bot.token":"YOUR_DISCORD_BOT_TOKEN",
            "discord.guild_id":"YOUR_DISCORD_GUILD_ID",
            "discord.zotate_id":"DISCORD_ZOTATE_CHANNEL_ID"
            },fp,indent=4)
    logging.info("created new keys.json. Please provide the required keys")
    sys.exit(1)

character_config = {
    "general":{
        "reset_sec": 60*60*8,
        "max_completion_tokens": 1200
    },
    "ChatGPT":{
        "system-message-file":"ChatGPT.txt",
        "model":"gpt-4o-mini",
        "temperature":1.0,
        "frequency":1.0,
        "presence":1.0,
        "voice":"nova",
        "limit":60000
    }
}

logging.info("loading config")
if os.path.exists("config.json"):
    with open("config.json","r") as fp:
        character_config.update(json.load(fp))
    with open("config.json","w") as fp:
        json.dump(character_config,fp,indent=4)
else:
    logging.error("config.json does not exist!")
    f_desc = os.open("config.json",flags=(os.O_WRONLY|os.O_CREAT|os.O_EXCL),mode=0o666)
    with open(f_desc,"w") as fp:
        json.dump(character_config,fp,indent=4)
        logging.info("created new config.json with default settings")

logging.info("Setting up discord bot")
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

ZOTATE_START = datetime(2023,9,13) # irgendwie in config vielleicht?
ZOTATE_CHANNEL = None
zotate = None
used_zotate = []
active_character=None
last_message_read = 0
last_voice = ""
timer = None
error = None
last_exception = None

RESET_TIMER=character_config["general"]["reset_sec"]

audio_semaphore = threading.Semaphore()

logging.info("Setting up openai")
client = AsyncOpenAI(
    api_key=secrets["openai.api-key"]
)

class Character:
    def __init__(self,name,developer_message,model,temperature,frequency,presence,voice,limit):
        self.name=name
        self.dev_message=developer_message
        self.model=model
        self.temperature=temperature
        self.frequency=frequency
        self.presence=presence
        self.voice=voice
        self.token_limit=limit
        self.clear()
        logging.debug(f"{name}: {model}, {temperature} {frequency} {presence} {voice} {limit}")
        
    def clear(self):
        self.message_memory=[{"role": "developer", "content": self.dev_message}]
        self.total_token=0
        self.total_messages=0

    def get_last_message(self):
        if len(self.message_memory) <= 1:
            return -1
        for i in range(-1,-len(self.message_memory),-1):
            if self.message_memory[i]["role"]=="assistant":
                message_to_read = self.message_memory[i]['content']
                return message_to_read
        return -2

    async def chat(self,prompt=None,user=None):
        try:
            if prompt:
                msg={"role": "user", "content": prompt}
                if user:
                    msg["user"]=user
                self.message_memory.append(msg)
            response = await client.chat.completions.create(
                model=self.model,
                messages=self.message_memory,
                temperature=self.temperature,
                frequency_penalty=self.frequency,
                presence_penalty=self.presence,
                max_completion_tokens=character_config["general"]["max_completion_tokens"]
            )
            logging.debug(f"API-Response received: {response}")
            antwort=response.choices[0].message.content
            self.message_memory.append({"role":"assistant", "content":antwort})
            self.total_token = response.usage.total_tokens
            logging.debug(f"Total number of tokens is now {self.total_token}")
            self.total_messages += 1
            if self.total_token > self.token_limit:
                logging.warning("The current conversation has reached the token limit!")
                self.message_memory=self.message_memory[len(self.message_memory)//2:]
                # message_memory.insert(0,{"role": "developer", "content": self.dev_message})
                self.total_token=-1
            return antwort
        except BadRequestError as e:
            global error
            error = e
            logging.error(f"Bad Request {e.message}")
            antwort = f"Bei der Verarbeitung ist ein Fehler aufgetreten ({e.status_code})."
            return antwort
        except Exception as e:
            global last_exception
            last_exception = e
            logging.exception("unkown Error")
        
    async def set_char(self, interaction: discord.Interaction):
        global active_character
        await interaction.response.defer(thinking=True)
        self.clear()
        active_character = self
        info_str=f"Die bisherige Konversation wurde gelöscht und {self.name} ist erschienen."
        logging.info(info_str)
        response = await self.chat("HALLO",interaction.user.display_name)
        msgs = partion_discord_message(response)
        for msg in msgs:
            await interaction.followup.send(msg)


logging.info("Creating Characters")
default_system_message="Du bist ChatGPT-DcBot."
characters:list[Character]=[]
character_names:list[str]=[]
for character in character_config:
    if character=="general":
        continue
    if os.path.isfile(character_config[character]["system-message-file"]):
        with open(character_config[character]["system-message-file"],"r",encoding="utf-8") as fp:
            system_message = fp.read()
    else:
        logging.error(f"{character_config[character]['system-message-file']} does not exist!")
        system_message=default_system_message
        f_desc = os.open(character_config[character]["system-message-file"],flags=(os.O_WRONLY|os.O_CREAT|os.O_EXCL),mode=0o666)
        with open(f_desc,"w",encoding="utf-8") as fp:
            fp.write(default_system_message)
            logging.info(f"created new {character_config[character]['system-message-file']} with default message")


    char = Character(character,
                system_message,
                character_config[character]["model"],
                character_config[character]["temperature"],
                character_config[character]["frequency"],
                character_config[character]["presence"],
                character_config[character]["voice"],
                character_config[character]["limit"])
    
    char.set_char = tree.command(name=character.lower(),description=f"Löscht den aktuellen Chat und startet einen Chat mit {character}",guild=discord.Object(id=secrets["discord.guild_id"]))(char.set_char)
    

    characters.append(char)
    character_names.append(character)
    logging.info(f"created Character {character}")

logging.info(f"created {len(characters)} Characters")

active_character=characters[0]

sync_file="synced"
synced_characters=[]
if os.path.isfile(sync_file):
    with open(sync_file,"r",encoding="utf-8") as fp:
        synced_characters = json.load(fp)

sync_flag = sorted(synced_characters)!=sorted(character_names)

def format_filename(s):
    """Take a string and return a valid filename constructed from the string.
Uses a whitelist approach: any characters not present in valid_chars are
removed. Also spaces are replaced with underscores.
"""
    valid_chars = "-_.() %s%säöüßÄÖÜ" % (string.ascii_letters, string.digits)
    filename = ''.join(c for c in s if c in valid_chars)
    return filename

async def get_chatgpt_heading(text:str):
    try:
        response = await client.chat.completions.create(model="gpt-4o-mini",messages=[
            {"role":"system","content":"Gib dem folgenenden Text eine kurze passende einzigartige Überschrift mit maximal 43 Buchstaben."},
            {"role":"user","content":text},
        ])
        logging.debug(f" Heading hat {response.usage.completion_tokens} Tokens")
        antwort=response.choices[0].message.content
        logging.debug(f"Heading für Text ist: {antwort}")
        filename = format_filename(antwort)+".mp3"
        logging.debug(f"Filename = {filename}")
        return filename
    except:
        return "Nachricht.mp3"

@bot.event
async def on_ready():
    global ZOTATE_CHANNEL
    if sync_flag:
        commands = await tree.sync(guild=discord.Object(id=secrets["discord.guild_id"]))
        print("Synced Commands:")
        for com in commands:
            print(f"{com.name}")
        
        if os.path.isfile(sync_file):
            with open(sync_file,"w") as fp:
                json.dump(character_names,fp,indent=4)
        else:
            f_desc = os.open(sync_file,flags=(os.O_WRONLY|os.O_CREAT|os.O_EXCL),mode=0o666)
            with open(f_desc,"w") as fp:
                json.dump(character_names,fp,indent=4)
    
    ZOTATE_CHANNEL = bot.get_channel(secrets["discord.zotate_id"])
    if ZOTATE_CHANNEL is None:
        logging.error("zotate Channel was not found!")
    logging.info(f'{bot.user.name} ist bereit!')

def partion_discord_message(msg:str,):
        split_messages:list[str]=[]
        while len(msg)>2000: #discord message limit
            index = msg.rindex(' ',0,2000)
            split_messages.append(msg[:index])
            msg = msg[index+1:]
        split_messages.append(msg)
        return split_messages

def timed_clear():
    global active_character
    active_character=characters[0] # ist das gewünscht?
    active_character.clear()
    info_str=f"Die bisherige Konversation wurde nach Timeout gelöscht."
    logging.info(info_str)

@tree.command(name="info", description="Zeigt an wie viele Tokens der derzeitige Chat kostet.",guild=discord.Object(id=secrets["discord.guild_id"]))
async def info(interaction: discord.Interaction):
    messages_len = len(active_character.message_memory)
    info_str=f"Diese Konversation besteht aus {active_character.total_messages} Nachrichten und zur Zeit aus {messages_len} Nachrichten. Das entspricht {active_character.total_token} Tokens."
    logging.info(info_str)
    await interaction.response.send_message(info_str)

@tree.command(name="error", description="Zeigt den letzten aufgetretenen Fehler an",guild=discord.Object(id=secrets["discord.guild_id"]))
async def error_message(interaction: discord.Interaction):
    global error,last_exception
    if error:
        info_str=f"Fehlercode: {error.status_code} / {error.code}\nNachricht: {error.message}"
        await interaction.response.send_message(info_str)
    if last_exception:
        info_str=f"Folgender Trace wurde aufgezeichnet: ````\n{traceback.format_exc()}\n```"
        await interaction.response.send_message(info_str)
    if error is None and last_exception is None:
        info_str="Es wurde kein Fehler festgestellt"
        await interaction.response.send_message(info_str)

@tree.command(name="vorlesen", description="Liest die letzte Nachricht vor.",guild=discord.Object(id=secrets["discord.guild_id"]))
@discord.app_commands.describe(stimme="Hiermit kann eine andere Stimme zum vorlesen ausgewählt werden")
async def vorlesen(interaction: discord.Interaction, stimme:Literal["Steve","Finn","Greta","Giesela","Lisa","Peter","Carol","Karen"]=None):
    global last_message_read, last_voice, audio_semaphore, last_exception, error
    logging.debug("called vorlesen")
    message_to_read = active_character.get_last_message()
    if message_to_read == -1:
        await interaction.response.send_message("Es gibt noch keine Nachricht zum vorlesen.")
        return
    elif message_to_read == -2:
        await interaction.response.send_message("Es wurde keine Nachricht zum vorlesen gefunden.")
        return
    await interaction.response.defer(thinking=True)
    user = interaction.user
    if user.voice:
        voice_channel = user.voice.channel
    else:
        voice_channel = None
    tempfile = "temp.opus"
    convfile = "temp.mp3"
    if stimme is None:
        current_voice=active_character.voice
    else:
        if stimme == "Steve":
            current_voice="echo"
        elif stimme == "Finn":
            current_voice="fable"
        elif stimme == "Greta":
            current_voice="shimmer"
        elif stimme == "Giesela":
            current_voice="alloy"
        elif stimme == "Lisa":
            current_voice="nova"
        elif stimme == "Peter":
            current_voice="onyx"
        elif stimme == "Carol":
            current_voice="sage"
        elif stimme == "Karen":
            current_voice="coral"
        else:
            current_voice=voice
    if audio_semaphore.acquire(blocking=False):
        try:
            if hash(message_to_read) != last_message_read or last_voice != current_voice:
                logging.info("new voice message will be generated")
                response = await client.audio.speech.create(model="tts-1",voice=current_voice,input=message_to_read,response_format='opus')
                response.stream_to_file(tempfile)
                if os.path.exists(convfile): 
                    os.remove(convfile)
                #ffmpeg -i Nachricht.opus -vn -ar 44100 -ac 2 -b:a 192k Nachricht.mp3
                FFmpeg().input(tempfile).output(convfile,{"b:a":"192k"},vn=None,ar=44100).execute()
                logging.debug("File converted")
                filename = await get_chatgpt_heading(message_to_read)
                file = discord.File(convfile,filename=filename)
                await interaction.followup.send("Hier ist die vorgelesene Nachricht",file=file)
                logging.debug("Sent followup mesage")
                last_message_read = hash(message_to_read)
                last_voice = current_voice
            else:
                if voice_channel!=None:
                    logging.warning("existing Message is read again")
                    await interaction.followup.send("Nachricht wird erneut vorgelesen")
            if voice_channel!=None:
                audio =discord.FFmpegOpusAudio(tempfile)
                vc = await voice_channel.connect()
                vc.play(audio)
                while vc.is_playing() and vc.is_connected():
                    await asyncio.sleep(1)
                # disconnect after the player has finished
                await vc.disconnect()
            else:
                logging.error(f"{user.display_name} ist nicht in einem Voice Channel")
        except BadRequestError as e:
            error = e
            await interaction.followup.send("Es ist ein Fehler aufgetreten. Verwende `/error` um mehr zu erfahren.")
        except discord.ClientException as e:
            last_exception = e
            logging.exception("ClientException")
            await interaction.followup.send("Es ist ein Fehler aufgetreten. Der Bot scheint bereits im Voice Chat zu sein.")
        except Exception as e:
            last_exception = e
            logging.exception("Unkown error")
            await interaction.followup.send("Es ist ein unbekannter Fehler aufgetreten.")
        finally:
            audio_semaphore.release()
    else:
        await interaction.followup.send("Der Bot liest noch vor. Versuche es später nochmal.")
    

@tree.context_menu(name="erneut vorlesen",guild=discord.Object(id=secrets["discord.guild_id"]))
async def erneut_vorlesen(interaction: discord.Interaction, message: discord.Message):
    global audio_semaphore
    if message.author.id == bot.user.id:
        if len(message.attachments) == 1 and message.attachments[0].content_type == "audio/mpeg": 
            await interaction.response.defer(thinking=True,ephemeral=True)
            if interaction.user.voice.channel:
                if audio_semaphore.acquire(blocking=False):
                    try:
                        audio = discord.FFmpegPCMAudio(message.attachments[0].url,executable="ffmpeg")
                        vc = await interaction.user.voice.channel.connect()
                        vc.play(audio)
                        await interaction.followup.send("Nachricht wird erneut vorgelesen.",ephemeral=True)
                        while vc.is_playing() and vc.is_connected():
                            await asyncio.sleep(1)
                        # disconnect after the player has finished
                        await vc.disconnect()
                    finally:
                        audio_semaphore.release()
                else:
                    await interaction.followup.send("Der Bot liest noch vor. Versuche es später nochmal.",ephemeral=True)
            else:

                await interaction.followup.send("Du bist nicht in einem Voice Channel",ephemeral=True)
        else:
            await interaction.response.send_message("Wähle eine Nachricht mit einer vorgelesenen Audio",ephemeral=True)
    else:
        await interaction.response.send_message("Das ist keine Nachricht vom ChatGPT-DcBot!",ephemeral=True)

@tree.command(name="help", description="Zeigt die Hilfe an",guild=discord.Object(id=secrets["discord.guild_id"]))
async def hilfe(interaction: discord.Interaction):
    help_text="""**Anleitung zur Nutzung von ChatGPT-DcBot:**

Mit **@** und dem Namen des Bots "__ChatGPT-DcBot__" kannst du ihm schreiben. Antworte dann einfach auf seine Nachricht um das Gespräch fortzuführen.

Mit `/chat_gpt` kannst du den aktuellen Chat löschen und mit __ChatGPT__ reden.

Mit `/hal` kannst du den aktuellen Chat löschen und stattdessen mit __HAL__ reden.

Mit `/peter_box` kannst du den aktuellen Chat löschen und stattdessen mit __Peter Box__ reden.

Mit `/schneutsch` kannst du den aktuellen Chat löschen und mit dem __Schneutsch-Lexikon__ reden.

Mit `/tobias88` kannst du den aktuellen Chat löschen und stattdessen mit __Tobias88__ reden.

Mit `/vorlesen` kannst du die letzte Chatnachricht vorlesen lassen. (*Wenn in VC, Audio wird ebenfalls generiert im Chat.*)

Mit **Rechtsklick** bei **Apps** auf __erneut vorlesen__ kannst du schon vom Bot generierte Audios erneut vorlesen lassen.

Mit `/help` kannst du den Bot nach Hilfe Fragen.

Mit `/info` kannst du dir anzeigen lassen, wie viel Token der derzeitige Chat kostet.

Mit `/error` kannst du dir den letzten aufgetretenen Fehler anzeigen lassen.

Der __ChatGPT-DcBot__ kann Interaktiv in einer Unterhaltung mit mehreren Chat Teilnehmern gleichzeitig schreiben, ohne das ein **Clear** nötig ist!

Bei Fragen kann man den Admin des Servers anschreiben, oder ein Thread öffnen bei "__hilfe__" und dort nach Hilfe Fragen.

*Sonst viel Spaß mit dem Bot :)*"""
    logging.info("sending help text")
    await interaction.response.send_message(help_text)

@tree.command(name="zotate", description="Erzeugt eine Geschichte aus zufälligen Zotaten",guild=discord.Object(id=secrets["discord.guild_id"]))
async def zotate(interaction: discord.Interaction):
    global used_zotate,zotate
    await interaction.response.defer(thinking=True)
    num_zitate = 7
    randoms = []
    used_dates = {}
    # days = (datetime.now()-ZOTATE_START).days
    
    if zotate is None:
        zotate = [message async for message in ZOTATE_CHANNEL.history(limit=None)]

    while len(randoms) < num_zitate:
        # messages = []
        # while len(messages)==0:
        #     random_days = random.randint(0,days)
        #     random_after = ZOTATE_START + timedelta(random_days-1)
        #     random_before = ZOTATE_START + timedelta(random_days+1)
        #     messages  = [message async for message in ZOTATE_CHANNEL.history(after=random_after,before=random_before,limit=None)]
        

        msg = zotate[random.randint(0,len(zotate)-1)]
        from_this_date = used_dates.get(msg.created_at.date(),0) 
        if from_this_date >= 3:
            continue
        re_match = re.search("\"(.*)\"",msg.clean_content)
        if re_match and msg.id not in used_zotate:
            used_zotate.append(msg.id)
            used_dates[msg.created_at.date()] = from_this_date+1
            randoms.append(re_match.group(1))
            #logging.debug(f"gewähltes Zotat vom {msg.created_at.strftime("%d.%m.%Y, %H:%M:%S")}: \"{re_match.group(1)}\"")

    content = await active_character.chat("Erzähl eine Geschichte und verwende dabei diese Zitate:\n"+"\n".join(randoms))
    while len(content)>2000: #discord message limit
        index = content.rindex(' ',0,2000)
        await interaction.followup.send(content[:index])
        content = content[index+1:]
    await interaction.followup.send(content)


@bot.event
async def on_message(message):
    global timer,total_messages
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
        if type(message.channel) != discord.channel.TextChannel:
            logging.info("ignoring message on a not text channel")
            return False
        logging.debug(f"Got this message: {message.clean_content}")
        async with message.channel.typing():
            active_character.total_messages += 1
            content = await active_character.chat(message.clean_content,message.author.display_name)
            msgs = partion_discord_message(content)
            for msg in msgs:
                await message.reply(msg)
        if timer and timer.is_alive():
            timer.cancel()
        if RESET_TIMER>0:
            timer = threading.Timer(RESET_TIMER,timed_clear)
            timer.start()
        return True
    return False

@bot.event
async def on_message_edit(before, after):
    logging.debug("on_message_edit event registered")
    # this function can also trigger in cases where the message was not changed (pining, embeding, etc.) so we check for a change
    if (before.content != after.content):
        # handle the changed message like a new message
        return await on_message(after)

bot.run(secrets["discord-bot.token"])
