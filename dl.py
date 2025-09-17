# index.py
import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TelegramError
import yt_dlp
import re

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_TOKEN = '8243320098:AAHqd_U3v9pROsBUQRPxTZOGoQoEjCFkczM'  # Replace with your bot token
REQUIRED_GROUP_USERNAME = 'tamaynonee'  # Replace with your group username (without @)
REQUIRED_GROUP_ID = -1002886005749  # Replace with your group chat ID (e.g., -100xxxxxxxxxx)
GROUP_INVITE_LINK = f'https://t.me/{REQUIRED_GROUP_USERNAME}'
DOWNLOAD_DIR = 'downloads'
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB limit for Telegram uploads

# Ensure download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Regex patterns for links
YOUTUBE_PATTERN = re.compile(r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[a-zA-Z0-9_-]{11})')
SOUNDCLOUD_PATTERN = re.compile(r'(https?://(?:www\.)?soundcloud\.com/(?:[^/]+/[^/]+|sets/[^/]+|playlists/[^/]+))')
INSTAGRAM_PATTERN = re.compile(r'(https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[a-zA-Z0-9_-]+)')
TELEGRAM_STORY_PATTERN = re.compile(r'(https?://t\.me/(?:[^/]+/\d+|[^/]+/s/\d+))')  # For story links or post links

# yt-dlp base options
YDL_OPTS_BASE = {
    'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
    'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'continuedl': True,
    'restrictfilenames': True,
}

async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is member of required group."""
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(REQUIRED_GROUP_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except TelegramError as e:
        logger.error(f"Membership check error: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    if not await check_membership(update, context):
        keyboard = [[InlineKeyboardButton("Join Group", url=GROUP_INVITE_LINK)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            'You must join the group first to use this bot! Click the button below:',
            reply_markup=reply_markup
        )
        return

    keyboard = [
        [InlineKeyboardButton("🎵 SoundCloud", callback_data='sc_help')],
        [InlineKeyboardButton("📺 YouTube", callback_data='yt_help')],
        [InlineKeyboardButton("📸 Instagram", callback_data='ig_help')],
        [InlineKeyboardButton("📱 Telegram Story", callback_data='tg_help')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        'Welcome to the Ultimate Downloader Bot! 🚀\n\n'
        'Supported platforms:\n'
        '- SoundCloud songs (audio)\n'
        '- YouTube videos (video/audio)\n'
        '- Instagram reels/posts (video)\n'
        '- Telegram stories (forward the story message)\n\n'
        'Send a link or forward a story to start downloading.\n'
        'Choose an option for help:',
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()

    if not await check_membership(update, context):
        keyboard = [[InlineKeyboardButton("Join Group", url=GROUP_INVITE_LINK)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            'You must join the group first to use this bot! Click the button below:',
            reply_markup=reply_markup
        )
        return

    data = query.data
    help_texts = {
        'sc_help': '🎵 SoundCloud:\nSend a track or set link (e.g., https://soundcloud.com/artist/track). Downloads as MP3.',
        'yt_help': '📺 YouTube:\nSend a video link (e.g., https://youtube.com/watch?v=...). Downloads video up to 720p.',
        'ig_help': '📸 Instagram:\nSend a post/reel link (e.g., https://instagram.com/reel/...). Downloads video.',
        'tg_help': '📱 Telegram Story:\nForward the story message to the bot. It will download the media (video/photo). Note: Direct links may not work; forwarding is recommended.',
    }
    if data in help_texts:
        await query.edit_message_text(help_texts[data])

async def download_with_yt_dlp(url: str, is_audio_only: bool = False) -> tuple[str, str]:
    """Download media using yt-dlp."""
    try:
        ydl_opts = YDL_OPTS_BASE.copy()
        if is_audio_only:
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if is_audio_only:
                filename = f"{os.path.splitext(filename)[0]}.mp3"

        file_size = os.path.getsize(filename)
        if file_size > MAX_FILE_SIZE:
            os.remove(filename)
            return None, f"File too large ({file_size / 1024 / 1024:.2f} MB > 50 MB). Try lower quality."

        return filename, None
    except Exception as e:
        logger.error(f"yt-dlp error: {e}")
        return None, f"Error downloading: {str(e)}"

async def handle_telegram_media(update: Update, context: ContextTypes.DEFAULT_TYPE, message: Update.message) -> None:
    """Handle forwarded Telegram media (stories/posts)."""
    if message.photo:
        photo = message.photo[-1]  # Highest resolution
        file = await photo.get_file()
        ext = 'jpg'
    elif message.video:
        file = await message.video.get_file()
        ext = 'mp4'
    elif message.document:
        file = await message.document.get_file()
        ext = message.document.file_name.split('.')[-1] if '.' in message.document.file_name else 'file'
    else:
        await message.reply_text("No downloadable media found in the forwarded message.")
        return

    filename = os.path.join(DOWNLOAD_DIR, f"telegram_media.{ext}")
    await file.download_to_drive(filename)  # Note: In v20+, it's download(custom_path=filename)

    file_size = os.path.getsize(filename)
    if file_size > MAX_FILE_SIZE:
        os.remove(filename)
        await message.reply_text("File too large to send back (>50 MB).")
        return

    try:
        if message.photo:
            await message.reply_photo(open(filename, 'rb'))
        elif message.video:
            await message.reply_video(open(filename, 'rb'))
        elif message.document:
            await message.reply_document(open(filename, 'rb'))
    except Exception as e:
        await message.reply_text(f"Error sending file: {e}")
    finally:
        os.remove(filename)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages with links or forwards."""
    message = update.message
    if not await check_membership(update, context):
        await message.reply_text('Please join the required group first! Use /start.')
        return

    text = message.text or message.caption or ""
    url_match = None
    platform = None
    is_audio_only = False

    # Check for forwards first (Telegram stories)
    if message.forward_date:  # More reliable for forwards
        await message.reply_text("Processing forwarded Telegram media... ⏳")
        await handle_telegram_media(update, context, message)
        return

    # Extract URL from text
    if YOUTUBE_PATTERN.search(text):
        url_match = YOUTUBE_PATTERN.search(text).group(0)
        platform = 'YouTube'
    elif SOUNDCLOUD_PATTERN.search(text):
        url_match = SOUNDCLOUD_PATTERN.search(text).group(0)
        platform = 'SoundCloud'
        is_audio_only = True
    elif INSTAGRAM_PATTERN.search(text):
        url_match = INSTAGRAM_PATTERN.search(text).group(0)
        platform = 'Instagram'
    elif TELEGRAM_STORY_PATTERN.search(text):
        url_match = TELEGRAM_STORY_PATTERN.search(text).group(0)
        platform = 'Telegram'
        await message.reply_text("Direct Telegram links may not be downloadable. Please forward the story message instead.")
        return  # Skip download for direct TG links as yt-dlp doesn't support

    if not url_match:
        await message.reply_text("Please send a valid link from supported platforms or forward a Telegram story.")
        return

    await message.reply_text(f"Downloading from {platform}... ⏳")

    filename, error = await download_with_yt_dlp(url_match, is_audio_only)

    if error:
        await message.reply_text(error)
        if filename:
            os.remove(filename)
        return

    try:
        with open(filename, 'rb') as f:
            if is_audio_only:
                await message.reply_audio(f, filename=os.path.basename(filename))
            else:
                await message.reply_video(f, filename=os.path.basename(filename))
    except TelegramError as e:
        await message.reply_text(f"Error sending file: {e}")
    finally:
        os.remove(filename)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))  # Handle all messages except commands

    # Error handler
    application.add_error_handler(error_handler)

    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
