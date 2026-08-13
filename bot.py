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

client_groq = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# CATALOGUE COMPLET (Prix, tailles, états)
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

# Le cerveau du bot : IA programmée pour la vente humaine, street et naturelle
SYSTEM_PROMPT = (
    f"Tu es l'assistant virtuel de 'IDF Running // V.I.P'.\n"
    f"Voici le catalogue dispo :\n{CATALOGUE_TEXTE}\n\n"
    "Règles strictes :\n"
    "1. LÉGIT CHECK VARIÉ : Si on doute de l'authenticité, ne dis pas toujours la même phrase. Varie avec des tournures comme : 'Zéro doute frérot, 100% legit, garantie à vie ou remboursé x2', 'Tu peux y aller les yeux fermés, que du vrai propre pour porter ça en léger', ou 'Pas de fake ici, tout est clean'.\n"
    "2. URGENCE & ANTI-ENERVEMENT : Si le client s'impatiente ou si tu gères l'attente, dis-lui : 'Le boss est en train de préparer les colis du jour, il arrive en DM très vite. En attendant, tu cherches plutôt du haut ou du bas ? J'ai peut-être une autre pépite qui pourrait t'intéresser...'\n"
    "3. FILTRE DE TAILLE : S'il donne sa taille (ex: M), liste UNIQUEMENT les articles disponibles dans cette taille.\n"
    "4. CROSS-SELLING / LOTS : S'il s'intéresse à un article, propose-lui subtilement une autre pièce assortie en lui rappelant que ça lui fera une réduction de -5€ sur le total global.\n"
    "5. PRODUIT MYSTÈRE : S'il ne sait pas quoi choisir, utilise cette vibe : 'Tu as du mal à te décider ? Donne ton budget ou ton style, et je te sors l'article qui te régalera.'\n"
    "6. CLOSING : S'il est chaud pour acheter un article, dis-lui de choisir son mode de livraison/paiement via les boutons interactifs ou propose-lui directement les options (Vinted, Main propre, Colissimo).\n"
    "7. TON : Street, naturel, vendeur pro, sans utiliser 'le flex' (utilise plutôt 'pour porter ça en léger', 'propre', 'lourd')."
)

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📦 Voir le Stock"), KeyboardButton("🔥 Nouveautés / Infos")],
        [KeyboardButton("🎁 Parrainage VIP"), KeyboardButton("❓ FAQ & Livraison")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Clavier interactif (Boutons sous le message pour choisir le mode d'achat)
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
        "Zéro fake, zéro douille. Utilise les boutons ci-dessous ou balance direct ta taille !"
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

async def handle_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    text = update.message.text.lower()
    user = update.effective_user

    # FAQ Instantanée / Mots-clés
    if any(w in text for w in ["livraison", "expedie", "envoi"]):
        await update.message.reply_text("📦 Expédition rapide et soignée, ou dispo en main propre en Île-de-France !", reply_markup=get_main_keyboard())
        return
    elif any(w in text for w in ["paiement", "payer", "carte", "rib"]):
        await update.message.reply_text("💳 Tu peux régler par Vinted, virement sur mon RIB Revolut, ou en espèces lors d'une remise en main propre.", reply_markup=get_main_keyboard())
        return
    elif text == "📦 voir le stock":
        await update.message.reply_text(f"📦 **Catalogue dispo :**\n\n{CATALOGUE_TEXTE}", reply_markup=get_main_keyboard())
        return
    elif text == "🔥 nouveautés / infos":
        await update.message.reply_text(f"🚀 Visuels & drops ici : {CANAL_TELEGRAM_URL}", reply_markup=get_main_keyboard())
        return
    elif text == "🎁 parrainage vip":
        await update.message.reply_text(f"🎁 2 parrainages = -10€ ! Preuves en DM sur {ADMIN_USER_PSEUDO}.", reply_markup=get_main_keyboard())
        return
    elif text == "❓ faq & livraison":
        await update.message.reply_text("❓ **FAQ :**\n• 100% réel (garantie x2)\n• Options : Vinted, Colissimo ou Main propre\n• Lot : -5€ sur le total !", reply_markup=get_main_keyboard())
        return

    # Si le client veut acheter ou commande un article, on lui propose les options de paiement cliquables
    if any(w in text for w in ["je prends", "je veux", "acheter", "commande", "interesse"]):
        buy_prompt = "Carré ! Choisis ton mode de livraison et de paiement préféré ci-dessous :"
        await update.message.reply_text(buy_prompt, reply_markup=get_checkout_inline_keyboard())
        return

    # Envoi de la question à l'IA Groq
    try:
        response = client_groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": update.message.text}
            ]
        )
        bot_reply = response.choices[0].message.content

        # Tracking pour le groupe admin
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"💬 [Suivi Client] @{user.username or user.first_name} : {update.message.text}")
        
        await update.message.reply_text(bot_reply, reply_markup=get_main_keyboard())

    except Exception as e:
        logging.error(f"Erreur technique : {e}")
        await update.message.reply_text("Désolé, petit souci technique. Le boss arrive en DM !", reply_markup=get_main_keyboard())

# Gestion des clics sur les boutons de paiement (Vinted, Main propre, Colissimo)
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if query.data == "pay_vinted":
        text_vinted = (
            f"🛍️ **Option Vinted sélectionnée :**\n\n"
            f"Rends-toi directement sur mon profil Vinted sécurisé : {VINTED_PROFILE_URL}\n\n"
            f"Envoie-moi un message directement là-bas sur l'article concerné pour qu'on valide la transaction en toute sécurité !"
        )
        await query.message.reply_text(text_vinted)
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"🔔 @{user.username or user.first_name} a choisi l'option **Vinted** !")

    elif query.data == "pay_hand":
        text_hand = (
            f"🤝 **Option Remise en main propre (IDF) :**\n\n"
            f"Impec ! Écris-moi tes disponibilités (jours/horaires) et ta ville/secteur en Île-de-France pour qu'on s'organise un rdv rapide."
        )
        await query.message.reply_text(text_hand)
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"🚨 @{user.username or user.first_name} veut une **Remise en main propre** ! Viens voir ses dispos.")

    elif query.data == "pay_colissimo":
        text_colissimo = (
            f"📦 **Option Colissimo / Virement Bancaire :**\n\n"
            f"Voici mon RIB Revolut pour effectuer le virement (envoie-moi la capture d'écran du paiement en DM une fois fait) :\n\n"
            f"🏦 **Banque :** Revolut Bank UAB\n"
            f"📋 **IBAN :** `FR76 2823 3000 0156 5721 3968 757`\n"
            f"🔤 **BIC :** `REVOFRP2`\n\n"
            f"N'oublie pas de m'envoyer ton nom, ton prénom et ton adresse complète de livraison par message !"
        )
        await query.message.reply_text(text_colissimo)
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"🚨 @{user.username or user.first_name} a choisi **Colissimo (RIB envoyé)** ! Prépare-toi à valider son paiement.")

def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_conversation))
    application.run_polling()

if __name__ == '__main__':
    main()
