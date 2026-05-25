import os
import sys
import asyncio
import re
import random
import edge_tts
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

# Import our newly configured Celery task pipeline broker
from tasks import process_voice_async

# Load configuration from environment file
load_dotenv()

# Add current directory to path for dependencies like ffmpeg
current_dir = os.path.dirname(os.path.abspath(__file__))
os.environ["PATH"] += os.pathsep + current_dir

# Global configuration from .env
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL_NAME", "gitavani")

if not TELEGRAM_BOT_TOKEN or "YOUR_TELEGRAM_BOT_API_TOKEN" in TELEGRAM_BOT_TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN is missing or invalid in the .env file.")
    sys.exit(1)

# Static interactive pool for immediate engagement
ENGAGEMENT_QUOTES = [
    "Calmness, gentleness, silence, self-restraint, and purity: these are the disciplines of the mind. (Gita 17.16)",
    "A person is said to have achieved yoga when they have abandoned all selfish desires and anxieties. (Gita 6.18)",
    "The mind is restless and difficult to restrain, but it is subdued by constant practice and detachment. (Gita 6.35)",
    "You have a right to perform your prescribed duties, but you are not entitled to the fruits of your actions. (Gita 2.47)"
]

def format_message_layout(text: str) -> str:
    """Splits raw text into readable paragraphs every 2 sentences."""
    cleaned = re.sub(r'\s+', ' ', text).strip()
    sentences = re.split(r'([.?])\s*', cleaned)
    
    paragraphs = []
    current_paragraph = ""
    sentence_count = 0
    
    for i in range(0, len(sentences) - 1, 2):
        sentence = sentences[i] + sentences[i+1]
        current_paragraph += " " + sentence
        sentence_count += 1
        
        if sentence_count >= 2:
            paragraphs.append(current_paragraph.strip())
            current_paragraph = ""
            sentence_count = 0
            
    if current_paragraph:
        paragraphs.append(current_paragraph.strip())
        
    return "\n\n".join(paragraphs) if paragraphs else cleaned


async def text_to_speech(text: str, output_filename: str):
    """Generates an MP3 file utilizing a deep, soft male voice mixed with bg flute via FFmpeg."""
    temp_voice_file = "temp_voice.mp3"
    bg_flute_file = "bg_flute.mp3"
    
    voice = "en-IN-PrabhatNeural"
    rate = "-18%"   
    pitch = "-3Hz"  
    
    clean_text = text.replace("\n", " ")
    communicator = edge_tts.Communicate(clean_text, voice, rate=rate, pitch=pitch)
    await communicator.save(temp_voice_file)
    
    if os.path.exists(bg_flute_file):
        command = [
            'ffmpeg', '-y',
            '-i', temp_voice_file,
            '-stream_loop', '-1', '-i', bg_flute_file,
            '-filter_complex', '[1:a]volume=0.12[bg];[0:a][bg]amix=inputs=2:duration=first[a]',
            '-map', '[a]',
            '-b:a', '48k',
            output_filename
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
        except Exception:
            os.replace(temp_voice_file, output_filename)
        finally:
            if os.path.exists(temp_voice_file):
                os.remove(temp_voice_file)
    else:
        os.replace(temp_voice_file, output_filename)


def get_engagement_keyboard():
    """Generates an interactive button menu to keep the user engaged."""
    keyboard = [
        [
            InlineKeyboardButton("📜 Read a Verse", callback_data="engage_quote"),
            InlineKeyboardButton("🧘 Take a Breath", callback_data="engage_breath")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    await update.message.reply_text(
        "Pranam. I am GitaVani.\n\n"
        "Send me a Text or a Voice message in English. "
        "I will listen to your situation and reply with gentle guidance from the Bhagavad Gita."
    )


async def handle_engagement_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles instant interactive actions while the main response processing runs."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "engage_quote":
        selected_quote = random.choice(ENGAGEMENT_QUOTES)
        message_text = f"✨ *While I prepare your guidance, reflect on this:* \n\n{selected_quote}"
    elif query.data == "engage_breath":
        message_text = "✨ *Breathe with Me:* \n\nInhale deeply for 4 seconds... Hold for 4 seconds... Exhale slowly for 4 seconds. Let the noise fade away."
    else:
        return

    try:
        await query.edit_message_text(text=message_text, parse_mode="Markdown", reply_markup=get_engagement_keyboard())
    except Exception:
        pass


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Streams text generation from Ollama directly (Text stays fast, voice uses Celery tasking)"""
    try:
        user_input = update.message.text.strip()
        print(f"Received text input: {user_input[:40]}...")
        
        status_message = await update.message.reply_text("✨ Tuning into your energy...")
        await update.message.reply_chat_action(action="typing")
        
        import ollama as local_ollama
        stream = local_ollama.generate(model=OLLAMA_MODEL, prompt=user_input, stream=True)
        
        accumulated_text = ""
        last_length = 0
        
        for chunk in stream:
            accumulated_text += chunk['response']
            formatted_text = format_message_layout(accumulated_text)
            
            if len(formatted_text) - last_length > 35:
                try:
                    await context.bot.edit_message_text(
                        text=formatted_text,
                        chat_id=update.message.chat_id,
                        message_id=status_message.message_id
                    )
                    last_length = len(formatted_text)
                except Exception:
                    pass
                
        final_text = format_message_layout(accumulated_text)
        await context.bot.edit_message_text(
            text=final_text, chat_id=update.message.chat_id, message_id=status_message.message_id
        )
        
    except Exception as e:
        print(f"Error in handle_text: {e}")
        await update.message.reply_text("An error occurred while processing your message.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Offloads transcription and LLM inference processing directly to background task queues."""
    try:
        await update.message.reply_chat_action(action="record_voice")
        
        status_message = await update.message.reply_text(
            text="✨ Absorbing your voice into the task queue...\nInteract below while the background workers process your guidance.",
            reply_markup=get_engagement_keyboard()
        )
        
        # Unique naming template to prevent race condition cross-talk file overwrites
        file_info = await context.bot.get_file(update.message.voice.file_id)
        input_audio = f"voice_job_{update.message.message_id}.ogg"
        await file_info.download_to_drive(input_audio)
        print(f"Main Thread: Saved transient file -> {input_audio}")

        # Dispatch execution completely off the main thread to Celery
        print("Main Thread: Dispatching job transaction frame down to Redis...")
        task_job = process_voice_async.delay(os.path.abspath(input_audio), OLLAMA_MODEL)
        
        # Non-blocking poll routine to watch our Celery async loop state check
        while not task_job.ready():
            await asyncio.sleep(0.5)
            
        task_result = task_job.result
        
        if "error" in task_result:
            await context.bot.edit_message_text(
                text=f"Solace generation failed: {task_result['error']}",
                chat_id=update.message.chat_id, message_id=status_message.message_id, reply_markup=None
            )
            return

        formatted_reply = format_message_layout(task_result["reply"])
        output_audio = f"response_{update.message.message_id}.mp3"
        
        print("Main Thread: Constructing audio wave matrix files...")
        await text_to_speech(formatted_reply, output_audio)

        await context.bot.delete_message(chat_id=update.message.chat_id, message_id=status_message.message_id)

        with open(output_audio, "rb") as voice_file:
            await update.message.reply_voice(voice=voice_file, caption="✨ GitaVani Solace")
            
        if os.path.exists(output_audio):
            os.remove(output_audio)

    except Exception as e:
        print(f"Error in handle_voice: {e}")
        await update.message.reply_text("An error occurred while processing your voice note.")


def main():
    print("Starting Telegram polling router application...")
    network_request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .request(network_request)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_engagement_callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    app.run_polling()


if __name__ == "__main__":
    main()