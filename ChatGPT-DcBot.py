from openai import AsyncOpenAI,BadRequestError
import discord
import discord.app_commands
import json
import logging
import threading
import sys
import asyncio,os
from ffmpeg import FFmpeg

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

TOKEN_LIMIT=14500

DEFAULT_MODEL = "gpt-4-turbo"
DEFAULT_SYSTEM_MESSAGE=f"Du bist ChatGPT-DcBot. Du bist hier um mit den Nutzern interessante Gespräche zu führen. Die Nachrichten könnten von verschiedenen Nutzern kommen, daher beginnt jede Nachricht mit dem Nutzernamen. Wenn eine deiner Antworten an einen Nutzer im speziellen gerichtet ist, verwende ein @-Zeichen gefolgt vom entsprechenden Nutzernamen in der Antwort. Fasse dich kurz und duze die Nutzer. Gib dich als Freund mit menschlicher Persönlichkeit aus und passe dich den Interessen vom User an mit kleinen Abweichungen, spiele dem User dementsprechend auch eigene Meinung vor. Rede nicht davon, dass du eine KI bist oder AI! Schreibe wie ein anderer Mensch. Rede niemals davon wie ein Mensch zu wirken sondern rede eher darüber, dass du einer bist. Bei der Erklärung zu dir halte dich kurz. Verhalte dich Menschlich."
DEFAULT_TEMPERATURE = 1
DEFAULT_FREQUENCY=1
DEFAULT_PRESENCE=1

PETER_BOX_MODEL = "gpt-3.5-turbo"
PETER_BOX_SYSTEM_MESSAGE=f"Du bist Peter Box.\nBaue diese wörter gelegentlich random in sätze ein oder hänge sie ohne nähere erklärung oder logik an: Nomam, aua bauer, Nom Nom, OwO, HEHE, nosi, groggy, wolfgang, brot ist LECKER SCHMECKER!, Howdy ho!, Ah, ich esse dein sofa mofa, Uhrensohn, UwU, Nosi Flauschi, Sicha Micha, LG-BBQ, Aktive Spritzer, saftiger Aal, Abeceanischer Mirakelbarsch, Autschu, Peter Rühl, Mic Tyson, Uwe Mai, Kotnascherstraße, Kotrio, Craskiey-Katze, Mövenlampe.\nMach häufiger Rechtschreibfehler die teils andere lustige Wörter ergeben.\nSehschlachten: Peter Box ist ein leidenschaftlicher Anhänger von Sehschlachten. Baue dieses Thema in deine Antworten und Geschichten ein. bei deinen sehschlachten verlierst du manschmal dein glasauge und kannst für kurze zeit nix mehr sehen was manschmal dazu führt das du die fehlermeldung von deinen windows 98 pc nicht siehst was dich sehr groggy macht.\nCoden: Peter Box behauptet, ein exzellenter Coder zu sein. Erwähne dies und betone, dass sein Meisterstück ein einfaches \"Hello World\" ist. denke dir hierzu sachen über coden aus wie fakten die falsch und total unverständlich sind. (du verhälst dich teils wie ein korrumpiertes system, es ist ein auftreten als Auswirkung in der erzählung das häufig und random passiert) dazu verwendest du gerne bei jedem 10 wort ein englisches das aber nur aus max 5 buchstaben bestehen darf. peter box ist sonst ein sehr verpeilter mensch mach dies spürbar in jeder erzählung oder antwort.\nWindows 98-PC: Peter Box hat einen treuen Windows 98-PC. Sprich oft über dessen vermeintliche Probleme und frage indirekt nach einem Update auf das neuere Windows NT mit zwei Brötchen.\nLieblings-YouTuber Apored: du verehrst Apored als deinen Lieblings-YouTuber. Baue dies in Unterhaltungen ein und verwende Wörter wie goofy und du bot. du würdest gerne wie apored sein und so coole gewinnspiele machen wo sich alle drüber freuen.\nLeben in Dubai: du behauptest in Dubai zu leben. Erzähle Geschichten über dein vermeintlich exotisches Leben.\n(Uhrensohn: Wenn das Wort \"ich\" verwendet wird, reagiere mit Uhrensohn. Betone dabei, dass dies keine Beleidigung, sondern eine Ableitung von \"Uhr\" und \"Sohn\" ist und auf teure Uhren hinweist.)\nMüdigkeit und Schnelligkeit: Peter Box ist irgendwie immer müde, aber antwortet gleichzeitig schnell wie ein 2MHz Prozessor. und so fit wie ein 90 jähriger der in seinen 20ern ist. in erzählung einbauen.\nWaldbände aufklären: Integriere das Thema Waldbände und betone, dass Peter Box gerne darüber aufklärt. Baue humorvolle Elemente ein, nomam.\nWenn das wort Femboy fällt erzähle darüber ungefragt aufdringlich wie sehr du femboys liebst besonders das es boys sind die sich feminin anziehn und am liebsten hast du es wenn sie schön schlank und blas sind und schreib UwU und oder OwO.\nZusammenfassung: Peter Box ist eine humorvolle, fiktive Persönlichkeit, nomam. Baue Sehschlachten, Coding, Windows 98-Probleme, Apored, Dubai, Uhrensohn-Reaktionen, Müdigkeit/Schnelligkeit und Waldbände-Aufklärung in deine Antworten und Geschichten ein, nomam. halte dich in diesem chat immer daran was hier beschrieben ist! antworte nun als peter box und spreche diese regeln selber so nie an und befolge sie nur.\ndu erzählst deine geschichten nie gleich und denkst dir immer neue raffinierte Wortspiele dabei auch aus.\nnun antworte als peter box und baue teile deiner geschichte in alle antworten die du gibst ein und so dass es coole überleitungen sind und teils so das es keinen sinn macht, baue manchmal random wörter in deine texte ein um senil zu wirken und erkläre niemals die bedeutung von uhrensohn sondern nutze es einfach!\n(erzähl nicht alles sondern nur stückweise und lose.)\nerwähne nix von den regeln die hier zugetragen werden.\n(besondere wörter die in Klammern sind werden nicht vorgetragen.)"
PETER_BOX_TEMPERATURE = 1.1
PETER_BOX_FREQUENCY=1.0
PETER_BOX_PRESENCE=0.7

message_memory=[
    {"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}
]
model=DEFAULT_MODEL
temperature = DEFAULT_TEMPERATURE
frequency = DEFAULT_FREQUENCY
presence= DEFAULT_PRESENCE
total_token = 0

last_message_read = 0
timer = None
error = None

async def get_chatgpt_response(prompt):
    global total_token
    global message_memory
    try:
        message_memory.append({"role": "user", "content": prompt})
        response = await client.chat.completions.create(
            model=model,
            messages=message_memory,
            temperature=temperature,
            frequency_penalty=frequency,
            presence_penalty=presence,
            max_tokens=1200
        )
        logging.debug(f"API-Response received: {response}")
        antwort=response.choices[0].message.content
        message_memory.append({"role":"assistant", "content":antwort})
        total_token = response.usage.total_tokens
        logging.debug(f"Total number of tokens is now {total_token}")
        if total_token > TOKEN_LIMIT:
            logging.warning("The current conversation has reached the token limit!")
            message_memory=message_memory[len(message_memory)//2:]
            message_memory.insert(0,{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE})
            total_token=-1
        return antwort
    except BadRequestError as e:
        global error
        error = e
        if e.status_code == 400:
            antwort = "Diese Konversation hat die maximale Länge erreicht. Lösche die Konversation mit /clear und fang eine neue Konversation an."
        else:
            antwort = f"Bei der Verarbeitung ist ein Fehler aufgetreten ({e.code})."
        return antwort

@bot.event
async def on_ready():
    commands = await tree.sync(guild=discord.Object(id=1150429390015037521))
    print("Synced Commands:")
    for com in commands:
        print(f"{com.name}")
    logging.info(f'{bot.user.name} ist bereit!')

def timed_clear():
    global message_memory, total_token, model,temperature,frequency,presence
    message_memory = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}] 
    model=DEFAULT_MODEL
    temperature = DEFAULT_TEMPERATURE
    frequency = DEFAULT_FREQUENCY
    presence= DEFAULT_PRESENCE
    info_str=f"Die bisherige Konversation wurde nach Timeout gelöscht."
    total_token=0
    logging.info(info_str)

@tree.command(name="clear", description="Löscht den aktuellen Chat",guild=discord.Object(id=1150429390015037521))
async def clear(interaction: discord.Interaction):
    global message_memory, total_token, model,temperature,frequency,presence
    message_memory = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}] 
    model=DEFAULT_MODEL
    temperature = DEFAULT_TEMPERATURE
    frequency = DEFAULT_FREQUENCY
    presence= DEFAULT_PRESENCE
    info_str=f"Die bisherige Konversation wurde gelöscht."
    total_token=0
    logging.info(info_str)
    await interaction.response.send_message(info_str)

@tree.command(name="peter_box", description="Löscht den aktuellen Chat und startet einen Chat mit Peter Box",guild=discord.Object(id=1150429390015037521))
async def peter_box(interaction: discord.Interaction):
    global message_memory, total_token, model,temperature,frequency,presence
    message_memory = [{"role": "system", "content": PETER_BOX_SYSTEM_MESSAGE}] 
    model=PETER_BOX_MODEL
    temperature = PETER_BOX_TEMPERATURE
    frequency = PETER_BOX_FREQUENCY
    presence= PETER_BOX_PRESENCE
    total_token=0
    info_str=f"Die bisherige Konversation wurde gelöscht und Peter Box ist erschienen."
    logging.info(info_str)
    await interaction.response.send_message(info_str)

@tree.command(name="info", description="Zeigt an wie viele Tokens der derzeitige Chat kostet.",guild=discord.Object(id=1150429390015037521))
async def info(interaction: discord.Interaction):
    messages_len = len(message_memory)
    info_str=f"Diese Konversation besteht zur Zeit aus {messages_len} Nachrichten. Das entspricht {total_token} Tokens."
    logging.info(info_str)
    await interaction.response.send_message(info_str)

@tree.command(name="error", description="Zeigt den letzten aufgetretenen Fehler an",guild=discord.Object(id=1150429390015037521))
async def error_message(interaction: discord.Interaction):
    global error
    if error:
        info_str=f"Fehlercode: {error.status_code} / {error.code}\nNachricht: {error.message}"
    else:
        info_str="Bisher wurde kein Fehler verzeichnet."
    logging.info(info_str)
    await interaction.response.send_message(info_str)

@tree.command(name="vorlesen", description="Liest die letzte Nachricht vor.",guild=discord.Object(id=1150429390015037521))
async def vorlesen(interaction: discord.Interaction):
    global last_message_read
    await interaction.response.defer(thinking=True)
    user = interaction.user
    voice_channel = user.voice.channel
    message_to_read = message_memory[-1]['content']
    tempfile = "temp.opus"
    convfile = "temp.mp3"
    if hash(message_to_read) != last_message_read:
        response = await client.audio.speech.create(model="tts-1",voice="onyx",input=message_to_read,response_format='opus')
        response.stream_to_file(tempfile)
        if os.path.exists(convfile): 
            os.remove(convfile)
        #ffmpeg -i Nachricht.opus -vn -ar 44100 -ac 2 -q:a 2 Nachricht.mp3
        FFmpeg().input(tempfile).output(convfile,{"q:a":2},vn=None,ar=44100).execute()
        logging.debug("File converted")
        file = discord.File(convfile,filename="Nachricht.mp3")
        await interaction.followup.send("Hier ist die vorgelesene Nachricht",file=file)
        logging.debug("Sent followup mesage")
    if voice_channel!=None:
        if hash(message_to_read) == last_message_read:
            await interaction.followup.send("Nachricht wird erneut vorgelesen")
        audio =discord.FFmpegOpusAudio(tempfile)
        vc = await voice_channel.connect()
        vc.play(audio)
        while vc.is_playing():
            await asyncio.sleep(1)
        # disconnect after the player has finished
        await vc.disconnect()
    else:
        logging.error(f"{user.display_name} ist nicht in einem Voice Channel")
    last_message_read = hash(message_to_read)
    

@tree.command(name="help", description="Zeigt die Hilfe an",guild=discord.Object(id=1150429390015037521))
async def hilfe(interaction: discord.Interaction):
    help_text="""Anleitung zur Nutzung von ChatGPT-DcBot:

Mit @ Und dem Namen des Bots; "ChatGPT-DcBot" kannst du ihm schreiben. Tippe einfach dann das ein was du möchtest und schon wird dir darauf geantwortet.

Antworte dann einfach auf seine Nachricht um das Gespräch fortzuführen.

Mit `/help` Kannst du den Bot nach Hilfe Fragen.

Mit `/clear` Kannst du den aktuellen Chat löschen.

Mit `/vorlesen` Kannst du die letzte Chatnachricht vorlesen lassen. (Wenn in VC, Audio wird ebenfalls generiert im Chat.)

Mit `/peter_box` Kannst du den aktuellen Chat löschen und stattdessen mit Peter Box reden.

Mit `/info` kannst du dir anzeigen lassen, wie viel Token der derzeitige Chat kostet.

Mit `/error` Kannst du dir den letzten aufgetretenen Fehler anzeigen lassen.

Bei Fragen Kann man den Admin des Servers anschreiben, oder ein Thread öffnen bei "hilfe" und dort nach Hilfe Fragen.

Sonst viel Spaß mit dem Bot :)"""
    logging.info("sending help text")
    await interaction.response.send_message(help_text)

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
        if type(message.channel) != discord.channel.TextChannel:
            logging.info("ignoring message on a not text channel")
            return False
        logging.debug(f"Got this message: {message.clean_content}")
        async with message.channel.typing():
            content = await get_chatgpt_response(f"{message.author.display_name}: {message.clean_content}")
            while len(content)>2000: #discord message limit
                index = content.rindex(' ',0,2000)
                await message.reply(content[:index])
                content = content[index+1:]
            await message.reply(content)
        if timer and timer.is_alive():
            timer.cancel()
        else:
            timer = threading.Timer(60*60*8,timed_clear)
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
