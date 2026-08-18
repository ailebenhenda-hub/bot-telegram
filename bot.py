import os
import json
import sqlite3
import requests
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
LAPOSTE_TRACKING_URL = "https://www.laposte.fr/outils/suivre-vos-envois?code="

# Configuration Supabase
SUPABASE_URL = "https://jzurawtfxwyinwzowpkx.supabase.co"
SUPABASE_KEY = "sb_publishable_OXqEOCgFVL4qbZUHK7DaKg_o6BzN8rK"
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

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
            poids INTEGER DEFAULT 250,
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
            ("1", "PANTALON NIKE TRAIL", "S", "8/10 (petite égratignure sur le genou)", 60, 250),
            ("2", "SWEAT NIKE TECH AVIATEUR V1", "M", "Excellent état", 60, 800),
            ("3", "TEE-SHIRT NIKE DRI-FIT", "M", "Excellent état", 30, 150),
            ("4", "SWEAT NIKE TECH FLEECE", "S", "Excellent état", 70, 850),
            ("5", "PANTALON NIKE PHENOM ELITE POCHE NOIR", "S", "8/10", 80, 250),
            ("6", "TEE-SHIRT NIKE TRAIL", "S", "Excellent état", 40, 150),
            ("7", "TEE-SHIRT NIKE RUNNING DIVISION", "M", "Excellent état", 35, 150),
            ("8", "PANTALON NIKE AEROSWIFT", "M", "Excellent état", 75, 250),
            ("9", "PANTALON NIKE PHENOM ELITE", "L", "Excellent état", 90, 250),
            ("10", "PANTALON NIKE PHENOM ELITE", "S", "Excellent état", 90, 250),
            ("11", "PULLOVER NIKE TECH KANGOUROU", "S", "9/10", 75, 750),
            ("12", "VESTE NIKE TECH FLEECE AVIATEUR", "L", "10/10", 75, 800),
            ("13", "ENSEMBLE NIKE X KELLY ANNA", "L", "10/10", 140, 800),
            ("14", "VESTE NIKE CHINESE DRAGON", "M", "9/10", 110, 700),
            ("15", "T-SHIRT NIKE RUNNING", "M", "10/10", 30, 150),
            ("16", "T-SHIRT NIKE RUNNING TECHNIQUE", "M", "9/10", 30, 150),
            ("17", "T-SHIRT NIKE RUNNING", "M", "8/10", 35, 150),
            ("18", "T-SHIRT NIKE TRAIL", "M", "10/10", 35, 150),
            ("19", "T-SHIRT NIKE TRAIL NOIR", "M", "10/10", 35, 150),
            ("20", "T-SHIRT NIKE RUNNING DIVISION OS", "XL", "10/10", 45, 150),
            ("21", "SHORT NIKE RUNNING", "M", "10/10", 25, 200),
            ("22", "SHORT NIKE RUNNING DIVISION", "L", "10/10", 30, 200),
            ("23", "SHORT NIKE RUNNING ROSE", "M", "10/10", 25, 200),
            ("24", "SHORT NIKE RUNNING NIKE PENCHÉ", "M", "10/10", 25, 200),
            ("25", "SHORT NIKE RUNNING NIKE PENCHÉ", "M", "10/10", 25, 200),
            ("26", "SHORT NIKE RUNNING NOIR CORDONS JAUNES", "M", "10/10", 25, 200),
            ("27", "SHORT NIKE STRIDE DRI-FIT", "S", "9/10", 25, 200),
            ("28", "SHORT NIKE RUNNING NOIR", "L", "10/10", 25, 200),
            ("29", "SHORT NIKE RUNNING NOIR", "XS", "9/10", 25, 200),
        ]
        cursor.executemany("INSERT INTO catalog (item_id, name, taille, etat, prix, poids, available) VALUES (?, ?, ?, ?, ?, ?, 1)", default_items)
    
    conn.commit()
    conn.close()

init_db()

def update_supabase_stock(item_id, available_status):
    try:
        requests.patch(
            f"{SUPABASE_URL}/rest/v1/catalog?item_id=eq.{item_id}",
            headers=SUPABASE_HEADERS,
            json={"available": 1 if available_status else 0}
        )
    except Exception as e:
        print(f"Erreur synchro stock Supabase pour #{item_id}: {e}")

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
                cursor.execute("UPDATE users SET discount_coupon = discount_coupon + 1 WHERE user_id = ?", (referrer_id,))
                conn.commit()
                conn.close()
                return referrer_id
        except Exception:
            pass
    conn.close()
    return None

def get_catalog_items():
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT item_id, name, taille, etat, prix, poids, available FROM catalog")
    rows = cursor.fetchall()
    conn.close()
    catalog = {}
    for r in rows:
        catalog[r[0]] = {"name": r[1], "taille": r[2], "etat": r[3], "prix": r[4], "poids": r[5], "available": bool(r[6])}
    return catalog

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

def calculate_colissimo_shipping(total_weight_grams):
    if total_weight_grams <= 250:
        return 5.49
    elif total_weight_grams <= 500:
        return 7.59
    elif total_weight_grams <= 750:
        return 9.29
    elif total_weight_grams <= 1000:
        return 9.59
    elif total_weight_grams <= 2000:
        return 11.19
    elif total_weight_grams <= 5000:
        return 17.39
    elif total_weight_grams <= 10000:
        return 25.29
    elif total_weight_grams <= 15000:
        return 31.99
    else:
        return 39.59

def generate_invoice_pdf(order_id, client_name, client_id, items_str, delivery_mode, total_price):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, 740, "SHVPPEUR CORP")
    p.setFont("Helvetica", 9)
    p.drawString(50, 725, "IDF Running Shop - Vêtements Streetwear & Running Second-Main")
    p.drawString(50, 712, "Telegram : @idf_runningshop | Snapchat : idf_runningshop")
    
    p.setFont("Helvetica-Bold", 10)
    p.drawRightString(560, 740, f"FACTURE #{order_id}")
    p.setFont("Helvetica", 9)
    p.drawRightString(560, 725, f"Date : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    p.drawRightString(560, 712, f"Client Telegram ID : {client_id}")
    
    p.rect(380, 640, 180, 55)
    p.setFont("Helvetica-Bold", 9)
    p.drawString(390, 680, "Facturé à :")
    p.setFont("Helvetica", 9)
    p.drawString(390, 665, f"Client : {client_name}")
    p.drawString(390, 650, f"ID : {client_id}")

    p.setFillColorRGB(0.9, 0.9, 0.9)
    p.rect(50, 580, 510, 20, fill=1, stroke=0)
    p.setFillColorRGB(0, 0, 0)
    p.setFont("Helvetica-Bold", 9)
    p.drawString(60, 586, "Description des articles")
    p.drawString(320, 586, "Livraison")
    p.drawRightString(550, 586, "Total TTC")
    
    p.setFont("Helvetica", 9)
    p.drawString(60, 555, items_str[:50])
    p.drawString(320, 555, delivery_mode)
    p.drawRightString(550, 555, f"{total_price} €")
    
    p.line(50, 535, 560, 535)
    
    p.drawString(380, 510, "Total Hors TVA :")
    p.drawRightString(550, 510, f"{total_price} €")
    p.drawString(380, 495, "TVA (0% - Franchise) :")
    p.drawRightString(550, 495, "0.00 €")
    p.setFont("Helvetica-Bold", 10)
    p.drawString(380, 475, "MONTANT TOTAL :")
    p.drawRightString(550, 475, f"{total_price} €")
    
    p.setFont("Helvetica-Oblique", 8)
    p.drawString(50, 100, "Merci pour votre achat chez Shvppeur Corp / IDF Running Shop !")
    p.drawString(50, 88, "Retrouvez tous nos drops sur Telegram et Snapchat.")
    
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

known_users = set()
delivery_choices = {}
user_reward_choices = {}

async def payment_timeout_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    user_id = job_data["user_id"]
    order_id = job_data["order_id"]
    item_ids = job_data["item_ids"]

    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM orders WHERE order_id = ? AND user_id = ?", (order_id, user_id))
    res = cursor.fetchone()
    
    if res and res[0] == 'En attente de paiement':
        cursor.execute("UPDATE orders SET status = 'Annulé' WHERE order_id = ?", (order_id,))
        for i_id in item_ids:
            cursor.execute("UPDATE catalog SET available = 1 WHERE item_id = ?", (i_id,))
            update_supabase_stock(i_id, True)
        conn.commit()
        conn.close()

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Délai dépassé ! Ta commande a été automatiquement annulée et les articles ont été remis en stock."
            )
        except Exception:
            pass
    else:
        conn.close()

async def send_3min_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    user_id = job_data["user_id"]
    order_id = job_data["order_id"]
    item_ids = job_data["item_ids"]

    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM orders WHERE order_id = ? AND user_id = ?", (order_id, user_id))
    res = cursor.fetchone()
    conn.close()

    if res and res[0] == 'En attente de paiement':
        red_reminder_text = (
            "🔴 [RAPPEL URGENT] 🔴\n\n"
            "🚨 N'oublie pas d'envoyer ton reçu de paiement pour finaliser ta commande ! 🚨\n"
            "Si tu n'envoies pas ton reçu ou si tu ne valides pas, ta commande expirera et tes articles seront libérés pour les autres acheteurs."
        )
        
        keyboard = [
            [InlineKeyboardButton("📸 Envoyer le reçu / Finaliser", url=f"https://t.me/{SELLER_USERNAME}")],
            [InlineKeyboardButton("❌ Annuler / Libérer l'article", callback_data=f"cancel_order_{order_id}_{'_'.join(item_ids)}")]
        ]
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=red_reminder_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            pass
        
        context.job_queue.run_once(
            payment_timeout_job,
            when=180,
            data={"user_id": user_id, "order_id": order_id, "item_ids": item_ids},
            name=f"timeout_{user_id}_{order_id}"
        )

def get_main_keyboard(user_id):
    vip_btn_text = "✨ Se désinscrire des VIP Drops" if is_vip(user_id) else "🔔 S'inscrire aux Drops VIP"
    keyboard = [
        [InlineKeyboardButton("📦 Catalogue & Stock", callback_data="show_catalog"),
         InlineKeyboardButton("🛒 Mon Panier", callback_data="show_cart")],
        [InlineKeyboardButton("🔍 Filtrer par taille", callback_data="filter_size"),
         InlineKeyboardButton("👕 Filtrer par type d’article", callback_data="filter_type")],
        [InlineKeyboardButton("📦 Mes Commandes & Suivi", callback_data="show_orders"),
         InlineKeyboardButton("🤝 Parrainage (-5€)", callback_data="show_referral")],
        [InlineKeyboardButton("⭐ Fidélité & Réductions", callback_data="show_points"),
         InlineKeyboardButton(vip_btn_text, callback_data="toggle_vip_status")],
        [InlineKeyboardButton("🤝 Livraison Gares IDF", callback_data="click_and_collect_info"),
         InlineKeyboardButton("📦 Suivi de Colis", url=LAPOSTE_TRACKING_URL)],
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
                    await update.message.reply_text("🎁 Tu as rejoint le lien de parrainage ! Ton parrain remportera une réduction de -5 € si tu valides ta première commande sous 7 jours.")
            except ValueError:
                pass

    welcome_msg = (
        f"👋 Bienvenue {user.first_name} sur IDF Running Shop !\n\n"
        "Boutique indépendante streetwear & vêtements running. 🔥\n"
        "• Chaque euro dépensé se transforme en points de fidélité !\n"
        "• Paliers de fidélité :\n"
        "  - 350 points : -10 € sur l'article de ton choix\n"
        "  - 1000 points : -50 € sur ta commande\n\n"
        "Utilise les boutons du menu ci-dessous !"
    )
    await update.message.reply_text(welcome_msg, reply_markup=get_main_keyboard(user.id))

async def admin_vendu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not context.args:
        return
    item_id = context.args[0]
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE catalog SET available = 0 WHERE item_id = ?", (item_id,))
    conn.commit()
    conn.close()
    update_supabase_stock(item_id, False)
    await update.message.reply_text(f"🔒 L'article #{item_id} a été marqué comme vendu.")

async def admin_resto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not context.args:
        return
    item_id = context.args[0]
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE catalog SET available = 1 WHERE item_id = ?", (item_id,))
    conn.commit()
    conn.close()
    update_supabase_stock(item_id, True)
    await update.message.reply_text(f"✅ L'article #{item_id} a été remis en stock !")

async def admin_suivi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Syntaxe : /suivi ID_TELEGRAM NUMERO_SUIVI")
        return
    try:
        target_id = int(context.args[0])
        tracking = context.args[1]
        tracking_link = f"{LAPOSTE_TRACKING_URL}{tracking}"

        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET tracking_num = ?, status = 'Expédié' WHERE user_id = ? AND status != 'Annulé' AND order_id = (SELECT MAX(order_id) FROM orders WHERE user_id = ?)",
            (tracking, target_id, target_id)
        )
        conn.commit()
        conn.close()

        await context.bot.send_message(
            chat_id=target_id, 
            text=f"🚚 Bonne nouvelle ! Ton colis a été expédié.\n\nNuméro de suivi : {tracking}\n\n👉 Lien de suivi La Poste : {tracking_link}"
        )
        await update.message.reply_text(f"✅ Suivi enregistré et envoyé à l'utilisateur #{target_id} avec succès.")
    except ValueError:
        await update.message.reply_text("❌ ID Telegram invalide.")

async def admin_annonce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not context.args:
        await update.message.reply_text("⚠️ Syntaxe : /annonce Votre message")
        return
    message_text = " ".join(context.args)
    count = 0
    for uid in known_users:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 ANNONCE OFFICIELLE\n\n{message_text}")
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Annonce diffusée à {count} utilisateur(s).")

async def admin_dropvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not context.args:
        await update.message.reply_text("⚠️ Syntaxe : /dropVIP Message")
        return
    message_text = " ".join(context.args)
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM vip_list")
    vip_users = cursor.fetchall()
    conn.close()
    
    count = 0
    for row in vip_users:
        uid = row[0]
        try:
            await context.bot.send_message(chat_id=uid, text=f"🚨 ALERTE DROP VIP 🚨\n\n{message_text}")
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Alerte VIP envoyée à {count} membre(s).")

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
        await update.message.reply_text(f"🔨 L'utilisateur {target_id} a été banni.")
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
        await update.message.reply_text(f"✨ L'utilisateur {target_id} a été débanni.")
    except ValueError:
        pass

async def admin_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not context.args:
        return
    try:
        target_id = int(context.args[0])
        if len(context.args) == 1:
            u_data = get_user(target_id)
            await update.message.reply_text(f"⭐ L'utilisateur {target_id} possède {u_data['points']} pts.")
        elif len(context.args) == 2:
            delta = int(context.args[1])
            add_points(target_id, delta)
            u_data = get_user(target_id)
            await update.message.reply_text(f"✅ Solde mis à jour pour {target_id}. Nouveau total : {u_data['points']} pts.")
    except ValueError:
        pass

async def admin_facture(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if len(context.args) < 3:
        await update.message.reply_text("⚠️ Syntaxe : /facture NomClient Article Montant\nExemple : /facture Lucas PantalonTrail 60")
        return
    client_name = context.args[0]
    item_name = " ".join(context.args[1:-1])
    try:
        amount = float(context.args[-1])
    except ValueError:
        await update.message.reply_text("❌ Le montant doit être un nombre valide.")
        return

    buffer = generate_invoice_pdf(0, client_name, update.effective_user.id, item_name, "Standard", amount)
    await update.message.reply_document(
        document=buffer,
        filename=f"facture_{client_name}.pdf",
        caption=f"📄 Facture officielle générée pour {client_name} ({amount} €)."
    )

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
            if item["available"]:
                add_to_cart(update.effective_user.id, item_id)
                await update.message.reply_text(f"✅ Article #{item_id} ({item['name']} - {item['prix']}€) ajouté au panier !")
            else:
                await update.message.reply_text(f"❌ L'article #{item_id} n'est plus disponible.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.photo:
        return

    if update.message.chat_id == ADMIN_GROUP_ID:
        return

    items_summary = "Non spécifié"
    total_price = 0.0
    shipping_info = "Non spécifié"
    order_id = 0
    found_order = False

    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT order_id, items_str, total_price, delivery_mode FROM orders WHERE user_id = ? AND status = 'En attente de paiement' ORDER BY order_id DESC LIMIT 1",
        (user.id,)
    )
    order = cursor.fetchone()
    conn.close()

    if order:
        order_id = order[0]
        items_summary = order[1]
        total_price = float(order[2])
        shipping_info = order[3]
        found_order = True

    if not found_order:
        await update.message.reply_text("❌ Aucune commande en attente trouvée. Merci de contacter le support.")
        return

    current_jobs = context.job_queue.get_jobs_by_name(f"reminder_{user.id}_{order_id}")
    for job in current_jobs:
        job.schedule_removal()
    
    timeout_jobs = context.job_queue.get_jobs_by_name(f"timeout_{user.id}_{order_id}")
    for job in timeout_jobs:
        job.schedule_removal()

    forwarded = await context.bot.forward_message(
        chat_id=ADMIN_GROUP_ID,
        from_chat_id=update.message.chat_id,
        message_id=update.message.message_id
    )
    
    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=f"📸 REÇU de {user.first_name} (@{user.username or 'N/A'}) [ID: {user.id}]\n"
             f"📦 Articles : {items_summary}\n"
             f"🚚 Livraison : {shipping_info}\n"
             f"💰 Montant : {total_price} €\n"
             f"Mode : Paiement",
        reply_to_message_id=forwarded.message_id,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👨‍💻 Prise en charge", callback_data=f"take_charge_{user.id}")],
            [InlineKeyboardButton("✅ Valider", callback_data=f"confirm_pay_{user.id}_{order_id}_{total_price}"),
             InlineKeyboardButton("❌ Refuser", callback_data=f"refuse_pay_{user.id}")]
        ])
    )
    await update.message.reply_text("📸 Reçu bien transmis aux admins ! Vérification en cours...")

async def refresh_cart_display(query, user_id, u_data, catalog):
    cart_items = get_cart(user_id)
    if not cart_items:
        await query.edit_message_text(
            "🛒 Ton panier est vide.\n\nAjoute des articles depuis le catalogue !",
            reply_markup=get_main_keyboard(user_id)
        )
        return

    text = "🛒 TON PANIER ACTUEL\n\n"
    total = 0
    for item_id in cart_items:
        if item_id in catalog:
            it = catalog[item_id]
            text += f"• #{item_id} - {it['name']} ({it['taille']} | {it['etat']}) : {it['prix']} €\n"
            total += it['prix']

    nb_items = len(cart_items)
    current_delivery = delivery_choices.get(user_id, "gare_proche")

    if current_delivery == "colissimo":
        total_weight = sum(catalog[item_id].get('poids', 250) for item_id in cart_items if item_id in catalog)
        shipping = calculate_colissimo_shipping(total_weight)
        if total >= 170:
            shipping = 0
    else:
        shipping_costs = {"gare_proche": 5, "gare_moyenne": 10, "gare_eloignee": 15}
        shipping = shipping_costs.get(current_delivery, 5)

    discount = 0
    if nb_items == 2 and total > 70:
        discount = 5
    elif nb_items == 3 and total > 90:
        discount = 10
    elif nb_items == 4 and total > 110:
        discount = 15
    elif nb_items >= 5 and total > 130:
        discount = 20

    points_discount = 0
    chosen_reward = user_reward_choices.get(user_id, 0)
    if chosen_reward == 1000 and u_data["points"] >= 1000:
        points_discount = 50
    elif chosen_reward == 350 and u_data["points"] >= 350:
        points_discount = 10

    final_total = max(0, total + shipping - discount - points_discount)

    text += f"\n📦 Articles : {nb_items} | Sous-total : {total} €"
    text += f"\n🚚 Livraison ({current_delivery}) : +{shipping} €"
    if discount > 0:
        text += f"\n🎁 Remise paliers articles : -{discount} €"
    if points_discount > 0:
        text += f"\n⭐ Remise Fidélité activée : -{points_discount} €"
    text += f"\n\n💰 TOTAL FINAL : {final_total} €"

    kb = [
        [InlineKeyboardButton("🚆 Livraison Gares IDF", callback_data="set_del_gare_proche"),
         InlineKeyboardButton("📦 Colissimo", callback_data="set_del_colissimo")],
    ]

    if u_data["points"] >= 350:
        r_choice = user_reward_choices.get(user_id, 0)
        btn_350_text = "☑️ Utiliser -10€ (350 pts)" if r_choice == 350 else "⭐ Utiliser -10€ (350 pts)"
        kb.append([InlineKeyboardButton(btn_350_text, callback_data="use_reward_350")])
    if u_data["points"] >= 1000:
        r_choice = user_reward_choices.get(user_id, 0)
        btn_1000_text = "☑️ Utiliser -50€ (1000 pts)" if r_choice == 1000 else "⭐ Utiliser -50€ (1000 pts)"
        kb.append([InlineKeyboardButton(btn_1000_text, callback_data="use_reward_1000")])

    kb.extend([
        [InlineKeyboardButton("✅ Valider et Passer la Commande", callback_data="checkout_cart")],
        [InlineKeyboardButton("🗑️ Vider le Panier", callback_data="clear_cart")],
        [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
    ])
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    u_data = get_user(user_id)
    if u_data["banned"]:
        return

    catalog = get_catalog_items()

    if query.data == "show_catalog":
        text = "🔥 STOCK ACTUEL 🔥\n\n"
        kb_rows = []
        for item_id, data in catalog.items():
            if not data["available"]:
                status = "🔴 [VENDU]"
                kb_rows.append([InlineKeyboardButton(f"❌ #{item_id} - {data['name']} (Vendu)", callback_data="noop")])
            else:
                status = f"• {data['taille']} | {data['etat']} | {data['prix']} € ({data['poids']}g)"
                kb_rows.append([InlineKeyboardButton(f"➕ #{item_id} ({data['name']} - {data['prix']}€)", callback_data=f"addcart_{item_id}")])
            text += f"#{item_id} - {data['name']}\n    {status}\n\n"

        kb_rows.append([InlineKeyboardButton("🛒 Voir mon panier", callback_data="show_cart")])
        kb_rows.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")])
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb_rows))

    elif query.data == "main_menu":
        await query.edit_message_text("Menu Principal :", reply_markup=get_main_keyboard(user_id))

    elif query.data.startswith("addcart_"):
        item_id = query.data.split("_")[1]
        if item_id in catalog and catalog[item_id]["available"]:
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

    elif query.data == "use_reward_350":
        if user_reward_choices.get(user_id) == 350:
            user_reward_choices[user_id] = 0
            await query.answer("Remise de -10€ désactivée.")
        else:
            user_reward_choices[user_id] = 350
            await query.answer("Remise de -10€ activée !")
        await refresh_cart_display(query, user_id, u_data, catalog)

    elif query.data == "use_reward_1000":
        if user_reward_choices.get(user_id) == 1000:
            user_reward_choices[user_id] = 0
            await query.answer("Remise de -50€ désactivée.")
        else:
            user_reward_choices[user_id] = 1000
            await query.answer("Remise de -50€ activée !")
        await refresh_cart_display(query, user_id, u_data, catalog)

    elif query.data == "clear_cart":
        clear_cart(user_id)
        if user_id in delivery_choices:
            del delivery_choices[user_id]
        if user_id in user_reward_choices:
            del user_reward_choices[user_id]
        await query.answer("🗑️ Panier vidé.", show_alert=True)
        await query.edit_message_text("🛒 Ton panier a été vidé.", reply_markup=get_main_keyboard(user_id))

    elif query.data == "checkout_cart":
        cart_items = get_cart(user_id)
        if not cart_items:
            await query.answer("Ton panier est vide.", show_alert=True)
            return
        
        total = sum(catalog[item_id]['prix'] for item_id in cart_items if item_id in catalog)
        nb_items = len(cart_items)
        current_delivery = delivery_choices.get(user_id, "gare_proche")
        
        if current_delivery == "colissimo":
            total_weight = sum(catalog[item_id].get('poids', 250) for item_id in cart_items if item_id in catalog)
            shipping = calculate_colissimo_shipping(total_weight)
            if total >= 170:
                shipping = 0
        else:
            shipping_costs = {"gare_proche": 5, "gare_moyenne": 10, "gare_eloignee": 15}
            shipping = shipping_costs.get(current_delivery, 5)

        discount = 0
        if nb_items == 2 and total > 70:
            discount = 5
        elif nb_items == 3 and total > 90:
            discount = 10
        elif nb_items == 4 and total > 110:
            discount = 15
        elif nb_items >= 5 and total > 130:
            discount = 20

        points_discount = 0
        chosen_reward = user_reward_choices.get(user_id, 0)
        if chosen_reward == 1000 and u_data["points"] >= 1000:
            points_discount = 50
        elif chosen_reward == 350 and u_data["points"] >= 350:
            points_discount = 10

        final_total = max(0, total + shipping - discount - points_discount)
        items_names = ", ".join([catalog[i]['name'] for i in cart_items if i in catalog])

        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (user_id, items_str, total_price, delivery_mode, status, date) VALUES (?, ?, ?, ?, 'En attente de paiement', ?)",
            (user_id, items_names, final_total, current_delivery, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        order_id = cursor.lastrowid
        
        for item_id in cart_items:
            cursor.execute("UPDATE catalog SET available = 0 WHERE item_id = ?", (item_id,))
            update_supabase_stock(item_id, False)
        
        conn.commit()
        conn.close()

        clear_cart(user_id)
        
        if context.job_queue:
            context.job_queue.run_once(
                send_3min_reminder_job,
                when=180,
                data={"user_id": user_id, "order_id": order_id, "item_ids": cart_items},
                name=f"reminder_{user_id}_{order_id}"
            )

        if current_delivery == "colissimo":
            pay_or_contact_button = InlineKeyboardButton("💳 Payer sur Revolut", url=f"{REVOLUT_BASE}/{final_total}")
        else:
            pay_or_contact_button = InlineKeyboardButton("📲 Contacter pour fixer le RDV en gare", url=f"https://t.me/{SELLER_USERNAME}")

        await query.edit_message_text(
            text=f"✅ Commande enregistrée ! (Articles réservés pour 3 minutes)\n\nTotal à régler : {final_total} €\n"
                 f"🔴 ATTENTION : N'oublie pas d'envoyer la photo de ton reçu de paiement directement ici dans le chat pour valider ta commande !",
            reply_markup=InlineKeyboardMarkup([
                [pay_or_contact_button],
                [InlineKeyboardButton("💬 Contacter le vendeur", url=f"https://t.me/{SELLER_USERNAME}")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
            ])
        )

    elif query.data.startswith("cancel_order_"):
        parts = query.data.split("_")
        order_id = int(parts[2])
        item_ids = parts[3:]

        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = 'Annulé' WHERE order_id = ? AND user_id = ?", (order_id, user_id))
        for i_id in item_ids:
            cursor.execute("UPDATE catalog SET available = 1 WHERE item_id = ?", (i_id,))
            update_supabase_stock(i_id, True)
        conn.commit()
        conn.close()

        await query.edit_message_text(
            text="❌ Commande annulée. Les articles ont été libérés et remis en stock.",
            reply_markup=get_main_keyboard(user_id)
        )

    elif query.data == "filter_size":
        text = "🔍 Filtrer par taille :\nSélectionne une taille :"
        kb = [
            [InlineKeyboardButton("Taille S", callback_data="size_S"),
             InlineKeyboardButton("Taille M", callback_data="size_M")],
            [InlineKeyboardButton("Taille L", callback_data="size_L"),
             InlineKeyboardButton("Taille XL", callback_data="size_XL")],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
        ]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb))

    elif query.data.startswith("size_"):
        selected_size = query.data.split("_")[1]
        text = f"🔥 ARTICLES EN TAILLE {selected_size} 🔥\n\n"
        kb_rows = []
        found = False
        for item_id, data in catalog.items():
            if data["taille"].upper() == selected_size.upper():
                found = True
                if data["available"]:
                    kb_rows.append([InlineKeyboardButton(f"➕ #{item_id} ({data['name']} - {data['prix']}€)", callback_data=f"addcart_{item_id}")])
                    text += f"#{item_id} - {data['name']} | {data['etat']} | {data['prix']} €\n\n"
                else:
                    text += f"#{item_id} - {data['name']} (Vendu)\n\n"
        if not found:
            text += "Aucun article disponible pour cette taille.\n\n"
        kb_rows.append([InlineKeyboardButton("🔍 Choisir une autre taille", callback_data="filter_size")])
        kb_rows.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")])
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb_rows))

    elif query.data == "filter_type":
        text = "👕 Filtrer par type d’article :\nSélectionne une catégorie :"
        kb = [
            [InlineKeyboardButton("Tee-Shirt", callback_data="type_tshirt"),
             InlineKeyboardButton("Short", callback_data="type_short")],
            [InlineKeyboardButton("Pull / Sweat", callback_data="type_pull"),
             InlineKeyboardButton("Pantalon", callback_data="type_pantalon")],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]
        ]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb))

    elif query.data.startswith("type_"):
        selected_type = query.data.split("_")[1]
        type_keywords = {
            "tshirt": ["tee-shirt", "t-shirt", "tee shirt"],
            "short": ["short"],
            "pull": ["pull", "sweat", "tech fleece", "aviateur", "ensemble", "pullover", "veste"],
            "pantalon": ["pantalon", "trousers", "pants"]
        }
        keywords = type_keywords.get(selected_type, [selected_type])
        
        text = f"🔥 ARTICLES DE TYPE : {selected_type.upper()} 🔥\n\n"
        kb_rows = []
        found = False
        for item_id, data in catalog.items():
            name_lower = data["name"].lower()
            if any(kw in name_lower for kw in keywords):
                found = True
                if data["available"]:
                    kb_rows.append([InlineKeyboardButton(f"➕ #{item_id} ({data['name']} - {data['prix']}€)", callback_data=f"addcart_{item_id}")])
                    text += f"#{item_id} - {data['name']} | {data['taille']} | {data['etat']} | {data['prix']} €\n\n"
                else:
                    text += f"#{item_id} - {data['name']} (Vendu)\n\n"
        if not found:
            text += "Aucun article disponible pour ce type.\n\n"
        kb_rows.append([InlineKeyboardButton("👕 Choisir un autre type", callback_data="filter_type")])
        kb_rows.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")])
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb_rows))

    elif query.data == "show_orders":
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("SELECT order_id, items_str, total_price, delivery_mode, status, tracking_num, date FROM orders WHERE user_id = ? ORDER BY order_id DESC LIMIT 5", (user_id,))
        orders = cursor.fetchall()
        conn.close()

        if not orders:
            await query.edit_message_text("📦 Tu n'as pas encore passé de commande.", reply_markup=get_main_keyboard(user_id))
            return

        text = "📦 TES DERNIÈRES COMMANDES\n\n"
        for o in orders:
            oid, items, price, mode, status, tracking, date = o
            text += f"• Cmd #{oid} ({date})\n  Articles : {items}\n  Total : {price}€ | Statut : {status}\n"
            if tracking:
                text += f"  Suivi : {tracking} (Lien : {LAPOSTE_TRACKING_URL}{tracking})\n"
            text += "\n"

        kb = [[InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "show_referral":
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        text = (
            f"🤝 PROGRAMME DE PARRAINAGE\n\n"
            f"Partage ton lien unique avec tes amis. S'ils passent une commande sous 7 jours, tu gagnes une réduction de -5 € !\n\n"
            f"🔗 Ton lien :\n{ref_link}"
        )
        kb = [[InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb))

    elif query.data == "show_points":
        text = (
            f"⭐ PROGRAMME FIDÉLITÉ\n\n"
            f"Tu possèdes actuellement **{u_data['points']} points**.\n\n"
            f"Règles :\n"
            f"• 1 € dépensé = 1 point gagné à chaque commande validée.\n"
            f"• Dès 350 points : -10 € de réduction dans ton panier.\n"
            f"• Dès 1000 points : -50 € de réduction dans ton panier.\n\n"
            f"Une fois la réduction utilisée, tes points seront remis à zéro !"
        )
        kb = [[InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif query.data == "toggle_vip_status":
        status = toggle_vip(user_id)
        state_text = "inscrit aux" if status else "désinscrit des"
        await query.answer(f"Tu es désormais {state_text} VIP Drops !", show_alert=True)
        await query.edit_message_text("Menu Principal :", reply_markup=get_main_keyboard(user_id))

    elif query.data == "click_and_collect_info":
        text = (
            "🤝 LIVRAISON GARES IDF (Mains Propres)\n\n"
            "Forfaits fixes par zone (sans poids) :\n"
            "• Gare proche : 5 €\n"
            "• Gare moyenne : 10 €\n"
            "• Gare éloignée : 15 €\n\n"
            "Contacte le vendeur pour convenir d'un rendez-vous en gare !"
        )
        kb = [[InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")]]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb))

    elif query.data.startswith("confirm_pay_") or query.data.startswith("refuse_pay_") or query.data.startswith("take_charge_"):
        if query.message.chat.id != ADMIN_GROUP_ID:
            return
        parts = query.data.split("_")
        action = parts[0]
        
        if action == "take":
            target_uid = int(parts[2])
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👨‍💻 Pris en charge par Admin", callback_data="noop")],
                [InlineKeyboardButton("✅ Valider", callback_data=f"confirm_pay_{target_uid}_0_0"),
                 InlineKeyboardButton("❌ Refuser", callback_data=f"refuse_pay_{target_uid}")]
            ]))
            await context.bot.send_message(chat_id=target_uid, text="👨‍💻 Un administrateur a pris en charge ton reçu et vérifie ton paiement.")
            
        elif action == "confirm":
            target_uid = int(parts[2])
            order_id = int(parts[3])
            total_price = float(parts[4])

            conn = sqlite3.connect("shop.db")
            cursor = conn.cursor()
            
            cursor.execute("SELECT order_id, items_str, total_price, delivery_mode FROM orders WHERE user_id = ? AND status = 'En attente de paiement' ORDER BY order_id DESC LIMIT 1", (target_uid,))
            ord_row = cursor.fetchone()
            
            if ord_row:
                order_id = ord_row[0]
                items_summary = ord_row[1]
                total_price = ord_row[2]
                delivery_mode = ord_row[3]
            else:
                items_summary = "Articles divers"
                delivery_mode = "Standard"

            cursor.execute("UPDATE orders SET status = 'Validé' WHERE order_id = ?", (order_id,))
            cursor.execute("SELECT username FROM users WHERE user_id = ?", (target_uid,))
            urow = cursor.fetchone()
            client_username = urow[0] if urow and urow[0] else "Client"

            earned_points = int(total_price)
            chosen_reward = user_reward_choices.get(target_uid, 0)
            
            if chosen_reward == 1000:
                cursor.execute("UPDATE users SET points = 0 + ? WHERE user_id = ?", (earned_points, target_uid))
            elif chosen_reward == 350:
                cursor.execute("UPDATE users SET points = points - 350 + ? WHERE user_id = ?", (earned_points, target_uid))
            else:
                cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (earned_points, target_uid))

            conn.commit()
            conn.close()

            if target_uid in user_reward_choices:
                del user_reward_choices[target_uid]

            for jname in [f"reminder_{target_uid}_{order_id}", f"timeout_{target_uid}_{order_id}"]:
                for job in context.job_queue.get_jobs_by_name(jname):
                    job.schedule_removal()

            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Paiement Validé & Facture envoyée", callback_data="noop")]
            ]))
            
            await context.bot.send_message(chat_id=target_uid, text=f"✅ Paiement validé avec succès ! Tu as gagné {earned_points} points fidélité. Ta commande est en cours de préparation.")
            
            pdf_buffer = generate_invoice_pdf(order_id, client_username, target_uid, items_summary, delivery_mode, total_price)
            await context.bot.send_document(
                chat_id=target_uid,
                document=pdf_buffer,
                filename=f"Facture_IDF_Running_Shop_{order_id}.pdf",
                caption="📄 Voici la facture officielle de ta commande."
            )
            
            ref_id = give_referral_reward(target_uid)
            if ref_id:
                try:
                    await context.bot.send_message(chat_id=ref_id, text="🎁 Ton filleul a validé sa commande ! Tu gagnes un coupon de réduction de -5 €.")
                except Exception:
                    pass
                    
        elif action == "refuse":
            target_uid = int(parts[2])
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Paiement Refusé", callback_data="noop")]
            ]))
            await context.bot.send_message(chat_id=target_uid, text="❌ Ton reçu a été refusé par l'administration. Merci de contacter le support pour plus d'informations.")

    elif query.data == "noop":
        pass

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("vendu", admin_vendu))
    app.add_handler(CommandHandler("resto", admin_resto))
    app.add_handler(CommandHandler("suivi", admin_suivi))
    app.add_handler(CommandHandler("annonce", admin_annonce))
    app.add_handler(CommandHandler("dropVIP", admin_dropvip))
    app.add_handler(CommandHandler("ban", admin_ban))
    app.add_handler(CommandHandler("unban", admin_unban))
    app.add_handler(CommandHandler("points", admin_points))
    app.add_handler(CommandHandler("facture", admin_facture))

    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("🤖 Bot démarré avec succès !")
    app.run_polling()

if __name__ == "__main__":
    main()
