import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
from openai import OpenAI

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TELEGRAM_TOKEN = ""
OPENAI_API_KEY = ""   
ADMIN_GROUP_ID = -1001234567890           
CANAL_TELEGRAM_URL = "https://t.me/idfrunningvip"
ADMIN_USER_PSEUDO = "@idf_runningshop"    

client_openai = OpenAI(api_key=OPENAI_API_KEY)

CATALOGUE_TEXTE = """
Voici la liste officielle des stocks 100% AUTHENTIQUES disponibles chez IDF Running // V.I.P avec leurs tailles et états :
- Nike t-shirt vert | Taille: M | État: 10/10
- Nike short bleu/gris | Taille: M | État: 9/10
- Nike short blanc | Taille: L | État: 10/10
- Nike t-shirt gris | Taille: S | État: 9/10
- Nike short rose | Taille: M | État: 10/10
- Nike aviateur v1 gris | Taille: M | État: 9/10
- Nike t-shirt os | Taille: XL | État: 10/10
- Nike t-shirt rose | Taille: S | État: 9/10
- Nike short noir | Taille: L & XS | État: 10/10
- Nike t-shirt bleu | Taille: S & M | État: 9/10
- Nike t-shirt trail noir | Taille: L | État: 10/10
- Nike t-shirt trail gris | Taille: L | État: 9/10
- Nike short noir lacet full noir | Taille: S | État: 10/10
- Nike short noir nike penché | Taille: M | État: 9/10
- Nike short bleu nike penché | Taille: M | État: 10/10
- Nike short gris nike penché | Taille: S | État: 9/10
- Nike pants phenom elite poche noir | Taille: S | État: 9/10
- Nike veste x kelly anna | Taille: L | État: 10/10
- Nike short x kelly anna | Taille: L | État: 9/10
- Nike veste chinese dragon | Taille: M | État: 10/10 (Collector rare)
- Nike kangourou noir | Taille: S | État: 10/10
- Nike aviateur v2 gris | Taille: L | État: 9/10
- Nike pull tech noir | Taille: S | État: 10/10
- Nike t-shirt trail bleu clair | Taille: S | État: 9/10
- Nike t-shirt rouge | Taille: S | État: 10/10
- Nike t-shirt noir reflet doré | Taille: M | État: 9/10
- Nike pants phenom elite noir | Taille: S, L, M | État: 10/10
- Nike pants phenom elite gris | Taille: L | État: 9/10
- Nike pants trail noir | Taille: S | État: 7/10 (Attention : petite égratignure au genou, vidéo dispo sur demande)
- Nike pants trail noir | Taille: L | État: 10/10 (Impeccable, neuf)
- Nike veste trail rouge et bleu | Taille: S | État: 10/10
- Nike pull trail blanc | Taille: L | État: 9/10
- Nike pants aeroswift | Taille: M | État: 10/10
- Nike pants tempo noir et gris | Taille: L | État: 10/10
- Nike mont blanc marron | Taille: M | État: 9/10
"""

SYSTEM_PROMPT = (
    f"Tu es l'assistant virtuel ultra-pro de 'IDF Running // V.I.P', le shop élite du textile running et trail 100% AUTHENTIQUE.\n"
    f"Voici le catalogue officiel avec des états variés (9/10 et 10/10).\n"
    f"Les prix ne sont pas gérés par le bot.\n{CATALOGUE_TEXTE}\n\n"
    "Règles strictes et arguments massues pour tes réponses :\n"
    "1. Affiche une confiance absolue : garantie authenticité à vie ou remboursé x2 (zéro fake, zéro douille).\n"
    "2. Rappelle la philosophie du shop : ici les tenues ne sont pas faites pour courir sous la pluie, mais pour flex ! Encourage les clients à balancer des photos portées et à identifier le shop.\n"
    "3. Mentionne le système de Parrainage VIP : -10€ de réduction si le client parraine 2 personnes qui rejoignent le canal (le client doit envoyer les captures d'écran de preuve directement en DM sur ton compte perso " + ADMIN_USER_PSEUDO + ").\n"
    "4. Parle des arrivages exclusifs et des pièces uniques annoncées sur le canal : " + CANAL_TELEGRAM_URL + "\n"
    "5. Si un client demande le prix d'un article ou veut voir les visuels, invite-le à consulter directement le canal.\n"
    "6. Donne la taille disponible et l'état exact pour chaque article demandé (avec transparence sur le pantalon trail S à 7/10 éraflé vs le L à 10/10 impeccable).\n"
    "7. Rappelle la promo sur les lots : -5€ par article dès qu'on en prend plusieurs.\n"
    "8. Crée un léger sentiment d'urgence : les stocks bougent vite, il ne faut pas traîner quand une pièce plaît.\n"
    "9. Explique la logistique pro : Main propre (Gare du Nord / IDF), Vinted, ou envois directs (Mondial Relay / Colissimo) avec expédition éclair garantie le jour même si validé avant 14h.\n"
    "10. Si le client veut valider ou acheter, indique-lui qu'un membre de l'équipe (Moha ou Salim) prend le relais immédiatement pour finaliser.\n"
    "11. Utilise un ton de vendeur pro, dominant, honnête, ultra-proche de sa communauté."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 Salut {user.first_name} !\n\n"
        "⚡ **Bienvenue chez IDF Running // V.I.P** 🏃‍♂️💨\n\n"
        "💎 **Le shop élite.** Ici, on le sait : les pépites ne sont pas faites pour courir, mais pour **flex** proprement. Zéro fake, zéro douille : garantie authenticité à vie (ou remboursé x2). Retrouve tous les prix et visuels sur notre [canal officiel]({CANAL_TELEGRAM_URL}).\n\n"
        "🔥 **Avantages exclusifs & Bons Plans :**\n"
        "• **Promo de groupe :** -5€ par article dès que tu en prends plusieurs !\n"
        "• **Parrainage VIP :** 2 personnes parrainées qui rejoignent le canal = **-10€ de réduction** (envoie les preuves des abonnés en DM sur ton compte perso " + ADMIN_USER_PSEUDO + ") !\n"
        "• **Expédition Éclair :** Colis envoyé le jour même si validé avant 14h.\n"
        "📸 **Le Flex :** Envoie-nous tes meilleures photos porté une fois l'outfit reçu !\n\n"
        "📦 Remise en main propre (Gare du Nord / IDF), Vinted, ou envois directs (Mondial Relay / Colissimo).\n\n"
        "Balance ta taille ou le modèle recherché !"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown", disable_web_page_preview=True)

async def handle_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    
    if message.chat.id == ADMIN_GROUP_ID:
        return

    user_message = message.text

    alert_client = (
        f"💬 **Client @{user.username if user.username else user.first_name}** (`{user.id}`):\n"
        f"\"{user_message}\""
    )
    await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=alert_client, parse_mode="Markdown")

    try:
        response = client_openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
        )
        bot_reply = response.choices[0].message.content
    except Exception as e:
        bot_reply = "Yo, petit souci technique mais l'équipe a bien reçu ton message et revient vers toi direct !"

    await message.reply_text(bot_reply, parse_mode="Markdown", disable_web_page_preview=True)

    alert_bot = f"🤖 *Réponse du bot :*\n\"{bot_reply}\""
    await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=alert_bot, parse_mode="Markdown")

def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND) & filters.ChatType.PRIVATE, handle_conversation))

    print("Le bot IDF Running V.I.P version flex est en ligne !")
    application.run_polling()

if __name__ == '__main__':
    main()