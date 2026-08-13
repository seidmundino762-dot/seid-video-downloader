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

# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_name = user.first_name if user.first_name else "User"
    
    # Professional welcome text exactly like the screenshot
    welcome_text = (
        f"Hello {user_name}! I can download (Below 40 mb) Videos from TikTok, just send me the link here, i may take upto 2 minutes to send you the video."
    )
    
    # Create START button (like in the professional example)
    keyboard = [
        [InlineKeyboardButton("📥 START", callback_data="start_download")],
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 How to use:\n\n"
        "1. Join our channel\n"
        "2. Send a TikTok video link\n"
        "3. Wait for download\n\n"
        "Example:\n"
        "https://www.tiktok.com/@username/video/xxxxx\n"
        "https://vt.tiktok.com/xxxxx\n\n"
        "Videos must be under 40MB."
    )

async def check_channel_membership(user_id):
    """Check if user is a member of the channel."""
    try:
        member = await application.bot.get_chat_member(
            chat_id=f"@{CHANNEL_USERNAME}", 
            user_id=user_id
        )
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking membership: {e}")
        return False

async def download_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    user_id = user.id
    
    # Skip if it's a command
    if text.startswith('/'):
        return
    
    # Skip if no link
    if not text.startswith(("http://", "https://")):
        await update.message.reply_text(
            "Please send a valid TikTok link."
        )
        return
    
    # Check if user is a channel member
    is_member = await check_channel_membership(user_id)
    
    if not is_member:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Please join my channels to use me, Due to overload only channel subscribers can use me!\nAfter joining just send me that link again to proceed!",
            reply_markup=reply_markup
        )
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
    msg = await update.message.reply_text("⚡ Processing your TikTok video... Please wait.")

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

        # Check file size (max 40MB)
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            
            if file_size > 40 * 1024 * 1024:  # 40MB in bytes
                await msg.edit_text(
                    f"Video is too large! Size: {file_size_mb:.1f}MB, Limit: 40MB. Please send a shorter TikTok video."
                )
                return

        await msg.edit_text("⬆️ Uploading to Telegram...")

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
                        caption=f"🎵 {info_dict.get('title', 'TikTok Video')}",
                        supports_streaming=True,
                        duration=info_dict.get('duration', 0)
                    )
            await msg.delete()
        else:
            await msg.edit_text("Download failed: File was empty.")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error processing URL: {error_msg}")
        
        if "rate-limit" in error_msg.lower():
            await msg.edit_text(
                "Rate limit reached! Please wait 2-3 minutes and try again."
            )
        elif "private" in error_msg.lower():
            await msg.edit_text(
                "This video is private. Please send a public TikTok video link."
            )
        else:
            await msg.edit_text(
                f"Download Failed: {error_msg[:150]}"
            )

    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

# ==================== CALLBACK HANDLER ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "start_download":
        await query.edit_message_text(
            "Send me a TikTok video link to download.\n\n"
            "Example:\n"
            "https://www.tiktok.com/@username/video/xxxxx\n"
            "https://vt.tiktok.com/xxxxx\n\n"
            "Videos must be under 40MB."
        )
    else:
        user_id = query.from_user.id
        is_member = await check_channel_membership(user_id)
        
        if is_member:
            await query.edit_message_text(
                "You have joined the channel! Now send me a TikTok link to download."
            )
        else:
            await query.edit_message_text(
                "Please join the channel first using the button above, then send your link."
            )

# ==================== REGISTER HANDLERS ====================

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_and_send))
application.add_handler(CallbackQueryHandler(button_callback))

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
