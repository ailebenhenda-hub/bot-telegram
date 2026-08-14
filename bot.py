import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# Configuration du logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Variables d'environnement
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "-3956183527"))
CREATOR_USERNAME = os.environ.get("CREATOR_USERNAME", "@idf_runningshop")

WAITING_ORDER_DETAILS, WAITING_RECEIPT = range(2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le menu principal."""
    keyboard = [
        [InlineKeyboardButton("💬 Parler au créateur", url=f"https://t.me/{CREATOR_USERNAME.replace('@', '')}")],
        [InlineKeyboardButton("🛍️ Passer une commande", callback_data="start_order")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "👋 **Bienvenue sur IDF Running Shop !**\n\n"
        "Chaque invité validé vous apporte des réductions exclusives !\n\n"
        "Que souhaitez-vous faire ?"
    )
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
        
    return ConversationHandler.END


async def start_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Étape 1 : Demande des détails de livraison."""
    query = update.callback_query
    await query.answer()

    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    step1_text = (
        "📝 **Étape 1/2 : Détails de la commande**\n\n"
        "Écris en un message :\n"
        "1. Articles + Tailles\n"
        "2. Mode de livraison (Colissimo 6€ ou Main propre)\n"
        "3. Adresse ou Ville du rendez-vous"
    )
    
    await query.edit_message_text(step1_text, reply_markup=reply_markup, parse_mode="Markdown")
    return WAITING_ORDER_DETAILS


async def receive_order_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Étape 2 : Enregistrement et demande du reçu."""
    context.user_data["order_details"] = update.message.text

    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    step2_text = (
        "📸 **Étape 2/2 : Reçu Revolut**\n\n"
        "Envoie maintenant la photo/capture d'écran de ton paiement Revolut."
    )
    
    await update.message.reply_text(step2_text, reply_markup=reply_markup, parse_mode="Markdown")
    return WAITING_RECEIPT


async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envoie la photo directement au groupe d'administration."""
    photo_file_id = update.message.photo[-1].file_id
    order_details = context.user_data.get("order_details", "Non renseigné")
    user = update.effective_user

    # Formatage HTML propre et sécurisé
    admin_caption = (
        f"🚨 <b>NOUVELLE COMMANDE</b> 🚨\n\n"
        f"👤 <b>Client :</b> {user.full_name} (@{user.username if user.username else 'Sans pseudo'})\n"
        f"🆔 <b>ID Telegram :</b> <code>{user.id}</code>\n\n"
        f"📦 <b>Détails de la commande :</b>\n{order_details}"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Valider", callback_data=f"confirm_{user.id}"),
            InlineKeyboardButton("❌ Refuser", callback_data=f"reject_{user.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Transmission au groupe admin
    await context.bot.send_photo(
        chat_id=ADMIN_GROUP_ID,
        photo=photo_file_id,
        caption=admin_caption,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

    # Message de confirmation au client
    await update.message.reply_text(
        "⚡ **Reçu bien transmis aux admins !** Tu recevras une confirmation ici.",
        parse_mode="Markdown"
    )

    return ConversationHandler.END


async def admin_decision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Traitement de la décision admin (Valider / Refuser)."""
    query = update.callback_query
    await query.answer()

    data = query.data
    action, user_id = data.split("_")
    user_id = int(user_id)

    if action == "confirm":
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ **Ta commande a été validée par un administrateur !** Elle sera traitée sous peu."
        )
        await query.edit_message_caption(
            caption=f"{query.message.caption}\n\n✅ **COMMANDE VALIDÉE** par @{query.from_user.username}",
            parse_mode="HTML"
        )
    elif action == "reject":
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ **Ta commande a été refusée.** Contacte le support pour plus de précisions."
        )
        await query.edit_message_caption(
            caption=f"{query.message.caption}\n\n❌ **COMMANDE REFUSÉE** par @{query.from_user.username}",
            parse_mode="HTML"
        )


def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN manquant !")

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_order_callback, pattern="^start_order$")],
        states={
            WAITING_ORDER_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_order_details)
            ],
            WAITING_RECEIPT: [
                MessageHandler(filters.PHOTO, receive_receipt)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(start, pattern="^main_menu$"),
            CommandHandler("start", start)
        ],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(start, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(admin_decision_callback, pattern="^(confirm|reject)_"))

    application.run_polling()


if __name__ == "__main__":
    main()
