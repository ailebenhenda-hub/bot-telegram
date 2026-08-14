import os
import logging
import sqlite3
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

RAW_ADMIN_ID = os.getenv("ADMIN_GROUP_ID", "-1003956183527")
try:
    ADMIN_GROUP_ID = int(RAW_ADMIN_ID)
except ValueError:
    ADMIN_GROUP_ID = RAW_ADMIN_ID

SELLER_USERNAME = "idf_runningshop"
REVOLUT_LINK = "https://revolut.me/shvppeur_corp"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# --- 1. BASE DE DONNÉES SQLITE ---
def init_db():
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            points INTEGER DEFAULT 0,
            banned INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item_id TEXT,
            item_name TEXT,
            price REAL,
            date TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user(user_id, username=""):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT points, banned FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    if not res:
        cursor.execute("INSERT INTO users (user_id, username, points, banned) VALUES (?, ?, 0, 0)", (user_id, username))
        conn.commit()
        res = (0, 0)
    conn.close()
    return {"points": res[0], "banned": res[1]}

def add_points(user_id, points):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (points, user_id))
    conn.commit()
    conn.close()

def set_ban(user_id, status):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET banned = ? WHERE user_id = ?", (status, user_id))
    conn.commit()
    conn.close()

referrals = {}
user_join_dates = {}
reservations = {}  # {item_id: {"user_id": int, "expires": datetime}}
known_users = set()

CATALOG = {
    "1": {"name": "Pantalon Nike Trail", "taille": "S", "etat": "8/10", "prix": 60, "available": True},
    "2": {"name": "Pantalon Nike Aeroswift", "taille": "M", "etat": "Excellent état", "prix": 75, "available": True},
    "3": {"name": "Pantalon Nike Phenom Elite", "taille": "L", "etat": "Excellent état", "prix": 90, "available": True},
    "4": {"name": "Sweat Nike Tech Aviateur v1", "taille": "M", "etat": "Excellent état", "prix": 60, "available": True},
    "5": {"name": "Pantalon Nike Phenom Elite (Gris)", "taille": "L", "etat": "Excellent état", "prix": 90, "available": True},
    "6": {"name": "Tee-Shirt Nike Trail", "taille": "S", "etat": "Excellent état", "prix": 40, "available": True},
    "7": {"name": "Tee-Shirt Nike Running Division", "taille": "M", "etat": "Excellent état", "prix": 35, "available": True},
    "8": {"name": "Tee-Shirt Nike Dri-Fit (Rouge)", "taille": "S", "etat": "Excellent état", "prix": 30, "available": True},
    "9": {"name": "Sweat Nike Tech Fleece (Noir)", "taille": "S", "etat": "Excellent état", "prix": 70, "available": True},
    "10": {"name": "Pantalon Nike Phenom Elite Poche Noir", "taille": "S", "etat": "8/10", "prix": 80, "available": True}
}

def clean_reservations():
    now = datetime.now()
    expired = [k for k, v in reservations.items() if v["expires"] < now]
    for k in expired:
        del reservations[k]

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📦 Catalogue & Stock", callback_data="show_catalog"),
            InlineKeyboardButton("🔍 Filtrer par taille", callback_data="filter_size")
        ],
        [
            InlineKeyboardButton("🤝 Parrainage (-5€)", callback_data="show_referral"),
            InlineKeyboardButton("⭐ Fidélité", callback_data="show_points")
        ],
        [
            InlineKeyboardButton("🚚 Livraisons & Offres", callback_data="show_info"),
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
    user = update.effective_user
    known_users.add(user.id)
    u_data = get_user(user.id, user.username)
    if u_data["banned"]:
        return

    if context.args and context.args[0].isdigit():
        referrer_id = int(context.args[0])
        if referrer_id != user.id and user.id not in referrals:
            referrals[user.id] = referrer_id
            user_join_dates[user.id] = datetime.now()

    welcome_msg = (
        f"👋 Bienvenue {user.first_name} sur IDF Running Shop !\n\n"
        "Boutique indépendante streetwear & vêtements running. 🔥\n"
        "• Port offert dès 170 € d'achat !\n"
        "• Remise de -5€ / article supplémentaire dès 70 € d'achat.\n\n"
        "Envoie le numéro d'un article (ex: #1) pour réserver (durée : 15 min) !"
    )
    await update.message.reply_text(welcome_msg, reply_markup=get_main_keyboard())

# --- 4. FILTRE PAR TAILLE & CALLBACKS ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    clean_reservations()

    user_id = query.from_user.id
    u_data = get_user(user_id)
    if u_data["banned"]:
        return

    if query.data == "show_catalog":
        text = "🔥 STOCK ACTUEL 🔥\n\n"
        for item_id, data in CATALOG.items():
            if not data["available"]:
                status = "🔴 [VENDU]"
            elif item_id in reservations:
                status = "⏳ [RÉSERVÉ - 15min]"
            else:
                status = f"• Taille : {data['taille']} | État : {data['etat']} | {data['prix']} €"
            text += f"#{item_id} - {data['name']}\n   {status}\n\n"
        await query.edit_message_text(text=text, reply_markup=get_main_keyboard())

    elif query.data == "filter_size":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Taille S", callback_data="size_S"), InlineKeyboardButton("Taille M", callback_data="size_M")],
            [InlineKeyboardButton("Taille L", callback_data="size_L"), InlineKeyboardButton("Taille XL", callback_data="size_XL")],
            [InlineKeyboardButton("🔙 Retour", callback_data="show_catalog")]
        ])
        await query.edit_message_text("Sélectionne ta taille :", reply_markup=kb)

    elif query.data.startswith("size_"):
        size = query.data.split("_")[1]
        text = f"🔎 Articles disponibles en taille {size} :\n\n"
        found = False
        for item_id, data in CATALOG.items():
            if data["taille"] == size and data["available"] and item_id not in reservations:
                text += f"#{item_id} - {data['name']} ({data['prix']} €)\n"
                found = True
        if not found:
            text += "Aucun article disponible pour cette taille."
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

    # --- 6. PROGRAMME DE FIDÉLITÉ (120 pts = -10€) ---
    elif query.data == "show_points":
        pts = u_data["points"]
        text = (
            f"⭐ TES POINTS FIDÉLITÉ : {pts} pts\n\n"
            "• 1 € dépensé = 1 point gagné.\n"
            "• Atteins 120 points pour débloquer -10 € sur ta commande !\n"
        )
        if pts >= 120:
            text += "\n🎉 Tu as 120 pts ! Envoie un MP au vendeur pour utiliser tes -10 € !"
        await query.edit_message_text(text=text, reply_markup=get_main_keyboard())

    elif query.data == "show_info":
        text = (
            "🚚 OFFRES & LIVRAISON\n\n"
            "🔥 RÈGLES DE RÉDUCTIONS :\n"
            "• Dès 70 € d'achat total : -5 € appliqués sur chaque article supplémentaire !\n"
            "• Dès 170 € d'achat total : Livraison Colissimo 100% GRATUITE !\n\n"
            "📍 Remise en main propre (93 / Gares IDF) ou Colissimo (+6 € sauf si >170 €)."
        )
        await query.edit_message_text(text=text, reply_markup=get_main_keyboard())

    elif query.data.startswith("claim_"):
        admin_name = query.from_user.first_name
        new_text = query.message.text + f"\n\n✅ Pris en charge par {admin_name}"
        await query.edit_message_text(text=new_text, reply_markup=None)

    elif query.data.startswith("confirm_pay_"):
        target_id = int(query.data.split("_")[2])
        add_points(target_id, 50)
        await context.bot.send_message(chat_id=target_id, text="✅ Ton paiement a été validé par l'équipe ! Tes points de fidélité ont été crédités.")
        await query.edit_message_text(text=query.message.text + "\n\n✅ PAIEMENT VALIDÉ", reply_markup=None)

# --- 3. RÉSERVATION 15 MIN & RECEPTION DES MESSAGES / PHOTOS ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clean_reservations()
    if str(update.effective_chat.id) == str(ADMIN_GROUP_ID):
        return

    user = update.effective_user
    known_users.add(user.id)
    u_data = get_user(user.id, user.username)
    if u_data["banned"]:
        return

    # --- 8. CAPTURE D'ÉCRAN DE PAIEMENT ---
    if update.message.photo:
        photo = update.message.photo[-1].file_id
        admin_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Valider le paiement", callback_data=f"confirm_pay_{user.id}")]
        ])
        await context.bot.send_photo(
            chat_id=ADMIN_GROUP_ID,
            photo=photo,
            caption=f"💳 REÇU DE PAIEMENT REÇU\nClient : {user.first_name} (@{user.username})\nID : {user.id}",
            reply_markup=admin_kb
        )
        await update.message.reply_text("✅ Reçu transmis à l'équipe. On valide ta commande rapidement !")
        return

    text = update.message.text.strip()

    if text.startswith("#") and text[1:].isdigit():
        item_id = text[1:]
        if item_id in CATALOG:
            item = CATALOG[item_id]

            if not item["available"]:
                await update.message.reply_text("❌ Cet article est définitivement vendu !")
                return

            if item_id in reservations and reservations[item_id]["user_id"] != user.id:
                await update.message.reply_text("⏳ Cet article est en cours de réservation par un autre client (15 min).")
                return

            reservations[item_id] = {
                "user_id": user.id,
                "expires": datetime.now() + timedelta(minutes=15)
            }

            confirm_text = (
                f"✅ Article #{item_id} ({item['name']}) bloqué pour toi pendant 15 minutes !\n"
                f"• Prix : {item['prix']} €\n\n"
                f"Envoie ton reçu Revolut ici en photo ou contacte @{SELLER_USERNAME} pour finaliser."
            )
            await update.message.reply_text(confirm_text, reply_markup=get_main_keyboard())

            claim_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⏳ Prise en charge", callback_data=f"claim_{item_id}")]])
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=f"🚨 NOUVELLE RÉSERVATION (15 min)\nClient : {user.first_name} (@{user.username})\nArticle : #{item_id} - {item['name']}",
                reply_markup=claim_kb
            )
            return

    await update.message.reply_text(f"Tape le numéro d'un article (ex: #1) ou contacte @{SELLER_USERNAME}.", reply_markup=get_main_keyboard())

# --- COMMANDES ADMIN ---
async def cmd_vendu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return
    if context.args and context.args[0] in CATALOG:
        item_id = context.args[0]
        CATALOG[item_id]["available"] = False
        await update.message.reply_text(f"❌ Article #{item_id} ({CATALOG[item_id]['name']}) marqué comme VENDU.")

async def cmd_resto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return
    if context.args and context.args[0] in CATALOG:
        item_id = context.args[0]
        CATALOG[item_id]["available"] = True
        await update.message.reply_text(f"✅ Article #{item_id} ({CATALOG[item_id]['name']}) remis EN STOCK.")

async def cmd_annonce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return
    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("Utilisation : `/annonce Votre message`", parse_mode="Markdown")
        return
    count = 0
    broadcast_text = f"📢 **ANNONCE IDF RUNNING SHOP**\n\n{message}"
    for user_id in known_users:
        try:
            await context.bot.send_message(chat_id=user_id, text=broadcast_text, parse_mode="Markdown")
            count += 1
        except Exception:
            continue
    await update.message.reply_text(f"🚀 Annonce envoyée à {count} client(s).")

# --- 2. EXPORT EXCEL / CSV ---
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sales")
    rows = cursor.fetchall()
    conn.close()

    csv_data = "ID,User_ID,Article_ID,Nom,Prix,Date\n"
    for r in rows:
        csv_data += f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]}\n"

    with open("ventes.csv", "w", encoding="utf-8") as f:
        f.write(csv_data)

    await context.bot.send_document(chat_id=ADMIN_GROUP_ID, document=open("ventes.csv", "rb"), caption="📊 Bilan des ventes Excel/CSV")

# --- 10. ANTI-SPAM & BAN ---
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return
    if context.args:
        target_id = int(context.args[0])
        set_ban(target_id, 1)
        await update.message.reply_text(f"🚫 L'utilisateur {target_id} a été banni.")

async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return
    if context.args:
        target_id = int(context.args[0])
        set_ban(target_id, 0)
        await update.message.reply_text(f"✅ L'utilisateur {target_id} a été débanni.")

# --- 5. GÉNÉRATION DE FACTURE ---
async def cmd_facture(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return
    if len(context.args) >= 2:
        client_name = context.args[0]
        montant = context.args[1]
        facture = (
            "📄 **FACTURE - IDF RUNNING SHOP**\n"
            f"Client : {client_name}\n"
            f"Date : {datetime.now().strftime('%d/%m/%Y')}\n"
            f"Montant Total : {montant} €\n"
            "Statut : PAIEMENT VALIDÉ\n\n"
            "Merci pour votre confiance !"
        )
        await update.message.reply_text(facture, parse_mode="Markdown")

# --- 7. SUIVI COLISSIMO ---
async def cmd_suivi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return
    if len(context.args) >= 2:
        target_id = int(context.args[0])
        tracking_num = context.args[1]
        msg = f"📦 **SUIVI DE TON COLIS**\n\nTon numéro de suivi Colissimo : `{tracking_num}`\nSuis ton colis ici : https://www.laposte.fr/outils/suivre-vos-envois"
        try:
            await context.bot.send_message(chat_id=target_id, text=msg, parse_mode="Markdown")
            await update.message.reply_text(f"✅ Numéro de suivi envoyé au client {target_id}.")
        except Exception as e:
            await update.message.reply_text(f"❌ Impossible d'envoyer le MP : {e}")
    else:
        await update.message.reply_text("Utilisation : `/suivi ID_CLIENT NUMERO_COLISSIMO`", parse_mode="Markdown")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("vendu", cmd_vendu))
    app.add_handler(CommandHandler("resto", cmd_resto))
    app.add_handler(CommandHandler("annonce", cmd_annonce))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("facture", cmd_facture))
    app.add_handler(CommandHandler("suivi", cmd_suivi))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
