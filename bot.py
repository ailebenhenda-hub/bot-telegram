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
from groq import Groq

# Configuration
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-5313705184"))

# Initialisation Groq
groq_client = Groq(api_key=GROQ_API_KEY)

# Stockage
DB_DIR = "/app/data" if os.path.exists("/app/data") else "."
DB_NAME = os.path.join(DB_DIR, "bot_data.db")

# Liens officiels (Tous les liens sont là, y compris ton DM Telegram)
REVOLUT_PAYMENT_LINK = "https://revolut.me/shvppeur_corp"
SUPPORT_LINK = "https://t.me/idfrunningvip"
COLISSUIVI_LINK = "https://www.laposte.fr/outils/suivre-vos-envois"
SNAPCHAT_LINK = "https://snapchat.com/t/KLL65sDJ"
VINTED_LINK = "https://www.vinted.fr/member/idf_runningshop"
TIKTOK_LINK = "https://www.tiktok.com/@idf_runningshop?_r=1&_t=ZN-98riuu613NW"
TELEGRAM_DM_LINK = "https://t.me/idfrunningvip"  # Ton lien direct pour te DM

# États
ENTERING_CART, WAITING_FOR_SCREENSHOT = range(2)
known_users = set()
restock_subscribers = {"tech_fleece": set(), "pants": set(), "tees": set()}
current_cart_data = {}
referral_counts = {}
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

# --- IA GROQ (INVENTAIRE & TOUS LES LIENS FORCÉS) ---
async def handle_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    system_prompt = (
        "Tu es l'assistant virtuel de 'IDF Running // V.I.P', un revendeur indépendant de streetwear / lifestyle en Île-de-France. "
        "INTERDICTION FORMELLE d'utiliser les mots 'boutique', 'magasin' ou 'enseigne'.\n\n"
        "RÈGLE 1 (STOCK) : Si on te demande ce que tu vends, ce que tu as en stock, ou une question sur tes articles, tu DOIS commencer par exactement : "
        "'Actuellement on vend :' et lister uniquement ces articles :\n"
        "- Pantalon Nike Trail (60 €)\n"
        "- Sweat Nike Tech Fleece (70 €)\n"
        "- Pantalon Nike Phenom Elite (Gris ou Noir, 80€ à 90 €)\n"
        "- Pantalon Nike Aeroswift (75 €)\n"
        "- Tee-shirts Nike (Dri-Fit Rouge 30 €, Nike Running Division Noir 35 €, Nike Trail Gris Clair 40 €).\n\n"
        "RÈGLE 2 (LIENS OBLIGATOIRES) : Si on te demande ton Snapchat, ton Vinted, ton TikTok, ton lien pour te DM / contacter sur Telegram, tu DOIS obligatoirement inclure les liens bruts correspondants :\n"
        f"- Telegram DM : {TELEGRAM_DM_LINK}\n"
        f"- Snapchat : {SNAPCHAT_LINK}\n"
        f"- Vinted : {VINTED_LINK}\n"
        f"- TikTok : {TIKTOK_LINK}\n\n"
        "RÈGLE 3 (MODE DE VENTE) : Envoi Colissimo soigné ou remise en main propre en Île-de-France (principalement dans le 93 et en gares selon tes disponibilités). "
        "Paiement par Revolut (https://revolut.me/shvppeur_corp).\n"
        "Sois direct, ultra-clair et donne immédiatement les informations demandées sans inventer de règles."
    )
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
            temperature=0.1, max_tokens=250
        )
        await update.message.reply_text(completion.choices[0].message.content)
    except Exception as e:
        logging.error(f"Erreur IA : {e}")
        await update.message.reply_text("Petit souci technique, utilise le menu pour m'aider !")

# --- MENU PRINCIPAL ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or is_blacklisted(user.id):
        return
    known_users.add(user.id)
    
    welcome_message = (
        "👋 **Bienvenue chez IDF Running // V.I.P 🔌** 🛒\n\n"
        "Revente indépendante de vêtements streetwear exclusifs.\n"
        "Que souhaites-tu faire aujourd'hui ?"
    )
    keyboard = [
        [InlineKeyboardButton("📦 Payer par Revolut", url=REVOLUT_PAYMENT_LINK)],
        [InlineKeyboardButton("🔔 Alertes Restock", callback_data="restock_menu")],
        [InlineKeyboardButton("🏷️ Codes Promo", callback_data="promo_codes")],
        [InlineKeyboardButton("🤝 Parrainage", callback_data="referral_menu")],
        [InlineKeyboardButton("📱 Réseaux (Vinted, Snap, TikTok)", callback_data="vinted_menu")],
        [InlineKeyboardButton("🤝 Remise en main propre (93 / Gares IDF)", callback_data="hand_delivery")],
        [InlineKeyboardButton("📦 Mes Commandes", callback_data="my_orders")],
        [InlineKeyboardButton("📏 Guide des tailles", callback_data="size_guide")],
        [InlineKeyboardButton("🚚 Suivre mon colis", callback_data="track_parcel")],
        [InlineKeyboardButton("✅ J'ai effectué mon paiement", callback_data="paid")],
        [InlineKeyboardButton("💬 Me DM sur Telegram", url=TELEGRAM_DM_LINK)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.edit_text(welcome_message, reply_markup=reply_markup, parse_mode="Markdown")
    
    return ConversationHandler.END

# --- GESTION DES BOUTONS INTERACTIFS ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if is_blacklisted(query.from_user.id):
        await query.message.reply_text("⛔ Accès refusé.")
        return

    data = query.data

    if data == "restock_menu":
        user_id = query.from_user.id
        sub_tf = "✅ " if user_id in restock_subscribers["tech_fleece"] else "🔔 "
        sub_pants = "✅ " if user_id in restock_subscribers["pants"] else "🔔 "
        sub_tees = "✅ " if user_id in restock_subscribers["tees"] else "🔔 "

        text = "🔔 **Centre d'Alertes Restock**\n\nAbonne-toi aux catégories de ton choix :"
        keyboard = [
            [InlineKeyboardButton(f"{sub_tf}Tech Fleece / Sweats", callback_data="sub_tech_fleece")],
            [InlineKeyboardButton(f"{sub_pants}Pantalons", callback_data="sub_pants")],
            [InlineKeyboardButton(f"{sub_tees}T-shirts", callback_data="sub_tees")],
            [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

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
                [InlineKeyboardButton(f"{sub_tf}Tech Fleece / Sweats", callback_data="sub_tech_fleece")],
                [InlineKeyboardButton(f"{sub_pants}Pantalons", callback_data="sub_pants")],
                [InlineKeyboardButton(f"{sub_tees}T-shirts", callback_data="sub_tees")],
                [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
            ]
            await query.message.edit_text(f"🔔 **Centre d'Alertes Restock**\n\n{st}", reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "referral_menu":
        user_id = query.from_user.id
        link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
        count = referral_counts.get(user_id, 0)
        text = f"🤝 **Programme de Parrainage**\n\nPartage ton lien personnel :\n`{link}`\n\n📊 Filleuls validés : `{count}`"
        kbd = [
            [InlineKeyboardButton("💬 Me DM directement", url=TELEGRAM_DM_LINK)],
            [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "promo_codes":
        promos = "\n".join(active_promo_codes)
        text = f"🏷️ **Offres & Codes Promo**\n\n{promos}"
        kbd = [[InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "vinted_menu":
        text = "📱 **Vinted, Snapchat & TikTok**\n\nRetrouve mes réseaux et profils officiels :"
        kbd = [
            [InlineKeyboardButton("🛍️ Mon Vinted", url=VINTED_LINK)],
            [InlineKeyboardButton("👻 Mon Snapchat", url=SNAPCHAT_LINK)],
            [InlineKeyboardButton("🎵 Mon TikTok", url=TIKTOK_LINK)],
            [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "hand_delivery":
        text = "🤝 **Remise en main propre**\n\nDisponible en Île-de-France (principalement dans le 93 et en gares selon mes disponibilités). Contacte-moi pour fixer les détails :"
        kbd = [
            [InlineKeyboardButton("💬 Me DM sur Telegram", url=TELEGRAM_DM_LINK)],
            [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "my_orders":
        text = "📦 **Mes Commandes**\n\nLes statuts de tes commandes s'affichent automatiquement après validation de ton reçu."
        kbd = [[InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "size_guide":
        text = "📏 **Guide des tailles**\n\n• S : Jusqu'à 1m80\n• M : 1m75 - 1m85\n• L : 1m80 - 1m90\n• XL : 1m90+"
        kbd = [[InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "track_parcel":
        text = "🚚 **Suivi Colissimo**\n\nClique ci-dessous pour suivre ton colis La Poste :"
        kbd = [
            [InlineKeyboardButton("🔍 Suivi La Poste", url=COLISSUIVI_LINK)],
            [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "back":
        await start(update, context)

# --- TUNNEL DE COMMANDE ---
async def ask_for_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if is_blacklisted(query.from_user.id):
        await query.message.reply_text("⛔ Accès refusé.")
        return ConversationHandler.END
    await query.message.reply_text("📝 **Détaille ta commande** (ex: Pantalon Nike Trail Taille S) :", parse_mode="Markdown")
    return ENTERING_CART

async def save_cart_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_cart_data[user_id] = {"items": update.message.text}
    await update.message.reply_text(
        "📸 Parfait !\n\nEnvoie maintenant la **capture d'écran de ton reçu Revolut** pour valider ta commande :"
    )
    return WAITING_FOR_SCREENSHOT

async def receive_payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.photo:
        await update.message.reply_text("⚠️ Ceci n'est pas une image. Envoie la capture de ton reçu.")
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
        await update.message.reply_text("⛔ **Doublon détecté :** Cette capture a déjà été utilisée.")
        return ConversationHandler.END
    conn.close()

    cart_info = current_cart_data.get(user.id, {}).get("items", "Non spécifié")
    admin_caption = (
        "🚨 **NOUVEAU REÇU REVOLUT !** 🚨\n\n"
        f"👤 **Client :** {user.first_name} (@{user.username or 'N/A'})\n"
        f"🆔 **ID :** `{user.id}`\n"
        f"📦 **Articles :** {cart_info}"
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
    
    await update.message.reply_text("🎉 **Reçu bien reçu !** Je transmets à l'équipe.")
    return ConversationHandler.END

async def admin_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if "admin_accept_" in data:
        client_id = int(data.split("_")[2])
        await query.edit_message_caption(caption=query.message.caption + "\n\n✅ **STATUT : VALIDÉ**", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=client_id, text="✅ Paiement validé ! On gère l'envoi ou la remise en main propre.")
        except Exception:
            pass
            
    elif "admin_ship_" in data:
        client_id = int(data.split("_")[2])
        await query.edit_message_caption(caption=query.message.caption + "\n\n🚚 **STATUT : EXPÉDIÉ**", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=client_id, text=f"🚚 **Colis expédié !**\n\nSuivi Colissimo : {COLISSUIVI_LINK}", parse_mode="Markdown")
        except Exception:
            pass

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
    app.add_handler(CallbackQueryHandler(admin_action_handler, pattern="^admin_"))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_chat))
    
    print("Bot 100% blindé avec Telegram DM, Snap, Vinted, TikTok, Stock et Main propre IDF !")
    app.run_polling()

if __name__ == "__main__":
    main()
