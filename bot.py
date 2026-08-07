import os
import uuid
import asyncio
import logging
import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variable setup
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a stylish welcome interface when /start is issued."""
    welcome_text = (
        "<b>✨ Welcome to Seid Media Downloader ✨</b>\n"
        "━━━━━━━ • ━━━━━━━\n\n"
        "⚡ <i>Fast & Free Social Media Video Downloader</i>\n\n"
        "<b>Supported Platforms:</b>\n"
        "📱 <b>TikTok</b> — Videos & Audio\n"
        "📸 <b>Instagram</b> — Reels & Posts\n"
        "🌐 <b>Facebook</b> — Public Videos & Reels\n\n"
        "<b>💡 How to use:</b>\n"
        "1. Simply paste your link here in the chat.\n"
        "2. Add <code>audio</code> or <code>mp3</code> after your link to get sound only!\n\n"
        "━━━━━━━ • ━━━━━━━\n"
        "🚀 <i>Send me a link to get started!</i>"
    )
    await update.message.reply_html(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends help instructions."""
    await update.message.reply_html(
        "<b>📖 Need Help?</b>\n\n"
        "Just copy any link from TikTok, Instagram, or Facebook and send it to me.\n"
        "Example: <code>https://vt.tiktok.com/example/ mp3</code>"
    )

async def download_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes incoming links from TikTok, Instagram, and Facebook."""
    text = update.message.text
    if not text or not text.startswith(("http://", "https://")):
        return

    # Check for audio request
    audio_only = "audio" in text.lower() or "mp3" in text.lower()
    raw_url = text.split()[0].strip()

    msg = await update.message.reply_text("⚡ <i>Processing link, please wait...</i>", parse_mode="HTML")

    # Unique file name generator prevents file collision issues
    unique_id = str(uuid.uuid4())[:8]
    output_template = f"dl_{unique_id}_%(id)s.%(ext)s"

    # Fully optimized yt-dlp configuration for Render backend environment
    ydl_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'retries': 5,
        'nocheckcertificate': True,
    }

    if audio_only:
        ydl_opts['format'] = 'bestaudio/best'
    else:
        ydl_opts['format'] = 'best[ext=mp4]/best'

    loop = asyncio.get_running_loop()
    file_path = None

    try:
        def run_ytdlp():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(raw_url, download=True)
                filename = ydl.prepare_filename(info)
                return info, filename

        info_dict, file_path = await loop.run_in_executor(None, run_ytdlp)

        await msg.edit_text("⬆️ <i>Uploading to Telegram...</i>", parse_mode="HTML")

        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, 'rb') as media_file:
                if audio_only:
                    await update.message.reply_audio(
                        audio=media_file,
                        title=info_dict.get('title', 'Downloaded Audio'),
                        performer=info_dict.get('uploader', 'Seid Downloader')
                    )
                else:
                    await update.message.reply_video(
                        video=media_file,
                        caption=f"🎥 <b>{info_dict.get('title', 'Video')}</b>",
                        parse_mode="HTML",
                        supports_streaming=True
                    )
            await msg.delete()
        else:
            await msg.edit_text("❌ Download failed: File was empty.")

    except Exception as e:
        logger.error(f"Error processing URL {raw_url}: {e}")
        await msg.edit_text(f"❌ <b>Download Failed:</b>\n<code>{str(e)}</code>", parse_mode="HTML")

    finally:
        # File cleanup
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable is not set!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_and_send))

    logger.info("Bot starting polling with auto-reconnect...")
    
    # Start polling with auto-reconnect and better error handling
    while True:
        try:
            # Clear any existing webhook that might interfere
            asyncio.run(application.bot.delete_webhook())
            
            # Start polling with reconnection settings
            application.run_polling(
                drop_pending_updates=True,  # Ignore old messages
                allowed_updates=["message"],  # Only process messages
                poll_interval=1.0,
                timeout=30,
                read_timeout=30,
                write_timeout=30,
                connect_timeout=30,
                pool_timeout=30
            )
        except Exception as e:
            logger.error(f"Polling error: {e}. Reconnecting in 5 seconds...")
            import time
            time.sleep(5)  # Wait before reconnecting
            continue  # Restart the loop
        break  # Exit if connection was successful and closed normally

if __name__ == '__main__':
    main()
