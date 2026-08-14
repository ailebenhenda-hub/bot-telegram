import logging
import os
import string
import random
import hashlib
import sqlite3
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from groq import Groq  # Import de la librairie Groq

# Configuration
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-5313705184"))
YOUR_ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "123456789"))

# Initialisation Groq
groq_client = Groq(api_key=GROQ_API_KEY)

# Stockage
DB_DIR = "/app/data" if os.path.exists("/app/data") else "."
DB_NAME = os.path.join(DB_DIR, "bot_data.db")

# Liens
REVOLUT_PAYMENT_LINK = "https://revolut.me/shvppeur_corp"
SUPPORT_LINK = "https://t.me/idfrunningvip"
REVIEWS_GROUP_LINK = "https://t.me/c/4339817330/8"
COLISSUIVI_LINK = "https://www.laposte.fr/outils/suivre-vos-envois"
TIKTOK_LINK = "https://www.tiktok.com/@idf_runningshop"
VINTED_LINK = "https://www.vinted.fr/member/toncompte"

# États
ENTERING_CART, WAITING_FOR_SCREENSHOT = range(2)
known_users = set()
restock_subscribers = {"tech_fleece": set(), "pants": set(), "tees": set()}
pending_reminders = {}
current_cart_data = {}
referral_counts = {}
referred_users = set()
unique_promo_codes = {}
active_promo_codes = [
    "• **Dès 70 € d'achat** : **-5 €** de réduction par article.",
    "• **Dès 170 € d'achat** : **Livraison offerte** 🚚",
    "• **Le Gagnant (Concours)** : -20 € dès 130 € d'achat."
]

# --- BASE DE DONNÉES & UTILS ---
def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (img_hash TEXT PRIMARY KEY, user_id INTEGER, amount REAL, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS stock (item TEXT PRIMARY KEY, qty INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS blacklist (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

def is_blacklisted(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT 1 FROM blacklist WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res is not None

# --- IA GROQ ---
async def handle_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    system_prompt = (
        "Tu es l'assistant IA de 'IDF Running // V.I.P'. Tu aides les clients pour leurs choix de tailles, "
        "les infos sur les envois Colissimo, et les paiements via Revolut.me/shvppeur_corp. "
        "Réponds de manière amicale, concise et professionnelle. Si on te demande de payer, donne le lien Revolut."
    )
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
            temperature=0.7, max_tokens=150
        )
        await update.message.reply_text(completion.choices[0].message.content)
    except Exception as e:
        logging.error(f"Erreur IA : {e}")
        await update.message.reply_text("Petit souci technique, utilise le menu pour m'aider !")

# --- FONCTIONS DU BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_blacklisted(user.id): return
    known_users.add(user.id)
    
    welcome_message = "👋 **Bienvenue chez IDF Running // V.I.P 🔌**\n\nSpécialiste de la revente de vêtements exclusifs. Que souhaites-tu faire ?"
    keyboard = [
        [InlineKeyboardButton("📦 Payer par Revolut", url=REVOLUT_PAYMENT_LINK)],
        [InlineKeyboardButton("🔔 Alertes Restock", callback_data="restock_menu")],
        [InlineKeyboardButton("🏷️ Codes Promo", callback_data="promo_codes")],
        [InlineKeyboardButton("🤝 Parrainage", callback_data="referral_menu")],
        [InlineKeyboardButton("✅ J'ai payé", callback_data="paid")],
        [InlineKeyboardButton("💬 Support / Aide", url=SUPPORT_LINK)],
    ]
    if update.message: await update.message.reply_text(welcome_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else: await update.callback_query.message.edit_text(welcome_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- LANCEMENT ---
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Gestionnaire de conversation pour le paiement
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: u.callback_query.message.reply_text("Détaille ta commande :") or ENTERING_CART, pattern="^paid$")],
        states={
            ENTERING_CART: [MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text("Envoie ton reçu !") or WAITING_FOR_SCREENSHOT)],
            WAITING_FOR_SCREENSHOT: [MessageHandler(filters.PHOTO, lambda u, c: u.message.reply_text("Reçu reçu !") or ConversationHandler.END)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_chat))
    app.run_polling()

if __name__ == "__main__":
    main()
