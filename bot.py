import os
import logging
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

ADMIN_GROUP_ID = -3956183527
SELLER_USERNAME = "@Shvppeur"

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🛒 Vinted", url="https://www.tiktok.com/@idf_runningshop?_r=1&_t=ZN-98sYce7fxhO"),
            InlineKeyboardButton("👻 Snapchat", url="https://snapchat.com/t/BW0Gzw9i"),
        ],
        [
            InlineKeyboardButton("🎵 TikTok", url="https://www.tiktok.com/@idf_runningshop?_r=1&_t=ZN-98sYce7fxhO"),
            InlineKeyboardButton("📢 Canal VIP", url="https://t.me/idfrunningvip"),
        ],
        [
            InlineKeyboardButton("💬 Avis & Retours", url="https://t.me/+q2HRbe-dBydlZWZk"),
            InlineKeyboardButton("💳 Preuves Paiement", url="https://t.me/c/4339817330/8"),
        ],
        [
            InlineKeyboardButton("📲 Contacter le vendeur", url="https://t.me/Shvppeur")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_msg = (
        f"👋 Bienvenue **{user_name}** sur **IDF Running Shop** !\n\n"
        "Spécialiste running & streetwear en Île-de-France.\n"
        "• Articles sélectionnés avec soin\n"
        "• Envoi rapide ou remise en main propre\n\n"
        "Que souhaites-tu faire ?"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == ADMIN_GROUP_ID:
        return

    user_text = update.message.text
    
    if not groq_client:
        await update.message.reply_text(f"Pour commander ou poser une question, contacte direct {SELLER_USERNAME}.", reply_markup=get_main_keyboard())
        return

    system_prompt = (
        "Tu es l'assistant virtuel officiel d'idf_runningshop. "
        "Ton ton est amical, professionnel et streetwear. "
        "Tu aides pour les questions sur les vêtements, baskets, livraisons et remises en main propre en IDF. "
        f"Pour tout achat ou négociation, renvoie vers {SELLER_USERNAME}."
    )

    try:
        completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            model="llama-3.3-70b-versatile",
        )
        reply = completion.choices[0].message.content
        await update.message.reply_text(reply, reply_markup=get_main_keyboard())
    except Exception as e:
        logging.error(f"Erreur Groq : {e}")
        await update.message.reply_text(f"Une erreur est survenue. Contacte directement {SELLER_USERNAME} !", reply_markup=get_main_keyboard())

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
