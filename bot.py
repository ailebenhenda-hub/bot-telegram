import hashlib
from io import BytesIO
import logging
import os
from groq import Groq
import psycopg
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

# ----------------------------------------------------
# LOGS & CONFIGURATION
# ----------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "-1003956183527"))
CREATOR_USERNAME = "@idf_runningshop"

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

WAITING_ORDER_DETAILS, WAITING_RECEIPT = range(2)


# ----------------------------------------------------
# BASE DE DONNÉES
# ----------------------------------------------------
def get_db():
  return psycopg.connect(DATABASE_URL)


def init_db():
  if not DATABASE_URL:
    return
  try:
    with get_db() as conn:
      with conn.cursor() as cursor:
        cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username VARCHAR(255),
                        first_name VARCHAR(255),
                        referrer_id BIGINT,
                        referrals_count INT DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS receipts (
                        hash_md5 VARCHAR(32) PRIMARY KEY,
                        user_id BIGINT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS blacklist (
                        user_id BIGINT PRIMARY KEY,
                        reason TEXT
                    );
                """)
        conn.commit()
  except Exception as e:
    logging.error(f"Erreur init_db: {e}")


def is_blacklisted(user_id: int) -> bool:
  if not DATABASE_URL:
    return False
  try:
    with get_db() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM blacklist WHERE user_id = %s;", (user_id,)
        )
        return cursor.fetchone() is not None
  except Exception:
    return False


def register_user(
    user_id: int, username: str, first_name: str, referrer_id: int = None
):
  if not DATABASE_URL:
    return
  try:
    with get_db() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            """
                    INSERT INTO users (user_id, username, first_name, referrer_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name;
                """,
            (user_id, username, first_name, referrer_id),
        )

        if referrer_id and referrer_id != user_id:
          cursor.execute(
              "SELECT 1 FROM users WHERE user_id = %s;", (referrer_id,)
          )
          if cursor.fetchone():
            cursor.execute(
                "UPDATE users SET referrals_count = referrals_count + 1 WHERE"
                " user_id = %s;",
                (referrer_id,),
            )
        conn.commit()
  except Exception as e:
    logging.error(f"Erreur register_user: {e}")


def check_and_save_receipt(hash_md5: str, user_id: int) -> bool:
  if not DATABASE_URL:
    return True
  try:
    with get_db() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM receipts WHERE hash_md5 = %s;", (hash_md5,)
        )
        if cursor.fetchone():
          return False
        cursor.execute(
            "INSERT INTO receipts (hash_md5, user_id) VALUES (%s, %s);",
            (hash_md5, user_id),
        )
        conn.commit()
        return True
  except Exception:
    return True


# ----------------------------------------------------
# MENUS
# ----------------------------------------------------
def main_menu():
  keyboard = [
      [
          InlineKeyboardButton(
              "💳 Paiement & Commande", callback_data="btn_order"
          ),
          InlineKeyboardButton("🔔 Restock", callback_data="btn_restock"),
      ],
      [
          InlineKeyboardButton("👥 Parrainage", callback_data="btn_ref"),
          InlineKeyboardButton(
              "🏷️ Promos & Livraison", callback_data="btn_promos"
          ),
      ],
      [
          InlineKeyboardButton("📲 Réseaux Sociaux", callback_data="btn_socials"),
          InlineKeyboardButton(
              "🤝 Main Propre (IDF)", callback_data="btn_hand"
          ),
      ],
      [
          InlineKeyboardButton("📏 Guide des Tailles", callback_data="btn_sizes"),
          InlineKeyboardButton(
              "📦 Suivi Colissimo", callback_data="btn_colissimo"
          ),
      ],
      [
          InlineKeyboardButton("⭐ Avis & Retours", callback_data="btn_reviews"),
          InlineKeyboardButton(
              "👨‍💻 Contact / Humain", callback_data="btn_contact"
          ),
      ],
  ]
  return InlineKeyboardMarkup(keyboard)


def restock_menu():
  keyboard = [
      [
          InlineKeyboardButton(
              "👕 Tech Fleece / Sweats", callback_data="sub_tech"
          )
      ],
      [InlineKeyboardButton("👖 Pantalons", callback_data="sub_pants")],
      [
          InlineKeyboardButton(
              "👟 T-Shirts / Running", callback_data="sub_tshirts"
          )
      ],
      [InlineKeyboardButton("🔙 Retour au menu", callback_data="btn_main")],
  ]
  return InlineKeyboardMarkup(keyboard)


# ----------------------------------------------------
# IA GROQ
# ----------------------------------------------------
SYSTEM_PROMPT = """
Tu es l'assistant IA officiel de 'idf_runningshop', boutique streetwear/running.
Règles :
1. Court, poli et efficace.
2. Livraisons : Colissimo 6€ (offerte dès 170€ d'achat).
3. Main propre : En Île-de-France (93 et gares).
4. Tailles : S (1m65-1m75), M (1m75-1m85), L (1m85-1m90), XL (1m90+). Précise que ces tranches sont indicatives/approximatives et que le client connaît mieux son propre gabarit.
5. Contact humain : Redirige vers @shvppeur_bot ou le bouton Contact si demandé.
"""


def ask_ai(question: str) -> str:
  if not groq_client:
    return "L'assistant IA est indisponible."
  try:
    res = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        temperature=0.5,
        max_tokens=250,
    )
    return res.choices[0].message.content
  except Exception as e:
    logging.error(f"Erreur IA: {e}")
    return "Désolé, une erreur est survenue."


# ----------------------------------------------------
# COMMANDES & NAVIGATION
# ----------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user = update.effective_user
  if is_blacklisted(user.id):
    await update.message.reply_text("⛔ Vous êtes banni du bot.")
    return

  ref_id = None
  if context.args and context.args[0].startswith("ref_"):
    try:
      ref_id = int(context.args[0].replace("ref_", ""))
    except ValueError:
      pass

  register_user(user.id, user.username, user.first_name, ref_id)

  await update.message.reply_text(
      f"🔥 **Bienvenue chez idf_runningshop, {user.first_name} !** 🔥\n\n"
      "Votre boutique spécialisée en running & streetwear.\n"
      "Utilisez le menu ci-dessous ou posez-moi votre question !",
      reply_markup=main_menu(),
      parse_mode="Markdown",
  )


async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  user = query.from_user

  if is_blacklisted(user.id):
    await query.edit_message_text("⛔ Vous êtes banni du bot.")
    return

  data = query.data

  if data == "btn_main":
    await query.edit_message_text(
        "🔥 **Menu Principal idf_runningshop**",
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )

  elif data == "btn_restock":
    await query.edit_message_text(
        "🔔 **Abonnement Alertes Restock**\nSélectionnez une catégorie :",
        reply_markup=restock_menu(),
    )

  elif data in ["sub_tech", "sub_pants", "sub_tshirts"]:
    cat_map = {
        "sub_tech": "Tech Fleece",
        "sub_pants": "Pantalons",
        "sub_tshirts": "T-Shirts/Running",
    }
    await query.edit_message_text(
        f"✅ Notification configurée pour **{cat_map[data]}** !",
        reply_markup=restock_menu(),
        parse_mode="Markdown",
    )

  elif data == "btn_ref":
    bot_info = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"
    await query.edit_message_text(
        "👥 **Système de Parrainage**\n\n"
        f"Votre lien exclusif :\n`{ref_link}`\n\n"
        "Partagez-le pour débloquer des réductions !",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Retour", callback_data="btn_main")]]
        ),
        parse_mode="Markdown",
    )

  elif data == "btn_promos":
    await query.edit_message_text(
        "🏷️ **Offres Promos & Shipping**\n\n"
        "• **Frais de port :** 6€ via Colissimo Suivi.\n"
        "• **LIVRAISON OFFERTE** dès 170€ d'achat !\n"
        "• **Remises lots :** Directement en DM.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Retour", callback_data="btn_main")]]
        ),
        parse_mode="Markdown",
    )

  elif data == "btn_socials":
    kb = [
        [
            InlineKeyboardButton(
                "📸 Snapchat", url="https://snapchat.com/t/BW0Gzw9i"
            )
        ],
        [
            InlineKeyboardButton(
                "🎵 TikTok",
                url=(
                    "https://www.tiktok.com/@idf_runningshop?_r=1&_t=ZN-98sYce7fxhO"
                ),
            )
        ],
        [InlineKeyboardButton("🛍️ Vinted", url="https://www.vinted.fr")],
        [
            InlineKeyboardButton(
                "📢 Canal VIP Telegram", url="https://t.me/idfrunningvip"
            )
        ],
        [InlineKeyboardButton("🔙 Retour", callback_data="btn_main")],
    ]
    await query.edit_message_text(
        "📲 **Nos Réseaux Officiels :**", reply_markup=InlineKeyboardMarkup(kb)
    )

  elif data == "btn_hand":
    kb = [
        [
            InlineKeyboardButton(
                "💬 Contacter le vendeur",
                url=f"https://t.me/{CREATOR_USERNAME.replace('@','')}",
            )
        ],
        [InlineKeyboardButton("🔙 Retour", callback_data="btn_main")],
    ]
    await query.edit_message_text(
        "🤝 **Remise en Main Propre**\n\n"
        "• Disponible partout en **Île-de-France**.\n"
        "• Secteur principal : **93 / Gares principales**.\n"
        "• Paiement espèces ou Revolut sur place.",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
    )

  elif data == "btn_sizes":
    await query.edit_message_text(
        "📏 **Guide des Tailles**\n\n"
        "• **S :** 1m65 - 1m75\n"
        "• **M :** 1m75 - 1m85\n"
        "• **L :** 1m85 - 1m90\n"
        "• **XL :** 1m90+\n\n"
        "💡 *Note : Ces indications restent approximatives. Vous connaissez"
        " mieux votre gabarit et vos préférences de coupe (ajustée ou"
        " ample).*",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Retour", callback_data="btn_main")]]
        ),
        parse_mode="Markdown",
    )

  elif data == "btn_colissimo":
    kb = [
        [
            InlineKeyboardButton(
                "🌐 Suivre mon colis sur La Poste",
                url="https://www.laposte.fr/outils/suivre-vos-envois",
            )
        ],
        [InlineKeyboardButton("🔙 Retour", callback_data="btn_main")],
    ]
    await query.edit_message_text(
        "📦 **Suivi Colissimo :**", reply_markup=InlineKeyboardMarkup(kb)
    )

  elif data == "btn_reviews":
    kb = [
        [
            InlineKeyboardButton(
                "💬 Groupe Avis & Retours", url="https://t.me/+q2HRbe-dBydlZWZk"
            )
        ],
        [
            InlineKeyboardButton(
                "💳 Avis Paiements en Ligne",
                url="https://t.me/c/4339817330/8",
            )
        ],
        [InlineKeyboardButton("🔙 Retour", callback_data="btn_main")],
    ]
    await query.edit_message_text(
        "⭐ **Avis Clients :**", reply_markup=InlineKeyboardMarkup(kb)
    )

  elif data == "btn_contact":
    try:
      alert_msg = (
          "🚨 **Demande d'assistance Humaine**\n\n"
          f"👤 **Client :** {user.first_name} (@{user.username or 'aucun'})\n"
          f"🆔 **ID :** `{user.id}`"
      )
      await context.bot.send_message(
          chat_id=ADMIN_GROUP_ID, text=alert_msg, parse_mode="Markdown"
      )
    except Exception as e:
      logging.error(f"Erreur alerte contact: {e}")

    kb = [
        [
            InlineKeyboardButton(
                "💬 Parler au créateur",
                url=f"https://t.me/{CREATOR_USERNAME.replace('@','')}",
            )
        ],
        [InlineKeyboardButton("🔙 Retour", callback_data="btn_main")],
    ]
    await query.edit_message_text(
        "👨‍💻 Un administrateur a été notifié !\n"
        "Tu peux aussi lui écrire directement ci-dessous :",
        reply_markup=InlineKeyboardMarkup(kb),
    )


# ----------------------------------------------------
# TUNNEL COMMANDE
# ----------------------------------------------------
async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  await query.message.reply_text(
      "📝 **Étape 1/2 : Détails de la commande**\n\n"
      "Écris en un message :\n"
      "1. Articles + Tailles\n"
      "2. Mode de livraison (Colissimo 6€ ou Main propre)\n"
      "3. Adresse ou Ville du rendez-vous"
  )
  return WAITING_ORDER_DETAILS


async def receive_order_details(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
  context.user_data["order_details"] = update.message.text
  await update.message.reply_text(
      "📸 **Étape 2/2 : Reçu Revolut**\n\n"
      "Envoie maintenant la photo/capture d'écran de ton paiement Revolut."
  )
  return WAITING_RECEIPT


async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user = update.effective_user
  photo_file = await update.message.photo[-1].get_file()

  image_bytes = await photo_file.download_as_bytearray()
  hash_md5 = hashlib.md5(image_bytes).hexdigest()

  if not check_and_save_receipt(hash_md5, user.id):
    await update.message.reply_text(
        "❌ **ERREUR : Ce reçu a déjà été utilisé !**"
    )
    return ConversationHandler.END

  order_details = context.user_data.get("order_details", "Non renseigné")

  caption = (
      "📥 **NOUVELLE COMMANDE REÇUE**\n\n"
      f"👤 **Client :** {user.first_name} (@{user.username or 'aucun'})\n"
      f"🆔 **ID :** `{user.id}`\n\n"
      f"📝 **Détails :**\n{order_details}\n\n"
      f"🔑 **Hash MD5 :** `{hash_md5}`"
  )

  admin_kb = InlineKeyboardMarkup([[
      InlineKeyboardButton(
          "✅ Valider Paiement", callback_data=f"adm_val_{user.id}"
      ),
      InlineKeyboardButton(
          "📦 Expédier (Colissimo)", callback_data=f"adm_ship_{user.id}"
      ),
  ]])

  try:
    await context.bot.send_photo(
        chat_id=ADMIN_GROUP_ID,
        photo=BytesIO(image_bytes),
        caption=caption,
        reply_markup=admin_kb,
        parse_mode="Markdown",
    )
  except Exception as e:
    logging.error(f"Erreur envoi groupe admin: {e}")

  await update.message.reply_text(
      "⚡ **Reçu bien transmis aux admins !** Tu recevras une confirmation"
      " ici."
  )
  return ConversationHandler.END


async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("Commande annulée.")
  return ConversationHandler.END


# ----------------------------------------------------
# ACTIONS ADMIN
# ----------------------------------------------------
async def admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  data = query.data

  if data.startswith("adm_val_"):
    target_id = int(data.replace("adm_val_", ""))
    await context.bot.send_message(
        chat_id=target_id,
        text=(
            "✅ **Votre paiement a été validé !**\nVotre commande est en"
            " préparation."
        ),
    )
    await query.edit_message_caption(
        caption=f"{query.message.caption}\n\n🟢 **STATUT : VALIDÉ**"
    )

  elif data.startswith("adm_ship_"):
    target_id = int(data.replace("adm_ship_", ""))
    coliss_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📦 Suivi Colissimo",
            url="https://www.laposte.fr/outils/suivre-vos-envois",
        )
    ]])
    await context.bot.send_message(
        chat_id=target_id,
        text=(
            "📦 **Votre commande a été expédiée !**\nConsultez votre suivi"
            " ci-dessous :"
        ),
        reply_markup=coliss_kb,
    )
    await query.edit_message_caption(
        caption=f"{query.message.caption}\n\n🔵 **STATUT : EXPÉDIÉ**"
    )


# ----------------------------------------------------
# MESSAGES TEXTES (IA & TRANSFERT)
# ----------------------------------------------------
async def handle_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user = update.effective_user
  if is_blacklisted(user.id):
    return

  text = update.message.text

  try:
    admin_log = (
        "💬 **Nouveau message client**\n"
        f"👤 **De :** {user.first_name} (@{user.username or 'aucun'})\n"
        f"🆔 **ID :** `{user.id}`\n"
        f"📩 **Message :** {text}"
    )
    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID, text=admin_log, parse_mode="Markdown"
    )
  except Exception as e:
    logging.error(f"Erreur transfert msg admin: {e}")

  ai_reply = ask_ai(text)
  await update.message.reply_text(ai_reply, reply_markup=main_menu())


# ----------------------------------------------------
# MAIN
# ----------------------------------------------------
if __name__ == "__main__":
  if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN manquante.")

  init_db()

  app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

  order_conv = ConversationHandler(
      entry_points=[CallbackQueryHandler(start_order, pattern="^btn_order$")],
      states={
          WAITING_ORDER_DETAILS: [
              MessageHandler(
                  filters.TEXT & ~filters.COMMAND, receive_order_details
              )
          ],
          WAITING_RECEIPT: [MessageHandler(filters.PHOTO, receive_receipt)],
      },
      fallbacks=[CommandHandler("cancel", cancel_order)],
  )

  app.add_handler(CommandHandler("start", start))
  app.add_handler(order_conv)
  app.add_handler(CallbackQueryHandler(admin_actions, pattern="^adm_"))
  app.add_handler(CallbackQueryHandler(button_click))
  app.add_handler(
      MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_text)
  )

  app.run_polling()
