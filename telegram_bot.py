# telegram_bot.py

import os
import time
import asyncio
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from state import manual_stream, presets, save_state
from youtube import fetch_channel_streams, set_channel_id

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID")
if ALLOWED_USER_ID:
    try:
        ALLOWED_USER_ID = int(ALLOWED_USER_ID)
    except ValueError:
        ALLOWED_USER_ID = None

def restricted(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
            print(f"Unauthorized access attempt by user {user_id}")
            if update.message:
                await update.message.reply_text(f"❌ Unauthorized. Your User ID: {user_id}")
            elif update.callback_query:
                await update.callback_query.answer(f"❌ Unauthorized (ID: {user_id})", show_alert=True)
            return
        return await func(update, context)
    return wrapper

def update_env_file(key: str, value: str):
    env_path = ".env"
    if not os.path.exists(env_path):
        with open(env_path, "w") as f:
            f.write(f"{key}={value}\n")
        return

    with open(env_path, "r") as f:
        lines = f.readlines()

    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    
    if not found:
        lines.append(f"{key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(lines)

# ---------- UI ----------

def main_menu():
    keyboard = [
        [InlineKeyboardButton("▶ Play Manual", callback_data="play"), InlineKeyboardButton("📡 Channel Streams", callback_data="channel_streams")],
        [InlineKeyboardButton("🔖 Manage Presets", callback_data="manage_presets")],
        [InlineKeyboardButton("🆔 Set Channel ID", callback_data="set_channel"), InlineKeyboardButton("⏹ Stop Stream", callback_data="stop")],
        [InlineKeyboardButton("📺 Status", callback_data="status"), InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ---------- Commands ----------

@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📺 TV Stream Controller\n\n"
        "🎯 Features:\n"
        "• Play custom streams (YouTube, M3U8, etc.)\n"
        "• View channel livestreams\n"
        "• Control stream playback\n"
        "• Configure YouTube Channel ID\n\n"
        "Use the buttons below 👇",
        reply_markup=main_menu()
    )

@restricted
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📺 TV Stream Controller - Help\n\n"
        "▶ Play Custom URL – Enter a YouTube or live stream URL\n"
        "📡 Channel Streams – Fetch and select livestreams from the configured channel\n"
        "⏹ Stop Stream – Stop the current manual stream\n"
        "📺 Status – Show current stream status\n\n"
        "Commands:\n"
        "/start – Show main menu\n"
        "/help – Show this help message\n",
        reply_markup=main_menu()
    )

# ---------- Button Actions ----------

@restricted
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "play":
        context.user_data["awaiting_url"] = True
        context.user_data["awaiting_channel_id"] = False
        
        keyboard = []
        # Dynamic Presets
        for idx, preset in enumerate(presets):
            keyboard.append([InlineKeyboardButton(f"📺 {preset['title']}", callback_data=f"play_preset_{idx}")])
        
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back")])
        
        await query.message.reply_text(
            "📥 Send a YouTube or live stream URL\n"
            "OR select a quick preset below:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("play_preset_"):
        idx = int(query.data.replace("play_preset_", ""))
        if 0 <= idx < len(presets):
            preset = presets[idx]
            manual_stream["enabled"] = True
            manual_stream["url"] = preset["url"]
            manual_stream["title"] = preset["title"]
            manual_stream["updated_at"] = int(time.time())
            save_state()
            
            await query.message.reply_text(
                f"✅ Playing: {preset['title']}\n\n🔗 {preset['url']}",
                reply_markup=main_menu()
            )

    elif query.data == "manage_presets":
        keyboard = [
            [InlineKeyboardButton("➕ Add Preset", callback_data="add_preset")],
            [InlineKeyboardButton("🗑 Delete Preset", callback_data="list_delete_presets")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back")]
        ]
        
        text = "🔖 Saved Presets:\n\n"
        if not presets:
            text += "No presets saved."
        for p in presets:
            text += f"• {p['title']}\n"
            
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "add_preset":
        context.user_data["awaiting_preset_url"] = True
        await query.message.reply_text("📥 Send the URL for the new preset:")

    elif query.data == "list_delete_presets":
        if not presets:
            await query.message.reply_text("No presets to delete.", reply_markup=main_menu())
            return
            
        keyboard = []
        for idx, p in enumerate(presets):
            keyboard.append([InlineKeyboardButton(f"❌ Delete {p['title']}", callback_data=f"delete_preset_{idx}")])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="manage_presets")])
        
        await query.message.reply_text("Select a preset to delete:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("delete_preset_"):
        idx = int(query.data.replace("delete_preset_", ""))
        if 0 <= idx < len(presets):
            deleted = presets.pop(idx)
            save_state()
            await query.message.reply_text(f"✅ Deleted: {deleted['title']}", reply_markup=main_menu())

    elif query.data == "set_channel":
        context.user_data["awaiting_channel_id"] = True
        context.user_data["awaiting_url"] = False
        import youtube
        await query.message.reply_text(
            f"🆔 Current Channel ID: `{youtube.CHANNEL_ID}`\n\n"
            "📥 Send the new YouTube Channel ID:",
            parse_mode="Markdown"
        )

    elif query.data == "channel_streams":
        await query.message.reply_text(
            "⏳ Fetching livestreams from the channel...",
        )
        try:
            streams = await fetch_channel_streams()
            if not streams:
                await query.message.reply_text(
                    "❌ No active or upcoming livestreams found on the configured channel.",
                    reply_markup=main_menu()
                )
            else:
                keyboard = []
                for stream in streams:
                    btn_text = f"{stream['status']} - {stream['title'][:30]}"
                    keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_stream_{stream['video_id']}")])
                
                keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back")])
                
                await query.message.reply_text(
                    "📡 Available Livestreams:\n\nSelect one to play:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                context.user_data["streams"] = streams
        except Exception as e:
            await query.message.reply_text(
                f"❌ Error fetching streams: {str(e)}",
                reply_markup=main_menu()
            )

    elif query.data.startswith("select_stream_"):
        video_id = query.data.replace("select_stream_", "")
        streams = context.user_data.get("streams", [])
        selected = next((s for s in streams if s["video_id"] == video_id), None)
        
        if selected:
            stream_url = f"https://www.youtube.com/watch?v={video_id}"
            manual_stream["enabled"] = True
            manual_stream["url"] = stream_url
            manual_stream["title"] = selected["title"]
            manual_stream["thumbnail"] = selected.get("thumbnail")
            manual_stream["updated_at"] = int(time.time())
            save_state()
            
            await query.message.reply_text(
                f"▶ Playing: {selected['title']}\n\n{stream_url}",
                reply_markup=main_menu()
            )

    elif query.data == "stop":
        manual_stream["enabled"] = False
        manual_stream["url"] = None
        manual_stream["title"] = None
        manual_stream["updated_at"] = int(time.time())
        save_state()

        await query.message.reply_text(
            "⏹ Manual stream stopped",
            reply_markup=main_menu()
        )

    elif query.data == "status":
        if manual_stream["enabled"]:
            text = f"▶ ACTIVE STREAM\n\n📺 Title: {manual_stream.get('title', 'Unknown')}\n🔗 URL: {manual_stream['url']}"
        else:
            text = "ℹ️ No manual stream set"

        await query.message.reply_text(
            text,
            reply_markup=main_menu()
        )

    elif query.data == "help":
        await help_cmd(update, context)

    elif query.data == "back":
        await query.message.reply_text(
            "📺 TV Stream Controller",
            reply_markup=main_menu()
        )

# ---------- URL & ID Receiver ----------

@restricted
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_preset_url"):
        url = update.message.text.strip()
        if not url.startswith(("http://", "https://")):
            await update.message.reply_text("❌ Invalid URL. Start with http:// or https://")
            return
        context.user_data["new_preset_url"] = url
        context.user_data["awaiting_preset_url"] = False
        context.user_data["awaiting_preset_title"] = True
        await update.message.reply_text("📛 Now send a Title for this preset:")
        return

    if context.user_data.get("awaiting_preset_title"):
        title = update.message.text.strip()
        url = context.user_data.get("new_preset_url")
        presets.append({"title": title, "url": url})
        save_state()
        context.user_data["awaiting_preset_title"] = False
        await update.message.reply_text(f"✅ Preset '{title}' added!", reply_markup=main_menu())
        return

    if context.user_data.get("awaiting_url"):
        url = update.message.text.strip()
        context.user_data["awaiting_url"] = False

        if not url.startswith(("http://", "https://")):
            await update.message.reply_text(
                "❌ Invalid URL. Please enter a valid URL starting with http:// or https://",
                reply_markup=main_menu()
            )
            return

        manual_stream["enabled"] = True
        manual_stream["url"] = url
        manual_stream["title"] = "Manual Stream"
        manual_stream["updated_at"] = int(time.time())
        save_state()

        await update.message.reply_text(
            f"✅ Stream set successfully\n\n🔗 {url}",
            reply_markup=main_menu()
        )
        return

    if context.user_data.get("awaiting_channel_id"):
        channel_id = update.message.text.strip()
        context.user_data["awaiting_channel_id"] = False

        if not channel_id:
            await update.message.reply_text(
                "❌ Invalid Channel ID.",
                reply_markup=main_menu()
            )
            return

        set_channel_id(channel_id)
        update_env_file("YOUTUBE_CHANNEL_ID", channel_id)

        await update.message.reply_text(
            f"✅ YouTube Channel ID updated to:\n`{channel_id}`",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        return

    await update.message.reply_text(
        "ℹ️ Please use the buttons to interact with the bot.",
        reply_markup=main_menu()
    )

# ---------- Runner ----------

def start_bot():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("🤖 Telegram bot with UI started")
    app.run_polling()
