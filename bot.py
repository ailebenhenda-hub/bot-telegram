import logging
import os
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from openai import OpenAI

# Configuration des logs
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Tes clés et variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_GROUP_ID = -5313705184
CANAL_TELEGRAM_URL = "https://t.me/idfrunningvip"
ADMIN_USER_PSEUDO = "@idf_runningshop"
VINTED_PROFILE_URL = "https://www.vinted.fr/member/idf_runningshop"
GROUPE_AVIS_URL = "https://t.me/+q2HRbe-dBydlZWZk" # Lien de ton groupe d'avis

client_groq = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# CATALOGUE COMPLET
CATALOGUE_TEXTE = """
Voici les pépites 100% AUTHENTIQUES chez IDF Running // V.I.P :
- T-shirt Nike Trail (Gris clair / Bleu glacier) | Taille: M | État: Excellent | 40€
- T-shirt Nike Running Division (Noir à motifs) | Taille: M | État: Excellent | 35€
- T-shirt Nike Dri-Fit (Rouge) | Taille: M | État: Excellent | 30€
- Pantalon Nike Phenom Elite (Noir) | Taille: M | État: Excellent | 90€
- Pantalon Nike Aeroswift (Noir) | Taille: M | État: Excellent | 75€
- Pantalon Nike Phenom Elite Poche Noir (Noir) | Taille: S | État: 8/10 | 80€
- Pantalon Nike Phenom Elite (Gris) | Taille: L | État: Excellent | 90€
- Sweat Nike Tech Aviateur v1 (Gris chiné) | Taille: M | État: Excellent | 60€
- Sweat Nike Tech Fleece (Noir classique) | Taille: S | État: Excellent | 70€
- Pantalon Nike Trail (Noir) | Taille: S | État: 8/10 (petite égratignure genou) | 60€
"""

# Le cerveau du bot mis à jour avec le lien des avis pour rassurance
SYSTEM_PROMPT = (
    f"Tu es l'assistant virtuel de 'IDF Running // V.I.P'.\n"
    f"Voici le catalogue dispo :\n{CATALOGUE_TEXTE}\n\n"
    f"Lien des avis clients à donner en cas de doute ou d'hésitation : {GROUPE_AVIS_URL}\n\n"
    "Règles strictes :\n"
    "1. RASSURANCE ANTI-DOUTE : Si le client doute de l'authenticité, a peur des arnaques ou hésite à commander, envoie-lui toujours le lien du groupe d'avis ({GROUPE_AVIS_URL}) en lui disant qu'il peut voir tous les retours des anciens acheteurs.\n"
    "2. LÉGIT CHECK VARIÉ : Varie les tournures : 'Zéro doute frérot, 100% legit', 'Tu peux y aller les yeux fermés, que du vrai propre pour porter ça en léger'.\n"
    "3. URGENCE & ATTENTE : Si le client s'impatiente, dis-lui : 'Le boss prépare les colis, il arrive en DM. Tu cherches plutôt haut ou bas ?'\n"
    "4. FILTRE DE TAILLE : S'il donne sa taille, liste UNIQUEMENT les articles dispo dans cette taille.\n"
    "5. CROSS-SELLING / LOTS : S'il s'intéresse à un article, propose une autre pièce en rappelant la réduction de -5€.\n"
    "6. TON : Street, naturel, vendeur pro, sans 'le flex' (utilise 'propre', 'lourd')."
)

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📦 Voir le Stock"), KeyboardButton("🔥 Nouveautés / Infos")],
        [KeyboardButton("⭐ Voir les Avis Clients"), KeyboardButton("❓ FAQ & Livraison")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_checkout_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("🛍️ Passer par Vinted", callback_data="pay_vinted")],
        [InlineKeyboardButton("🤝 Remise en main propre (IDF)", callback_data="pay_hand")],
        [InlineKeyboardButton("📦 Par la Poste (Colissimo + RIB)", callback_data="pay_colissimo")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        f"👋 Salut {update.effective_user.first_name} !\n\n"
        "Bienvenue chez IDF Running // V.I.P 🏃‍♂️💨\n\n"
        "Zéro fake, zéro douille. Regarde les avis si tu as des doutes, ou balance ta taille !"
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

async def handle_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    text = update.message.text.lower()
    user = update.effective_user

    # FAQ et boutons du clavier permanent
    if any(w in text for w in ["livraison", "expedie", "envoi"]):
        await update.message.reply_text(f"📦 Expédition rapide et soignée ! Tu peux checker les retours ici : {GROUPE_AVIS_URL}", reply_markup=get_main_keyboard())
        return
    elif any(w in text for w in ["paiement", "payer", "carte", "rib"]):
        await update.message.reply_text("💳 Tu peux régler par Vinted, virement sur mon RIB Revolut, ou en espèces en main propre.", reply_markup=get_main_keyboard())
        return
    elif text == "📦 voir le stock":
        await update.message.reply_text(f"📦 **Catalogue dispo :**\n\n{CATALOGUE_TEXTE}", reply_markup=get_main_keyboard())
        return
    elif text == "🔥 nouveautés / infos":
        await update.message.reply_text(f"🚀 Visuels & drops ici : {CANAL_TELEGRAM_URL}", reply_markup=get_main_keyboard())
        return
    elif text == "⭐ voir les avis clients":
        await update.message.reply_text(f"⭐ Viens jeter un œil aux retours de tous nos clients validés ici : {GROUPE_AVIS_URL}", reply_markup=get_main_keyboard())
        return
    elif text == "❓ faq & livraison":
        await update.message.reply_text(f"❓ **FAQ :**\n• 100% réel (garantie)\n• Regarde les avis des clients : {GROUPE_AVIS_URL}\n• Lot : -5€ sur le total !", reply_markup=get_main_keyboard())
        return

    # Si le client veut acheter
    if any(w in text for w in ["je prends", "je veux", "acheter", "commande", "interesse"]):
        buy_prompt = f"Carré ! Pour que tu commandes en toute confiance (tu peux voir nos retours ici : {GROUPE_AVIS_URL}), choisis ton mode de livraison et de paiement ci-dessous :"
        await update.message.reply_text(buy_prompt, reply_markup=get_checkout_inline_keyboard())
        return

    # Envoi à l'IA Groq
    try:
        response = client_groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": update.message.text}
            ]
        )
        bot_reply = response.choices[0].message.content

        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"💬 [Suivi Client] @{user.username or user.first_name} : {update.message.text}")
        await update.message.reply_text(bot_reply, reply_markup=get_main_keyboard())

    except Exception as e:
        logging.error(f"Erreur technique : {e}")
        await update.message.reply_text(f"Désolé, petit souci technique. Regarde nos avis ici en attendant : {GROUPE_AVIS_URL}", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if query.data == "pay_vinted":
        text_vinted = (
            f"🛍️ **Option Vinted (100% sécurisé) :**\n\n"
            f"Rends-toi sur mon profil Vinted : {VINTED_PROFILE_URL}\n"
            f"(Et si tu veux voir les retours des autres acheteurs : {GROUPE_AVIS_URL})"
        )
        await query.message.reply_text(text_vinted)
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"🔔 @{user.username or user.first_name} a choisi **Vinted** !")

    elif query.data == "pay_hand":
        text_hand = (
            f"🤝 **Option Remise en main propre (IDF) :**\n\n"
            f"Impec ! Écris-moi tes dispos et ta ville en Île-de-France.\n"
            f"(Tu peux aussi checker nos avis ici : {GROUPE_AVIS_URL})"
        )
        await query.message.reply_text(text_hand)
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"🚨 @{user.username or user.first_name} veut une **Remise en main propre** !")

    elif query.data == "pay_colissimo":
        text_colissimo = (
            f"📦 **Option Colissimo / Virement :**\n\n"
            f"Si tu as le moindre doute, va jeter un œil à nos retours clients ici : {GROUPE_AVIS_URL}\n\n"
            f"Voici mon RIB Revolut pour le virement :\n"
            f"🏦 **Revolut** | 📋 **IBAN :** `FR76 2823 3000 0156 5721 3968 757` | 🔤 **BIC :** `REVOFRP2`"
        )
        await query.message.reply_text(text_colissimo)
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"🚨 @{user.username or user.first_name} a choisi **Colissimo (RIB envoyé)** !")

def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_conversation))
    application.run_polling()

if __name__ == '__main__':
    main()
