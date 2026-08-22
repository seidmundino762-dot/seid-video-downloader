import os
import uuid
import asyncio
import logging
import yt_dlp
import time
import threading
import requests
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

# ============ KEEP-ALIVE SERVICE ============
def keep_alive():
    while True:
        try:
            url = "https://seid-video-downloader.onrender.com"
            requests.get(url, timeout=10)
            time.sleep(300)
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
            time.sleep(60)

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()
logger.info("Keep-alive service started!")

# Bot token
BOT_TOKEN = "8629569320:AAFUXlbXdw4KzdVuD5TClFRQPDdfdVOtSQc"

# Channel username
CHANNEL_USERNAME = "TechWithSeidOfficial"

# Verified users cache (persists across restarts)
verified_users = set()

def load_verified_users():
    try:
        if os.path.exists("verified_users.txt"):
            with open("verified_users.txt", 'r') as f:
                return set(line.strip() for line in f if line.strip())
    except Exception as e:
        logger.error(f"Error loading verified users: {e}")
    return set()

verified_users = load_verified_users()
logger.info(f"Loaded {len(verified_users)} verified users")

def save_verified_users():
    try:
        with open("verified_users.txt", 'w') as f:
            for user_id in verified_users:
                f.write(f"{user_id}\n")
    except Exception as e:
        logger.error(f"Error saving verified users: {e}")

# Membership cache
membership_cache = {}
CACHE_DURATION = 300

async def check_channel_membership_fast(user_id):
    # Check cache first
    if user_id in membership_cache:
        cached_time, is_member = membership_cache[user_id]
        if time.time() - cached_time < CACHE_DURATION:
            return is_member
    
    try:
        try:
            member = await application.bot.get_chat_member(
                chat_id=f"@{CHANNEL_USERNAME}", 
                user_id=int(user_id)
            )
            is_member = member.status in ['member', 'administrator', 'creator']
            membership_cache[user_id] = (time.time(), is_member)
            return is_member
        except Exception as e:
            logger.warning(f"Quick check failed: {e}")
        
        try:
            chat = await application.bot.get_chat(f"@{CHANNEL_USERNAME}")
            member = await application.bot.get_chat_member(
                chat_id=chat.id, 
                user_id=int(user_id)
            )
            is_member = member.status in ['member', 'administrator', 'creator']
            membership_cache[user_id] = (time.time(), is_member)
            return is_member
        except Exception as e:
            logger.error(f"Fallback failed: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error checking membership: {e}")
        return False

# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_name = user.first_name if user.first_name else "User"
    user_id = str(user.id)
    message_id = update.message.message_id
    
    # Check if user is already verified (in memory or file)
    is_verified = user_id in verified_users
    
    # If not verified, check channel membership
    if not is_verified:
        is_member = await check_channel_membership_fast(user_id)
        if is_member:
            verified_users.add(user_id)
            save_verified_users()
            logger.info(f"User {user_id} verified and saved")
            is_verified = True
    
    # Build welcome text
    welcome_text = (
        f"Hello {user_name}! I can download (Below 50 mb) Videos from TikTok, just send me the link here, i may take a few minutes to send you the video."
    )
    
    # Build keyboard based on verification status
    keyboard = [
        [InlineKeyboardButton("📥 START", callback_data="start_download")]
    ]
    
    # Only show Join Channel button if NOT verified
    if not is_verified:
        keyboard.append([InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        reply_to_message_id=message_id
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 How to use:\n\n"
        "1. Join our channel\n"
        "2. Send a TikTok video link\n"
        "3. Wait for download\n\n"
        "Videos must be under 50MB."
    )

async def download_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    user_id = str(user.id)
    message_id = update.message.message_id
    
    if text.startswith('/'):
        return
    
    if not text.startswith(("http://", "https://")):
        await update.message.reply_text(
            "Please send a valid TikTok link.",
            reply_to_message_id=message_id
        )
        return
    
    # ============ VERIFICATION: Check once, save forever ============
    if user_id not in verified_users:
        is_member = await check_channel_membership_fast(user_id)
        if is_member:
            verified_users.add(user_id)
            save_verified_users()
            logger.info(f"User {user_id} verified and saved during download")
        else:
            keyboard = [[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Please join my channels to use me, Due to overload only channel subscribers can use me!\nAfter joining just send me that link again to proceed!",
                reply_markup=reply_markup,
                reply_to_message_id=message_id
            )
            return
    
    # ============ NOW USER IS VERIFIED - DOWNLOAD ============
    if 'tiktok.com' not in text.lower():
        await update.message.reply_text(
            "No media found to download and send! If it's valid then maybe give a retry after 2-5 minutes!",
            reply_to_message_id=message_id
        )
        return

    audio_only = "audio" in text.lower() or "mp3" in text.lower()
    raw_url = text.split()[0].strip()

    start_time = time.time()

    msg = await update.message.reply_text(
        "⚡ Processing... Please wait.",
        reply_to_message_id=message_id
    )

    unique_id = str(uuid.uuid4())[:8]
    output_template = f"dl_{unique_id}_%(id)s.%(ext)s"

    ydl_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 15,
        'retries': 2,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'no_color': True,
        'format': 'best[ext=mp4]/best',
        'concurrent_fragment_downloads': 10,
        'http_chunk_size': 10485760,
        'throttledratelimit': 100000,
        'fragment_retries': 2,
        'skip_download': False,
        'buffersize': 10485760,
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
        },
        'extractor_args': {
            'tiktok': {
                'api_hostname': ['www.tiktok.com'],
            }
        }
    }

    if audio_only:
        ydl_opts['format'] = 'bestaudio/best'

    file_path = None

    try:
        def run_ytdlp():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(raw_url, download=True)
                filename = ydl.prepare_filename(info)
                return info, filename

        loop = asyncio.get_event_loop()
        info_dict, file_path = await loop.run_in_executor(None, run_ytdlp)

        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            if file_size > 50 * 1024 * 1024:
                await msg.edit_text(
                    f"❌ Video is too large!\n"
                    f"Size: {file_size_mb:.1f}MB\n"
                    f"Limit: 50MB\n\n"
                    f"Please send a shorter TikTok video."
                )
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
                return

        await msg.edit_text("⬆️ Uploading...")

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
                        caption=f"🎵 {info_dict.get('title', 'TikTok Video')}\n"
                                f"👤 {info_dict.get('uploader', 'Unknown')}\n"
                                f"📦 {file_size_mb:.1f}MB",
                        supports_streaming=True,
                        duration=info_dict.get('duration', 0)
                    )
            await msg.delete()
            
            elapsed = time.time() - start_time
            logger.info(f"Download completed in {elapsed:.1f} seconds")
        else:
            await msg.edit_text("Download failed: File was empty.")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error: {error_msg}")
        
        if "rate-limit" in error_msg.lower():
            await msg.edit_text(
                "⏳ Rate limit reached!\n"
                "Please wait 2-3 minutes and try again."
            )
        elif "private" in error_msg.lower():
            await msg.edit_text(
                "🔒 This video is private.\n"
                "Please send a public TikTok video link."
            )
        else:
            await msg.edit_text(f"❌ Download Failed: {error_msg[:150]}")

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
    
    user_id = str(query.from_user.id)
    user_name = query.from_user.first_name if query.from_user.first_name else "User"
    
    # If already verified, show download instructions
    if user_id in verified_users:
        await query.edit_message_text(
            f"Send me a TikTok video link to download.\n\n"
            f"Videos must be under 50MB."
        )
        return
    
    # Check channel membership
    is_member = await check_channel_membership_fast(user_id)
    if is_member:
        verified_users.add(user_id)
        save_verified_users()
        await query.edit_message_text(
            f"✅ You are verified {user_name}!\n\n"
            f"Send me a TikTok video link to download.\n"
            f"Videos must be under 50MB."
        )
    else:
        keyboard = [[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Hello {user_name}! Please join my channel to use me!\n"
            f"After joining click START again to proceed.",
            reply_markup=reply_markup
        )

# ==================== REGISTER HANDLERS ====================

application = Application.builder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_and_send))
application.add_handler(CallbackQueryHandler(button_callback))

# ==================== FLASK WEBHOOK ====================

@app.route('/webhook', methods=['POST'])
def webhook():
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
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.initialize())
    
    render_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'seid-video-downloader.onrender.com')}/webhook"
    logger.info(f"Setting webhook to: {render_url}")
    
    loop.run_until_complete(application.bot.delete_webhook())
    loop.run_until_complete(application.bot.set_webhook(url=render_url))
    
    logger.info("Webhook set successfully!")
    loop.close()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
