import os
import uuid
import asyncio
import logging
import yt_dlp
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Initialize Flask
app = Flask(__name__)

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variable setup
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Initialize Application
application = Application.builder().token(BOT_TOKEN).build()

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

# Add handlers to application
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_and_send))

@app.route('/webhook', methods=['POST'])
async def webhook():
    """Handle incoming webhook updates from Telegram."""
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
        return "ok", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return str(e), 500

@app.route('/')
def index():
    """Health check endpoint."""
    return "Bot is running!", 200

if __name__ == '__main__':
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable is not set!")
        exit(1)
    
    # Set webhook on Render URL
    render_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')}/webhook"
    
    logger.info(f"Setting webhook to: {render_url}")
    
    # Delete any existing webhook and set new one
    asyncio.run(application.bot.delete_webhook())
    asyncio.run(application.bot.set_webhook(url=render_url))
    
    logger.info("Webhook set successfully!")
    
    # Start Flask server
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
