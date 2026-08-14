import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Clé d'environnement Telegram depuis Railway
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Identifiants du shop
ADMIN_GROUP_ID = -3956183527
SELLER_USERNAME = "@Shvppeur"

# Configuration des logs
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Menu interactif avec tous tes liens
def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🛒 Vinted", url="https://www.vinted.fr/member/idf_runningshop"),
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

# Commande /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_msg = (
        f"👋 Bienvenue **{user_name}** sur **IDF Running Shop** !\n\n"
        "Spécialiste running & streetwear en Île-de-France. 🔥\n"
        "• Articles sélectionnés avec soin\n"
        "• Envoi rapide ou remise en main propre\n\n"
        "Que souhaites-tu faire ?"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

# Reponse automatique simple sans IA
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Ignore les messages dans le groupe admin
    if update.effective_chat.id == ADMIN_GROUP_ID:
        return

    reply_text = f"Pour toute question, commande ou réservation, contacte directement {SELLER_USERNAME} !"
    await update.message.reply_text(reply_text, reply_markup=get_main_keyboard())

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
