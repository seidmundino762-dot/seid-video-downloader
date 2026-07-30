import os
import re
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import httpx
from urllib.parse import urlparse, urlunparse
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
import yt_dlp

TOKEN = os.environ.get("BOT_TOKEN", "8629569320:AAFUXlbXdw4KzdVuD5TClFRQPDdfdVOtSQc")

# Permanent File Storage for Stats
USER_FILE = "users.txt"

def load_users() -> set:
    if os.path.exists(USER_FILE):
        with open(USER_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_user(user_id: int):
    users = load_users()
    if str(user_id) not in users:
        with open(USER_FILE, "a") as f:
            f.write(f"{user_id}\n")

# Health Check HTTP Server for Render
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

def clean_url(url: str) -> str:
    parsed = urlparse(url)
    if "facebook.com" in parsed.netloc or "fb.watch" in parsed.netloc or "instagram.com" in parsed.netloc:
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
    return url

async def get_real_url(url: str) -> str:
    url = clean_url(url)
    if "facebook.com/share/" in url or "fb.watch/" in url:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                res = await client.head(url, headers=headers)
                return clean_url(str(res.url))
        except Exception:
            pass
    return url

def clean_error_message(error_str: str) -> str:
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    cleaned = ansi_escape.sub('', str(error_str))
    cleaned = re.sub(r'\[\d+;\d+m', '', cleaned)
    return cleaned.strip()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        save_user(update.effective_user.id)
        
    await update.message.reply_text(
        "👋 Welcome to Seid Video Downloader!\n\n"
        "Send me any link from:\n"
        "• YouTube (Videos & Shorts)\n"
        "• TikTok (Videos)\n"
        "• Facebook (Videos & Reels)\n"
        "• Instagram (Reels & Posts)\n\n"
        "💡 Tip: Add 'audio' or 'mp3' after a link to download audio only!"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    total_users = len(users)
    await update.message.reply_text(f"📊 Total unique users tracked: {total_users}")

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        save_user(update.effective_user.id)

    text = update.message.text.strip()
    
    if not text.startswith(('http://', 'https://')):
        return

    audio_only = "audio" in text.lower() or "mp3" in text.lower()
    raw_url = text.split()[0]

    if "/photo/" in raw_url:
        await update.message.reply_text("⚠️ This is a TikTok Photo Slideshow. Please send a direct TikTok Video link instead!")
        return

    msg = await update.message.reply_text("⏳ Processing link... downloading media...")

    url = await get_real_url(raw_url)
    output_template = "downloaded_media.%(ext)s"

    # Base options safe for ALL platforms
    base_ydl_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
        'retries': 5,
        'geo_bypass': True,
        'no_color': True,
    }

    # Platform Routing Logic
    is_youtube = "youtube.com" in url.lower() or "youtu.be" in url.lower()

    if is_youtube:
        # YouTube Specific Workarounds
        base_ydl_opts['extractor_args'] = {
            'youtube': {
                'player_client': ['mweb', 'android', 'web']
            }
        }
        if audio_only:
            base_ydl_opts['format'] = 'bestaudio/best'
            base_ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }]
        else:
            base_ydl_opts['format'] = 'best[height<=720]/bestvideo[height<=720]+bestaudio/best'
    else:
        # Non-YouTube Platforms (TikTok, IG, FB)
        if audio_only:
            base_ydl_opts['format'] = 'bestaudio/best'
            base_ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }]
        else:
            base_ydl_opts['format'] = 'best/bestvideo+bestaudio'

    loop = asyncio.get_running_loop()

    def run_ytdlp():
        with yt_dlp.YoutubeDL(base_ydl_opts) as ydl:
            ydl.download([url])

    try:
        await loop.run_in_executor(None, run_ytdlp)

        downloaded_file = None
        for file in os.listdir('.'):
            if file.startswith("downloaded_media."):
                if os.path.exists(file) and os.path.getsize(file) > 0:
                    downloaded_file = file
                    break
                else:
                    try:
                        os.remove(file)
                    except Exception:
                        pass

        if downloaded_file:
            await msg.edit_text("📤 Uploading to Telegram...")
            
            with open(downloaded_file, 'rb') as media:
                if audio_only or downloaded_file.endswith('.mp3'):
                    await update.message.reply_audio(audio=media, write_timeout=300, read_timeout=300)
                else:
                    try:
                        await update.message.reply_video(video=media, write_timeout=300, read_timeout=300)
                    except Exception:
                        await update.message.reply_document(document=media, write_timeout=300, read_timeout=300)

            os.remove(downloaded_file)
            await msg.delete()
        else:
            await msg.edit_text("❌ Could not download this media. Please ensure the post is public.")

    except Exception as e:
        clean_err = clean_error_message(str(e))
        await msg.edit_text(f"❌ Download Error:\n{clean_err}")
        for file in os.listdir('.'):
            if file.startswith("downloaded_media."):
                try:
                    os.remove(file)
                except Exception:
                    pass

def main():
    threading.Thread(target=run_health_check_server, daemon=True).start()

    request = HTTPXRequest(connect_timeout=60.0, read_timeout=300.0, write_timeout=300.0)
    app = Application.builder().token(TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_media))

    print("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
