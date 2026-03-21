import os
import json
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
from dateutil.relativedelta import relativedelta
from database import salvar_transacoes_no_banco

# 1. Carrega as chaves
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Inicializa o Client da IA
groq_client = Groq(api_key=GROQ_API_KEY)

def gerar_detalhamento_parcelas(valor_total, qtd_parcelas, mes_inicio_str):
    if qtd_parcelas <= 1:
        return []
    
    detalhamento = []
    valor_parcela = round(valor_total / qtd_parcelas, 2)
    mes_inicio = datetime.strptime(mes_inicio_str, "%m/%Y")
    
    for i in range(qtd_parcelas):
        mes_atual = mes_inicio + relativedelta(months=i)
        detalhamento.append({
            "mes": mes_atual.strftime("%m/%Y"),
            "valor": valor_parcela
        })
    return detalhamento

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
    Você é um assistente financeiro inteligente. Hoje é {data_formatada}.
    
    ========================
    PASSO 1: VALIDAÇÃO CRÍTICA (OBRIGATÓRIO)
    ========================
    Analise rigorosamente a mensagem do usuário. Ela DEVE conter os 2 dados abaixo:
    1. VALOR: Expresso em números ou palavras (ex: "350 reais", "R$ 50", "50 mil", "10k").
    2. LOCAL: O nome do estabelecimento, aplicativo, marca ou site (ex: "no Mercado Livre", "na Amazon", "no mercado", "loja Chevrolet", "Ifood", "Shopee").

    SE (E SOMENTE SE) FALTAR O VALOR OU O LOCAL, VOCÊ DEVE ABORTAR A EXTRAÇÃO!
    Retorne APENAS este JSON pequeno e pare imediatamente:
    {{
      "sucesso": false,
      "mensagem_interacao": "⚠️ Opa, faltou um detalhe! Por favor, reenvie a frase dizendo [o que faltou: o valor ou o local da compra]."
    }}

    ========================
    PASSO 2: EXTRAÇÃO (SÓ EXECUTE SE PASSOU NO PASSO 1)
    ========================
    Se o texto TEM LOCAL e TEM VALOR, retorne "sucesso": true e preencha a estrutura completa abaixo.
    
    REGRAS FINANCEIRAS E MATEMÁTICAS:
    - FORMATAÇÃO DE NÚMEROS (CRÍTICO): Use SEMPRE ponto (.) como separador decimal. NUNCA use vírgula (,). Exemplo: 50000.00.
    - metodo_pagamento: Preencha apenas se o usuário falar EXPLICITAMENTE (Pix, Boleto, Cartão, Dinheiro). Se não falar, retorne "Desconhecido". NUNCA deduza ou adivinhe o método.
    - quantidade_parcelas: Se não for parcelado ou a quantidade não for informada, assuma SEMPRE 1 por padrão. NUNCA use 0.
    - valor_total_pago: O valor final real da transação.
    - desconto_aplicado: 0.0 (a não ser que a palavra "desconto" ou "abatimento" seja citada).
    - valor_original: Exatamente a soma de (valor_total_pago + desconto_aplicado).
    - valor_unitario: Deixe sempre como 0.0. O sistema calculará isso depois.
    - hierarquia_categorias: Gere nomes reais e lógicos para macro, categoria, subcategoria e produto.
    - ATENÇÃO A VALORES GRANDES: "1 mil" = 1000.00, "50 mil" = 50000.00. 
    - mes_inicio_parcelas: Se o mês não for informado no texto, use {hoje.strftime('%m/%Y')}.

    ESTRUTURA DO JSON DE SUCESSO:
    {{
      "sucesso": true,
      "mensagem_interacao": "Ok",
      "transacoes": [
        {{
          "numero_nota": null,
          "data_compra": "DD/MM/YYYY",
          "local_compra": {{ "nome": "Nome do local", "tipo": "Físico | Online | App | Desconhecido" }},
          "status": "Ativa",
          "itens": [
            {{
              "numero_item_nota": null,
              "item": "Nome do produto",
              "marca": "Marca ou null",
              "valor_unitario": 0.0,
              "quantidade": float,
              "hierarquia_categorias": {{ "macro": "Nome", "categoria": "Nome", "subcategoria": "Nome", "produto": "Nome", "detalhe": "Detalhe ou null" }}
            }}
          ],
          "valor_original": float,
          "desconto_aplicado": float,
          "valor_total_pago": float,
          "categoria_macro": "Nome",
          "metodo_pagamento": "Dinheiro | Cartão de Crédito | Cartão de Débito | Pix | Financiamento | Desconhecido",
          "parcelado": boolean,
          "quantidade_parcelas": int,
          "mes_inicio_parcelas": "MM/YYYY"
        }}
      ]
    }}

    REGRA FINAL (CRÍTICA): 
    RETORNE APENAS 1 (UM) ÚNICO BLOCO JSON. NUNCA REPITA O JSON, NUNCA ESCREVA TEXTOS COMO "Resposta final:". APENAS ABRA A CHAVE {{ E FECHE A CHAVE }}.
    """

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": texto_recebido}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.0,
            max_tokens=4000,
        )

        resposta_ia = chat_completion.choices[0].message.content.strip()

        inicio_json = resposta_ia.find('{')
        fim_json = resposta_ia.rfind('}') + 1

        if inicio_json != -1 and fim_json != 0:
            resposta_ia = resposta_ia[inicio_json:fim_json]

        dados_json = json.loads(resposta_ia)

        if not dados_json.get("sucesso", True):
            await mensagem_espera.edit_text(f"⚠️ **Opa, faltou um detalhe:**\n\n{dados_json.get('mensagem_interacao')}")
        
        else:
            for transacao in dados_json.get("transacoes", []):

                valor_original_transacao = transacao.get("valor_original", 0.0)
                itens = transacao.get("itens", [])
                
                # Se for só 1 item, o valor unitário dele é o valor total dividido pela quantidade dele
                if len(itens) == 1:
                    qtd_item = itens[0].get("quantidade", 1.0)
                    if qtd_item > 0:
                        itens[0]["valor_unitario"] = round(valor_original_transacao / qtd_item, 2)

                if transacao.get("parcelado"):
                    valor = transacao.get("valor_total_pago", 0.0)
                    qtd = transacao.get("quantidade_parcelas", 1)

                    mes_inicio = transacao.get("mes_inicio_parcelas", hoje.strftime('%m/%Y'))

                    transacao["detalhamento_parcelas"] = gerar_detalhamento_parcelas(valor, qtd, mes_inicio)
                else:
                    transacao["detalhamento_parcelas"] = []
            
            resposta_formatada = json.dumps(dados_json, indent=2, ensure_ascii=False)

            if len(resposta_formatada) > 3900:
                resposta_formatada = resposta_formatada[:3900] + "\n\n... [JSON TRUNCADO DEVIDO AO LIMITE DE CARACTERES DO TELEGRAM]"

            
            sucesso_db, mensagem_db = salvar_transacoes_no_banco(dados_json)
            icone = "💾✅" if sucesso_db else "💾❌"

            await mensagem_espera.edit_text(
                f"✅ **Extração Concluída:**\n"
                f"{icone} **Status do Banco:** {mensagem_db}\n\n"
                f"```json\n{resposta_formatada}\n```", 
                parse_mode="Markdown"
            )

    except json.JSONDecodeError:
        erro_msg = f"❌ Erro de Parsing: A IA não retornou um JSON válido.\n\nResposta bruta: {resposta_ia}"
        # Trava também no erro!
        if len(erro_msg) > 3900:
            erro_msg = erro_msg[:3900] + "\n\n... [TEXTO TRUNCADO]"

        await mensagem_espera.edit_text(erro_msg)
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

