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
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}!\n\n"
        "Send me a video link from YouTube, TikTok, Instagram, Facebook, or Twitter, and I will download it for you!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Just send me a direct link to any supported video platform.")

async def get_real_url(url: str) -> str:
    """Helper to un-shorten links or strip tracking query parameters."""
    return url.strip()

async def download_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages containing video URLs."""
    raw_url = update.message.text
    if not raw_url or not raw_url.startswith(("http://", "https://")):
        return

    msg = await update.message.reply_text("⏳ Processing your link, please wait...")

    url = await get_real_url(raw_url)
    output_template = "downloaded_media.%(ext)s"

    # Base options configured with cookies and client overrides
    base_ydl_opts = {
        'cookiefile': 'cookies.txt',
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios'],
            }
        },
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
        'retries': 5,
        'geo_bypass': True,
    }

    loop = asyncio.get_running_loop()

    try:
        def extract():
            with yt_dlp.YoutubeDL(base_ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                return info, filename

        info_dict, file_path = await loop.run_in_executor(None, extract)

        await msg.edit_text("⬆️ Uploading video to Telegram...")

        with open(file_path, 'rb') as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=info_dict.get('title', 'Downloaded Video'),
                supports_streaming=True
            )

        await msg.delete()

        # Clean up local file after sending
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
