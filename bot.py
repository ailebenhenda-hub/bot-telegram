import logging
import os
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from openai import OpenAI

# Configuration des logs
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- TES PARAMÈTRES ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("OPENAI_API_KEY") 
ADMIN_GROUP_ID = -5313705184 # ID de ton groupe admin actuel
CANAL_TELEGRAM_URL = "https://t.me/idfrunningvip"
GROUPE_AVIS_URL = "https://t.me/+q2HRbe-dBydlZWZk"
VINTED_PROFILE_URL = "https://www.vinted.fr/member/idf_runningshop"

client_groq = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

# --- CATALOGUE DES ARTICLES ---
CATALOGUE_ARTICLES = [
    {"id": 1, "nom": "T-shirt Nike Trail (Gris/Bleu)", "taille": "M", "prix": 40},
    {"id": 2, "nom": "T-shirt Nike Running Division", "taille": "M", "prix": 35},
    {"id": 3, "nom": "T-shirt Nike Dri-Fit (Rouge)", "taille": "M", "prix": 30},
    {"id": 4, "nom": "Pantalon Nike Phenom Elite (Noir)", "taille": "M", "prix": 90},
    {"id": 5, "nom": "Pantalon Nike Aeroswift", "taille": "M", "prix": 75},
    {"id": 6, "nom": "Pantalon Nike Phenom Elite (S)", "taille": "S", "prix": 80},
    {"id": 7, "nom": "Pantalon Nike Phenom Elite (Gris)", "taille": "L", "prix": 90},
    {"id": 8, "nom": "Sweat Nike Tech Aviateur v1", "taille": "M", "prix": 60},
    {"id": 9, "nom": "Sweat Nike Tech Fleece (Noir)", "taille": "S", "prix": 70},
    {"id": 10, "nom": "Pantalon Nike Trail (Noir)", "taille": "S", "prix": 60}
]

def generer_texte_catalogue():
    texte = "📦 **CATALOGUE DISPO EN TEMPS RÉEL :**\n\n"
    for item in CATALOGUE_ARTICLES:
        texte += f"#{item['id']} - {item['nom']} | Taille: {item['taille']} | {item['prix']}€\n"
    texte += "\n👉 *Envoie simplement le numéro (ex: #4) pour commander.*"
    return texte

# --- CLAVIERS ---
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📦 Voir le catalogue"), KeyboardButton("🔔 S'abonner aux alertes")],
        [KeyboardButton("💬 Parler au vendeur"), KeyboardButton("⭐ Voir les avis")]
    ], resize_keyboard=True)

def get_checkout_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍️ Vinted (100% sécurisé)", callback_data="pay_vinted")],
        [InlineKeyboardButton("🤝 Remise en main propre (IDF)", callback_data="pay_hand")],
        [InlineKeyboardButton("📦 Envoi Colissimo", callback_data="pay_colissimo")]
    ])

# --- GESTION DES COMMANDES ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        f"👋 Salut {update.effective_user.first_name} ! Bienvenue chez **IDF Running // V.I.P** 🏃‍♂️💨\n\n"
        "Ici, tu trouveras les meilleures pièces en exclu. Que souhaites-tu faire ?"
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(), parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    if query.data == "pay_vinted":
        await query.message.reply_text(f"🛍️ Rends-toi sur mon profil Vinted pour commander : {VINTED_PROFILE_URL}")
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"🛍️ @{user.username or user.first_name} a choisi de payer via **Vinted** !")
    elif query.data == "pay_hand":
        await query.message.reply_text("🤝 Impec ! Dis-moi ta ville et tes disponibilités en IDF pour organiser ça.")
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"🤝 @{user.username or user.first_name} veut une **Remise en main propre** !")
    elif query.data == "pay_colissimo":
        await query.message.reply_text("📦 Pour un envoi, envoie-moi ton adresse complète et ton mode de paiement préféré en MP.")
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"📦 @{user.username or user.first_name} veut un **Envoi Colissimo** !")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    user = update.effective_user
    
    # Navigation principale
    if "catalogue" in text:
        await update.message.reply_text(generer_texte_catalogue(), parse_mode='Markdown')
    
    elif "parler au vendeur" in text:
        await update.message.reply_text("💬 Envoie-moi ta question ou une capture d'écran, je te réponds dès que possible !")
    
    elif "avis" in text:
        await update.message.reply_text(f"⭐ Viens voir les retours de la commu ici : {GROUPE_AVIS_URL}")
    
    elif "alerte" in text:
        await update.message.reply_text("🔔 Tu es inscrit aux alertes ! Je te préviens dès qu'une nouveauté arrive.")

    # Achat rapide par ID (ex: #4 ou 4)
    elif text.strip().replace("#", "").isdigit():
        id_cherche = int(text.strip().replace("#", ""))
        article = next((item for item in CATALOGUE_ARTICLES if item["id"] == id_cherche), None)
        
        if article:
            await update.message.reply_text(
                f"✅ **{article['nom']}** sélectionné !\nComment souhaites-tu régler ?",
                reply_markup=get_checkout_inline_keyboard()
            )
            await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"🔥 @{user.username or user.first_name} s'intéresse à l'article **#{article['id']} - {article['nom']}** !")
        else:
            await update.message.reply_text("❌ Article non trouvé. Vérifie le numéro dans le catalogue !")

    # Discussion avec l'IA pour tout le reste
    else:
        try:
            response = client_groq.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": f"Tu es l'assistant de la boutique IDF Running. Réponds de façon courte, pro et naturelle. Si le client doute ou pose des questions sur l'authenticité, donne toujours le lien des avis : {GROUPE_AVIS_URL}"},
                    {"role": "user", "content": update.message.text}
                ]
            )
            bot_reply = response.choices[0].message.content
            await update.message.reply_text(bot_reply)
            
            # Transfert direct au groupe admin
            await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"💬 @{user.username or user.first_name} : {update.message.text}")
        except Exception as e:
            logging.error(f"Erreur IA : {e}")
            await update.message.reply_text("Petit souci technique, je reviens vers toi très vite !")

def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.run_polling()

if __name__ == '__main__':
    main()
