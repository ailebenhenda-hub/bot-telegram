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

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# ==========================================
# CONFIGURATION & VARIABLES GLOBALES
# ==========================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "TON_TOKEN_ICI")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-5313705184"))
YOUR_ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "123456789"))

# Stockage persistant SQLite (Chemin adapté pour Railway Volume)
DB_DIR = "/app/data" if os.path.exists("/app/data") else "."
DB_NAME = os.path.join(DB_DIR, "bot_data.db")

STRIPE_PAYMENT_LINK = "https://buy.stripe.com/test_4gMdRa0fc8ZV26a2DL3cc00"
SUPPORT_LINK = "https://t.me/idfrunningvip"
REVIEWS_GROUP_LINK = "https://t.me/c/4339817330/8"
COLISSUIVI_LINK = "https://www.laposte.fr/outils/suivre-vos-envois"
TIKTOK_LINK = "https://www.tiktok.com/@idf_runningshop"
VINTED_LINK = "https://www.vinted.fr/member/toncompte"

# États de conversation
ENTERING_CART, WAITING_FOR_SCREENSHOT = range(2)

# Structures en mémoire pour le fonctionnement dynamique
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

# ==========================================
# INITIALISATION DE LA BASE DE DONNÉES
# ==========================================
def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        img_hash TEXT PRIMARY KEY, 
        user_id INTEGER, 
        amount REAL, 
        status TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS stock (
        item TEXT PRIMARY KEY, 
        qty INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS blacklist (
        user_id INTEGER PRIMARY KEY
    )''')
    conn.commit()
    conn.close()

def is_blacklisted(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT 1 FROM blacklist WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res is not None

# ==========================================
# GESTION DES COMMANDES PRINCIPALES & START
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
        
    if is_blacklisted(user.id):
        if update.message:
            await update.message.reply_text("⛔ Accès refusé.")
        return ConversationHandler.END

    known_users.add(user.id)
    user_name = user.first_name
    
    # Traitement du parrainage automatique
    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0].split("_")[1])
            if referrer_id != user.id and user.id not in referred_users:
                referred_users.add(user.id)
                referral_counts[referrer_id] = referral_counts.get(referrer_id, 0) + 1
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 **Nouveau parrainage validé !** Total de tes filleuls : `{referral_counts[referrer_id]}`",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
        except Exception:
            pass

    hour = datetime.now().hour
    greeting = "Bonjour" if 5 <= hour < 18 else "Bonsoir"
    
    welcome_message = (
        f"{greeting}, {user_name} ! Bienvenue chez **IDF Running // V.I.P 🔌** 🛒\n\n"
        "Spécialiste de la revente de vêtements exclusifs.\n"
        "Que souhaites-tu faire aujourd'hui ?"
    )

    keyboard = [
        [InlineKeyboardButton("📦 Payer par Carte (Colissimo)", url=STRIPE_PAYMENT_LINK)],
        [InlineKeyboardButton("🔔 Être alerté des nouveautés (Restock)", callback_data="restock_menu")],
        [InlineKeyboardButton("🔥 Rejoindre le Tirage & Concours", callback_data="contest")],
        [InlineKeyboardButton("🏷️ Voir les offres & Codes Promo", callback_data="promo_codes")],
        [InlineKeyboardButton("🤝 Mon lien de parrainage", callback_data="referral_menu")],
        [InlineKeyboardButton("📦 Historique / Mes commandes", callback_data="my_orders")],
        [InlineKeyboardButton("📏 Guide des tailles", callback_data="size_guide")],
        [InlineKeyboardButton("🚚 Suivre mon colis", callback_data="track_parcel")],
        [InlineKeyboardButton("⭐ Avis Paiements en Ligne", url=REVIEWS_GROUP_LINK)],
        [InlineKeyboardButton("✅ J'ai effectué mon paiement", callback_data="paid")],
        [InlineKeyboardButton("📌 FAQ Interactive", callback_data="faq_menu")],
        [InlineKeyboardButton("💬 Contacter le Support", url=SUPPORT_LINK)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode="Markdown")
    
    return ConversationHandler.END

# ==========================================
# PANIER DYNAMIQUE & RAPPELS
# ==========================================
async def ask_for_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if is_blacklisted(query.from_user.id):
        await query.message.reply_text("⛔ Accès refusé.")
        return ConversationHandler.END
        
    await query.message.reply_text("📝 **Détaille ta commande** (ex: Tech Fleece Gris + Pantalon) :", parse_mode="Markdown")
    return ENTERING_CART

async def save_cart_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_cart_data[user_id] = {"items": update.message.text}
    
    await update.message.reply_text(
        "📸 Parfait !\n\n"
        "Pour valider ta commande, **la capture d'écran de ton reçu Stripe est indispensable**.\n"
        "Envoie-la directement ici :"
    )
    
    if user_id in pending_reminders:
        pending_reminders[user_id].schedule_removal()
        
    job = context.job_queue.run_once(send_cart_reminder, 180, data={"user_id": user_id})
    pending_reminders[user_id] = job
    
    return WAITING_FOR_SCREENSHOT

async def send_cart_reminder(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data["user_id"]
    if user_id in pending_reminders:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="⏳ **Rappel :** Tu as initié une commande mais tu n'as pas envoyé ton reçu. Envoie ta capture d'écran pour valider !",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        del pending_reminders[user_id]

async def send_review_request(context: ContextTypes.DEFAULT_TYPE):
    client_id = context.job.data["client_id"]
    try:
        await context.bot.send_message(
            chat_id=client_id,
            text="⭐ **Salut ! Ton colis est censé être arrivé !**\n\nQu'as-tu pensé de ta commande ? N'hésite pas à laisser ton avis sur notre groupe dédié :",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⭐ Laisser mon avis", url=REVIEWS_GROUP_LINK)]]),
            parse_mode="Markdown"
        )
    except Exception:
        pass

# ==========================================
# RÉCEPTION ET ANTI-FRAUDE (SCREENSHOT)
# ==========================================
async def receive_payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.photo:
        await update.message.reply_text("⚠️ Ceci n'est pas une image. Envoie la capture d'écran de ton reçu.")
        return WAITING_FOR_SCREENSHOT

    if user.id in pending_reminders:
        pending_reminders[user.id].schedule_removal()
        del pending_reminders[user.id]

    photo_file = await update.message.photo[-1].get_file()
    photo_path = await photo_file.download_as_bytearray()
    
    # Calcul du Hash anti-fraude
    img_hash = hashlib.md5(photo_path).hexdigest()
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO transactions (img_hash, user_id, amount, status) VALUES (?, ?, 0, 'PENDING')", (img_hash, user.id))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        await update.message.reply_text("⛔ **Fraude détectée :** Cette capture d'écran a déjà été utilisée par le passé.")
        return ConversationHandler.END
    conn.close()

    cart_info = current_cart_data.get(user.id, {}).get("items", "Non spécifié")
    
    # Vérification d'un code promo unique lié au client
    promo_msg = "Aucun code promo."
    for code, data in unique_promo_codes.items():
        if data["user_id"] == user.id and not data["used"]:
            unique_promo_codes[code]["used"] = True
            promo_msg = f"✨ Code promo appliqué : -{data['value']}€"
            break

    admin_caption = (
        "🚨 **NOUVEAU REÇU DE PAIEMENT !** 🚨\n\n"
        f"👤 **Client :** {user.first_name} (@{user.username or 'N/A'})\n"
        f"🆔 **ID :** `{user.id}`\n"
        f"📦 **Articles :** {cart_info}\n"
        f"{promo_msg}"
    )
    
    admin_keyboard = [
        [
            InlineKeyboardButton("✅ Valider", callback_data=f"admin_accept_{user.id}"),
            InlineKeyboardButton("📦 Expédier", callback_data=f"admin_ship_{user.id}")
        ]
    ]
    
    try:
        await context.bot.send_photo(
            chat_id=ADMIN_GROUP_ID,
            photo=photo_path,
            caption=admin_caption,
            reply_markup=InlineKeyboardMarkup(admin_keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Erreur envoi admin: {e}")
    
    await update.message.reply_text("🎉 **Reçu bien reçu !** Transmis à l'équipe pour vérification.")
    return ConversationHandler.END

# ==========================================
# GESTION ADMIN (VALIDATION & EXPÉDITION)
# ==========================================
async def admin_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if "admin_accept_" in data:
        client_id = int(data.split("_")[2])
        await query.edit_message_caption(caption=query.message.caption + "\n\n✅ **STATUT : VALIDÉ**", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=client_id, text="✅ Ton paiement a été validé ! Ton colis est en préparation.")
        except Exception:
            pass
            
    elif "admin_ship_" in data:
        client_id = int(data.split("_")[2])
        await query.edit_message_caption(caption=query.message.caption + "\n\n🚚 **STATUT : EXPÉDIÉ**", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=client_id, text=f"🚚 **Ton colis a été expédié !**\n\nSuivi Colissimo : {COLISSUIVI_LINK}", parse_mode="Markdown")
        except Exception:
            pass
        # Programmer la demande d'avis 48h plus tard
        context.job_queue.run_once(send_review_request, 172800, data={"client_id": client_id})

# ==========================================
# COMMANDES ADMIN SPÉCIALES (/offre, /ban, /stats, /stock, /drop)
# ==========================================
async def generate_offer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_ADMIN_USER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage : `/offre [user_id] [montant]`", parse_mode="Markdown")
        return

    target_user_id = int(context.args[0])
    amount = context.args[1]
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    unique_promo_codes[code] = {"user_id": target_user_id, "value": amount, "used": False}
    await update.message.reply_text(f"✅ Code `{code}` généré pour `{target_user_id}` (-{amount}€)", parse_mode="Markdown")
    
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎁 **Cadeau exclusif !**\n\nVoici ton code promo personnel : `{code}` (-{amount}€)",
            parse_mode="Markdown"
        )
    except Exception:
        pass

async def ban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_ADMIN_USER_ID:
        return
    if not context.args:
        return
    target_id = int(context.args[0])
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO blacklist (user_id) VALUES (?)", (target_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🚫 Utilisateur `{target_id}` banni avec succès.", parse_mode="Markdown")

async def show_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_ADMIN_USER_ID:
        return
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*), COUNT(DISTINCT user_id) FROM transactions")
    res = c.fetchone()
    total_tx, unique_clients = res[0], res[1]
    conn.close()
    
    await update.message.reply_text(
        f"📊 **Dashboard Statistiques**\n\n"
        f"• Total des reçus soumis : `{total_tx}`\n"
        f"• Clients uniques : `{unique_clients}`",
        parse_mode="Markdown"
    )

async def set_stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_ADMIN_USER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage : `/stock [article] [quantité]`", parse_mode="Markdown")
        return
        
    item, qty = context.args[0], int(context.args[1])
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO stock (item, qty) VALUES (?, ?)", (item, qty))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ Stock mis à jour : `{item}` = `{qty}` restants.", parse_mode="Markdown")
    if qty <= 3:
        await update.message.reply_text(f"⚠️ **Alerte stock faible** pour `{item}` ({qty} restants).")

async def drop_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_ADMIN_USER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage : `/drop [catégorie ou all] [message]`", parse_mode="Markdown")
        return
        
    target = context.args[0].lower()
    msg = " ".join(context.args[1:])
    
    if target == "all":
        recipients = known_users
    elif target in restock_subscribers:
        recipients = restock_subscribers[target]
    else:
        await update.message.reply_text("⚠️ Catégorie inconnue (`tech_fleece`, `pants`, `tees` ou `all`).")
        return
        
    success = 0
    for uid in recipients:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"🚨 **ALERTE NOUVEAUTÉ !** 🚨\n\n{msg}\n\n👉 Fonce sur le canal !",
                parse_mode="Markdown"
            )
            success += 1
        except Exception:
            pass
            
    await update.message.reply_text(f"✅ Broadcast envoyé à {success} utilisateurs.")

# ==========================================
# BOUTONS DU MENU INTERACTIF CLIENT
# ==========================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if is_blacklisted(query.from_user.id):
        await query.message.reply_text("⛔ Accès refusé.")
        return ConversationHandler.END

    data = query.data

    if data == "restock_menu":
        user_id = query.from_user.id
        sub_tf = "✅ " if user_id in restock_subscribers["tech_fleece"] else "🔔 "
        sub_pants = "✅ " if user_id in restock_subscribers["pants"] else "🔔 "
        sub_tees = "✅ " if user_id in restock_subscribers["tees"] else "🔔 "

        text = (
            "🔔 **Centre d'Alertes Restock**\n\n"
            "Abonne-toi aux catégories de ton choix pour être prévenu en priorité :"
        )
        keyboard = [
            [InlineKeyboardButton(f"{sub_tf}Ensembles / Tech Fleece", callback_data="sub_tech_fleece")],
            [InlineKeyboardButton(f"{sub_pants}Pantalons / Cargos", callback_data="sub_pants")],
            [InlineKeyboardButton(f"{sub_tees}T-shirts / Sweats", callback_data="sub_tees")],
            [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
        ]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("sub_"):
        user_id = query.from_user.id
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
                [InlineKeyboardButton(f"{sub_tf}Ensembles / Tech Fleece", callback_data="sub_tech_fleece")],
                [InlineKeyboardButton(f"{sub_pants}Pantalons / Cargos", callback_data="sub_pants")],
                [InlineKeyboardButton(f"{sub_tees}T-shirts / Sweats", callback_data="sub_tees")],
                [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
            ]
            await query.message.edit_text(f"🔔 **Centre d'Alertes Restock**\n\n{st}", reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "referral_menu":
        user_id = query.from_user.id
        link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
        count = referral_counts.get(user_id, 0)
        text = (
            "🤝 **Programme de Parrainage**\n\n"
            f"Partage ton lien personnel :\n`{link}`\n\n"
            f"📊 Filleuls validés : `{count}`"
        )
        kbd = [
            [InlineKeyboardButton("💬 Réclamer mes avantages", url=SUPPORT_LINK)],
            [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
        ]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "my_orders":
        text = "📦 **Mes Commandes**\n\nLes statuts de tes commandes s'affichent automatiquement après validation de ton reçu."
        kbd = [[InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "promo_codes":
        promos = "\n".join(active_promo_codes)
        text = f"🏷️ **Offres & Codes Promo**\n\n{promos}"
        kbd = [[InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "contest":
        text = (
            "🎁 **Tirage au sort & Concours**\n\n"
            "1️⃣ Abonne-toi à TikTok & Vinted\n"
            "2️⃣ Partage ton lien de parrainage\n"
            "Envoie tes preuves au support !"
        )
        kbd = [
            [InlineKeyboardButton("🎵 TikTok", url=TIKTOK_LINK)],
            [InlineKeyboardButton("🛍️ Vinted", url=VINTED_LINK)],
            [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
        ]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "size_guide":
        text = "📏 **Guide des tailles**\n\n• S : Jusqu'à 1m80\n• M : 1m75 - 1m85\n• L : 1m80 - 1m90\n• XL : 1m90+"
        kbd = [[InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "track_parcel":
        text = "🚚 **Suivi Colissimo**\n\nClique ci-dessous pour entrer ton numéro :"
        kbd = [
            [InlineKeyboardButton("🔍 Suivi La Poste", url=COLISSUIVI_LINK)],
            [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
        ]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "faq_menu":
        text = "📌 **FAQ Interactive**\n\n100% sécurisé via Stripe, envois en 48h max en Colissimo."
        kbd = [[InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "back":
        await start(update, context)

    return ConversationHandler.END

# ==========================================
# LANCEMENT DU BOT
# ==========================================
def main():
    init_db()
    application = ApplicationBuilder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_for_cart, pattern="^paid$")],
        states={
            ENTERING_CART: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_cart_items)],
            WAITING_FOR_SCREENSHOT: [MessageHandler(filters.PHOTO & ~filters.COMMAND, receive_payment_screenshot)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("suivi", start))
    application.add_handler(CommandHandler("offre", generate_offer_command))
    application.add_handler(CommandHandler("ban", ban_user_command))
    application.add_handler(CommandHandler("stats", show_stats_command))
    application.add_handler(CommandHandler("stock", set_stock_command))
    application.add_handler(CommandHandler("drop", drop_broadcast_command))
    application.add_handler(CallbackQueryHandler(admin_action_handler, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Bot opérationnel avec stockage persistant SQLite et toutes les fonctionnalités !")
    application.run_polling()

if __name__ == "__main__":
    main()
