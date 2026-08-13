import os
import uuid
import asyncio
import logging
import yt_dlp
from flask import Flask, request
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

# Bot token
BOT_TOKEN = "8629569320:AAFUXlbXdw4KzdVuD5TClFRQPDdfdVOtSQc"

# Create application
application = Application.builder().token(BOT_TOKEN).build()

# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 Welcome to Seid Video Downloader\n\n"
        "Download videos from:\n"
        "▶️ YouTube\n"
        "🎵 TikTok\n"
        "📘 Facebook\n"
        "📸 Instagram\n\n"
        "🎧 For audio only, add 'audio' or 'mp3' after the link.\n"
        "📎 Just paste ANY link to download instantly!"
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Help:\n\n"
        "Just send me ANY link from:\n"
        "• YouTube (Videos & Shorts)\n"
        "• TikTok (Videos)\n"
        "• Facebook (Videos & Reels)\n"
        "• Instagram (Reels & Posts)\n\n"
        "Add 'audio' or 'mp3' after the link for audio only!\n"
        "Example: https://youtube.com/watch?v=xxx mp3\n\n"
        "✅ One link = One download!"
    )

async def download_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    # Skip if it's a command
    if text.startswith('/'):
        return
    
    # Skip if no link
    if not text.startswith(("http://", "https://")):
        return

    # Check for audio request (only if user adds it)
    audio_only = "audio" in text.lower() or "mp3" in text.lower()
    
    # Extract the URL (first word)
    raw_url = text.split()[0].strip()

    # Send processing message
    msg = await update.message.reply_text("⚡ Downloading... Please wait.")

    unique_id = str(uuid.uuid4())[:8]
    output_template = f"dl_{unique_id}_%(id)s.%(ext)s"

    # ============ YT-DLP CONFIGURATION ============
    ydl_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'retries': 10,
        'nocheckcertificate': True,
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        }
    }

    # Instagram specific fixes
    if 'instagram.com' in raw_url.lower():
        ydl_opts['extractor_args'] = {
            'instagram': {
                'skip': ['dash', 'hls'],
                'api': ['mobile'],
            }
        }

    if audio_only:
        ydl_opts['format'] = 'bestaudio/best'
    else:
        ydl_opts['format'] = 'best[ext=mp4]/best'

    file_path = None

    try:
        # Run yt-dlp in a separate thread
        def run_ytdlp():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(raw_url, download=True)
                filename = ydl.prepare_filename(info)
                return info, filename

        # Run in executor
        loop = asyncio.get_event_loop()
        info_dict, file_path = await loop.run_in_executor(None, run_ytdlp)

        await msg.edit_text("⬆️ Uploading to Telegram...")

        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, 'rb') as media_file:
                if audio_only:
                    await update.message.reply_audio(
                        audio=media_file,
                        title=info_dict.get('title', 'Downloaded Audio'),
                        performer=info_dict.get('uploader', 'Seid Downloader'),
                        duration=info_dict.get('duration', 0)
                    )
                else:
                    await update.message.reply_video(
                        video=media_file,
                        caption=f"🎥 {info_dict.get('title', 'Video')}\n"
                                f"📺 {info_dict.get('uploader', 'Unknown')}",
                        supports_streaming=True,
                        duration=info_dict.get('duration', 0)
                    )
            await msg.delete()
        else:
            await msg.edit_text("❌ Download failed: File was empty.")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error processing URL: {error_msg}")
        
        # Provide user-friendly error messages
        if "rate-limit" in error_msg.lower() or "login required" in error_msg.lower():
            await msg.edit_text(
                "❌ This platform is blocking the download.\n\n"
                "Try these alternatives:\n"
                "1. Wait a few minutes and try again\n"
                "2. Use a different link\n"
                "3. Try YouTube or TikTok links\n\n"
                "📎 Send a different link to get started."
            )
        elif "copyright" in error_msg.lower():
            await msg.edit_text(
                "❌ This video is copyrighted and cannot be downloaded.\n\n"
                "Try a different video link."
            )
        else:
            await msg.edit_text(f"❌ Failed: {str(e)[:150]}")

    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

# ==================== REGISTER HANDLERS ====================

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_and_send))

# ==================== FLASK WEBHOOK ====================

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook updates."""
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        asyncio.run(application.process_update(update))
        return "ok", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return str(e), 500

@app.route('/')
def index():
    return "Bot is running!", 200

# ==================== MAIN ====================

if __name__ == '__main__':
    # Initialize application
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.initialize())
    
    # Set webhook
    render_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'seid-video-downloader.onrender.com')}/webhook"
    logger.info(f"Setting webhook to: {render_url}")
    
    loop.run_until_complete(application.bot.delete_webhook())
    loop.run_until_complete(application.bot.set_webhook(url=render_url))
    
    logger.info("Webhook set successfully!")
    loop.close()
    
    # Run Flask
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
