import logging
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
from openai import OpenAI

# Configuration des logs
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Variables d'environnement
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# La clé est récupérée en toute sécurité depuis les variables d'environnement de Railway
GROQ_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_GROUP_ID = -5313705184

CANAL_TELEGRAM_URL = "https://t.me/idfrunningvip"
ADMIN_USER_PSEUDO = "@idf_runningshop"    

# Configuration du client OpenAI pointant vers l'API gratuite de Groq
client_groq = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

CATALOGUE_TEXTE = """
Voici la liste des stocks 100% AUTHENTIQUES chez IDF Running // V.I.P :
- Nike t-shirt vert | Taille: M
- Nike short bleu/gris | Taille: M
- Nike short blanc | Taille: L
- Nike t-shirt gris | Taille: S
- Nike short rose | Taille: M
- Nike aviateur v1 gris | Taille: M
- Nike t-shirt os | Taille: XL
- Nike t-shirt rose | Taille: S
- Nike short noir | Taille: L & XS
- Nike t-shirt bleu | Taille: S & M
- Nike t-shirt trail noir | Taille: L
- Nike t-shirt trail gris | Taille: L
- Nike short noir lacet full noir | Taille: S
- Nike short noir nike penché | Taille: M
- Nike short bleu nike penché | Taille: M
- Nike short gris nike penché | Taille: S
- Nike pants phenom elite noir | Taille: S, L, M
- Nike pants phenom elite gris | Taille: L
- Nike veste x kelly anna | Taille: L
- Nike veste chinese dragon | Taille: M
- Nike pull tech noir | Taille: S
- Nike pants aeroswift | Taille: M
- Nike pull trail blanc | Taille: L
"""

SYSTEM_PROMPT = (
    f"Tu es l'assistant virtuel ultra-pro de 'IDF Running // V.I.P'. "
    f"Voici le catalogue : {CATALOGUE_TEXTE}\n"
    "Règles : \n"
    "1. Garantie authenticité à vie ou remboursé x2.\n"
    "2. Rappelle que c'est pour le 'flex' plus que pour courir.\n"
    "3. Parrainage VIP : 2 pers = -10€ (Preuves en DM sur " + ADMIN_USER_PSEUDO + ").\n"
    "4. Canal officiel : " + CANAL_TELEGRAM_URL + "\n"
    "5. Promo lot : -5€ par article en plus.\n"
    "6. Expédition éclair avant 14h.\n"
    "7. Ton, vendeur pro, dominant, honnête, ultra-proche."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 Salut {user.first_name} !\n\n"
        "Bienvenue chez IDF Running // V.I.P 🏃‍♂️💨\n\n"
        "Zéro fake, zéro douille. Retrouve tous les visuels sur notre canal officiel : " + CANAL_TELEGRAM_URL + "\n\n"
        "• Promo de groupe : -5€ par article si tu en prends plusieurs !\n"
        "• Parrainage VIP : 2 personnes parrainées = -10€ (envoie les preuves en DM sur " + ADMIN_USER_PSEUDO + ") !\n\n"
        "Balance ta taille ou le modèle recherché, je te dis si ça flex !"
    )
    await update.message.reply_text(welcome_text, disable_web_page_preview=True)

async def handle_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    user_message = message.text

    # 1. Envoi au groupe Admin
    try:
        alert_text = f"💬 @{user.username if user.username else user.first_name} a demandé : \"{user_message}\""
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=alert_text)
    except Exception as e:
        logging.error(f"Erreur envoi admin : {e}")

    # 2. Réponse de l'IA (via Groq et Llama 3)
    try:
        response = client_groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
        )
        bot_reply = response.choices[0].message.content
    except Exception as e:
        logging.error(f"Erreur Groq : {e}")
        bot_reply = "Désolé, petit souci technique. L'équipe arrive en DM !"

    await message.reply_text(bot_reply, disable_web_page_preview=True)

def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND) & filters.ChatType.PRIVATE, handle_conversation))
    application.run_polling()

if __name__ == '__main__':
    main()
