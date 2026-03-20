import os
import json
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# 1. Carrega as chaves
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Inicializa o Client da IA
groq_client = Groq(api_key=GROQ_API_KEY)

# 2. Define a resposta para o comando /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Sou seu Assistente Financeiro Inteligente. 📊🧠\nMe mande um gasto em texto livre (ex: 'Comprei um tênis por 500 em 5x no cartão') e eu estruturo pra você!")

# 3. Define o que ele faz ao receber qualquer texto
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_recebido = update.message.text
    mensagem_espera = await update.message.reply_text("Processando com Inteligência Artificial... 🧠")

    today = datetime.now()
    data_formatada = today.strftime("%d/%m/%Y")

    SYSTEM_PROMPT = f"""
    Você é um extrator de dados financeiros altamente preciso.
    Hoje é {data_formatada}. Seu ÚNICO objetivo é ler o texto do usuário e extrair os dados da despesa.

    REGRAS RÍGIDAS:
    1. Retorne APENAS um objeto JSON válido. Nada de texto antes ou depois.
    2. O JSON deve seguir EXATAMENTE esta estrutura:
       - "item": Nome do que foi comprado.
       - "valor_total": (float) Valor total. Use ponto.
       - "categoria_macro": Escolha entre [Alimentação, Transporte, Moradia, Lazer, Saúde, Educação, Compras, Serviços, Outros].
       - "categoria_detalhada": Seja específico (ex: Restaurante, Combustível, Roupas, Eletrônicos, Streaming, etc).
       - "metodo_pagamento": [Dinheiro, Cartão de Crédito, Cartão de Débito, Pix, Desconhecido].
       - "parcelado": (boolean) true se foi parcelado, false se à vista.
       - "quantidade_parcelas": (int) Número de parcelas (1 se à vista).
       - "valor_parcela": (float) Valor de cada parcela.
       - "meses_parcelas": (lista de strings) Se parcelado, calcule e liste os meses exatos das parcelas no formato "MM/YYYY" começando do mês atual ({data_formatada}). Se não for parcelado, retorne uma lista vazia [].

    Exemplo de compra parcelada:
    {{
      "item": "Geladeira",
      "valor_total": 3000.00,
      "categoria_macro": "Moradia",
      "categoria_detalhada": "Eletrodomésticos",
      "metodo_pagamento": "Cartão de Crédito",
      "parcelado": true,
      "quantidade_parcelas": 3,
      "valor_parcela": 1000.00,
      "meses_parcelas": ["{today.strftime('%m/%Y')}", "{(today.month%12)+1:02d}/{today.year + (today.month//12)}", "{(today.month+1)%12+1:02d}/{today.year + ((today.month+1)//12)}"]
    }}
    """

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": texto_recebido}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.0,
        )

        resposta_ia = chat_completion.choices[0].message.content
        dados_json = json.loads(resposta_ia)
        resposta_formatada = json.dumps(dados_json, indent=2, ensure_ascii=False)

        await mensagem_espera.edit_text(
            f"✅ **Extração Concluída:**\n```json\n{resposta_formatada}\n```", 
            parse_mode="Markdown"
        )

    except json.JSONDecodeError:
        await mensagem_espera.edit_text(f"❌ Erro de Parsing: A IA não retornou um JSON válido.\n\nResposta bruta: {resposta_ia}")
    except Exception as e:
        await mensagem_espera.edit_text(f"❌ Erro no processamento: {str(e)}")


# 4. Inicia o servidor do bot (Long Polling)
if __name__ == '__main__':
    print("Iniciando o bot com IA Avançada... Pressione Ctrl+C para parar.")

    # Constrói a aplicaçã com seu token
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Configura as "rotas" (handlers) do bot
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()