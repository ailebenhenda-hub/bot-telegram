import os
import json
import sqlite3
from datetime import datetime, timedelta
from io import BytesIO
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
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
REVOLUT_BASE = "https://revolut.me/shvppeur_corp"
WEBAPP_URL = "https://ailebenhenda-hub.github.io/bot-telegram/"

import logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

def init_db():
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            points INTEGER DEFAULT 0,
            banned INTEGER DEFAULT 0,
            referred_by INTEGER,
            discount_coupon INTEGER DEFAULT 0,
            join_date TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS catalog (
            item_id TEXT PRIMARY KEY,
            name TEXT,
            taille TEXT,
            etat TEXT,
            prix REAL,
            available INTEGER DEFAULT 1
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wishlist (
            user_id INTEGER,
            item_id TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            user_id INTEGER,
            item_id TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            items_str TEXT,
            total_price REAL,
            delivery_mode TEXT,
            status TEXT DEFAULT 'En attente de paiement',
            tracking_num TEXT,
            date TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vip_list (
            user_id INTEGER PRIMARY KEY
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY,
            total_sales INTEGER DEFAULT 0,
            revenue REAL DEFAULT 0.0
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO stats (id, total_sales, revenue) VALUES (1, 0, 0.0)")
    
    cursor.execute("SELECT COUNT(*) FROM catalog")
    if cursor.fetchone()[0] == 0:
        default_items = [
            ("1", "Pantalon Nike Trail", "S", "8/10", 60),
            ("2", "Pantalon Nike Aeroswift", "M", "Excellent état", 75),
            ("3", "Pantalon Nike Phenom Elite", "L", "Excellent état", 90),
            ("4", "Sweat Nike Tech Aviateur v1", "M", "Excellent état", 60),
            ("5", "Pantalon Nike Phenom Elite (Gris)", "L", "Excellent état", 90),
            ("6", "Tee-Shirt Nike Trail", "S", "Excellent état", 40),
            ("7", "Tee-Shirt Nike Running Division", "M", "Excellent état", 35),
            ("8", "Tee-Shirt Nike Dri-Fit (Rouge)", "S", "Excellent état", 30),
            ("9", "Sweat Nike Tech Fleece (Noir)", "S", "Excellent état", 70),
            ("10", "Pantalon Nike Phenom Elite Poche Noir", "S", "8/10", 80),
        ]
        cursor.executemany("INSERT INTO catalog (item_id, name, taille, etat, prix, available) VALUES (?, ?, ?, ?, ?, 1)", default_items)
    
    conn.commit()
    conn.close()

init_db()

def get_user(user_id, username=""):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT points, banned, referred_by, discount_coupon, join_date FROM users WHERE user_id = ?", (user_id,)
    )
    res = cursor.fetchone()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not res:
        cursor.execute(
            "INSERT INTO users (user_id, username, points, banned, discount_coupon, join_date) VALUES (?, ?, 0, 0, 0, ?)",
            (user_id, username, now_str),
        )
        conn.commit()
        res = (0, 0, None, 0, now_str)
    conn.close()
    return {"points": res[0], "banned": res[1], "referred_by": res[2], "discount_coupon": res[3], "join_date": res[4]}

def add_points(user_id, points):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (points, user_id))
    conn.commit()
    conn.close()

def set_referrer(user_id, referrer_id):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row[0] is None and user_id != referrer_id:
        cursor.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, user_id))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def give_referral_reward(user_id):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT referred_by, join_date FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row[0] and row[0] != -1:
        referrer_id = row[0]
        join_date_str = row[1]
        try:
            join_dt = datetime.strptime(join_date_str, "%Y-%m-%d %H:%M:%S")
            if datetime.now() <= join_dt + timedelta(days=7):
                cursor.execute("UPDATE users SET discount_coupon = discount_coupon + 1, referred_by = -1 WHERE user_id = ?", (user_id,))
                conn.commit()
                conn.close()
                return referrer_id
        except Exception:
            pass
    conn.close()
    return None

def use_coupon(user_id):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET discount_coupon = discount_coupon - 1 WHERE user_id = ? AND discount_coupon > 0", (user_id,))
    conn.commit()
    conn.close()

def get_catalog_items():
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT item_id, name, taille, etat, prix, available FROM catalog")
    rows = cursor.fetchall()
    conn.close()
    catalog = {}
    for r in rows:
        catalog[r[0]] = {"name": r[1], "taille": r[2], "etat": r[3], "prix": r[4], "available": bool(r[5])}
    return catalog

def add_wishlist(user_id, item_id):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO wishlist (user_id, item_id) VALUES (?, ?)", (user_id, item_id))
    conn.commit()
    conn.close()

def add_to_cart(user_id, item_id):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM cart WHERE user_id = ? AND item_id = ?", (user_id, item_id))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO cart (user_id, item_id) VALUES (?, ?)", (user_id, item_id))
        conn.commit()
    conn.close()

def get_cart(user_id):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT item_id FROM cart WHERE user_id = ?", (user_id,))
    items = [row[0] for row in cursor.fetchall()]
    conn.close()
    return items

def clear_cart(user_id):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def is_vip(user_id):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM vip_list WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def toggle_vip(user_id):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    if is_vip(user_id):
        cursor.execute("DELETE FROM vip_list WHERE user_id = ?", (user_id,))
        status = False
    else:
        cursor.execute("INSERT INTO vip_list (user_id) VALUES (?)", (user_id,))
        status = True
    conn.commit()
    conn.close()
    return status

reservations = {}  
known_users = set()
delivery_choices = {}

async def check_reservations_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    for item_id, res in list(reservations.items()):
        if not res.get("warned", False) and now >= res["expires"] - timedelta(minutes=2):
            res["warned"] = True
            try:
                await context.bot.send_message(
                    chat_id=res["user_id"],
                    text=f"⏳ Plus que 2 minutes pour régler ton article #{item_id} avant qu'il ne soit remis en stock !"
                )
            except Exception:
                pass
        elif now >= res["expires"]:
            del reservations[item_id]
            conn = sqlite3.connect("shop.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE catalog SET available = 1 WHERE item_id = ?", (item_id,))
            conn.commit()
            conn.close()
            try:
                await context.bot.send_message(
                    chat_id=res["user_id"],
                    text=f"❌ Ta réservation pour l'article #{item_id} a expiré. Il est de nouveau disponible."
                )
            except Exception:
                pass

def get_main_keyboard(user_id):
    vip_btn_text = "🔕 Se désinscrire des VIP Drops" if is_vip(user_id) else "🔔 S'inscrire aux Drops VIP"
    keyboard = [
        [InlineKeyboardButton("🛍️ Ouvrir la Boutique (Web App)", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("📦 Catalogue & Stock", callback_data="show_catalog"),
         InlineKeyboardButton("🛒 Mon Panier", callback_data="show_cart")],
        [InlineKeyboardButton("🔍 Filtrer par taille", callback_data="filter_size"),
         InlineKeyboardButton("📦 Mes Commandes & Suivi", callback_data="show_orders")],
        [InlineKeyboardButton("🤝 Parrainage (-5€)", callback_data="show_referral"),
         InlineKeyboardButton("⭐ Fidélité", callback_data="show_points")],
        [InlineKeyboardButton("📏 Guide des Tailles", callback_data="size_guide"),
         InlineKeyboardButton(vip_btn_text, callback_data="toggle_vip_status")],
        [InlineKeyboardButton("🤝 Livraison Gares IDF", callback_data="click_and_collect_info"),
         InlineKeyboardButton("💳 Revolut Direct", url=REVOLUT_BASE)],
        [InlineKeyboardButton("🛒 Vinted", url="https://www.vinted.fr/member/idf_runningshop"),
         InlineKeyboardButton("👻 Snapchat", url="https://snapchat.com/t/BW0Gzw9i")],
        [InlineKeyboardButton("💬 Avis & Retours", url="https://t.me/+q2HRbe-dBydlZWZk"),
         InlineKeyboardButton("📲 Contacter le vendeur", url=f"https://t.me/{SELLER_USERNAME}")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    known_users.add(user.id)
    u_data = get_user(user.id, user.username)
    if u_data["banned"]:
        return

    if context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg.split("_")[1])
                success = set_referrer(user.id, referrer_id)
                if success:
                    await update.message.reply_text("🎁 Tu as rejoint le lien de parrainage ! Ton parrain remportera -5 € si tu valides une commande sous **7 jours**.")
            except ValueError:
                pass

    welcome_msg = (
        f"👋 Bienvenue {user.first_name} sur IDF Running Shop !\n\n"
        "Boutique indépendante streetwear & vêtements running. 🔥\n"
        "• Remise dégressive : -5€ pour 2 articles, -10€ pour 3 articles, -15€ pour 4 articles (dès 70€ d'achat) !\n"
        "• Livraison en Gares IDF (Gare du Nord, etc.) de 5€ à 10€ selon la distance.\n\n"
        "Ouvre la Web App ci-dessous ou envoie le numéro d'un article (ex: #1) !"
    )
    await update.message.reply_text(welcome_msg, reply_markup=get_main_keyboard(user.id))

# --- COMMANDES ADMIN ---

async def admin_vendu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not context.args:
        await update.message.reply_text("Syntaxe: `/vendu ID_ARTICLE`", parse_mode="Markdown")
        return
    item_id = context.args[0]
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE catalog SET available = 0 WHERE item_id = ?", (item_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🔒 L'article #{item_id} a été marqué comme vendu.")

async def admin_resto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not context.args:
        await update.message.reply_text("Syntaxe: `/resto ID_ARTICLE`", parse_mode="Markdown")
        return
    item_id = context.args[0]
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE catalog SET available = 1 WHERE item_id = ?", (item_id,))
    if item_id in reservations:
        del reservations[item_id]
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ L'article #{item_id} a été remis en stock !")

async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not context.args:
        return
    try:
        target_id = int(context.args[0])
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"⛔ Utilisateur {target_id} banni.")
    except ValueError:
        pass

async def admin_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not context.args:
        return
    try:
        target_id = int(context.args[0])
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"🟢 Utilisateur {target_id} débanni.")
    except ValueError:
        pass

async def admin_annonce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not context.args:
        return
    msg = " ".join(context.args)
    count = 0
    for uid in known_users:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 **ANNONCE**\n\n{msg}", parse_mode="Markdown")
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Annonce diffusée à {count} utilisateurs.")

async def admin_dropvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not context.args:
        return
    msg = " ".join(context.args)
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM vip_list")
    vips = cursor.fetchall()
    conn.close()
    count = 0
    for row in vips:
        uid = row[0]
        try:
            await context.bot.send_message(chat_id=uid, text=f"🚨 **VIP DROP**\n\n{msg}", parse_mode="Markdown")
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Drop VIP envoyé à {count} membres VIP.")

async def admin_suivi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if len(context.args) < 2:
        return
    try:
        target_id = int(context.args[0])
        tracking = context.args[1]
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET tracking_num = ?, status = 'Expédié' WHERE user_id = ? AND status != 'Annulé' ORDER BY order_id DESC LIMIT 1", (tracking, target_id))
        conn.commit()
        conn.close()
        await context.bot.send_message(chat_id=target_id, text=f"🚚 Colis expédié ! Suivi : `{tracking}`", parse_mode="Markdown")
        await update.message.reply_text(f"✅ Suivi enregistré pour #{target_id}.")
    except ValueError:
        pass

async def admin_facture(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if len(context.args) < 3:
        return
    try:
        target_id = int(context.args[0])
        amount = float(context.args[-1])
        items_desc = " ".join(context.args[1:-1])
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        cursor.execute("INSERT INTO orders (user_id, items_str, total_price, delivery_mode, status, date) VALUES (?, ?, ?, 'Manuel', 'Payé', ?)", (target_id, items_desc, amount, date_str))
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()
        pdf_buffer = generate_invoice_pdf(target_id, order_id, items_desc, amount, "Manuel")
        await context.bot.send_document(chat_id=target_id, document=pdf_buffer, filename=f"Facture_{order_id}.pdf")
        await update.message.reply_text(f"✅ Facture #{order_id} envoyée.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur : {e}")

# --- GESTION MESSAGES TEXTE ET PHOTOS ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text:
        return
    clean_text = text.strip()
    if clean_text.startswith("#"):
        item_id = clean_text[1:]
        catalog = get_catalog_items()
        if item_id in catalog:
            item = catalog[item_id]
            if item["available"] and item_id not in reservations:
                add_to_cart(update.effective_user.id, item_id)
                await update.message.reply_text(f"✅ Article #{item_id} ({item['name']} - {item['prix']}€) ajouté au panier !")
            elif item_id in reservations:
                await update.message.reply_text(f"⏳ L'article #{item_id} est réservé.")
            else:
                await update.message.reply_text(f"❌ L'article #{item_id} est déjà vendu.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.photo:
        return

    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT order_id, total_price, delivery_mode FROM orders WHERE user_id = ? AND status = 'En attente de paiement' ORDER BY order_id DESC LIMIT 1", 
        (user.id,)
    )
    order = cursor.fetchone()
    
    if not order:
        date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        cursor.execute(
            "INSERT INTO orders (user_id, items_str, total_price, delivery_mode, status, date) VALUES (?, ?, ?, ?, ?, ?)",
            (user.id, "Panier / Web App", 0.0, "Web App", "En attente de paiement", date_str)
        )
        conn.commit()
        cursor.execute(
            "SELECT order_id, total_price, delivery_mode FROM orders WHERE user_id = ? AND status = 'En attente de paiement' ORDER BY order_id DESC LIMIT 1", 
            (user.id,)
        )
        order = cursor.fetchone()

    conn.close()

    order_id, total_price, delivery_mode = order
    source_text = "Payé via la Web App" if delivery_mode == "Web App" else "Payé via Telegram"

    forwarded = await context.bot.forward_message(
        chat_id=ADMIN_GROUP_ID,
        from_chat_id=update.message.chat_id,
        message_id=update.message.message_id
    )
    
    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=f"📸 REÇU de {user.first_name} (@{user.username or 'N/A'}) [ID: {user.id}]\nCommande #{order_id} - Montant : {total_price} €\nMode : {source_text}",
        reply_to_message_id=forwarded.message_id,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Valider", callback_data=f"confirm_pay_{user.id}_{total_price}"),
             InlineKeyboardButton("❌ Refuser", callback_data=f"refuse_pay_{user.id}")]
        ])
    )
    await update.message.reply_text("📸 Reçu bien transmis aux admins ! Vérification en cours...")

# --- CALLBACKS CLIENTS & ADMINS ---

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    admin_name = query.from_user.first_name
    u_data = get_user(user_id)
    if u_data["banned"]:
        return

    catalog = get_catalog_items()

    if query.data == "show_catalog":
        text = "🔥 STOCK ACTUEL 🔥\n\n"
        kb_rows = []
        for item_id, data in catalog.items():
            if not data["available"] and item_id not in reservations:
                status = "🔴 [VENDU]"
                kb_rows.append([InlineKeyboardButton(f"❌ #{item_id} - {data['name']} (Vendu)", callback_data=f"alert_{item_id}")])
            elif item_id in reservations:
                status = "⏳ [RÉSERVÉ]"
                kb_rows.append([InlineKeyboardButton(f"⏳ #{item_id} - {data['name']} (Réservé)", callback_data=f"busy_{item_id}")])
            else:
                status = f"• {data['taille']} | {data['etat']} | {data['prix']} €"
                kb_rows.append([InlineKeyboardButton(f"➕ Ajouter #{item_id} ({data['name']} - {data['prix']}€)", callback_data=f"addcart_{item_id}")])
            text += f"#{item_id} - {data['name']}\n    {status}\n\n"

        kb_rows.append([InlineKeyboardButton("🛒 Voir mon panier", callback_data="show_cart")])
        kb_rows.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")])
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb_rows))

    elif query.data == "main_menu":
        await query.edit_message_text("Menu Principal :", reply_markup=get_main_keyboard(user_id))

    elif query.data.startswith("addcart_"):
        item_id = query.data.split("_")[1]
        if catalog[item_id]["available"] and item_id not in reservations:
            add_to_cart(user_id, item_id)
            await query.answer(f"✅ Article #{item_id} ajouté au panier !", show_alert=True)
        else:
            await query.answer("❌ Article non disponible.", show_alert=True)

    elif query.data == "show_cart":
        await refresh_cart_display(query, user_id, u_data, catalog)

    elif query.data.startswith("set_del_"):
        delivery_choices[user_id] = query.data.replace("set_del_", "")
        await query.answer("Mode de livraison mis à jour.")
        await refresh_cart_display(query, user_id, u_data, catalog)

    elif query.data == "clear_cart":
        clear_cart(user_id)
        if user_id in delivery_choices:
            del delivery_choices[user_id]
        await query.answer("🗑️ Panier vidé.", show_alert=True)
        await query.edit_message_text("🛒 Ton panier a été vidé.", reply_markup=get_main_keyboard(user_id))

    elif query.data == "checkout_cart":
        cart_items = get_cart(user_id)
        if not cart_items:
            await query.answer("Ton panier est vide !", show_alert=True)
            return

        for i in cart_items:
            if not catalog[i]["available"] or i in reservations:
                await query.answer(f"❌ L'article #{i} n'est plus disponible.", show_alert=True)
                return

        total = sum(catalog[i]["prix"] for i in cart_items)
        nb_items = len(cart_items)
        current_delivery = delivery_choices.get(user_id, "gare_nord")

        # Calcul frais de livraison gares IDF (5€ à 10€)
        shipping_costs = {
            "gare_nord": 5,
            "gare_est": 6,
            "gare_lyon": 7,
            "gare_montparnasse": 8,
            "chatelet": 9,
            "autre_gare": 10
        }
        shipping = shipping_costs.get(current_delivery, 5)

        # Calcul remise dégressive (-5€ par article dès 70€ d'achat si nb_items >= 2)
        discount = 0
        if total >= 70 and nb_items >= 2:
            discount = nb_items * 5

        final_total = max(0, total + shipping - discount)
        revolut_link = f"{REVOLUT_BASE}/{final_total}"

        item_names = []
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        for i in cart_items:
            reservations[i] = {
                "user_id": user_id,
                "expires": datetime.now() + timedelta(minutes=5),
                "warned": False,
            }
            cursor.execute("UPDATE catalog SET available = 0 WHERE item_id = ?", (i,))
            item_names.append(f"#{i} {catalog[i]['name']}")
        conn.commit()
        conn.close()

        items_str = ", ".join(item_names)
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        cursor.execute(
            "INSERT INTO orders (user_id, items_str, total_price, delivery_mode, status, date) VALUES (?, ?, ?, ?, 'En attente de paiement', ?)",
            (user_id, items_str, final_total, current_delivery, date_str)
        )
        conn.commit()
        conn.close()

        kb_pay = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💳 Payer {final_total} € sur Revolut", url=revolut_link)],
            [InlineKeyboardButton("📲 Contacter le vendeur", url=f"https://t.me/{SELLER_USERNAME}")]
        ])

        confirm_text = (
            f"⏱️ **Articles bloqués pendant 5 minutes !**\n"
            f"• Articles : {items_str}\n"
            f"• Livraison : {current_delivery} ({shipping} €)\n"
            f"• Remise appliquée : -{discount} €\n"
            f"💰 **TOTAL À PAYER : {final_total} €**\n\n"
            "Règler sur Revolut puis **envoie la capture du reçu ici en photo** !"
        )
        await query.edit_message_text(text=confirm_text, reply_markup=kb_pay, parse_mode="Markdown")
        
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=f"🚨 NOUVELLE COMMANDE (BLOQUÉE 5 MIN)\nClient : {query.from_user.first_name} (@{query.from_user.username})\nArticles : {items_str}\nMontant : {final_total} €",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛠️ Prise en charge", callback_data=f"take_{user_id}")]
            ])
        )
        clear_cart(user_id)
        if user_id in delivery_choices:
            del delivery_choices[user_id]

    elif query.data == "show_orders":
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("SELECT order_id, items_str, total_price, delivery_mode, status, tracking_num, date FROM orders WHERE user_id = ?", (user_id,))
        orders = cursor.fetchall()
        conn.close()

        if not orders:
            text = "📦 Aucune commande enregistrée."
            kb_orders = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]])
        else:
            text = "📦 **TES COMMANDES** :\n\n"
            kb_buttons = []
            for o in orders:
                text += f"• Cmd #{o[0]} ({o[6]}) - {o[4]} | Total : {o[2]}€\n  {o[1]}\n\n"
            kb_buttons.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")])
            kb_orders = InlineKeyboardMarkup(kb_buttons)
        await query.edit_message_text(text=text, reply_markup=kb_orders, parse_mode="Markdown")

    elif query.data == "show_referral":
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        text = (
            f"🤝 **PARRAINAGE (-5 €)**\n\n"
            f"Partage ton lien :\n`{ref_link}`\n\n"
            f"Gagne -5 € si ton filleul valide une commande sous **7 jours** max !\n"
            f"🎟️ Bons disponibles : **{u_data['discount_coupon']}**"
        )
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="Markdown")

    elif query.data == "show_points":
        await query.edit_message_text(f"⭐ Points fidélité : **{u_data['points']} pts**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="Markdown")

    elif query.data == "size_guide":
        await query.edit_message_text("📏 Guide des tailles standard Nike.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]))

    elif query.data == "click_and_collect_info":
        await query.edit_message_text("🤝 Livraison en Gares IDF (Gare du Nord, Lyon, etc.) entre 5€ et 10€ selon la distance.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]))

    elif query.data == "toggle_vip_status":
        new_status = toggle_vip(user_id)
        await query.answer("Statut VIP mis à jour.", show_alert=True)
        await query.edit_message_text("Menu Principal :", reply_markup=get_main_keyboard(user_id))

    elif query.data.startswith("confirm_pay_"):
        parts = query.data.split("_")
        target_id = int(parts[2])
        total_price = float(parts[3])

        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = 'Payé' WHERE user_id = ? AND status = 'En attente de paiement'", (target_id,))
        cursor.execute("UPDATE stats SET total_sales = total_sales + 1, revenue = revenue + ? WHERE id = 1", (total_price,))
        conn.commit()
        conn.close()

        add_points(target_id, int(total_price))
        referrer_id = give_referral_reward(target_id)
        if referrer_id:
            try:
                await context.bot.send_message(chat_id=referrer_id, text="🎉 Ton filleul a commandé dans les 7 jours ! Tu gagnes -5 € !")
            except Exception:
                pass

        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Validé", callback_data="noop")]]))
        await context.bot.send_message(chat_id=target_id, text="✅ Paiement validé avec succès !")

    elif query.data.startswith("refuse_pay_"):
        target_id = int(query.data.split("_")[2])
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = 'Annulé' WHERE user_id = ? AND status = 'En attente de paiement'", (target_id,))
        conn.commit()
        conn.close()
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Refusé", callback_data="noop")]]))
        await context.bot.send_message(chat_id=target_id, text="❌ Reçu refusé par l'administration.")

    elif query.data == "noop":
        pass

async def refresh_cart_display(query, user_id, u_data, catalog):
    cart_items = get_cart(user_id)
    if not cart_items:
        text = "🛒 Ton panier est vide."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📦 Voir le catalogue", callback_data="show_catalog")]])
    else:
        current_delivery = delivery_choices.get(user_id, "gare_nord")
        text = "🛒 **TON PANIER** :\n\n"
        total = 0
        nb_items = len(cart_items)
        for item_id in cart_items:
            item = catalog[item_id]
            text += f"• #{item_id} - {item['name']} : **{item['prix']} €**\n"
            total += item['prix']
        
        shipping_costs = {
            "gare_nord": 5,
            "gare_est": 6,
            "gare_lyon": 7,
            "gare_montparnasse": 8,
            "chatelet": 9,
            "autre_gare": 10
        }
        shipping = shipping_costs.get(current_delivery, 5)

        discount = 0
        if total >= 70 and nb_items >= 2:
            discount = nb_items * 5

        final_total = max(0, total + shipping - discount)

        text += f"\n• Sous-total : {total} €\n"
        text += f"• Livraison ({current_delivery}) : +{shipping} €\n"
        if discount > 0:
            text += f"• Remise dégressive (-{nb_items} articles) : -{discount} €\n"
        text += f"💰 **TOTAL : {final_total} €**"

        kb_buttons = [
            [InlineKeyboardButton("🚂 Gare du Nord (5€)", callback_data="set_del_gare_nord"),
             InlineKeyboardButton("🚂 Gare de l'Est (6€)", callback_data="set_del_gare_est")],
            [InlineKeyboardButton("🚂 Gare de Lyon (7€)", callback_data="set_del_gare_lyon"),
             InlineKeyboardButton("🚂 Montparnasse (8€)", callback_data="set_del_gare_montparnasse")],
            [InlineKeyboardButton("🚇 Châtelet (9€)", callback_data="set_del_chatelet"),
             InlineKeyboardButton("📍 Autre Gare IDF (10€)", callback_data="set_del_autre_gare")],
            [InlineKeyboardButton("✅ Valider et Payer", callback_data="checkout_cart")],
            [InlineKeyboardButton("🗑️ Vider", callback_data="clear_cart"),
             InlineKeyboardButton("📦 Catalogue", callback_data="show_catalog")]
        ]
        kb = InlineKeyboardMarkup(kb_buttons)
    await query.edit_message_text(text=text, reply_markup=kb, parse_mode="Markdown")

def generate_invoice_pdf(user_id, order_id, items_str, total_price, delivery_mode):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    p.drawString(50, height - 50, "IDF RUNNING SHOP - FACTURE")
    p.drawString(50, height - 70, f"Facture N° : {order_id}")
    p.drawString(50, height - 90, f"Total Payé : {total_price} €")
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

def main():
    if not TELEGRAM_TOKEN:
        return
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.job_queue.run_repeating(check_reservations_job, interval=10, first=10)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("vendu", admin_vendu))
    application.add_handler(CommandHandler("resto", admin_resto))
    application.add_handler(CommandHandler("ban", admin_ban))
    application.add_handler(CommandHandler("unban", admin_unban))
    application.add_handler(CommandHandler("annonce", admin_annonce))
    application.add_handler(CommandHandler("dropVIP", admin_dropvip))
    application.add_handler(CommandHandler("suivi", admin_suivi))
    application.add_handler(CommandHandler("facture", admin_facture))

    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot démarré avec succès...")
    application.run_polling()

if __name__ == "__main__":
    main()
