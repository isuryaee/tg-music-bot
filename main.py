import asyncio
import logging
import requests
import yt_dlp
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Config ---
BOT_TOKEN = os.getenv("BOT_TOKEN")  # We'll set this in Render
DEFAULT_COUNTRY = "IN"
SEARCH_LIMIT = 5
# ---------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HybridBot")

# -------- iTunes Search --------
def itunes_search_sync(query, country=DEFAULT_COUNTRY, limit=SEARCH_LIMIT):
    url = "https://itunes.apple.com/search"
    params = {
        "term": query,
        "media": "music",
        "entity": "song",
        "country": country,
        "limit": limit
    }
    r = requests.get(url, params=params, timeout=10)
    return r.json().get("results", [])


async def itunes_search(query, country=DEFAULT_COUNTRY, limit=SEARCH_LIMIT):
    return await asyncio.to_thread(itunes_search_sync, query, country, limit)

# -------- YouTube Download --------
def download_youtube_audio(query):
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": "song.%(ext)s",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }],
        "quiet": True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"ytsearch:{query}"])
    return "song.mp3"

# -------- Bot Handlers --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🎵 Welcome! Send /search <song name> to find music.\n\n"
        "Example: /search kesariya"
    )
    await update.message.reply_text(msg)


def build_keyboard(tracks):
    buttons = []
    for t in tracks:
        title = t.get("trackName", "Unknown")
        artist = t.get("artistName", "Unknown")
        track_id = t.get("trackId")
        label = f"{title} - {artist}"
        if len(label) > 50:
            label = label[:47] + "…"
        buttons.append([InlineKeyboardButton(label, callback_data=f"it:{track_id}")])
    return InlineKeyboardMarkup(buttons)


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: /search <song name>")
        return

    await update.message.reply_text(f"🔍 Searching for: {query}")

    tracks = await itunes_search(query)
    if not tracks:
        await update.message.reply_text("No results found.")
        return

    context.user_data["tracks"] = {str(t["trackId"]): t for t in tracks}
    await update.message.reply_text("Select a track:", reply_markup=build_keyboard(tracks))


async def on_track_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("it:"):
        return

    track_id = data.split(":")[1]
    tracks = context.user_data.get("tracks", {})
    track = tracks.get(track_id)

    if not track:
        await query.edit_message_text("Track not found.")
        return

    title = track.get("trackName", "Unknown")
    artist = track.get("artistName", "Unknown")
    album = track.get("collectionName", "Unknown")
    artwork = track.get("artworkUrl100", "")
    caption = f"<b>{title}</b>\n👤 {artist}\n💽 {album}"

    await query.edit_message_text(f"🎧 Downloading full song: {title}...")

    try:
        # Download from YouTube
        audio_path = await asyncio.to_thread(download_youtube_audio, f"{title} {artist}")
        # Send artwork if available
        if artwork:
            artwork = artwork.replace("100x100bb.jpg", "600x600bb.jpg")
            await query.message.chat.send_photo(photo=artwork, caption=caption, parse_mode=ParseMode.HTML)

# Send audio
        await query.message.chat.send_audio(audio=open(audio_path, "rb"), title=title, performer=artist)
        os.remove(audio_path)
    except Exception as e:
        logger.error(f"Error downloading: {e}")
        await query.message.chat.send_message("❌ Failed to download song.")

# -------- Main --------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CallbackQueryHandler(on_track_select))

    app.run_polling()


if __name__ == "__main__":
    main()
