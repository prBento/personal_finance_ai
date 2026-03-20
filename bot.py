import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# 1. Carrega as senhas
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# 2. Define a resposta para o comando /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    boas_vindas = (
        "Olá! Sou seu Assistente Financeiro de IA. 📊🤖\n\n"
        "Você pode me mandar coisas como:\n"
        "- 'Comprei um pão por 5 reais na padaria'\n"
        "- Ou o link de uma nota fiscal (NFC-e)\n\n"
        "Estou pronto para registrar!"
    )
    await update.message.reply_text(boas_vindas)

# 3. Define o que ele faz ao receber qualquer texto
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_recebido = update.message.text

    reposta_temporaria = f"Anotado! Recebi a seguinte mensagem: '{texto_recebido}'.\n\n(A integração com a IA virá em breve!)"

    await update.message.reply_text(reposta_temporaria)


# 4. Inicia o servidor do bot (Long Polling)
if __name__ == '__main__':
    print("Iniciando o bot... Pressione Ctrl+C no terminal para parar.")

    # Constrói a aplicaçã com seu token
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Configura as "rotas" (handlers) do bot
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()