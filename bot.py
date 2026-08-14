import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from groq import Groq

# Configuration des logs
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Récupération des clés depuis Railway
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
STRIPE_LINK = os.getenv("STRIPE_LINK", "https://buy.stripe.com/TON_VRAI_LIEN_ICI")

# Initialisation du client Groq (IA)
groq_client = Groq(api_key=GROQ_API_KEY)


# 1. Commande /start (Menu principal aéré)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 **Bienvenue sur IDF Running // V.I.P**\n\n"
        "Spécialiste vêtements exclusifs.\n"
        "Que souhaites-tu faire aujourd'hui ?"
    )
    keyboard = [
        [InlineKeyboardButton("📦 Payer par Carte (Colissimo)", url=STRIPE_LINK)],
        [InlineKeyboardButton("🎁 Concours & Codes Promo", callback_data="promo_contest")],
        [InlineKeyboardButton("📌 Infos, Tailles & FAQ", callback_data="info_menu")],
        [InlineKeyboardButton("💬 Contacter le Support & Avis", callback_data="support_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")


# 2. Gestionnaire des clics sur les boutons (Sous-menus propres)
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back":
        await start(update, context)

    elif data == "info_menu":
        text = "📌 **Centre d'Aide & Informations**\n\nChoisis une rubrique :"
        kbd = [
            [InlineKeyboardButton("📏 Guide des tailles", callback_data="size_guide")],
            [InlineKeyboardButton("🚚 Suivi des colis (Colissimo)", callback_data="track_parcel")],
            [InlineKeyboardButton("❓ FAQ : Délais & Sécurité", callback_data="faq_main")],
            [InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "size_guide":
        text = "📏 **Guide des tailles :**\n\nNos articles taillent généralement normalement. Si tu hésites entre deux tailles, nous te conseillons de prendre la taille au-dessus pour un effet fit, ou deux pour un effet oversize."
        kbd = [[InlineKeyboardButton("🔙 Retour", callback_data="info_menu")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "track_parcel":
        text = "🚚 **Suivi des colis :**\n\nToutes nos expéditions se font en Colissimo avec suivi sous 48h maximum. Tu recevras ton numéro de suivi directement après validation."
        kbd = [[InlineKeyboardButton("🔙 Retour", callback_data="info_menu")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "faq_main":
        text = "❓ **Foire Aux Questions (FAQ)**"
        kbd = [
            [InlineKeyboardButton("⏱️ Quels sont vos délais d'envoi ?", callback_data="faq_1")],
            [InlineKeyboardButton("🔒 Le paiement est-il sécurisé ?", callback_data="faq_2")],
            [InlineKeyboardButton("🔙 Retour", callback_data="info_menu")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "faq_1":
        text = "⏱️ **Délais :** Tous nos envois partent en 48h maximum via Colissimo."
        kbd = [[InlineKeyboardButton("🔙 Retour FAQ", callback_data="faq_main")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "faq_2":
        text = "🔒 **Sécurité :** Oui, 100% via Stripe. Nous n'avons jamais accès à tes coordonnées bancaires."
        kbd = [[InlineKeyboardButton("🔙 Retour FAQ", callback_data="faq_main")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "support_menu":
        text = "💬 **Support Client & Avis**\n\nUne question spécifique ? Envoie-nous un message directement ici dans le chat, notre IA ou notre équipe te répondra instantanément !"
        kbd = [[InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")

    elif data == "promo_contest":
        text = "🎁 **Concours & Codes Promo**\n\nSuis bien le canal principal pour ne rater aucun drop de codes promo ou de concours exclusifs !"
        kbd = [[InlineKeyboardButton("🔙 Retour au menu", callback_data="back")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")


# 3. Le Cerveau IA (Groq) pour répondre aux messages libres des clients
async def handle_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    
    # Consigne de comportement pour l'IA
    system_prompt = (
        "Tu es l'assistant virtuel intelligent de 'IDF Running // V.I.P', une boutique de revente de streetwear et vêtements exclusifs. "
        "Tu es amical, direct, et tu aides les clients pour leurs questions sur les tailles (S, M, L, XL), "
        "les envois en Colissimo, et les paiements sécurisés via Stripe. "
        "Reste concis et professionnel dans tes réponses."
    )

    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=150
        )
        ai_reply = completion.choices[0].message.content
        await update.message.reply_text(ai_reply)
    except Exception as e:
        await update.message.reply_text("Oups, j'ai un petit souci technique. Utilise les boutons du menu ou contacte le support !")


# 4. Lancement du Bot
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Gestionnaires de commandes et boutons
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Gestionnaire de texte libre (Propulsé par l'IA Groq)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_chat))

    print("🤖 Bot démarré avec succès et connecté à l'IA Groq !")
    app.run_polling()

if __name__ == "__main__":
    main()
