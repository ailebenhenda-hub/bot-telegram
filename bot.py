import logging
import os
import hashlib
import sqlite3
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

# Configuration des logs
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-3956183527"))

# Stockage base de données
DB_DIR = "/app/data" if os.path.exists("/app/data") else "."
DB_NAME = os.path.join(DB_DIR, "bot_data.db")

# Liens officiels
REVOLUT_PAYMENT_LINK = "https://revolut.me/shvppeur_corp"
COLISSUIVI_LINK = "https://www.laposte.fr/outils/suivre-vos-envois"
SNAPCHAT_LINK = "https://snapchat.com/t/KLL65sDJ"
VINTED_LINK = "https://www.vinted.fr/member/idf_runningshop"
TIKTOK_LINK = "https://www.tiktok.com/@idf_runningshop?_r=1&_t=ZN-98riuu613NW"
PRIVATE_TELEGRAM_LINK = "https://t.me/idf_runningshop"
ADMIN_GROUP_LINK = "https://t.me/+q2HRbe-dBydlZWZk"

# États de la conversation
ENTERING_CART, WAITING_FOR_SCREENSHOT = range(2)
restock_subscribers = {"tech_fleece": set(), "pants": set(), "tees": set()}
current_cart_data = {}
referral_counts = {}

# --- BASE DE DONNÉES ---
def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (img_hash TEXT PRIMARY KEY, user_id INTEGER, amount REAL, status TEXT)''')
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

# --- MENU PRINCIPAL ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or is_blacklisted(user.id):
        return
    
    welcome_message = (
        "👋 Bienvenue chez IDF Running // V.I.P\n\n"
        "Revente indépendante de vêtements streetwear exclusifs.\n"
        "Choisis une option ci-dessous :"
    )
    keyboard = [
        [InlineKeyboardButton("📦 Payer par Revolut", url=REVOLUT_PAYMENT_LINK)],
        [InlineKeyboardButton("🔔 Alertes Restock", callback_data="restock_menu")],
        [InlineKeyboardButton("🏷️ Codes Promo", callback_data="promo_codes")],
        [InlineKeyboardButton("🤝 Parrainage", callback_data="referral_menu")],
        [InlineKeyboardButton("📱 Réseaux (Vinted, Snap, TikTok)", callback_data="vinted_menu")],
        [InlineKeyboardButton("🤝 Remise en main propre (93 / Gares IDF)", callback_data="hand_delivery")],
        [InlineKeyboardButton("📏 Guide des tailles", callback_data="size_guide")],
        [InlineKeyboardButton("🚚 Suivre mon colis", callback_data="track_parcel")],
        [InlineKeyboardButton("✅ J'ai effectué mon paiement", callback_data="paid")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text(welcome_message, reply_markup=reply_markup)
    
    return ConversationHandler.END

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Support IDF Running // V.I.P\n\n"
        f"Contacte directement le créateur ici : {PRIVATE_TELEGRAM_LINK}\n"
        f"Ou rejoins le groupe staff : {ADMIN_GROUP_LINK}"
    )
    if update.message:
        await update.message.reply_text(text)

# --- GESTIONNAIRE DE BOUTONS ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if is_blacklisted(user_id):
        await query.message.reply_text("⛔ Accès refusé.")
        return

    data = query.data

    if data == "restock_menu":
        sub_tf = "✅ " if user_id in restock_subscribers["tech_fleece"] else "🔔 "
        sub_pants = "✅ " if user_id in restock_subscribers["pants"] else "🔔 "
        sub_tees = "✅ " if user_id in restock_subscribers["tees"] else "🔔 "

        text = "Centre d'Alertes Restock\n\nAbonne-toi aux catégories de ton choix :"
        keyboard = [
            [InlineKeyboardButton(f"{sub_tf}Tech Fleece / Sweats", callback_data="sub_tech_fleece")],
            [InlineKeyboardButton(f"{sub_pants}Pantalons", callback_data="sub_pants")],
            [InlineKeyboardButton(f"{sub_tees}T-shirts", callback_data="sub_tees")],
            [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("sub_"):
        cat = data.replace("sub_", "")
        if cat in restock_subscribers:
            if user_id in restock_subscribers[cat]:
                restock_subscribers[cat].remove(user_id)
                st = "❌ Désabonné de cette catégorie."
            else:
                restock_subscribers[cat].add(user_id)
                st = "✅ Abonné avec succès !"
                
            sub_tf = "✅ " if user_id in restock_subscribers["tech_fleece"] else "🔔 "
            sub_pants = "✅ " if user_id in restock_subscribers["pants"] else "🔔 "
            sub_tees = "✅ " if user_id in restock_subscribers["tees"] else "🔔 "
            kbd = [
                [InlineKeyboardButton(f"{sub_tf}Tech Fleece / Sweats", callback_data="sub_tech_fleece")],
                [InlineKeyboardButton(f"{sub_pants}Pantalons", callback_data="sub_pants")],
                [InlineKeyboardButton(f"{sub_tees}T-shirts", callback_data="sub_tees")],
                [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
            ]
            await query.message.edit_text(f"Centre d'Alertes Restock\n\n{st}", reply_markup=InlineKeyboardMarkup(kbd))

    elif data == "referral_menu":
        link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
        count = referral_counts.get(user_id, 0)
        text = f"Programme de Parrainage\n\nPartage ton lien personnel :\n{link}\n\nFilleuls validés : {count}"
        kbd = [[InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd))

    elif data == "promo_codes":
        text = (
            "Offres & Codes Promo Actuels :\n\n"
            "• Dès 70 € d'achat : -5 € de réduction par article.\n"
            "• Dès 170 € d'achat : Livraison offerte 🚚\n"
            "• Le Gagnant (Concours) : -20 € dès 130 € d'achat."
        )
        kbd = [[InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd))

    elif data == "vinted_menu":
        text = "Retrouve mes réseaux et profils officiels :"
        kbd = [
            [InlineKeyboardButton("🛍️ Mon Vinted", url=VINTED_LINK)],
            [InlineKeyboardButton("👻 Mon Snapchat", url=SNAPCHAT_LINK)],
            [InlineKeyboardButton("🎵 Mon TikTok", url=TIKTOK_LINK)],
            [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd))

    elif data == "hand_delivery":
        text = "Remise en main propre :\n\nDisponible en Île-de-France (principalement dans le 93 et en gares selon disponibilités)."
        kbd = [[InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd))

    elif data == "size_guide":
        text = "Guide des tailles :\n\n• S : Jusqu'à 1m80\n• M : 1m75 - 1m85\n• L : 1m80 - 1m90\n• XL : 1m90+"
        kbd = [[InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd))

    elif data == "track_parcel":
        text = "Suivi Colissimo :\n\nClique ci-dessous pour suivre ton colis La Poste :"
        kbd = [
            [InlineKeyboardButton("🔍 Suivi La Poste", url=COLISSUIVI_LINK)],
            [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd))

    elif data == "back":
        await start(update, context)

# --- TUNNEL DE COMMANDE SÉCURISÉ ---
async def ask_for_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if is_blacklisted(query.from_user.id):
        await query.message.reply_text("⛔ Accès refusé.")
        return ConversationHandler.END
    
    await query.message.reply_text("📝 Détaille ta commande (ex: Pantalon Nike Trail Taille S) :")
    return ENTERING_CART

async def save_cart_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_cart_data[user_id] = {"items": update.message.text}
    await update.message.reply_text(
        "📸 Parfait !\n\nEnvoie maintenant la capture d'écran de ton reçu Revolut pour que l'équipe valide ton paiement :"
    )
    return WAITING_FOR_SCREENSHOT

async def receive_payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.photo:
        await update.message.reply_text("⚠️ Ceci n'est pas une image. Envoie la capture d'écran de ton reçu.")
        return WAITING_FOR_SCREENSHOT

    photo_file = await update.message.photo[-1].get_file()
    photo_path = await photo_file.download_as_bytearray()
    img_hash = hashlib.md5(photo_path).hexdigest()
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO transactions (img_hash, user_id, amount, status) VALUES (?, ?, 0, 'PENDING')", (img_hash, user.id))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        await update.message.reply_text("⛔ Doublon détecté : Cette capture a déjà été utilisée.")
        return ConversationHandler.END
    conn.close()

    cart_info = current_cart_data.get(user.id, {}).get("items", "Non spécifié")
    
    # Texte brut sans aucun formatage markdown risqué pour éviter les plantages
    admin_caption = (
        "NOUVEAU REÇU REVOLUT SOUMIS !\n\n"
        f"Client : {user.first_name} (@{user.username or 'N/A'})\n"
        f"ID : {user.id}\n"
        f"Articles : {cart_info}\n\n"
        "Vérifie ton compte Revolut avant de valider :"
    )
    
    admin_keyboard = [
        [
            InlineKeyboardButton("✅ Valider", callback_data=f"admin_accept_{user.id}"),
            InlineKeyboardButton("🚚 Expédier", callback_data=f"admin_ship_{user.id}")
        ]
    ]
    
    # Envoi sécurisé vers le groupe admin sans parse_mode pour garantir la réception
    try:
        await context.bot.send_photo(
            chat_id=ADMIN_GROUP_ID,
            photo=photo_path,
            caption=admin_caption,
            reply_markup=InlineKeyboardMarkup(admin_keyboard)
        )
    except Exception as e:
        logging.error(f"Erreur critique envoi groupe admin : {e}")
    
    await update.message.reply_text("🎉 Reçu transmis aux admins ! Un administrateur va vérifier ton paiement.")
    return ConversationHandler.END

async def admin_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if "admin_accept_" in data:
        client_id = int(data.split("_")[2])
        await query.edit_message_caption(caption=query.message.caption + "\n\n[STATUT : PAIEMENT VALIDÉ PAR UN ADMIN]")
        try:
            await context.bot.send_message(chat_id=client_id, text="✅ Paiement validé par l'équipe ! On gère l'envoi ou la remise en main propre.")
        except Exception:
            pass
            
    elif "admin_ship_" in data:
        client_id = int(data.split("_")[2])
        await query.edit_message_caption(caption=query.message.caption + "\n\n[STATUT : COLIS EXPÉDIÉ]")
        try:
            await context.bot.send_message(chat_id=client_id, text=f"🚚 Colis expédié !\n\nSuivi Colissimo : {COLISSUIVI_LINK}")
        except Exception:
            pass

# Gestionnaire pour les messages texte hors tunnel (évite le silence ou les erreurs)
async def text_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        await update.message.reply_text(
            "Utilise les boutons du menu principal ou tape /start pour naviguer. "
            f"Pour contacter directement le staff : {PRIVATE_TELEGRAM_LINK}"
        )

# --- LANCEMENT ---
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_for_cart, pattern="^paid$")],
        states={
            ENTERING_CART: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_cart_items)],
            WAITING_FOR_SCREENSHOT: [MessageHandler(filters.PHOTO & ~filters.COMMAND, receive_payment_screenshot)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("aide", help_command))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(CallbackQueryHandler(admin_action_handler, pattern="^admin_"))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_fallback))
    
    print("Bot 100% fonctionnel et sécurisé (sans IA) démarré !")
    app.run_polling()

if __name__ == "__main__":
    main()
