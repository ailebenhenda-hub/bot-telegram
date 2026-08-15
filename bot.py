import logging
import os
import sqlite3
from datetime import datetime, timedelta
from io import BytesIO
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


# --- BASE DE DONNÉES SQLITE PRO ---
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
            discount_coupon INTEGER DEFAULT 0
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
    
    # Ajouter quelques articles par défaut si la table est vide
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
        "SELECT points, banned, referred_by, discount_coupon FROM users WHERE user_id = ?", (user_id,)
    )
    res = cursor.fetchone()
    if not res:
        cursor.execute(
            "INSERT INTO users (user_id, username, points, banned, discount_coupon) VALUES (?, ?, 0, 0, 0)",
            (user_id, username),
        )
        conn.commit()
        res = (0, 0, None, 0)
    conn.close()
    return {"points": res[0], "banned": res[1], "referred_by": res[2], "discount_coupon": res[3]}


def add_points(user_id, points):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (points, user_id))
    conn.commit()
    conn.close()


def set_ban_status(user_id, banned_status):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET banned = ? WHERE user_id = ?", (banned_status, user_id))
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
    cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row[0] and row[0] != -1:
        referrer_id = row[0]
        cursor.execute("UPDATE users SET discount_coupon = discount_coupon + 1, referred_by = -1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        return referrer_id
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


reservations = {}  # item_id -> {"user_id": ..., "expires": datetime, "warned": bool}
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
            # Remettre disponible en BDD
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
        [InlineKeyboardButton("📦 Catalogue & Stock", callback_data="show_catalog"),
         InlineKeyboardButton("🛒 Mon Panier", callback_data="show_cart")],
        [InlineKeyboardButton("🔍 Filtrer par taille", callback_data="filter_size"),
         InlineKeyboardButton("📦 Mes Commandes", callback_data="show_orders")],
        [InlineKeyboardButton("🤝 Parrainage (-5€)", callback_data="show_referral"),
         InlineKeyboardButton("⭐ Fidélité", callback_data="show_points")],
        [InlineKeyboardButton("📏 Guide des Tailles", callback_data="size_guide"),
         InlineKeyboardButton(vip_btn_text, callback_data="toggle_vip_status")],
        [InlineKeyboardButton("🤝 Click & Collect (IDF)", callback_data="click_and_collect_info"),
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
                    await update.message.reply_text("🎁 Tu as rejoint le lien de parrainage ! Tu as **7 jours** pour valider un achat et faire gagner -5 € à ton parrain.")
            except ValueError:
                pass

    welcome_msg = (
        f"👋 Bienvenue {user.first_name} sur IDF Running Shop !\n\n"
        "Boutique indépendante streetwear & vêtements running. 🔥\n"
        "• Port offert dès 170 € d'achat !\n"
        "• Remise de -5€ / article supplémentaire dès 70 € d'achat.\n\n"
        "Envoie le numéro d'un article (ex: #1) ou gère ton panier !"
    )
    await update.message.reply_text(welcome_msg, reply_markup=get_main_keyboard(user.id))


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
            text += f"#{item_id} - {data['name']}\n   {status}\n\n"

        kb_rows.append([InlineKeyboardButton("🛒 Voir mon panier", callback_data="show_cart")])
        kb_rows.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="main_menu")])
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb_rows))

    elif query.data == "main_menu":
        await query.edit_message_text("Menu Principal :", reply_markup=get_main_keyboard(user_id))

    elif query.data.startswith("busy_"):
        item_id = query.data.split("_")[1]
        if item_id in reservations:
            expires_at = reservations[item_id]["expires"]
            remaining_sec = int((expires_at - datetime.now()).total_seconds())
            if remaining_sec > 0:
                mins = remaining_sec // 60
                secs = remaining_sec % 60
                await query.answer(f"⏳ Cet article est réservé ! Il reste environ {mins}m {secs}s à l'acheteur avant qu'il ne soit libéré.", show_alert=True)
            else:
                await query.answer("⏳ La réservation expire d'une minute à l'autre, réessaye !", show_alert=True)

    elif query.data.startswith("addcart_"):
        item_id = query.data.split("_")[1]
        if catalog[item_id]["available"] and item_id not in reservations:
            add_to_cart(user_id, item_id)
            await query.answer(f"✅ Article #{item_id} ajouté au panier !", show_alert=True)
        else:
            await query.answer("❌ Cet article n'est plus disponible.", show_alert=True)

    elif query.data == "show_cart":
        cart_items = get_cart(user_id)
        if not cart_items:
            text = "🛒 Ton panier est vide."
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("📦 Voir le catalogue", callback_data="show_catalog")]])
        else:
            current_delivery = delivery_choices.get(user_id, "colissimo")
            text = "🛒 **TON PANIER ACTUEL** :\n\n"
            total = 0
            for item_id in cart_items:
                item = catalog[item_id]
                text += f"• #{item_id} - {item['name']} : **{item['prix']} €**\n"
                total += item['prix']
            
            if current_delivery == "click_collect":
                shipping = 0
                delivery_text = "🤝 Click & Collect (Main propre IDF - Gratuit)"
            else:
                shipping = 6 if total < 170 else 0
                delivery_text = f"🚚 Colissimo ({shipping} € {'OFFERT 🎉' if shipping == 0 else ''})"

            final_total = total + shipping
            if u_data["discount_coupon"] > 0:
                final_total = max(0, final_total - 5)
                text += f"\n🎟️ **Bon de parrainage (-5 €) appliqué !**\n"

            text += f"\n• Sous-total : {total} €\n"
            text += f"• Mode : {delivery_text}\n"
            text += f"💰 **TOTAL GLOBAL : {final_total} €**"

            cc_check = "✅ " if current_delivery == "click_collect" else ""
            col_check = "✅ " if current_delivery == "colissimo" else ""

            kb_buttons = [
                [InlineKeyboardButton(f"{col_check}🚚 Colissimo (+6€)", callback_data="set_del_colissimo"),
                 InlineKeyboardButton(f"{cc_check}🤝 Click & Collect", callback_data="set_del_cc")],
                [InlineKeyboardButton("✅ Valider et Payer (Bloquer 5 min)", callback_data="checkout_cart")],
                [InlineKeyboardButton("🗑️ Vider le panier", callback_data="clear_cart")],
                [InlineKeyboardButton("📦 Continuer mes achats", callback_data="show_catalog")]
            ]
            kb = InlineKeyboardMarkup(kb_buttons)
        await query.edit_message_text(text=text, reply_markup=kb, parse_mode="Markdown")

    elif query.data == "set_del_colissimo":
        delivery_choices[user_id] = "colissimo"
        await query.answer("Mode Colissimo sélectionné.")
        await refresh_cart_display(query, user_id, u_data, get_catalog_items())

    elif query.data == "set_del_cc":
        delivery_choices[user_id] = "click_collect"
        await query.answer("Mode Click & Collect sélectionné.")
        await refresh_cart_display(query, user_id, u_data, get_catalog_items())

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

        # Vérifier si l'un des articles du panier vient d'être pris par quelqu'un d'autre
        for i in cart_items:
            if not catalog[i]["available"] or i in reservations:
                await query.answer(f"❌ Désolé, l'article #{i} vient d'être réservé par un autre client !", show_alert=True)
                return

        total = sum(catalog[i]["prix"] for i in cart_items)
        current_delivery = delivery_choices.get(user_id, "colissimo")
        shipping = 0 if current_delivery == "click_collect" else (6 if total < 170 else 0)
        del_label = "Click & Collect" if current_delivery == "click_collect" else "Colissimo"

        final_total = total + shipping
        if u_data["discount_coupon"] > 0:
            final_total = max(0, final_total - 5)

        revolut_link = f"{REVOLUT_BASE}/{final_total}"

        item_names = []
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        for i in cart_items:
            # Réserver pour 5 minutes pile
            reservations[i] = {
                "user_id": user_id,
                "expires": datetime.now() + timedelta(minutes=5),
                "warned": False,
            }
            cursor.execute("UPDATE catalog SET available = 0 WHERE item_id = ?", (i,))
            item_names.append(f"#{i} {catalog[i]['name']}")
        conn.commit()
        conn.close()

        # Enregistrer la commande en BDD avec statut "En attente"
        items_str = ", ".join(item_names)
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        cursor.execute(
            "INSERT INTO orders (user_id, items_str, total_price, delivery_mode, status, date) VALUES (?, ?, ?, ?, 'En attente de paiement', ?)",
            (user_id, items_str, final_total, del_label, date_str)
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
            f"• Mode : {del_label}\n"
            f"💰 **TOTAL À PAYER : {final_total} €**\n\n"
            "Règler sur Revolut ci-dessous, puis **envoie la capture du reçu ici en photo** !"
        )
        await query.edit_message_text(text=confirm_text, reply_markup=kb_pay, parse_mode="Markdown")
        
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=f"🚨 NOUVELLE COMMANDE (BLOQUÉE 5 MIN)\nClient : {query.from_user.first_name} (@{query.from_user.username})\nMode : {del_label}\nArticles : {items_str}\nMontant : {final_total} €"
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
            text = "📦 Tu n'as pas encore d'historique de commandes."
        else:
            text = "📦 **TON SUIVI DE COMMANDES** :\n\n"
            for o in orders:
                status_icon = "⏳"
                if o[4] == "Payé": status_icon = "💳"
                elif o[4] == "En préparation": status_icon = "📦"
                elif o[4] == "Expédié": status_icon = "🚚"
                
                text += f"• **Cmd #{o[0]}** ({o[6]})\n"
                text += f"  {o[1]}\n"
                text += f"  Montant : {o[2]} € | Statut : {status_icon} *{o[4]}*\n"
                if o[5]:
                    text += f"  Suivi La Poste : `{o[5]}`\n"
                text += "\n"
        await query.edit_message_text(text=text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

    elif query.data == "show_referral":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        coupons = u_data["discount_coupon"]
        text = (
            "🤝 **PROGRAMME DE PARRAINAGE**\n\n"
            "Invite tes amis ! S'ils achètent dans les **7 jours**, **tu gagnes un bon de -5 €**.\n\n"
            f"🎟️ Bons -5 € disponibles : **{coupons}**\n\n"
            f"🔗 Lien personnel :\n`{ref_link}`"
        )
        await query.edit_message_text(text=text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

    elif query.data == "toggle_vip_status":
        status = toggle_vip(user_id)
        msg_text = "✅ Inscrit aux VIP Drops !" if status else "❌ Désinscrit des VIP Drops."
        await query.answer(msg_text, show_alert=True)
        await query.edit_message_reply_markup(reply_markup=get_main_keyboard(user_id))

    elif query.data == "filter_size":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Taille S", callback_data="size_S"),
             InlineKeyboardButton("Taille M", callback_data="size_M")],
            [InlineKeyboardButton("Taille L", callback_data="size_L"),
             InlineKeyboardButton("Taille XL", callback_data="size_XL")],
            [InlineKeyboardButton("🔙 Retour", callback_data="show_catalog")]
        ])
        await query.edit_message_text("Sélectionne ta taille :", reply_markup=kb)

    elif query.data == "size_guide":
        text = (
            "📏 GUIDE DES TAILLES\n\n"
            "• Nike Aeroswift : Coupe très ajustée. Prends une taille au-dessus si tu hésites.\n"
            "• Phenom Elite : Coupe fuselée standard.\n"
            "• Tech Fleece : Taille normalement."
        )
        await query.edit_message_text(text=text, reply_markup=get_main_keyboard(user_id))

    elif query.data == "click_and_collect_info":
        text = (
            "🤝 **CLICK & COLLECT (IDF)**\n\n"
            "📍 Lieux : Gares d'Île-de-France ou secteur 93.\n"
            "💰 Frais : 100% Gratuit !\n"
            "Choisis l'option directement dans ton panier."
        )
        await query.edit_message_text(text=text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

    elif query.data.startswith("alert_"):
        item_id = query.data.split("_")[1]
        add_wishlist(user_id, item_id)
        await query.answer("🔔 Alerte activée pour le restock !", show_alert=True)

    elif query.data.startswith("size_"):
        size = query.data.split("_")[1]
        text = f"🔎 Articles en taille {size} :\n\n"
        kb_rows = []
        found = False
        for item_id, data in catalog.items():
            if data["taille"] == size and data["available"] and item_id not in reservations:
                kb_rows.append([InlineKeyboardButton(f"➕ Ajouter #{item_id} - {data['name']} ({data['prix']}€)", callback_data=f"addcart_{item_id}")])
                found = True
        if not found:
            text += "Aucun article dispo pour cette taille."
            kb_rows.append([InlineKeyboardButton("🔙 Retour", callback_data="filter_size")])
        else:
            text += "Clique pour ajouter :"
            kb_rows.append([InlineKeyboardButton("🛒 Voir mon panier", callback_data="show_cart")])
            kb_rows.append([InlineKeyboardButton("🔙 Retour", callback_data="filter_size")])
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb_rows))

    elif query.data == "show_points":
        pts = u_data["points"]
        text = f"⭐ TES POINTS : {pts} pts\n• 1 € = 1 point.\n• Atteins 200 pts pour -10 € !"
        await query.edit_message_text(text=text, reply_markup=get_main_keyboard(user_id))

    elif query.data.startswith("confirm_pay_"):
        parts = query.data.split("_")
        target_id = int(parts[2])
        price = float(parts[3]) if len(parts) > 3 else 0

        add_points(target_id, int(price))
        
        target_u_data = get_user(target_id)
        if target_u_data["discount_coupon"] > 0:
            use_coupon(target_id)

        referrer_id = give_referral_reward(target_id)
        if referrer_id:
            try:
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text="🎉 Un filleul a validé son achat ! Tu gagnes un **bon de réduction de -5 €** !"
                )
            except Exception:
                pass

        # Mettre à jour les réservations et le statut des commandes
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        
        # Trouver la dernière commande en attente de cet utilisateur
        cursor.execute("SELECT order_id, items_str, total_price, delivery_mode FROM orders WHERE user_id = ? AND status = 'En attente de paiement' ORDER BY order_id DESC LIMIT 1", (target_id,))
        ord_res = cursor.fetchone()
        order_id = ord_res[0] if ord_res else 0
        items_summary = ord_res[1] if ord_res else "Articles divers"
        del_mode = ord_res[3] if ord_res else "Colissimo"

        cursor.execute("UPDATE orders SET status = 'Payé' WHERE order_id = ?", (order_id,))

        for item_id, res_data in list(reservations.items()):
            if res_data["user_id"] == target_id:
                cursor.execute("UPDATE catalog SET available = 0 WHERE item_id = ?", (item_id,))
                del reservations[item_id]

        cursor.execute("UPDATE stats SET total_sales = total_sales + 1, revenue = revenue + ? WHERE id = 1", (price,))
        conn.commit()
        conn.close()

        # Générer la facture PDF automatiquement
        pdf_buffer = generate_invoice_pdf(target_id, order_id, items_summary, price, del_mode)

        await context.bot.send_message(
            chat_id=target_id,
            text=f"✅ Ton paiement de {int(price)} € a été validé ! +{int(price)} pts fidélité. Voici ta facture officielle ci-dessous 👇"
        )
        await context.bot.send_document(
            chat_id=target_id,
            document=pdf_buffer,
            filename=f"Facture_IDF_Running_Shop_{order_id}.pdf"
        )

        new_text = query.message.caption if query.message.caption else query.message.text
        new_text += f"\n\n✅ PAIEMENT VALIDÉ PAR {admin_name}"
        await query.edit_message_caption(caption=new_text, reply_markup=None)

    elif query.data.startswith("refuse_pay_"):
        parts = query.data.split("_")
        target_id = int(parts[2])

        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        for item_id, res_data in list(reservations.items()):
            if res_data["user_id"] == target_id:
                cursor.execute("UPDATE catalog SET available = 1 WHERE item_id = ?", (item_id,))
                del reservations[item_id]
        cursor.execute("UPDATE orders SET status = 'Annulé' WHERE user_id = ? AND status = 'En attente de paiement'", (target_id,))
        conn.commit()
        conn.close()

        await context.bot.send_message(
            chat_id=target_id,
            text="❌ Ton reçu de paiement a été refusé. Contacte @idf_runningshop si besoin."
        )
        new_text = query.message.caption if query.message.caption else query.message.text
        new_text += f"\n\n❌ PAIEMENT REFUSÉ PAR {admin_name}"
        await query.edit_message_caption(caption=new_text, reply_markup=None)


def generate_invoice_pdf(user_id, order_id, items_desc, amount, delivery_mode):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # En-tête
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 50, "IDF RUNNING SHOP")
    
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 70, "Boutique Streetwear & Running Second-Main")
    c.drawString(50, height - 85, "contact: @idf_runningshop")

    # Infos Facture
    c.setFont("Helvetica-Bold", 12)
    c.drawString(400, height - 50, f"FACTURE #{order_id}")
    c.setFont("Helvetica", 10)
    c.drawString(400, height - 68, f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    c.drawString(400, height - 85, f"Client ID: {user_id}")

    # Ligne de séparation
    c.setLineWidth(1)
    c.line(50, height - 110, width - 50, height - 110)

    # Détails
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, height - 140, "Désignation des articles :")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 160, items_desc)

    c.drawString(50, height - 190, f"Mode de livraison : {delivery_mode}")

    c.line(50, height - 220, width - 50, height - 220)

    # Total
    c.setFont("Helvetica-Bold", 14)
    c.drawString(350, height - 250, f"TOTAL PAYÉ : {amount} €")

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(50, height - 300, "Merci pour votre confiance ! - IDF Running Shop")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


async def refresh_cart_display(query, user_id, u_data, catalog):
    cart_items = get_cart(user_id)
    text = "🛒 **TON PANIER ACTUEL** :\n\n"
    total = 0
    for item_id in cart_items:
        item = catalog[item_id]
        text += f"• #{item_id} - {item['name']} : **{item['prix']} €**\n"
        total += item['prix']
    
    current_delivery = delivery_choices.get(user_id, "colissimo")
    if current_delivery == "click_collect":
        shipping = 0
        delivery_text = "🤝 Click & Collect (Gratuit)"
    else:
        shipping = 6 if total < 170 else 0
        delivery_text = f"🚚 Colissimo ({shipping} €)"

    final_total = total + shipping
    if u_data["discount_coupon"] > 0:
        final_total = max(0, final_total - 5)
        text += f"\n🎟️ **Bon de parrainage (-5 €) appliqué !**\n"

    text += f"\n• Sous-total : {total} €\n"
    text += f"• Mode : {delivery_text}\n"
    text += f"💰 **TOTAL GLOBAL : {final_total} €**"

    cc_check = "✅ " if current_delivery == "click_collect" else ""
    col_check = "✅ " if current_delivery == "colissimo" else ""

    kb_buttons = [
        [InlineKeyboardButton(f"{col_check}🚚 Colissimo (+6€)", callback_data="set_del_colissimo"),
         InlineKeyboardButton(f"{cc_check}🤝 Click & Collect", callback_data="set_del_cc")],
        [InlineKeyboardButton("✅ Valider et Payer (Bloquer 5 min)", callback_data="checkout_cart")],
        [InlineKeyboardButton("🗑️ Vider le panier", callback_data="clear_cart")],
        [InlineKeyboardButton("📦 Continuer mes achats", callback_data="show_catalog")]
    ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb_buttons), parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) == str(ADMIN_GROUP_ID):
        return

    user = update.effective_user
    known_users.add(user.id)
    u_data = get_user(user.id, user.username)
    if u_data["banned"]:
        return

    if update.message.photo:
        photo = update.message.photo[-1].file_id

        total_price_with_shipping = 0
        current_delivery = delivery_choices.get(user.id, "colissimo")
        catalog = get_catalog_items()
        for item_id, res_data in reservations.items():
            if res_data["user_id"] == user.id:
                raw_price = catalog[item_id]["prix"]
                shipping = 0 if current_delivery == "click_collect" else (6 if raw_price < 170 else 0)
                total_price_with_shipping = raw_price + shipping
                break
        
        if u_data["discount_coupon"] > 0:
            total_price_with_shipping = max(0, total_price_with_shipping - 5)

        admin_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Valider", callback_data=f"confirm_pay_{user.id}_{total_price_with_shipping}"),
             InlineKeyboardButton("❌ Refuser", callback_data=f"refuse_pay_{user.id}")]
        ])
        await context.bot.send_photo(
            chat_id=ADMIN_GROUP_ID,
            photo=photo,
            caption=(
                f"💳 REÇU DE PAIEMENT REÇU\nClient : {user.first_name} (@{user.username})\nID : {user.id}\nMontant : {total_price_with_shipping} €"
            ),
            reply_markup=admin_kb,
        )
        await update.message.reply_text("✅ Reçu transmis ! On valide ta commande rapidement.")
        return

    text = update.message.text.strip()
    catalog = get_catalog_items()

    if text.startswith("#") and text[1:].isdigit():
        item_id = text[1:]
        if item_id in catalog:
            item = catalog[item_id]
            if not item["available"]:
                await update.message.reply_text("❌ Cet article est vendu ! Veux-tu être alerté s'il revient ?", 
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔔 M'alerter", callback_data=f"alert_{item_id}")]]))
                return

            add_to_cart(user.id, item_id)
            await update.message.reply_text(
                f"✅ Article #{item_id} ({item['name']}) ajouté au panier !",
                reply_markup=get_main_keyboard(user.id)
            )
            return

    await update.message.reply_text(
        "Tape le numéro d'un article (ex: #1) ou utilise le catalogue.",
        reply_markup=get_main_keyboard(user.id),
    )


# --- COMMANDES ADMIN ---
async def cmd_additem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return
    # Format: /additem Nom | Taille | État | Prix | ID
    try:
        args_text = " ".join(context.args)
        parts = [p.strip() for p in args_text.split("|")]
        if len(parts) < 5:
            await update.message.reply_text("Utilisation : `/additem Nom | Taille | État | Prix | ID`", parse_mode="Markdown")
            return
        
        name, taille, etat, prix, item_id = parts[0], parts[1], parts[2], float(parts[3]), parts[4]
        
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO catalog (item_id, name, taille, etat, prix, available) VALUES (?, ?, ?, ?, ?, 1)",
                       (item_id, name, taille, etat, prix))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ Article #{item_id} ({name}) ajouté avec succès au catalogue BDD !")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur : {e}")


async def cmd_suivi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return
    if len(context.args) >= 2:
        order_id = int(context.args[0])
        tracking_num = context.args[1]

        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            await update.message.reply_text("❌ Commande introuvable.")
            return
        target_id = row[0]
        cursor.execute("UPDATE orders SET status = 'Expédié', tracking_num = ? WHERE order_id = ?", (tracking_num, order_id))
        conn.commit()
        conn.close()

        tracking_link = f"https://www.laposte.fr/outils/suivre-vos-envois?code={tracking_num}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚚 Suivre mon colis La Poste", url=tracking_link)]])

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"📦 **TA COMMANDE #{order_id} A ÉTÉ EXPÉDIÉE !**\n\nNuméro de suivi : `{tracking_num}`",
                reply_markup=kb,
                parse_mode="Markdown",
            )
            await update.message.reply_text(f"✅ Suivi envoyé au client pour la commande #{order_id}.")
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur d'envoi : {e}")
    else:
        await update.message.reply_text("Utilisation : `/suivi ID_COMMANDE NUMERO_COLISSIMO`", parse_mode="Markdown")


async def cmd_vendu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return
    if context.args and context.args[0] in get_catalog_items():
        item_id = context.args[0]
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE catalog SET available = 0 WHERE item_id = ?", (item_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"❌ Article #{item_id} marqué comme VENDU.")


async def cmd_resto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return
    if context.args and context.args[0] in get_catalog_items():
        item_id = context.args[0]
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE catalog SET available = 1 WHERE item_id = ?", (item_id,))
        cursor.execute("SELECT user_id FROM wishlist WHERE item_id = ?", (item_id,))
        users_to_notify = cursor.fetchall()
        conn.close()

        for u in users_to_notify:
            try:
                await context.bot.send_message(chat_id=u[0], text=f"🔔 **RESTOCK !** L'article #{item_id} est de nouveau dispo !")
            except Exception:
                continue

        await update.message.reply_text(f"✅ Article #{item_id} remis en stock.")


async def cmd_annonce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return
    message = " ".join(context.args)
    if not message: return
    count = 0
    for uid in known_users:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 **ANNONCE**\n\n{message}", parse_mode="Markdown")
            count += 1
        except Exception:
            continue
    await update.message.reply_text(f"🚀 Annonce envoyée à {count} clients.")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(ADMIN_GROUP_ID):
        return
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT total_sales, revenue FROM stats WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    sales, revenue = row if row else (0, 0.0)
    await update.message.reply_text(f"📊 Ventes : **{sales}** | CA : **{revenue:.2f} €**", parse_mode="Markdown")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(check_reservations_job, interval=30, first=5)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("additem", cmd_additem))
    app.add_handler(CommandHandler("suivi", cmd_suivi))
    app.add_handler(CommandHandler("vendu", cmd_vendu))
    app.add_handler(CommandHandler("resto", cmd_resto))
    app.add_handler(CommandHandler("annonce", cmd_annonce))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()
