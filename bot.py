import os
import asyncio
import logging
import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send custom welcome message when /start is issued."""
    await update.message.reply_html(
        "👋 Welcome to Seid Video Downloader!\n\n"
        "Send me any link from:\n"
        "• YouTube (Videos & Shorts)\n"
        "• TikTok (Videos)\n"
        "• Facebook (Videos & Reels)\n"
        "• Instagram (Reels & Posts)\n\n"
        "💡 Tip: Add 'audio' or 'mp3' after a YouTube link to download audio only!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message."""
    await update.message.reply_text("Just send me a direct link to any supported video platform.")

async def get_real_url(url: str) -> str:
    """Helper to clean and prepare URLs."""
    return url.strip()

async def download_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages containing video URLs."""
    text = update.message.text
    if not text or not text.startswith(("http://", "https://")):
        return

    # Check if audio only is requested
    audio_only = "audio" in text.lower() or "mp3" in text.lower()
    
    # Extract the actual URL
    raw_url = text.split()[0]

    msg = await update.message.reply_text("⏳ Processing your link, please wait...")

    url = await get_real_url(raw_url)
    output_template = "downloaded_media.%(ext)s"

    # Base options optimized for YouTube bypass
    ydl_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
        'retries': 10,
        'geo_bypass': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'mweb'],
                'skip': ['webpage', 'configs'],
            }
        },
    }

    # Format selector based on video vs audio request
    if audio_only:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

    # Check for cookies file
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    loop = asyncio.get_running_loop()

    try:
        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                if audio_only and not filename.endswith('.mp3'):
                    base, _ = os.path.splitext(filename)
                    filename = f"{base}.mp3"
                return info, filename

        info_dict, file_path = await loop.run_in_executor(None, extract)

        await msg.edit_text("⬆️ Uploading to Telegram...")

        with open(file_path, 'rb') as media_file:
            if audio_only:
                await update.message.reply_audio(
                    audio=media_file,
                    title=info_dict.get('title', 'Audio'),
                    performer=info_dict.get('uploader', 'Seid Downloader')
                )
            else:
                await update.message.reply_video(
                    video=media_file,
                    caption=info_dict.get('title', 'Downloaded Video'),
                    supports_streaming=True
                )

        await msg.delete()

        # Clean up local file
        if os.path.exists(file_path):
            os.remove(file_path)

    except Exception as e:
        logger.error(f"Error processing URL {url}: {e}")
        await msg.edit_text(f"❌ Download Error:\n{str(e)}")

def main():
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable is not set!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_and_send))

    logger.info("Bot starting polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
