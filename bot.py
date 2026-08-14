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
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

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

    welcome_msg = (
        f"👋 Bienvenue {user.first_name} sur IDF Running Shop !\n\n"
        "Boutique indépendante streetwear & vêtements running. 🔥\n"
        "• Port offert dès 170 € d'achat !\n"
        "• Remise de -5€ / article supplémentaire dès 70 € d'achat.\n\n"
        "Envoie le numéro d'un article (ex: #1) pour réserver (durée : 15 min) !"
    )
    await update.message.reply_text(welcome_msg, reply_markup=get_main_keyboard())

# --- CALLBACKS & FIDÉLITÉ (200 PTS = -10€) ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    clean_reservations()

    user_id = query.from_user.id
    admin_name = query.from_user.first_name
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

    elif query.data == "show_points":
        pts = u_data["points"]
        text = (
            f"⭐ TES POINTS FIDÉLITÉ : {pts} pts\n\n"
            "• 1 € dépensé = 1 point gagné.\n"
            "• Atteins 200 points pour débloquer -10 € sur ta commande !\n"
        )
        if pts >= 200:
            text += "\n🎉 Tu as atteint 200 pts ! Envoie un MP au vendeur pour utiliser tes -10 € !"
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
        new_text = query.message.text + f"\n\n✅ Pris en charge par {admin_name}"
        await query.edit_message_text(text=new_text, reply_markup=None)

    # Validation du paiement avec attribution exacte du montant en points
    elif query.data.startswith("confirm_pay_"):
        parts = query.data.split("_")
        target_id = int(parts[2])
        price = float(parts[3]) if len(parts) > 3 else 0

        add_points(target_id, int(price))
        await context.bot.send_message(
            chat_id=target_id, 
            text=f"✅ Ton paiement de {int(price)} € a été validé ! Tu as gagné +{int(price)} points de fidélité. 🎁"
        )
        new_text = query.message.caption if query.message.caption else query.message.text
        new_text += f"\n\n✅ PAIEMENT VALIDÉ PAR {admin_name} (+{int(price)} pts)"
        await query.edit_message_caption(caption=new_text, reply_markup=None)

    # Refus du paiement
    elif query.data.startswith("refuse_pay_"):
        parts = query.data.split("_")
        target_id = int(parts[2])

        await context.bot.send_message(
            chat_id=target_id, 
            text="❌ Ton reçu de paiement n'a pas pu être validé. Merci de contacter le vendeur en MP (@idf_runningshop)."
        )
        new_text = query.message.caption if query.message.caption else query.message.text
        new_text += f"\n\n❌ PAIEMENT REFUSÉ PAR {admin_name}"
        await query.edit_message_caption(caption=new_text, reply_markup=None)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clean_reservations()
    if str(update.effective_chat.id) == str(ADMIN_GROUP_ID):
        return

    user = update.effective_user
    known_users.add(user.id)
    u_data = get_user(user.id, user.username)
    if u_data["banned"]:
        return

    # Gestion de la photo de paiement
    if update.message.photo:
        photo = update.message.photo[-1].file_id
        
        # Chercher s'il y a une réservation en cours pour connaître le montant exact
        item_price = 0
        for item_id, res_data in reservations.items():
            if res_data["user_id"] == user.id:
                item_price = CATALOG[item_id]["prix"]
                break

        admin_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Valider", callback_data=f"confirm_pay_{user.id}_{item_price}"),
                InlineKeyboardButton("❌ Refuser", callback_data=f"refuse_pay_{user.id}")
            ]
        ])
        await context.bot.send_photo(
            chat_id=ADMIN_GROUP_ID,
            photo=photo,
            caption=f"💳 REÇU DE PAIEMENT REÇU\nClient : {user.first_name} (@{user.username})\nID : {user.id}\nMontant estimé : {item_price} €",
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
                text=f"🚨 NOUVELLE RÉSERVATION (15 min)\nClient : {user.first_name} (@{user.username})\nArticle : #{item_id} - {item['name']} ({item['prix']} €)",
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

# --- GÉNÉRATION DE FACTURE PDF RÉELLE ---
async def cmd_facture(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return

    if len(context.args) >= 3:
        client_name = context.args[0]
        article_name = context.args[1]
        montant = context.args[2]

        pdf_path = f"facture_{client_name}.pdf"
        c = canvas.Canvas(pdf_path, pagesize=letter)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(200, 750, "IDF RUNNING SHOP")
        
        c.setFont("Helvetica", 12)
        c.drawString(50, 700, f"Facture N° : {datetime.now().strftime('%Y%m%d%H%M')}")
        c.drawString(50, 680, f"Date : {datetime.now().strftime('%d/%m/%Y')}")
        c.drawString(50, 660, f"Client : {client_name}")
        
        c.drawString(50, 610, "--------------------------------------------------------")
        c.drawString(50, 590, f"Article : {article_name}")
        c.drawString(50, 570, f"Montant Total : {montant} €")
        c.drawString(50, 550, "Statut : PAIEMENT VALIDÉ")
        c.drawString(50, 530, "--------------------------------------------------------")
        
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(50, 480, "Merci pour votre achat chez IDF Running Shop !")
        c.save()

        await context.bot.send_document(
            chat_id=ADMIN_GROUP_ID,
            document=open(pdf_path, "rb"),
            caption=f"📄 Facture PDF générée pour {client_name}"
        )
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
    else:
        await update.message.reply_text("Utilisation : `/facture NomClient NomArticle Montant`\nExemple : `/facture Lucas PantalonTrail 60`", parse_mode="Markdown")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("vendu", cmd_vendu))
    app.add_handler(CommandHandler("resto", cmd_resto))
    app.add_handler(CommandHandler("annonce", cmd_annonce))
    app.add_handler(CommandHandler("facture", cmd_facture))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
