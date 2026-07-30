import os
import uuid
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

async def download_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages containing video URLs."""
    text = update.message.text
    if not text or not text.startswith(("http://", "https://")):
        return

    # Check if audio only is requested
    audio_only = "audio" in text.lower() or "mp3" in text.lower()
    
    # Extract the actual URL
    raw_url = text.split()[0].strip()

    msg = await update.message.reply_text("⏳ Processing your link, please wait...")

    # Unique output pattern prevents collision & HTTP 416 errors on cloud environments
    unique_id = str(uuid.uuid4())[:8]
    output_template = f"download_{unique_id}_%(id)s.%(ext)s"

    # Base configuration incorporating the screenshot's 720p limit + anti-bot client emulation
    ydl_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
        'retries': 10,
        'geo_bypass': True,
        'nocheckcertificate': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'mweb'],
            }
        },
    }

    # Format logic from your screenshot adapted for fast processing
    if audio_only:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }]
    else:
        ydl_opts['format'] = 'best[height<=720]/bestvideo[height<=720]+bestaudio/best'

    # Check for cookies file if available
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    loop = asyncio.get_running_loop()
    file_path = None

    try:
        def run_ytdlp():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(raw_url, download=True)
                filename = ydl.prepare_filename(info)
                
                # Adjust extension if FFmpeg extracted audio to mp3
                if audio_only:
                    base, _ = os.path.splitext(filename)
                    filename = f"{base}.mp3"
                return info, filename

        info_dict, file_path = await loop.run_in_executor(None, run_ytdlp)

        await msg.edit_text("⬆️ Uploading to Telegram...")

        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
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
        else:
            await msg.edit_text("❌ Download failed: File was empty or missing.")

    except Exception as e:
        logger.error(f"Error processing URL {raw_url}: {e}")
        await msg.edit_text(f"❌ Download Error:\n{str(e)}")

    finally:
        # Clean up temporary download file
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

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
