import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import logging
from collections import deque
import asyncio

# Configurações de logging
logging.basicConfig(level=logging.INFO)

# Configurações dos Intents
intents = discord.Intents.default()
intents.message_content = True  # Permite que o bot leia o conteúdo das mensagens
intents.voice_states = True    # Permite que o bot gerencie estados de voz

# Configurações
TOKEN = 'SEU_TOKEN_AQUI'  # Substitua pelo token real do seu bot
YDL_OPTIONS = {
    'format': 'bestaudio/best',  # Garantir o formato de melhor qualidade para áudio
    'quiet': True,
    'noplaylist': True,          # Não extrair playlist
}
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

bot = commands.Bot(command_prefix='!', intents=intents)

# Fila de reprodução
queue = deque()
idle_timeout = 30  # Tempo em segundos para timeout de inatividade
voice_client = None
timeout_task = None

@bot.event
async def on_ready():
    logging.info(f'Logged in as {bot.user.name}')

@bot.command()
async def play(ctx, *, query: str):
    """Comando para adicionar uma música à fila e tocar no canal de voz"""
    global voice_client, timeout_task

    if ctx.voice_client is None:
        # Conecta ao canal de voz
        channel = ctx.author.voice.channel
        voice_client = await channel.connect()
    else:
        voice_client = ctx.voice_client

    # Se o usuário forneceu uma URL do YouTube
    if 'youtube.com' in query or 'youtu.be' in query:
        url = query
    else:
        # Se for uma pesquisa, busca o vídeo
        ydl = youtube_dl.YoutubeDL(YDL_OPTIONS)
        try:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)
            logging.info(f"Informações da pesquisa: {info}")
            if 'entries' in info and len(info['entries']) > 0:
                url = info['entries'][0]['url']
                title = info['entries'][0].get('title', 'Título desconhecido')
            else:
                await ctx.send('Nenhum vídeo encontrado para a pesquisa.')
                return
        except Exception as e:
            logging.error(f'Erro ao realizar a pesquisa: {e}')
            await ctx.send('Erro ao buscar vídeos.')
            return

    # Extrai informações do vídeo usando yt-dlp
    ydl = youtube_dl.YoutubeDL(YDL_OPTIONS)
    try:
        info = ydl.extract_info(url, download=False)
        logging.info(f"Informações do vídeo: {info}")
        if 'formats' in info:
            formats = info['formats']
            audio_formats = [f for f in formats if 'audio' in f['format']]
            if audio_formats:
                url2 = audio_formats[0]['url']
                title = info.get('title', 'Título desconhecido')
            else:
                await ctx.send('Não foi possível encontrar um stream de áudio.')
                return
        else:
            await ctx.send('Não foi possível extrair informações do áudio.')
            return
    except Exception as e:
        logging.error(f'Erro ao extrair informações: {e}')
        await ctx.send('Erro ao extrair informações do áudio.')
        return

    # Adiciona a URL à fila
    queue.append((url2, title))
    logging.info(f'URL do áudio adicionada à fila: {url2}')
    
    # Deleta a mensagem de comando
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        logging.error("Permissões insuficientes para deletar a mensagem.")
    
    # Reinicia o temporizador de inatividade
    if timeout_task:
        timeout_task.cancel()
    timeout_task = bot.loop.create_task(start_idle_timer(ctx))

    # Se não estiver tocando nada, começa a tocar a próxima música
    if not voice_client.is_playing() and not voice_client.is_paused():
        await play_next(ctx)

async def play_next(ctx):
    """Toca a próxima música da fila"""
    global timeout_task

    if queue:
        url2, title = queue.popleft()
        try:
            ctx.voice_client.stop()
            ctx.voice_client.play(discord.FFmpegPCMAudio(url2, **FFMPEG_OPTIONS), after=lambda e: bot.loop.create_task(play_next(ctx)))
            # Envia uma mensagem com o título do vídeo
            await ctx.send(f'Começando a tocar: {title}')
        except Exception as e:
            logging.error(f'Erro ao tentar tocar o áudio: {e}')
            await ctx.send('Ocorreu um erro ao tentar tocar o áudio.')
    else:
        await ctx.send("A fila está vazia.")

async def start_idle_timer(ctx):
    """Inicia um temporizador para desconectar o bot após um período de inatividade"""
    await asyncio.sleep(idle_timeout)
    if not voice_client.is_playing():
        await ctx.send("Desconectando devido à inatividade.")
        await voice_client.disconnect()
        queue.clear()  # Limpa a fila ao desconectar

@bot.command()
async def stop(ctx):
    """Comando para parar e desconectar do canal de voz"""
    global timeout_task

    if ctx.voice_client is not None:
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        queue.clear()  # Limpa a fila ao desconectar
        await ctx.send("Parado e desconectado do canal de voz.")
        if timeout_task:
            timeout_task.cancel()  # Cancela o temporizador de inatividade
    else:
        await ctx.send("Não estou conectado a nenhum canal de voz.")

bot.run(TOKEN)
