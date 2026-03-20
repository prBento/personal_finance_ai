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

    hoje = datetime.now()
    data_formatada = hoje.strftime("%d/%m/%Y")

    SYSTEM_PROMPT = f"""
    Você é um extrator de dados financeiros altamente preciso.
    Hoje é {data_formatada}. Seu objetivo é extrair TODAS as compras descritas no texto.

    ========================
    REGRA PRINCIPAL DE SEPARAÇÃO (CRÍTICA)
    ========================
    Se o texto descrever produtos com FORMAS DE PAGAMENTO DIFERENTES (ex: um parcelado e outro à vista) ou compras não relacionadas, você DEVE OBRIGATORIAMENTE criar múltiplos objetos independentes dentro da lista "transacoes". NUNCA agrupe itens com condições de pagamento diferentes na mesma transação.

    ========================
    ESTRUTURA DO JSON
    ========================
    {{
      "transacoes": [
        {{
          "numero_nota": "String com o número da nota fiscal/NFC-e (ou null se não houver)",
          "data_compra": "DD/MM/YYYY",
          "itens": [
            {{
              "numero_item_nota": int (posição do item na nota, ou null se não houver),
              "item": "Nome",
              "marca": "Nome da marca ou null",
              "valor": float,
              "quantidade": float,
              "hierarquia_categorias": {{
                "macro": "Macro categoria",
                "categoria": "Categoria principal",
                "subcategoria": "Subcategoria",
                "produto": "Tipo do produto",
                "detalhe": "Variação ou detalhe específico"
              }}
            }}
          ],
          "valor_total": float,
          "categoria_macro": "...",
          "metodo_pagamento": "Dinheiro | Cartão de Crédito | Cartão de Débito | Pix | Financiamento | Desconhecido",
          "parcelado": boolean,
          "quantidade_parcelas": int (1 se à vista),
          "detalhamento_parcelas": [] (lista de objetos contendo "mes" e "valor". Vazia se à vista)
        }}
      ]
    }}

    ========================
    REGRAS DE CATEGORIZAÇÃO (HIERARQUIA)
    ========================
    Siga ESTRITAMENTE esta estrutura de 5 níveis para o campo 'hierarquia_categorias'. 
    Exemplos guiados:
    - Tomate cereja -> {{"macro": "Alimentação", "categoria": "Hortifruti", "subcategoria": "Verduras", "produto": "Tomate", "detalhe": "Tomate Cereja"}}
    - Arroz integral -> {{"macro": "Alimentação", "categoria": "Mercado", "subcategoria": "Grãos", "produto": "Arroz", "detalhe": "Integral"}}
    - Carro Hatch -> {{"macro": "Transporte", "categoria": "Veículos", "subcategoria": "Automóvel", "produto": "Carro", "detalhe": "Hatch"}}
    - Camiseta Hurley -> {{"macro": "Compras", "categoria": "Vestuário", "subcategoria": "Roupas", "produto": "Camiseta", "detalhe": "Estampada"}}

    ========================
    REGRAS DE MARCA E DATA
    ========================
    1. Extrair marca quando explícita (ex: "ventilador Mondial" -> Mondial). Se não houver, retorne null.
    2. Se não houver data explícita na mensagem, use {data_formatada}.

    ========================
    REGRAS DE PARCELAMENTO E VALORES
    ========================
    1. Se "à vista": parcelado=false, quantidade_parcelas=1, detalhamento_parcelas=[].
    2. Se "parcelado": parcelado=true.
       - detalhamento_parcelas = gerar a lista exata contendo "mes" (MM/YYYY) e o "valor" da parcela daquele mês, considerando a data atual ({data_formatada}) ou a data mencionada no texto (ex: "a partir do próximo mês").

    RETORNE APENAS JSON VÁLIDO. NÃO INCLUA NENHUM TEXTO ANTES OU DEPOIS DAS CHAVES.
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

        resposta_ia = chat_completion.choices[0].message.content.strip()

        inicio_json = resposta_ia.find('{')
        fim_json = resposta_ia.rfind('}') + 1

        if inicio_json != -1 and fim_json != 0:
            resposta_ia = resposta_ia[inicio_json:fim_json]

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

