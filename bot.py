import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Récupération souple de l'ID (gestion string / int)
RAW_ADMIN_ID = os.getenv("ADMIN_GROUP_ID", "-3956183527")
try:
    ADMIN_GROUP_ID = int(RAW_ADMIN_ID)
except ValueError:
    ADMIN_GROUP_ID = RAW_ADMIN_ID

SELLER_USERNAME = "idf_runningshop"
REVOLUT_LINK = "https://revolut.me/shvppeur_corp"

referrals = {}
user_join_dates = {}

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

CATALOG = {
    "1": {"name": "Pantalon Nike Trail", "taille": "S", "etat": "8/10", "prix": "60 €"},
    "2": {"name": "Pantalon Nike Aeroswift", "taille": "Non précisée", "etat": "Excellent état", "prix": "75 €"},
    "3": {"name": "Pantalon Nike Phenom Elite", "taille": "Non précisée", "etat": "Excellent état", "prix": "90 €"},
    "4": {"name": "Sweat Nike Tech Aviateur v1", "taille": "M", "etat": "Excellent état", "prix": "60 €"},
    "5": {"name": "Pantalon Nike Phenom Elite (Gris)", "taille": "L", "etat": "Excellent état", "prix": "90 €"},
    "6": {"name": "Tee-Shirt Nike Trail", "taille": "Non précisée", "etat": "Excellent état", "prix": "40 €"},
    "7": {"name": "Tee-Shirt Nike Running Division", "taille": "Non précisée", "etat": "Excellent état", "prix": "35 €"},
    "8": {"name": "Tee-Shirt Nike Dri-Fit (Rouge)", "taille": "Non précisée", "etat": "Excellent état", "prix": "30 €"},
    "9": {"name": "Sweat Nike Tech Fleece (Noir)", "taille": "S", "etat": "Excellent état", "prix": "70 €"},
    "10": {"name": "Pantalon Nike Phenom Elite Poche Noir", "taille": "S", "etat": "8/10", "prix": "80 €"}
}

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📦 Catalogue & Stock", callback_data="show_catalog"),
            InlineKeyboardButton("🤝 Parrainage (-5€)", callback_data="show_referral")
        ],
        [
            InlineKeyboardButton("🚚 Livraisons & Paiements", callback_data="show_info"),
            InlineKeyboardButton("💳 Payer sur Revolut", url=REVOLUT_LINK)
        ],
        [
            InlineKeyboardButton("🛒 Vinted", url="https://www.vinted.fr/member/idf_runningshop"),
            InlineKeyboardButton("👻 Snapchat", url="https://snapchat.com/t/BW0Gzw9i")
        ],
        [
            InlineKeyboardButton("🎵 TikTok", url="https://www.tiktok.com/@idf_runningshop?_r=1&_t=ZN-98sYce7fxhO"),
            InlineKeyboardButton("📢 Canal VIP", url="https://t.me/idfrunningvip")
        ],
        [
            InlineKeyboardButton("💬 Avis & Retours", url="https://t.me/+q2HRbe-dBydlZWZk"),
            InlineKeyboardButton("💳 Preuves Paiement", url="https://t.me/c/4339817330/8")
        ],
        [
            InlineKeyboardButton("📲 Contacter le vendeur", url=f"https://t.me/{SELLER_USERNAME}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    if context.args and context.args[0].isdigit():
        referrer_id = int(context.args[0])
        if referrer_id != user_id and user_id not in referrals:
            referrals[user_id] = referrer_id
            user_join_dates[user_id] = datetime.now()

    welcome_msg = (
        f"👋 Bienvenue {user_name} sur IDF Running Shop !\n\n"
        "Boutique indépendante streetwear & vêtements running pour jeunes. 🔥\n"
        "(Aucune chaussure ni accessoire — vêtements uniquement)\n\n"
        "• Envoi rapide Colissimo ou remise en main propre (IDF)\n"
        "• Paiements : Liquide, Vinted, Snapchat, Revolut\n\n"
        "Envoie directement le numéro d'un article (ex: #1, #4) pour commander !"
    )
    await update.message.reply_text(welcome_msg, reply_markup=get_main_keyboard())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "show_catalog":
        text = "🔥 STOCK ACTUEL (Sape Running / Streetwear) 🔥\n\n"
        for item_id, data in CATALOG.items():
            text += f"#{item_id} - {data['name']}\n"
            text += f"   • Taille : {data['taille']} | État : {data['etat']} | {data['prix']}\n\n"
        text += "👉 Pour réserver, envoie # suivi du numéro (ex: #1)."
        await query.edit_message_text(text=text, reply_markup=get_main_keyboard())

    elif query.data == "show_referral":
        bot_info = await context.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={query.from_user.id}"
        text = (
            "🎁 PROGRAMME DE PARRAINAGE\n\n"
            f"Partage ton lien à tes potes :\n{ref_link}\n\n"
            "📌 Règle : Si ton filleul passe commande dans les 20 jours suivant son arrivée, "
            "tu reçois 5 € de réduction sur ta prochaine commande !"
        )
        await query.edit_message_text(text=text, reply_markup=get_main_keyboard())

    elif query.data == "show_info":
        text = (
            "🚚 LIVRAISONS & MOYENS DE PAIEMENT\n\n"
            "📍 Remise en main propre :\n"
            "• Basé dans le 93, livraison possible dans les gares d'Île-de-France (frais selon la distance).\n"
            "• Paiement : Liquide uniquement lors de la remise.\n\n"
            "📦 Envoi Colissimo / Vinted :\n"
            "• Départ des colis avant 14h pour toute commande Telegram.\n"
            "• Pour Colissimo : Ajouter 6 € de frais de port au prix de l'article.\n"
            f"• Paiement Colissimo direct via Revolut : {REVOLUT_LINK}\n"
            "• Également disponible sur Vinted & Snapchat."
        )
        await query.edit_message_text(text=text, reply_markup=get_main_keyboard())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Affiche l'ID du chat dans les logs pour le récupérer facilement
    logging.info(f"Message reçu sur le chat ID : {update.effective_chat.id}")

    if str(update.effective_chat.id) == str(ADMIN_GROUP_ID):
        return

    text = update.message.text.strip()
    user = update.effective_user

    if text.startswith("#") and text[1:].isdigit():
        item_id = text[1:]
        if item_id in CATALOG:
            item = CATALOG[item_id]
            
            has_valid_ref = False
            referrer_id = referrals.get(user.id)
            if referrer_id and user.id in user_join_dates:
                if datetime.now() - user_join_dates[user.id] <= timedelta(days=20):
                    has_valid_ref = True

            confirm_text = (
                f"✅ Tu as sélectionné l'article #{item_id} : {item['name']}\n"
                f"• Prix : {item['prix']}\n\n"
                "Pour finaliser la commande :\n"
                f"1. Clique sur 'Contacter le vendeur' (@{SELLER_USERNAME})\n"
                f"2. Pour un paiement direct et envoi Colissimo (+6 €), utilise Revolut : {REVOLUT_LINK}"
            )
            await update.message.reply_text(confirm_text, reply_markup=get_main_keyboard())

            username_str = f"@{user.username}" if user.username else "Aucun pseudo"
            admin_alert = (
                "🚨 NOUVELLE INTERACTION ARTICLE\n\n"
                f"• Client : {user.first_name} ({username_str})\n"
                f"• ID Client : {user.id}\n"
                f"• Article : #{item_id} - {item['name']} ({item['prix']})\n"
            )
            if has_valid_ref:
                admin_alert += f"\n🎁 Alerte Parrainage : Arrivé via parrain {referrer_id} depuis moins de 20j."

            try:
                await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=admin_alert)
            except Exception as e:
                logging.error(f"Erreur envoi groupe admin ({ADMIN_GROUP_ID}): {e}")

            return

    reply = f"Pour réserver un article, tape le numéro avec un hashtag (ex: #1). Sinon contacte directement @{SELLER_USERNAME} !"
    await update.message.reply_text(reply, reply_markup=get_main_keyboard())

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()

if __name__ == "__main__":
    main()
