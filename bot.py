import os
import uuid
import asyncio
import logging
import yt_dlp
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

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

# Channel username (without @)
CHANNEL_USERNAME = "seidvideodownloaderbot"

# Create application
application = Application.builder().token(BOT_TOKEN).build()

# ==================== CHECK SUBSCRIPTION ====================

async def is_subscribed(user_id, context):
    """Check if user is subscribed to the channel"""
    try:
        chat_member = await context.bot.get_chat_member(
            chat_id=f"@{CHANNEL_USERNAME}", 
            user_id=user_id
        )
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        return False

async def send_subscription_request(update, context):
    """Send a message asking user to join channel"""
    keyboard = [
        [InlineKeyboardButton("Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton("I've Joined", callback_data="check_sub")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Please join my channels to use me, Due to overload only channel subscribers can use me!\n"
        "After joining just send me that link again to proceed!",
        reply_markup=reply_markup
    )

# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    
    # Check if user is subscribed
    if not await is_subscribed(user_id, context):
        await send_subscription_request(update, context)
        return
    
    welcome_text = (
        "What can this bot do?\n\n"
        "Download TikTok videos in telegram!\n\n"
        "Hello! I can download (Below 40 mb) Videos from TikTok, just send me the link here, i may take upto 2 minutes to send you the video."
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    user_id = update.effective_user.id
    
    # Check if user is subscribed
    if not await is_subscribed(user_id, context):
        await send_subscription_request(update, context)
        return
    
    await update.message.reply_text(
        "Help:\n\n"
        "Send a TikTok video link:\n"
        "https://www.tiktok.com/@username/video/xxxxx\n"
        "https://vt.tiktok.com/xxxxx\n\n"
        "For audio only, add 'audio' or 'mp3' after the link.\n\n"
        "Videos must be under 40MB\n"
        "May take up to 2 minutes"
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button press for subscription check"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if query.data == "check_sub":
        if await is_subscribed(user_id, context):
            await query.edit_message_text(
                "You are subscribed! Welcome to Seid Video Downloader.\n\n"
                "What can this bot do?\n\n"
                "Download TikTok videos in telegram!\n\n"
                "Hello! I can download (Below 40 mb) Videos from TikTok, just send me the link here, i may take upto 2 minutes to send you the video."
            )
        else:
            await query.edit_message_text(
                "You haven't joined the channel yet!\n\n"
                "Please join first then click 'I've Joined' again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")],
                    [InlineKeyboardButton("I've Joined", callback_data="check_sub")]
                ])
            )

async def download_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages"""
    text = update.message.text
    
    # Skip if it's a command
    if text.startswith('/'):
        return
    
    # Skip if no link
    if not text.startswith(("http://", "https://")):
        await update.message.reply_text(
            "No media found to download and send! If it's valid then maybe give a retry after 2-5 minutes!"
        )
        return
    
    # Check if user is subscribed
    user_id = update.effective_user.id
    if not await is_subscribed(user_id, context):
        await send_subscription_request(update, context)
        return
    
    # Only process TikTok links
    if 'tiktok.com' not in text.lower():
        await update.message.reply_text(
            "No media found to download and send! If it's valid then maybe give a retry after 2-5 minutes!"
        )
        return

    # Check for audio request
    audio_only = "audio" in text.lower() or "mp3" in text.lower()
    
    # Extract the URL (first word)
    raw_url = text.split()[0].strip()

    # Send processing message
    msg = await update.message.reply_text("Downloading TikTok video... Please wait up to 2 minutes.")

    unique_id = str(uuid.uuid4())[:8]
    output_template = f"dl_{unique_id}_%(id)s.%(ext)s"

    # ============ TIKTOK YT-DLP CONFIGURATION ============
    ydl_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'retries': 10,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'no_color': True,
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        },
        'extractor_args': {
            'tiktok': {
                'api_hostname': ['www.tiktok.com'],
            }
        }
    }

    # Format selection
    if audio_only:
        ydl_opts['format'] = 'bestaudio/best'
    else:
        ydl_opts['format'] = 'best[ext=mp4]/best'

    file_path = None
    file_size_mb = 0

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

        # Check file size
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            
            # Check if file is under 40MB
            if file_size > 40 * 1024 * 1024:  # 40MB in bytes
                await msg.edit_text(
                    f"Video is too large!\n\n"
                    f"Size: {file_size_mb:.1f}MB\n"
                    f"Limit: 40MB\n\n"
                    f"Please send a shorter TikTok video."
                )
                return

        await msg.edit_text("Uploading to Telegram...")

        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, 'rb') as media_file:
                if audio_only:
                    await update.message.reply_audio(
                        audio=media_file,
                        title=info_dict.get('title', 'TikTok Audio'),
                        performer=info_dict.get('uploader', 'TikTok'),
                        duration=info_dict.get('duration', 0)
                    )
                else:
                    await update.message.reply_video(
                        video=media_file,
                        caption=f"{info_dict.get('title', 'TikTok Video')}\n"
                                f"👤 {info_dict.get('uploader', 'Unknown')}\n"
                                f"📦 {file_size_mb:.1f}MB",
                        supports_streaming=True,
                        duration=info_dict.get('duration', 0)
                    )
            await msg.delete()
        else:
            await msg.edit_text("No media found to download and send! If it's valid then maybe give a retry after 2-5 minutes!")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error processing URL: {error_msg}")
        
        # User-friendly error messages (no ❌)
        if "rate-limit" in error_msg.lower():
            await msg.edit_text(
                "Rate limit reached!\n\n"
                "Please wait 2-5 minutes and try again."
            )
        elif "private" in error_msg.lower():
            await msg.edit_text(
                "This video is private.\n\n"
                "Please send a public TikTok video link."
            )
        else:
            await msg.edit_text(
                "No media found to download and send! If it's valid then maybe give a retry after 2-5 minutes!"
            )

    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

# ==================== REGISTER HANDLERS ====================

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CallbackQueryHandler(button_callback))
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
