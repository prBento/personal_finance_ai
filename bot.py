import os
import json
import re
import traceback
import uuid
import asyncio
import random
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from groq import AsyncGroq

from database import (
    create_tables, save_transactions_to_db, get_card_from_db, save_card_to_db, list_cards_from_db, 
    add_to_queue, get_next_in_queue, reschedule_queue_item, reschedule_queue_item_busy, complete_queue_item, check_existing_invoice,
    check_similar_transaction, cancel_queue_items, get_pending_bills_by_month, pay_bill_in_db,
    get_all_overdue_installments, cancel_installment, get_max_pending_month, pay_grouped_card_bills_in_db, get_max_month_for_transaction,
    get_cash_flow_by_month
)

# --- Environment & Configuration ---
ENV = os.getenv("ENVIRONMENT", "dev").lower()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN_PROD") if ENV == "prod" else os.getenv("TELEGRAM_TOKEN_DEV")
GROQ_API_KEY = os.getenv("GROQ_API_KEY_PROD") if ENV == "prod" else os.getenv("GROQ_API_KEY_DEV")

# Whitelist: Only these Telegram User IDs can interact with the bot. Essential for personal finance security.
ALLOWED_CHAT_IDS = [int(x.strip()) for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()]

# Asynchronous LLM Client
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

# Global State Managers
# TEMP_SESSION holds the parsed JSON temporarily while the bot asks the user for missing info.
TEMP_SESSION = {}
# ACTIVE_CHATS prevents the background queue from interrupting a user who is actively answering a questionnaire.
ACTIVE_CHATS = set()

# --- Prompts (Two-Agent Architecture) ---
# Agent 1 focuses ONLY on Data Extraction. It parses raw text/PDFs into a rigid JSON structure.
PROMPT_AGENTE_1 = """
Você é um extrator de dados de notas fiscais e textos financeiros. Hoje é [DATA_ATUAL].
Sua função é ler o texto e extrair os dados. Se o texto for informal, deduza o local e os itens.

ESTRUTURA DE SAÍDA OBRIGATÓRIA (Apenas JSON):
{
  "sucesso": true,
  "mensagem_interacao": "Ok",
  "cabecalho": {
    "tipo_transacao": "RECEITA ou DESPESA",
    "local": "NOME DA EMPRESA fornecedora (Ex: Ultragaz, Copel). 🚨 NUNCA use o endereço do cliente. Se a empresa não estiver clara, deduza pela URL (ex: 'minhaultragaz' = Ultragaz). Se mesmo assim não ficar claro, retorne Não Informado.",
    "_raciocinio_vencimento": "1. PDF convertido perde formatação. 2. PROIBIDO usar 'DATA DE EMISSÃO'. Ignore datas perto de SÉRIE/Protocolo. 3. Vencimento costuma ser linha com 'Mês/Ano Data Valor'. Qual é o vencimento real e por quê?",
    "dt_transacao": "DD/MM/YYYY (Use a data de VENCIMENTO descoberta no raciocínio. Para compras normais, a data da compra)",
    "numero_nota": "Número da nota ou null",
    "serie_nota": "Série ou null",
    "valor_total_bruto": 0.00,
    "desconto_total": "PROCURE POR DESCONTOS ou FAÇA (VALOR TOTAL DOS PRODUTOS - VALOR DA NOTA) ou 0,00",
    "valor_total": 0.00,
    "metodo_pagamento": "Dinheiro, Cartão de Crédito, Cartão de Débito, Pix, Boleto, Conta Corrente, Financiamento ou null",
    "quantidade_parcelas": 1,
    "cartao": { "banco": "Banco ou null", "variante": "Variante ou null" }
  },
  "itens": [
    {
      "codigo": "Código ou null",
      "nome": "Nome do item ou motivo do recebimento",
      "quantidade": 1.0,
      "valor_unitario": 0.00
    }
  ]
}
"""

# Agent 2 takes the JSON from Agent 1 and applies Business Rules and Categorization.
# Splitting this into two steps dramatically reduces AI hallucinations.
PROMPT_AGENTE_2 = """
Você é um Analista Financeiro Sênior. Hoje é [DATA_ATUAL].
Sua missão é enriquecer e categorizar o JSON recebido.

MAPA DE CATEGORIAS (DESPESAS):
- Alimentação > Hortifruti | Carnes | Mercearia | Laticínios | Bebidas | Padaria | Restaurante | Limpeza
- Moradia > Contas Residenciais (Contas de Gás, Energia, Água, etc.) | Aluguel | Manutenção
- Transporte > Combustível | App de Transporte | Passagens | Manutenção Veicular
- Saúde e Beleza > Farmácia | Consultas/Exames | Cuidados Pessoais | Higiene Pessoal | Academia
- Lazer e Cultura > Livros | Ingressos | Jogos | Viagem
- Educação > Cursos | Material Escolar
- Compras > Vestuário | Eletrônicos | Casa/Móveis
- Serviços > Assinaturas | Manutenção Geral
- Outros > Despesas diversas
MAPA DE CATEGORIAS (RECEITAS):
- Entradas > Salário | Rendimentos | Aluguel | Reembolso | Vendas | Cashback | Outros

REGRAS DE DESAMBIGUAÇÃO (CRÍTICAS — Aplique ANTES de classificar):
- 🚨 Notas Fiscais (NF-e, NFC-e, DANFE), cupons e recibos de lojas (ex: Petlove, Mercado Livre) são SEMPRE gastos. Portanto o `tipo_transacao` é obrigatoriamente "DESPESA" e a categoria JAMAIS será "Entradas" (ignore se o texto da nota disser "valor recebido", pois foi a loja que recebeu o seu dinheiro).
- "Total Pass", "Gympass", "Smart Fit", "Bluefit" e similares são ACADEMIAS → sempre "Saúde e Beleza > Academias". NUNCA classifique como Transporte ou Lazer.
- "Uber", "99", "inDriver", "Cabify" → "Transporte > App de Transporte". NUNCA como Lazer ou Viagem.
- "Netflix", "Spotify", "Disney+", "Amazon Prime", "Max" → "Serviços > Assinaturas". NUNCA como Lazer.
- Contas de "Claro", "Vivo", "TIM", "Oi", "NET" → "Moradia > Contas Residenciais". NUNCA como Serviços > Assinaturas.
- Compras no "iFood", "Rappi", "Delivery" → "Alimentação > Restaurante". NUNCA como Transporte ou Serviços.

REGRAS (CRÍTICAS):
- valor_original: Copie "valor_total_bruto". desconto_aplicado: Copie "desconto_total".
- Retorne APENAS o JSON válido. SEM comentários (//) e SEM aspas duplas dentro dos valores de texto.

ESTRUTURA DO JSON FINAL:
{
  "sucesso": true,
  "mensagem_interacao": "Ok",
  "transacoes": [
    {
      "tipo_transacao": "String", "numero_nota": "Número ou null", "serie_nota": "Série ou null",
      "dt_transacao": "DD/MM/YYYY",
      "local_compra": { "nome": "Nome", "tipo": "Físico | Online | App | Boleto/Fatura" },
      "status": "Ativa", "cartao": { "banco": "Nome ou null", "variante": "Nome ou null" },
      "valor_original": 0.00, "desconto_aplicado": 0.00, "valor_total": 0.00,
      "categoria_macro": "Categoria do mapa", "metodo_pagamento": "String",
      "parcelado": false, "quantidade_parcelas": 1,
      "itens": [
        {
          "numero_item_nota": null, "item": "Nome", "codigo_produto": "Código ou null",
          "marca": "Marca ou null", "valor_unitario": 0.00, "quantidade": 1.0,
          "hierarquia_categorias": { "macro": "Mapa", "categoria": "Mapa", "subcategoria": "Mapa", "produto": "Nome" }
        }
      ]
    }
  ]
}
"""

def security_check(func):
    """
    Decorator that acts as a bouncer for all Telegram handlers.
    If the user's chat_id is not in ALLOWED_CHAT_IDS, the request is silently dropped.
    """
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if ALLOWED_CHAT_IDS and update.effective_chat.id not in ALLOWED_CHAT_IDS:
            print(f"🚨 Acesso negado para ID: {update.effective_chat.id}")
            return
        return await func(update, context)
    return wrapper

def extract_text_from_url(url):
    """Web scraping fallback. If the user sends a URL (like an NFC-e link), it fetches the HTML and extracts raw text."""
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        for script_or_style in soup(['script', 'style']): script_or_style.extract()
        return '\n'.join([linha.strip() for linha in soup.get_text(separator=' ').splitlines() if linha.strip()])
    except Exception as e: return f"Erro ao acessar link: {str(e)}"

def extract_json_from_response(raw_text):
    """
    LLM outputs often contain conversational fluff (e.g., "Here is your JSON: ```json ... ```").
    This regex forces the extraction of ONLY the JSON block, cleaning up common formatting errors.
    """
    match = re.search(r'\{[\s\S]*\}', raw_text)
    if not match: return None
    json_text = match.group(0)
    json_text = re.sub(r'(?<![:"\/])\/\/.*', '', json_text)
    json_text = json_text.replace(": False", ": false").replace(": True", ": true").replace(": None", ": null")
    json_text = json_text.replace(":False", ":false").replace(":True", ":true").replace(":None", ":null")
    try: return json.loads(json_text, strict=False)
    except: return None

def calculate_invoice_due_date(purchase_date, closing_day, due_day):
    """
    Calculates the exact due date of a credit card invoice based on the purchase date
    and the specific bank's rules (closing/due days) saved in the database.
    """
    base_month = purchase_date.replace(day=1)
    if purchase_date.day >= closing_day:
        base_month += relativedelta(months=1)
    if due_day < closing_day:
        base_month += relativedelta(months=1)
    return base_month + relativedelta(day=due_day)

def generate_installment_details(total_amount, total_installments, transaction_date_str, card_rules, payment_method, transaction_type="DESPESA", first_inst_date=None):
    """
    The Accounts Payable (AP) Engine. 
    It splits a total amount into 'n' installments, assigning precise due dates
    and determining if the installment is immediately 'PAID' (like Pix/Cash) or 'PENDING' (Credit/Financing).
    """
    details = []
    actual_installments = max(1, total_installments)
    installment_value = round(total_amount / actual_installments, 2)
    
    br_tz = timezone(timedelta(hours=-3))
    today_dt = datetime.now(br_tz)
    
    try: 
        tx_date = datetime.strptime(transaction_date_str, "%d/%m/%Y").replace(tzinfo=br_tz)
    except: 
        tx_date = today_dt
        
    closing = int(card_rules.get("closing", 0)) if card_rules else 0
    due = int(card_rules.get("due", 0)) if card_rules else 0
    method_str = str(payment_method).lower()
    
    # Determines the baseline date for the first installment
    if first_inst_date:
        try: 
            base_date = datetime.strptime(first_inst_date, "%d/%m/%Y").replace(tzinfo=br_tz)
        except: 
            base_date = tx_date
    elif card_rules and closing == 0 and due == 0: 
        base_date = tx_date
    elif "crédito" in method_str or "credito" in method_str:
        if card_rules: base_date = calculate_invoice_due_date(tx_date, closing, due)
        else: base_date = tx_date + relativedelta(months=1)
    else: 
        base_date = tx_date

    cash_keywords = ["débito", "debito", "pix", "dinheiro", "conta corrente", "poupança", "benefício", "pré-pago"]
    is_cash_payment = any(word in method_str for word in cash_keywords)
    
    payment_status = "PAID" if (is_cash_payment or str(transaction_type).upper() == "RECEITA") and "aberto" not in method_str and "pendente" not in method_str else "PENDING"
    
    # --- NOVA LÓGICA: REALOCAÇÃO DE REGIME DE CAIXA (PAGAMENTO ANTECIPADO) ---
    if payment_status == "PAID":
        # Se a data de vencimento extraída for no futuro, mas foi pago HOJE, a data real é hoje.
        if tx_date > today_dt:
            real_pay_date = today_dt
        else:
            real_pay_date = tx_date
            
        date_paid_str = real_pay_date.strftime("%d/%m/%Y")
        base_payment_month = real_pay_date.strftime("%m/%Y")
    else:
        date_paid_str = None
        base_payment_month = None

    paid_value = installment_value if payment_status == "PAID" else 0.0

    for i in range(actual_installments):
        installment_date = base_date + relativedelta(months=i)
        
        # Se foi pago, força o mês da parcela a ser o mês do pagamento real para bater com o Extrato
        assigned_month = base_payment_month if payment_status == "PAID" else installment_date.strftime("%m/%Y")
        
        details.append({
            "mes": assigned_month, 
            "data_vencimento": installment_date.strftime("%d/%m/%Y"), 
            "valor": installment_value, "status_pagamento": payment_status,
            "dt_pagamento": date_paid_str, "valor_pago": paid_value
        })
    return details

async def queue_processor(context: ContextTypes.DEFAULT_TYPE):
    """
    Background Worker Pattern (The core of data resilience).
    This function runs continuously every 10 seconds. It pulls items from the DB outbox,
    sends them to the Groq LLM, and handles rate limits without blocking the Telegram Chat.
    """
    item = get_next_in_queue()
    if not item: return

    chat_id = item['chat_id']
    user_state = context.application.user_data.get(chat_id, {}).get("estado")
    
    # Busy check: If the user is answering a questionnaire, pause the queue for this chat
    if (chat_id in ACTIVE_CHATS) or (chat_id in TEMP_SESSION) or (user_state is not None):
        reschedule_queue_item_busy(item['id'], 15)
        return

    ACTIVE_CHATS.add(chat_id)

    today_str = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y")
    current_attempt = item['attempts']
    max_attempts = item['max_attempts']
    
    try:
        text_to_process = item['text']
        if text_to_process.startswith("http://") or text_to_process.startswith("https://"):
            text_to_process = extract_text_from_url(text_to_process)
            if "Erro ao acessar link" in text_to_process: raise Exception("Não consegui ler o site.")

        prompt_1 = PROMPT_AGENTE_1.replace("[DATA_ATUAL]", today_str)
        prompt_2 = PROMPT_AGENTE_2.replace("[DATA_ATUAL]", today_str)
        
        # LLM Call 1: Extraction
        chat_ext = await groq_client.chat.completions.create(
            messages=[{"role": "system", "content": prompt_1}, {"role": "user", "content": text_to_process}],
            model="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0.0, max_tokens=8000
        )
        json_ext = extract_json_from_response(chat_ext.choices[0].message.content)
        if not json_ext: raise Exception("Falha na Estruturação.")

        # LLM Call 2: Enrichment
        chat_enr = await groq_client.chat.completions.create(
            messages=[{"role": "system", "content": prompt_2}, {"role": "user", "content": json.dumps(json_ext, ensure_ascii=False)}],
            model="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0.1, max_tokens=8000
        )
        final_json = extract_json_from_response(chat_enr.choices[0].message.content)
        if not final_json: raise Exception("Falha na Categorização.")

        # Pre-Processing and Idempotency Checks before asking the user
        for tx in final_json.get("transacoes", []):
            inv_num = tx.get("numero_nota")
            
            # Check 1: Exact invoice duplicate
            if inv_num and str(inv_num).lower() != "null":
                if check_existing_invoice(inv_num):
                    await context.bot.send_message(chat_id, f"🚫 *Duplicado!* A nota `{inv_num}` já foi enviada.", parse_mode="Markdown")
                    complete_queue_item(item['id'])
                    return
            else:
                tx["numero_nota"] = f"M-{random.randint(100000000, 999999999)}"
                loc_check = str(tx.get("local_compra", {}).get("nome", "DESCONHECIDO")).upper()
                # Check 2: Heuristic duplicate (Same Place, Same Money, Same Date)
                if check_similar_transaction(loc_check, float(tx.get("valor_total") or 0.0), tx.get("dt_transacao") or today_str):
                    tx["alerta_duplicidade"] = True

            # --- CODE-FORCED MATH & DISCOUNT FALLBACK ---
            val_total = float(tx.get("valor_total") or 0.0)
            
            # 1. Calculates the true gross total directly from the items
            sum_items = round(sum(float(i.get("valor_unitario", 0)) * float(i.get("quantidade", 1)) for i in tx.get("itens", [])), 2)
            
            # 2. Fixes zeroed totals
            if val_total == 0.0 and sum_items > 0:
                val_total = sum_items
                tx["valor_total"] = val_total
                
            # 3. Hidden Discount Detector
            # If the mathematical sum of the items is greater than the total invoice value, 
            # we have a discount that the LLM missed.
            if sum_items > val_total > 0:
                calc_discount = round(sum_items - val_total, 2)
                current_discount = float(tx.get("desconto_aplicado") or 0.0)
                
                # Overwrites LLM hallucination with hard code math
                if calc_discount > current_discount:
                    tx["valor_original"] = sum_items
                    tx["desconto_aplicado"] = calc_discount
                    
            raw_dt = str(tx.get("dt_transacao", "")).strip()
            if re.match(r'^\d{2}/\d{2}$', raw_dt):
                tx["dt_transacao"] = f"{raw_dt}/{datetime.now(timezone(timedelta(hours=-3))).year}"
            elif not raw_dt or raw_dt.lower() == "null" or len(raw_dt) < 5:
                tx["dt_transacao"] = today_str
            
            for idx, it in enumerate(tx.get("itens", []), start=1):
                it["numero_item_nota"] = str(idx)
                if it.get("valor_unitario", 0.0) == 0.0:
                    it["valor_unitario"] = round(float(tx.get("valor_total") or 0) / max(1, float(it.get("quantidade") or 1)), 2)

        complete_queue_item(item['id'])
        
        # Passes the processed JSON to the State Machine Evaluator
        TEMP_SESSION[chat_id] = {"transacao_pendente_json": final_json, "is_pdf": item['is_pdf'], "estado": None}
        await dispatch_confirmation_triggers(context.bot, chat_id, TEMP_SESSION[chat_id])

    except Exception as e:
        error_msg = str(e).lower()
        print(f"\n[ERRO FILA {item['id']}] Tentativa {current_attempt + 1}: {e}")
        
        # Rate Limit Handler (Protects against LLM bans)
        if "429" in error_msg or "rate limit" in error_msg: 
            br_now = datetime.now(timezone(timedelta(hours=-3)))
            wait_seconds = 60
            
            # TPD (Tokens Per Day) check -> Defers to 90 min
            if "tokens per day" in error_msg or "tpd" in error_msg:
                wait_seconds = 5400 # 90 minutes
                br_time = br_now + timedelta(seconds=wait_seconds)
                
                print(f"⏳ [RATE LIMIT TPD] IA sobrecarregada. Retentativa agendada para {br_time.strftime('%H:%M:%S')} (BRT).")
                reschedule_queue_item(item['id'], wait_seconds, current_attempt, 999) # 999 prevents permanent failure
                
                if current_attempt == 0:
                    await context.bot.send_message(
                        chat_id, 
                        f"⚠️ *IA indisponível (TPD).* 🛑\n\n"
                        f"⏳ O seu registro está salvo na fila de espera.\n"
                        f"A retentativa automática será às {br_time.strftime('%H:%M')}.\n"
                        f"Assim que processado, envio o resumo para você confirmar.",
                        parse_mode="Markdown"
                    )
            # Standard RPM/TPM check -> Extracts wait time from error log 
            else:
                match = re.search(r'try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?', error_msg)
                if match:
                    h = float(match.group(1) or 0)
                    m = float(match.group(2) or 0)
                    s = float(match.group(3) or 0)
                    wait_seconds = int(h * 3600 + m * 60 + s) + 15
                
                br_time = br_now + timedelta(seconds=wait_seconds)
                minutos = wait_seconds / 60
                print(f"⏳ [RATE LIMIT] Esperando {minutos:.1f} minutos. Retentativa agendada para as {br_time.strftime('%H:%M:%S')} (BRT)")
                
                reschedule_queue_item(item['id'], wait_seconds, current_attempt, 999)
                
                if current_attempt == 0:
                    await context.bot.send_message(
                        chat_id, 
                        f"⚠️ *IA sobrecarregada.*\n\n"
                        f"⏳ Não se preocupe! O seu registro está salvo na fila.\n"
                        f"A retentativa automática será em aprox. {int(minutos)} min, às *{br_time.strftime('%H:%M')}*.\n"
                        f"Assim que conseguir, eu envio o resumo para você confirmar.",
                        parse_mode="Markdown"
                    )
        # Standard errors (Exponential Backoff up to max_attempts)
        else: 
            wait_time = min(60 * (2 ** current_attempt), 3600)
            reschedule_queue_item(item['id'], wait_time, current_attempt, max_attempts)
            
            if current_attempt == 0:
                await context.bot.send_message(chat_id, "⚠️ *Erro na leitura.* IA tentando fazer a leitura em segundo plano...", parse_mode="Markdown")
            elif current_attempt + 1 >= max_attempts:
                preview = "📄 Documento PDF" if item.get('is_pdf') else item['text'][:40].replace('\n', ' ') + "..."
                await context.bot.send_message(chat_id, f"❌ *Falha Permanente:* Limite de tentativas excedido.\n*Ref:* `{preview}`", parse_mode="Markdown")
            
    finally:
        ACTIVE_CHATS.discard(chat_id)

async def dispatch_confirmation_triggers(bot, chat_id, user_data):
    """
    The Cascading Central Evaluator (State Machine Core).
    Instead of asking everything blindly, it evaluates the JSON from top to bottom.
    If ANY crucial information is missing (Method, Location, Card Bank, Installment Date),
    it halts the execution, sets a state (e.g., 'AGUARDANDO_LOCAL'), and asks the user.
    Once answered, it evaluates again until the JSON is perfectly valid to generate the Markdown summary.
    """
    tx = user_data["transacao_pendente_json"]["transacoes"][0]
    tx_type = str(tx.get("tipo_transacao", "DESPESA")).upper()
    method = str(tx.get("metodo_pagamento")).lower() if tx.get("metodo_pagamento") else "desconhecido"
    
    bank = tx.get("cartao", {}).get("banco")
    variant = tx.get("cartao", {}).get("variante")

    clean_words = ["null", "none", "não informado", "nao informado", "desconhecido", ""]
    if bank and str(bank).strip().lower() in clean_words: bank = None
    if variant and str(variant).strip().lower() in clean_words: variant = None

    current_state = user_data.get("estado")
    loc_name = tx.get("local_compra", {}).get("nome", "Local Desconhecido")
    tx_val = float(tx.get('valor_total') or 0.0)
    tx_date = tx.get("dt_transacao", datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y"))

    # Whitelists prevent the LLM from inventing fake payment methods
    trusted_methods = ["pix", "dinheiro", "conta", "poupança", "crédito", "credito", "débito", "debito", "cartão", "cartao", "benefício", "financiamento", "boleto", "aberta", "aberto", "pendente"]
    is_method_trusted = any(tm in method for tm in trusted_methods)
    is_missing_loc = str(loc_name).strip().lower() in clean_words or "desconhecido" in str(loc_name).strip().lower()

    if current_state != "AGUARDANDO_CONFIRMACAO":
        if user_data.get("is_pdf") or method in clean_words or not is_method_trusted:
            user_data["estado"] = "AGUARDANDO_METODO_PAGAMENTO"
            if tx_type == "RECEITA":
                keyboard = ReplyKeyboardMarkup([
                    ["Pix", "Conta Corrente/Poupança"], 
                    ["Cartão de Benefício", "Dinheiro"],
                    ["⏳ Ainda não recebi (Previsto)"]
                ], resize_keyboard=True, one_time_keyboard=True)
                await bot.send_message(chat_id, f"📄 Recebimento de *{loc_name}* (R$ {tx_val:.2f})\nOnde esse valor entrará?", reply_markup=keyboard, parse_mode="Markdown")
            else:
                keyboard = ReplyKeyboardMarkup([["Cartão de Crédito", "Cartão de Débito"], ["Pix", "Dinheiro", "Boleto"], ["Financiamento", "⏳ Ainda não paguei (Aberto)"]], resize_keyboard=True, one_time_keyboard=True)
                await bot.send_message(chat_id, f"📄 Compra em *{loc_name}* (R$ {tx_val:.2f})\nComo você pagou?", reply_markup=keyboard, parse_mode="Markdown")
            return

        # Step 2: Validate Location
        if is_missing_loc:
            user_data["estado"] = "AGUARDANDO_LOCAL"
            await bot.send_message(chat_id, f"🏢 Qual foi o *Local/Nome* dessa transação no valor de R$ {tx_val:.2f}?", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
            return

        # Step 3: Validate Card Info (if applicable)
        method_needs_card = any(word in method for word in ["cartão", "cartao", "crédito", "credito", "débito", "debito", "benefício", "beneficio"])
        
        if method_needs_card:
            if not bank:
                buttons = [[f"{c['bank']} {c['variant']}".strip()] for c in list_cards_from_db()]
                buttons.append(["➕ Adicionar Novo Cartão"])
                user_data["estado"] = "AGUARDANDO_SELECAO_CARTAO"
                
                # Dinamiza a pergunta se for entrada ou saída
                verb = "Recebimento" if tx_type == "RECEITA" else "Compra"
                await bot.send_message(chat_id, f"💳 {verb} em *{loc_name}* (R$ {tx_val:.2f})\nQual cartão?", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True), parse_mode="Markdown")
                return
            else:
                db_card = get_card_from_db(bank, variant)
                # If the card is unknown, pause and learn its rules (upsert logic)
                if not db_card:
                    user_data.update({"estado": "AGUARDANDO_DATAS_CARTAO", "pendente_banco": bank, "pendente_variante": variant})
                    await bot.send_message(chat_id, f"💳 Cartão Novo: *{bank} {variant}*!\nQual *fechamento e vencimento*? (Ex: 1 e 8)", parse_mode="Markdown")
                    return

        # Step 4: Validate Target Date for long-term debts
        parcels = int(tx.get("quantidade_parcelas") or 1)
        needs_first_date = "financiamento" in method or (parcels > 1 and "boleto" in method)
        if needs_first_date and not user_data.get("primeira_parcela_definida"):
            user_data["estado"] = "AGUARDANDO_DATA_PRIMEIRA_PARCELA"
            await bot.send_message(chat_id, f"📅 Qual a *Data de Vencimento da 1ª Parcela*?\n*(As outras {parcels-1} parcelas cairão no mesmo dia nos meses seguintes)*\n\nExemplo: `15/05/2026`", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
            return

    # Once all cascades pass, generate the final parsed data
    db_card = get_card_from_db(bank, variant) if bank else None
    is_prepaid = db_card and db_card.get("closing") == 0 and db_card.get("due") == 0
    is_cash = method in ["débito", "debito", "pix", "dinheiro", "conta corrente", "poupança"]
    
    if is_prepaid or is_cash or tx_type == "RECEITA":
        tx["quantidade_parcelas"] = 1
        tx["parcelado"] = False
        if is_prepaid and ("crédito" in method or "credito" in method):
            tx["metodo_pagamento"] = "Cartão de Benefício/Pré-pago"
            method = "benefício"

    tx["detalhamento_parcelas"] = generate_installment_details(
        float(tx.get("valor_total") or 0.0), 
        int(tx.get("quantidade_parcelas") or 1), 
        tx.get("dt_transacao"), 
        db_card, 
        method, 
        tx_type,
        first_inst_date=user_data.get("primeira_parcela_definida")
    )
    user_data["estado"] = "AGUARDANDO_CONFIRMACAO"
    
    # --- UI: Markdown Summary Building ---
    cat = tx.get("categoria_macro", "Não classificada")
    parcels = int(tx.get("quantidade_parcelas") or 1)
    
    summary = f"📈 *Resumo*\n🏢 *Origem:* {loc_name}\n📅 *Data:* {tx_date}\n" if tx_type == "RECEITA" else f"🛒 *Resumo*\n📍 *Local:* {loc_name}\n📅 *Data:* {tx_date}\n"
    summary += f"🏷️ *Categoria:* {cat}\n"
    
    discount_app = float(tx.get('desconto_aplicado') or 0.0)
    if discount_app > 0:
        summary += f"💰 *Valor Bruto:* R$ {float(tx.get('valor_original') or 0):.2f}\n"
        summary += f"✂️ *Desconto:* -R$ {discount_app:.2f}\n"
        summary += f"💵 *Valor Final:* R$ {float(tx.get('valor_total') or 0):.2f}\n"
    else:
        summary += f"💰 *Valor:* R$ {float(tx.get('valor_total') or 0):.2f}\n"
        
    summary += f"💳 *Método:* {tx.get('metodo_pagamento')}"
    summary += f" ({bank} {variant})\n" if bank else "\n"
    
    if tx_type != "RECEITA": summary += f"📅 *Parcelas:* {parcels}x\n\n"
    else: summary += "\n"
    
    items_list = tx.get("itens", [])
    if items_list:
        summary += "📋 *Itens/Detalhes:*\n"
        for i_data in items_list[:5]:
            qty = float(i_data.get("quantidade") or 1)
            name = str(i_data.get("item") or "Produto")
            unit_val = float(i_data.get("valor_unitario") or 0.0)
            hier = i_data.get("hierarquia_categorias") or {}
            item_cat = hier.get("subcategoria") or hier.get("categoria") or ""
            cat_tag = f" _({item_cat})_" if item_cat else ""
            summary += f"🔸 {qty}x {name} (R$ {unit_val:.2f}){cat_tag}\n"
        if len(items_list) > 5:
            summary += f"   *(...e mais {len(items_list) - 5} itens)*\n"
        summary += "\n"
        
    if tx_type == "DESPESA":
        summary += "*Vencimentos:*\n"
        for p in tx.get("detalhamento_parcelas", [])[:3]:
            icon = "✅" if p['status_pagamento'] == 'PAID' else "🔹"
            summary += f"{icon} {p['data_vencimento']} - R$ {float(p.get('valor') or 0):.2f}\n"
        if parcels > 3: summary += f"...e mais {parcels - 3} parcelas.\n"
        
    summary += f"\n📋 *ID:* `{tx.get('numero_nota')}`\n"
    if tx.get("alerta_duplicidade"): summary += f"\n🚨 *ALERTA DE DUPLICIDADE:* Registro idêntico encontrado hoje!\n\n⚠️ *Deseja salvar NOVAMENTE?*"
    else: summary += "\n⚠️ *Salvar no banco?*"
    
    await bot.send_message(chat_id, summary, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup([["Sim", "Não"]], resize_keyboard=True, one_time_keyboard=True))

@security_check
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Flushes the database queue for the user and clears their active session states."""
    chat_id = update.effective_chat.id
    cancel_queue_items(chat_id)
    TEMP_SESSION.pop(chat_id, None)
    ACTIVE_CHATS.discard(chat_id)
    context.user_data.clear()
    await update.message.reply_text("🛑 *Cancelado!* Fila limpa.", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

async def show_bills_month(update: Update, context: ContextTypes.DEFAULT_TYPE, target_month: str, filter_tx_id: int = None):
    """
    Renders the interactive AP Dashboard.
    If 'filter_tx_id' is provided, it enters "Isolated View".
    Visually differentiates Incomes (Receitas) from Expenses (Despesas).
    """
    bills = get_pending_bills_by_month(target_month)
    
    # Isolation Filter
    if filter_tx_id:
        bills = [b for b in bills if b.get('transaction_id') == filter_tx_id]
        overdue_other = [] # Hides global warnings in isolated view
        text = f"🔍 *Modo Isolado - {target_month}*\nVisualizando apenas parcelas desta transação:\n"
    else:
        overdue_all = get_all_overdue_installments()
        overdue_other = [b for b in overdue_all if b['month'] != target_month]
        text = f"🗓️ *Painel de Pendências - {target_month}*\n"
        if overdue_other:
            text += f"\n🚨 *ATENÇÃO:* Você tem {len(overdue_other)} pendências *VENCIDAS* em outros meses!\n"

    keyboard = []
    if not bills:
        text += "\n🎉 Nenhuma pendência para este mês!"
    else:
        if not filter_tx_id:
            text += "\nSelecione um item para gerenciar:\n"
        
        grouped_cards = {}
        standalone_bills = []
        
        for b in bills:
            if b['bank']:
                group_key = f"{b['bank']}_{b['variant']}" if b['variant'] else b['bank']
                if group_key not in grouped_cards:
                    grouped_cards[group_key] = {
                        "bank": b['bank'], "variant": b['variant'], 
                        "total_amount": 0.0, "items": [], "due_date": b['due_date'], "is_overdue": False
                    }
                grouped_cards[group_key]["total_amount"] += b['amount']
                grouped_cards[group_key]["items"].append(b)
                if b['is_overdue']: grouped_cards[group_key]["is_overdue"] = True
            else:
                standalone_bills.append(b)
                
        expanded_groups = context.user_data.setdefault(f"expanded_{target_month}", {})
        
        # Render Grouped Cards (Credit cards are always expenses)
        for key, card in grouped_cards.items():
            is_expanded = expanded_groups.get(key, False) # Verifica se deve mostrar os filhos
            
            icon_alert = "🔴" if card['is_overdue'] else "💳"
            toggle_icon = "⏷" if is_expanded else "⏵"
            
            v_tag = f" {card['variant']}" if card['variant'] else ""
            display_name = f"{card['bank']}{v_tag}"
            safe_var = card['variant'] if card['variant'] else "none"
            
            # O botão principal agora serve para expandir/encolher (toggle)
            parent_text = f"{toggle_icon} {icon_alert} {display_name} - R$ {card['total_amount']:.2f}"
            keyboard.append([InlineKeyboardButton(parent_text, callback_data=f"toggle_{card['bank']}_{safe_var}_{target_month}")])
            
            # Só desenha os botões de baixo SE o acordeon estiver aberto
            if is_expanded:
                # O botão de pagar a fatura fechada fica aqui dentro como primeira opção
                keyboard.append([InlineKeyboardButton("   💸 Pagar Fatura Fechada", callback_data=f"fatgroup_{card['bank']}_{safe_var}_{target_month}")])
                
                # Renderiza os itens individuais
                for item in card['items']:
                    item_icon = "🔴" if item['is_overdue'] else "🔸"
                    child_text = f"   ↳ {item_icon} {item['location'][:12]} - R$ {item['amount']:.2f}"
                    keyboard.append([InlineKeyboardButton(child_text, callback_data=f"fatura_{item['id']}_{target_month}")])

        # Render Standalone Bills (Can be Income or Expense)
        for b in standalone_bills:
            is_income = b.get('type', 'DESPESA') == 'RECEITA'
            
            if is_income:
                icon = "🟡" if b['is_overdue'] else "🟢"
                sign = "+"
            else:
                icon = "🔴" if b['is_overdue'] else "🔹"
                sign = ""
                
            btn_text = f"{icon} {b['location'][:14]} {sign}R$ {b['amount']:.2f} ({b['due_date'][:5]})"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"fatura_{b['id']}_{target_month}")])

    target_dt = datetime.strptime(target_month, "%m/%Y")
    prev_month = (target_dt - relativedelta(months=1)).strftime("%m/%Y")
    next_month = (target_dt + relativedelta(months=1)).strftime("%m/%Y")

    # Navigation logic
    tx_param = f"_tx_{filter_tx_id}" if filter_tx_id else ""
    nav_row = [
        InlineKeyboardButton(f"⬅️ {prev_month}", callback_data=f"mes_{prev_month}{tx_param}"),
        InlineKeyboardButton(f"{next_month} ➡️", callback_data=f"mes_{next_month}{tx_param}")
    ]
    keyboard.append(nav_row)
    
    # Contextual controls
    if filter_tx_id:
        keyboard.append([InlineKeyboardButton("⬅️ Voltar à Visão Geral", callback_data=f"mes_{target_month}")])
    else:
        max_month = get_max_pending_month()
        if max_month and max_month != target_month and datetime.strptime(max_month, "%m/%Y") > target_dt:
            keyboard.append([InlineKeyboardButton(f"⏭️ Pular para Último Mês ({max_month})", callback_data=f"mes_{max_month}")])

    # Feature: Return to Current Month (Appears if user is time-traveling)
    current_month_str = datetime.now(timezone(timedelta(hours=-3))).strftime("%m/%Y")
    if target_month != current_month_str:
        keyboard.append([InlineKeyboardButton(f"📅 Voltar para Mês Atual ({current_month_str})", callback_data=f"mes_{current_month_str}{tx_param}")])
        
    # Global Escape Hatch (Only in main view)
    if not filter_tx_id:
        keyboard.append([InlineKeyboardButton("❌ Fechar Painel", callback_data="close_panel")])

    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")

async def ask_for_payment_amount(bot, chat_id, query, target_month, pay_date, bill_id=None, group_bank=None, group_variant=None):
    """Modified to include dynamic text based on Transaction Type (Income vs Expense)."""
    amount = 0.0
    is_income = False
    
    if bill_id:
        bills = get_pending_bills_by_month(target_month)
        bill = next((b for b in bills if str(b['id']) == str(bill_id)), None)
        amount = bill['amount'] if bill else 0.0
        if bill and bill.get('type', 'DESPESA') == 'RECEITA':
            is_income = True
        callback_str = f"payamt_full_single_{bill_id}"
    else:
        # Grouped cards are always expenses
        bills = get_pending_bills_by_month(target_month)
        for b in bills:
            v_check = b['variant'] if b['variant'] else "none"
            if b['bank'] == group_bank and v_check == group_variant:
                amount += float(b['amount'])
        callback_str = f"payamt_full_group_{group_bank}_{group_variant}_{target_month}"
        
    keyboard = [
        [InlineKeyboardButton(f"💰 Valor Integral (R$ {amount:.2f})", callback_data=callback_str)],
        [InlineKeyboardButton("❌ Cancelar Ação", callback_data="cancel_fsm")]
    ]
    
    # Dynamic wording based on transaction type
    action_word = "recebido" if is_income else "pago"
    
    text = f"💰 *Qual foi o valor exato {action_word}?*\nValor integral: *R$ {amount:.2f}*\n\nSe houve diferença, *digite* o valor final {action_word} (Ex: `150,50`).\nSe {action_word} o valor integral, clique no botão abaixo:"
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- (CASH FLOW) ---
async def show_cash_flow_month(update: Update, context: ContextTypes.DEFAULT_TYPE, target_month: str):
    """
    Renders the Financial Ledger (Extrato) on Telegram.
    Now includes a visual tag [B] in the monospace list to explicitly show 
    which items were successfully isolated into the Benefit Balance.
    """
    transactions = get_cash_flow_by_month(target_month)
    
    def fmt_money(val):
        return f"{val:,.2f}".replace(',', 'v').replace('.', ',').replace('v', '.')
    
    main_tx = []
    ben_tx = []
    
    for t in transactions:
        # Junta todas as colunas que podem conter a palavra chave
        m = f"{t.get('method', '')} {t.get('bank', '')} {t.get('variant', '')}".lower()
        if "benefício" in m or "beneficio" in m or "pré-pago" in m or "pre-pago" in m or "vr" in m or "va" in m or "caju" in m:
            ben_tx.append(t)
            t['is_benefit'] = True # Flag para a interface
        else:
            main_tx.append(t)
            t['is_benefit'] = False

    rec_pagas = sum(t['paid_amount'] for t in main_tx if t['type'] == 'RECEITA' and t['status'] == 'PAID')
    rec_prev = sum(t['expected_amount'] for t in main_tx if t['type'] == 'RECEITA' and t['status'] == 'PENDING')
    desp_pagas = sum(t['paid_amount'] for t in main_tx if t['type'] == 'DESPESA' and t['status'] == 'PAID')
    desp_prev = sum(t['expected_amount'] for t in main_tx if t['type'] == 'DESPESA' and t['status'] == 'PENDING')
    
    saldo_atual = rec_pagas - desp_pagas
    saldo_projetado = (rec_pagas + rec_prev) - (desp_pagas + desp_prev)

    ben_rec_pagas = sum(t['paid_amount'] for t in ben_tx if t['type'] == 'RECEITA' and t['status'] == 'PAID')
    ben_desp_pagas = sum(t['paid_amount'] for t in ben_tx if t['type'] == 'DESPESA' and t['status'] == 'PAID')
    ben_saldo_atual = ben_rec_pagas - ben_desp_pagas

    text = f"📊 *Extrato — {target_month}*\n\n"
    
    text += f"💰 *Saldo Atual:* R$ {fmt_money(saldo_atual)}\n"
    text += f"📈 *Projetado:* R$ {fmt_money(saldo_projetado)}\n"
    
    if ben_tx:
        text += f"\n🎫 *Saldo Benefício:* R$ {fmt_money(ben_saldo_atual)}\n"

    text += "\n─────────────────\n"
    text += f"💵 *Receitas*\n"
    text += f"  Realizado: R$ {fmt_money(rec_pagas)}\n"
    text += f"  Previsto:  R$ {fmt_money(rec_prev)}\n\n"
    
    text += f"💸 *Despesas*\n"
    text += f"  Realizado: R$ {fmt_money(desp_pagas)}\n"
    text += f"  Previsto:  R$ {fmt_money(desp_prev)}\n"
    
    text += "─────────────────\n"
    text += "📋 *Últimos Lançamentos*\n"
    
    if not transactions:
        text += "_Nenhuma movimentação neste mês._"
    else:
        text += "```text\n"
        
        for t in transactions[:30]:
            is_income = t['type'] == 'RECEITA'
            is_paid = t['status'] == 'PAID'
            
            date_str = t['payment_date'][:5] if is_paid and t['payment_date'] else t['due_date'][:5]
            amount_val = t['paid_amount'] if is_paid else t['expected_amount']
            
            amt_formatted = fmt_money(amount_val)
            amt_str = f"{amt_formatted}" if is_income else f"({amt_formatted})"
            
            loc_raw = t['location'].strip().title()
            
            # --- TAG VISUAL DE BENEFÍCIO ---
            if t.get('is_benefit'):
                loc_raw = f"[B] {loc_raw}"
            
            if t.get('is_installment') and t.get('installment_count', 1) > 1:
                parcel_str = f" {t['inst_num']}/{t['installment_count']}"
                max_loc_len = max(0, 14 - len(parcel_str))
                loc = f"{loc_raw[:max_loc_len]}{parcel_str}"
            else:
                loc = loc_raw[:14]
            
            tag = " " if is_paid else "*"
            
            line = f"{loc:<14} {date_str} - {amt_str:>10} {tag}"
            text += line + "\n"

        text += "```\n"

        if len(transactions) > 30:
            text += f"_...e mais {len(transactions) - 30} transações._\n"
            
        text += "_( * ) = Lançamento Previsto/Pendente_\n"

    target_dt = datetime.strptime(target_month, "%m/%Y")
    prev_month = (target_dt - relativedelta(months=1)).strftime("%m/%Y")
    next_month = (target_dt + relativedelta(months=1)).strftime("%m/%Y")

    nav_row = [
        InlineKeyboardButton(f"⬅️ {prev_month}", callback_data=f"extmes_{prev_month}"),
        InlineKeyboardButton(f"{next_month} ➡️", callback_data=f"extmes_{next_month}")
    ]
    
    keyboard = [nav_row]
    
    current_month_str = datetime.now(timezone(timedelta(hours=-3))).strftime("%m/%Y")
    if target_month != current_month_str:
        keyboard.append([InlineKeyboardButton(f"📅 Voltar para Mês Atual", callback_data=f"extmes_{current_month_str}")])
        
    keyboard.append([InlineKeyboardButton("❌ Fechar Extrato", callback_data="close_panel")])
    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")

@security_check
async def extrato_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for the /extrato command."""
    current_month = datetime.now(timezone(timedelta(hours=-3))).strftime("%m/%Y")
    await show_cash_flow_month(update, context, current_month)

@security_check
async def list_pending_bills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for the /contas command. Defaults to the current real-world month."""
    current_month = datetime.now(timezone(timedelta(hours=-3))).strftime("%m/%Y")
    await show_bills_month(update, context, current_month)

@security_check
async def handle_inline_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Router for all Telegram Inline Buttons. Adapted for dynamic Income/Expense text."""
    query = update.callback_query
    await query.answer() 
    data = query.data

    if data == "close_panel":
        context.user_data.clear()
        await query.edit_message_text("✅ Painel fechado.", parse_mode="Markdown")
        return
        
    elif data == "cancel_fsm":
        context.user_data.clear()
        await query.edit_message_text("🛑 Ação cancelada. Você pode enviar novos recibos normalmente.", parse_mode="Markdown")
        return
    
    elif data.startswith("toggle_"):
        parts = data.split("_")
        bank = parts[1]
        variant = parts[2]
        target_month = parts[3]
        
        # Recria a chave do grupo
        group_key = f"{bank}_{variant}" if variant != "none" else bank
        
        # Acessa a memória de acordeons deste mês
        expanded_dict = context.user_data.setdefault(f"expanded_{target_month}", {})
        
        # Inverte o estado atual (Se True vira False, se False vira True)
        expanded_dict[group_key] = not expanded_dict.get(group_key, False)
        
        # Chama a função para desenhar a tela novamente com o novo estado
        await show_bills_month(update, context, target_month)
    
    elif data == "help_main":
        await help_command(update, context)
        return

    elif data.startswith("help_"):
        topic = data.split("_")[1]
        
        if topic == "lancamentos":
            text = (
                "📥 *COMO LANÇAR TRANSAÇÕES*\n\n"
                "Basta mandar uma mensagem — o Zotto entende tudo:\n\n"
                "✏️ *Texto Livre*\n"
                "_\"Padaria 18,50 no débito\"_\n"
                "_\"Recebi salário de 3000\"_\n"
                "_\"iPhone 12x no Nubank Ultravioleta\"_\n\n"
                "🔗 *Link de NFC-e*\n"
                "Cole o link do QR Code da nota fiscal direto no chat.\n\n"
                "📄 *PDF*\n"
                "Envie o arquivo da conta de luz, internet, fatura, etc.\n"
                "⚠️ _PDFs com senha (faturas de celular) ainda não são suportados._\n\n"
                "Após a análise, o Zotto envia um *resumo para você confirmar* antes de salvar."
            )
        elif topic == "painel":
            text = (
                "🗓️ *PAINEL DE CONTAS (/contas)*\n\n"
                "🔴 *Vencida* — Parcela com data de vencimento no passado\n"
                "🔹 *Pendente* — Parcela em aberto dentro do prazo\n"
                "💳 *Fatura* — Total consolidado de um cartão de crédito no mês\n"
                "   └ 🔸 Parcelas individuais dentro dessa fatura\n\n"
                "🔲 *Navegação:*\n"
                "⬅️ ➡️ Navega entre meses\n"
                "⏭️ Salta direto ao mês mais distante com pendências\n"
                "📅 Volta ao mês atual quando estiver navegando no calendário"
            )
        elif topic == "extrato":
            text = (
                "📊 *PAINEL DE EXTRATO (/extrato)*\n\n"
                "Sua visão gerencial e fluxo de caixa do mês.\n\n"
                "💰 *Saldos:*\n"
                "• *Atual:* Dinheiro líquido disponível hoje (Receitas Realizadas - Despesas Realizadas).\n"
                "• *Projetado:* Como terminará o mês após receber/pagar tudo que está previsto.\n"
                "• *Benefício:* Saldo isolado de VR/VA (não se mistura com o dinheiro líquido).\n\n"
                "🔲 *Legenda de Lançamentos:*\n"
                "▫️ Receita Realizada (Entrou na conta)\n"
                "▪️ Despesa Realizada (Saiu da conta)\n"
                "◽️ Receita Prevista (Salário a receber)\n"
                "🔶 Despesa Prevista (Conta a pagar)\n"
            )
        elif topic == "pagamentos":
            text = (
                "💸 *COMO PAGAR / BAIXAR*\n\n"
                "📌 *Parcela avulsa:* Clique em qualquer item → *Pagar / Antecipar*\n"
                "📌 *Fatura completa:* Clique no header 💳 → *Pagar Fatura Fechada*\n\n"
                "O bot pedirá a *data*, o *método* e o *valor pago*:\n"
                "• Clique em 📅 Hoje ou digite a data (`DD/MM/AAAA`)\n"
                "• Confirme de onde o dinheiro saiu\n"
                "• Clique em Valor Integral ou digite um menor (desconto)\n\n"
                "💡 *Dica: Boleto Futuro pago no Passado*\n"
                "Pagou um boleto de Maio *ontem*, mas enviou o PDF só hoje? Se você marcar como pago na hora, o Zotto assumirá a data de *hoje*. Para o registro contábil perfeito:\n\n"
                "1️⃣ *Lance como Previsto:* Envie o PDF e clique em *⏳ Ainda não paguei (Aberto)*. Ele salva no mês do vencimento.\n"
                "2️⃣ *Dê a baixa manual:* Abra o `/contas`, vá até o mês do vencimento e clique em *Pagar/Antecipar*.\n"
                "3️⃣ *Controle Absoluto:* Quando pedir a data, ignore o botão 'Hoje' e *digite a data de ontem* (Ex: `06/04/2026`). O Zotto puxará a conta pro extrato no dia exato!"
            )
        elif topic == "avancado":
            text = (
                "🔍 *RECURSOS AVANÇADOS*\n\n"
                "🗑️ *Cancelar Parcela (Conciliação):*\n"
                "Quando você lança a fatura do cartão como uma única transação do mês, "
                "use esta opção para marcar individualmente as parcelas previstas como "
                "ignoradas — sem apagar os meses futuros da mesma compra.\n\n"
                "⏭️ *Última Parcela (Modo Isolado):*\n"
                "Ao clicar em \"Pular para Última Parcela\" de uma compra parcelada, "
                "o painel entra no *Modo Isolado* — exibe apenas as parcelas daquela "
                "compra específica ao longo de todos os meses, ótimo para ver o saldo "
                "restante de um financiamento ou compra longa.\n"
                "Use *\"Voltar à Visão Geral\"* para sair do modo isolado."
            )
        elif topic == "cancelar":
            text = (
                "🛑 *BOTÃO DE EMERGÊNCIA (/cancelar)*\n\n"
                "Use este comando em duas situações:\n\n"
                "1️⃣ *Preso em uma pergunta:*\n"
                "Se o bot perguntar algo (ex: _Qual a data?_) e você desistir da ação ou digitar errado, mande `/cancelar` para ele esquecer tudo e voltar ao estado normal.\n\n"
                "2️⃣ *Limpar a Fila de IA:*\n"
                "Se você enviou várias notas e a IA entrou em espera por limite de uso (Rate Limit), digitar `/cancelar` limpa todas as suas notas pendentes que estão na fila do banco de dados."
            )    
            
        # Botões universais para retornar ou fechar
        keyboard = [
            [InlineKeyboardButton("⬅️ Voltar ao Menu", callback_data="help_main")],
            [InlineKeyboardButton("❌ Fechar Ajuda", callback_data="close_panel")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    elif data.startswith("extmes_"):
        parts = data.split("_")
        target_month = parts[1]
        await show_cash_flow_month(update, context, target_month)

    elif data.startswith("mes_"):
        parts = data.split("_")
        target_month = parts[1]
        filter_tx_id = int(parts[3]) if len(parts) > 3 and parts[2] == "tx" else None
        await show_bills_month(update, context, target_month, filter_tx_id=filter_tx_id)

    elif data.startswith("fatura_"):
        parts = data.split("_")
        bill_id = parts[1]
        target_month = parts[2]
        
        # Check if income or expense to adapt UI
        bills = get_pending_bills_by_month(target_month)
        bill = next((b for b in bills if str(b['id']) == bill_id), None)
        is_income = bill and bill.get('type', 'DESPESA') == 'RECEITA'

        title_text = "⚙️ *Gerenciar Recebimento*" if is_income else "⚙️ *Gerenciar Parcela*"
        action_text = "💸 Confirmar Recebimento" if is_income else "💸 Pagar / Antecipar"
        cancel_text = "🗑️ Cancelar (Ignorar Entrada)" if is_income else "🗑️ Cancelar (Ignorar Parcela)"

        text = f"{title_text}\nO que você deseja fazer com este item?"
        keyboard = [
            [InlineKeyboardButton(action_text, callback_data=f"pagar_{bill_id}_{target_month}")],
            [InlineKeyboardButton(cancel_text, callback_data=f"cancelar_{bill_id}_{target_month}")]
        ]
        
        max_month, tx_id = get_max_month_for_transaction(int(bill_id))
        if max_month and max_month != target_month and datetime.strptime(max_month, "%m/%Y") > datetime.strptime(target_month, "%m/%Y"):
            keyboard.append([InlineKeyboardButton(f"⏭️ Pular para Última Parcela ({max_month})", callback_data=f"mes_{max_month}_tx_{tx_id}")])
            
        keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data=f"mes_{target_month}")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("fatgroup_"):
        parts = data.split("_")
        bank = parts[1]
        variant = parts[2]
        target_month = parts[3]
        
        v_tag = f" {variant}" if variant != "none" else ""
        text = f"⚙️ *Gerenciar Fatura {bank}{v_tag}*\nO que você deseja fazer com a fatura integral deste mês?"
        
        keyboard = [
            [InlineKeyboardButton("💸 Pagar Fatura Fechada", callback_data=f"paygroup_{bank}_{variant}_{target_month}")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data=f"mes_{target_month}")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("pagar_"):
        parts = data.split("_")
        bill_id = int(parts[1])
        target_month = parts[2]
        
        # Check if income
        bills = get_pending_bills_by_month(target_month)
        bill = next((b for b in bills if str(b['id']) == str(bill_id)), None)
        is_income = bill and bill.get('type', 'DESPESA') == 'RECEITA'
        
        context.user_data["estado"] = "WAITING_FOR_BAIXA_METHOD"
        context.user_data["parcela_pagamento_id"] = bill_id
        context.user_data["parcela_target_month"] = target_month
        context.user_data["is_group_payment"] = False
        context.user_data["is_income"] = is_income
        
        if is_income:
            keyboard = [
                ["Pix", "Conta Corrente/Poupança"], 
                ["Cartão de Benefício", "Dinheiro"],
                ["🔄 Manter Método Original"]
            ]
            text = "💸 *Onde este valor entrou?*"
        else:
            keyboard = [
                ["Cartão de Crédito", "Cartão de Débito"], 
                ["Pix", "Dinheiro", "Boleto"],
                ["Cartão de Benefício", "🔄 Manter Método Original"]
            ]
            text = "💸 *Como você pagou esta conta?*"
            
        await query.edit_message_text("Prosseguindo com a baixa...", parse_mode="Markdown")
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True), parse_mode="Markdown")

    elif data.startswith("paygroup_"):
        parts = data.split("_")
        bank = parts[1]
        variant = parts[2]
        target_month = parts[3]
        
        context.user_data["estado"] = "WAITING_FOR_PAYMENT_DATE"
        context.user_data["parcela_target_month"] = target_month
        context.user_data["is_group_payment"] = True
        context.user_data["group_bank"] = bank
        context.user_data["group_variant"] = variant if variant != "none" else None
        
        keyboard = [
            [InlineKeyboardButton("📅 Hoje", callback_data=f"paydate_hoje_group")],
            [InlineKeyboardButton("❌ Cancelar Ação", callback_data="cancel_fsm")]
        ]
        await query.edit_message_text("📅 *Qual a data do pagamento da fatura?*\n(Clique no botão para Hoje ou digite a data: `DD/MM/YYYY`).", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("paydate_hoje_"):
        target_month = context.user_data.get("parcela_target_month")
        pay_date = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y")
        context.user_data["parcela_pagamento_data"] = pay_date
        context.user_data["estado"] = "WAITING_FOR_PAYMENT_AMOUNT"
        
        if context.user_data.get("is_group_payment"):
            bank = context.user_data.get("group_bank")
            variant = context.user_data.get("group_variant")
            await ask_for_payment_amount(context.bot, update.effective_chat.id, query, target_month, pay_date, group_bank=bank, group_variant=variant)
        else:
            bill_id = context.user_data.get("parcela_pagamento_id")
            await ask_for_payment_amount(context.bot, update.effective_chat.id, query, target_month, pay_date, bill_id=bill_id)

    elif data.startswith("payamt_full_single_"):
        bill_id = int(data.split("_")[3])
        pay_date = context.user_data.get("parcela_pagamento_data")
        
        # Puxa os métodos novos salvos na sessão
        n_method = context.user_data.get("baixa_new_method")
        n_bank = context.user_data.get("baixa_new_bank")
        n_variant = context.user_data.get("baixa_new_variant")
        
        success, msg = pay_bill_in_db(bill_id, pay_date, None, new_method=n_method, new_bank=n_bank, new_variant=n_variant)
        
        if success: 
            await query.edit_message_text(msg, parse_mode="Markdown")
            await context.bot.send_message(update.effective_chat.id, "✅ Operação concluída.", reply_markup=ReplyKeyboardRemove())
        else:
            await query.edit_message_text(f"❌ {msg}", parse_mode="Markdown")
        context.user_data.clear()
        
    elif data.startswith("payamt_full_group_"):
        parts = data.split("_")
        bank = parts[3]
        variant = parts[4] if parts[4] != "none" else None
        target_month = parts[5]
        pay_date = context.user_data.get("parcela_pagamento_data")
        
        success, msg = pay_grouped_card_bills_in_db(target_month, bank, variant, pay_date, None)
        if success:
            await query.edit_message_text(msg, parse_mode="Markdown")
        else:
            await query.edit_message_text(f"❌ {msg}", parse_mode="Markdown")
        context.user_data.clear()

    elif data.startswith("cancelar_"):
        parts = data.split("_")
        bill_id = int(parts[1])
        target_month = parts[2]
        if cancel_installment(bill_id):
            await query.edit_message_text("✅ *Registro ignorado/cancelado com sucesso!*\n(Isso não apaga outras parcelas originais).", parse_mode="Markdown")
            await asyncio.sleep(2)
            await show_bills_month(update, context, target_month)

@security_check
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Downloads PDF files, extracts their raw text using pypdf, and injects it into the DB Queue."""
    pdf_path = f"temp_{uuid.uuid4().hex}.pdf" 
    try:
        file = await update.message.document.get_file()
        await file.download_to_drive(pdf_path)
        
        reader = PdfReader(pdf_path)
        if reader.is_encrypted: raise Exception("PDF_CRIPTOGRAFADO")
        pdf_text = "".join([page.extract_text() + "\n" for page in reader.pages if page.extract_text()])
        
        if not pdf_text.strip(): raise Exception("ARQUIVO_VAZIO")
            
        add_to_queue(update.effective_chat.id, f"Extraia:\n\n{pdf_text}", is_pdf=True)
        await update.message.reply_text("📥 Recebido! A IA está analisando.")
        
    except Exception as e:
        if "PDF_CRIPTOGRAFADO" in str(e) or "PasswordRequiredException" in str(e):
            await update.message.reply_text("❌ *Erro:* PDF protegido por senha.", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ *Erro:* Arquivo corrompido ou sem texto.", parse_mode="Markdown")
    finally:
        if os.path.exists(pdf_path): os.remove(pdf_path)

@security_check
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    The Text Handler Engine.
    This function routes ALL typed user text. If the user has an active 'estado' (state) in context.user_data,
    it means the bot previously asked them a question. The text is treated as the answer to that state,
    and then pushed back to the 'dispatch_confirmation_triggers' evaluator to see what's next.
    If there is no state, the text is treated as a new financial transaction and sent to the LLM Queue.
    """
    chat_id = update.effective_chat.id

    if chat_id in TEMP_SESSION:
        context.user_data.update(TEMP_SESSION.pop(chat_id))

    state = context.user_data.get("estado")
    try:
        # FSM: Paying a Bill -> Asking Method
        if state == "WAITING_FOR_BAIXA_METHOD":
            ans = update.message.text.strip()
            if ans != "🔄 Manter Método Original":
                context.user_data["baixa_new_method"] = ans
            else:
                context.user_data["baixa_new_method"] = None
                
            method_needs_card = any(word in ans.lower() for word in ["cartão", "cartao", "crédito", "credito", "débito", "debito", "benefício", "beneficio"])
            
            if method_needs_card and ans != "🔄 Manter Método Original":
                buttons = [[f"{c['bank']} {c['variant']}".strip()] for c in list_cards_from_db()]
                buttons.append(["❌ Cancelar Ação"])
                context.user_data["estado"] = "WAITING_FOR_BAIXA_CARD"
                await update.message.reply_text("💳 Qual cartão?", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True))
                return
                
            context.user_data["estado"] = "WAITING_FOR_PAYMENT_DATE"
            bill_id = context.user_data["parcela_pagamento_id"]
            action_word = "recebimento" if context.user_data.get("is_income") else "pagamento"
            
            await update.message.reply_text("✅ Método registrado.", reply_markup=ReplyKeyboardRemove())
            keyboard = [[InlineKeyboardButton("📅 Hoje", callback_data=f"paydate_hoje_{bill_id}")], [InlineKeyboardButton("❌ Cancelar Ação", callback_data="cancel_fsm")]]
            await update.message.reply_text(f"📅 *Qual a data do {action_word}?*\n(Clique no botão para Hoje ou digite a data: `DD/MM/YYYY`).", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return
            
        # FSM: Paying a Bill -> Asking Card
        if state == "WAITING_FOR_BAIXA_CARD":
            ans = update.message.text.strip()
            if ans == "❌ Cancelar Ação":
                context.user_data.clear()
                await update.message.reply_text("🛑 Ação cancelada.", reply_markup=ReplyKeyboardRemove())
                return
                
            parts = ans.split(" ", 1)
            context.user_data["baixa_new_bank"] = parts[0]
            context.user_data["baixa_new_variant"] = parts[1] if len(parts) > 1 else ""
            
            context.user_data["estado"] = "WAITING_FOR_PAYMENT_DATE"
            bill_id = context.user_data["parcela_pagamento_id"]
            action_word = "recebimento" if context.user_data.get("is_income") else "pagamento"
            
            await update.message.reply_text("✅ Cartão registrado.", reply_markup=ReplyKeyboardRemove())
            keyboard = [[InlineKeyboardButton("📅 Hoje", callback_data=f"paydate_hoje_{bill_id}")], [InlineKeyboardButton("❌ Cancelar Ação", callback_data="cancel_fsm")]]
            await update.message.reply_text(f"📅 *Qual a data do {action_word}?*\n(Clique no botão para Hoje ou digite a data: `DD/MM/YYYY`).", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        # FSM: Paying a Bill -> Custom Date
        if state == "WAITING_FOR_PAYMENT_DATE":
            ans = update.message.text.lower().strip()
            target_month = context.user_data.get("parcela_target_month")
            is_group = context.user_data.get("is_group_payment", False)
            
            pay_date = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y") if ans == "hoje" else ans

            if re.match(r'^\d{2}/\d{2}$', pay_date):
                pay_date = f"{pay_date}/{datetime.now(timezone(timedelta(hours=-3))).year}"

            if not re.match(r'\d{2}/\d{2}/\d{4}', pay_date):
                await update.message.reply_text("❌ Formato inválido. Use DD/MM/YYYY ou 'hoje'.")
                return

            context.user_data["parcela_pagamento_data"] = pay_date
            context.user_data["estado"] = "WAITING_FOR_PAYMENT_AMOUNT"
            
            if is_group:
                bank = context.user_data.get("group_bank")
                variant = context.user_data.get("group_variant")
                await ask_for_payment_amount(context.bot, chat_id, None, target_month, pay_date, group_bank=bank, group_variant=variant)
            else:
                bill_id = context.user_data.get("parcela_pagamento_id")
                await ask_for_payment_amount(context.bot, chat_id, None, target_month, pay_date, bill_id=bill_id)
            return
            
        # FSM: Paying a Bill -> Custom Amount (Anticipation/Discount)
        if state == "WAITING_FOR_PAYMENT_AMOUNT":
            ans = update.message.text.lower().strip()
            pay_date = context.user_data.get("parcela_pagamento_data")
            is_group = context.user_data.get("is_group_payment", False)

            custom_amount = None
            if ans != "ok": 
                try:
                    clean_val = ans.replace("r$", "").replace(" ", "")
                    if "," in clean_val and "." in clean_val: clean_val = clean_val.replace(".", "").replace(",", ".")
                    elif "," in clean_val: clean_val = clean_val.replace(",", ".")
                    custom_amount = float(clean_val)
                except ValueError:
                    await update.message.reply_text("❌ Valor inválido. Digite apenas números (ex: `150,50`) ou clique no botão de valor integral.", parse_mode="Markdown")
                    return

            success = False
            msg = ""
            if is_group:
                bank = context.user_data.get("group_bank")
                variant = context.user_data.get("group_variant")
                target_month = context.user_data.get("parcela_target_month")
                success, msg = pay_grouped_card_bills_in_db(target_month, bank, variant, pay_date, custom_amount)
            else:
                bill_id = context.user_data.get("parcela_pagamento_id")
                n_method = context.user_data.get("baixa_new_method")
                n_bank = context.user_data.get("baixa_new_bank")
                n_variant = context.user_data.get("baixa_new_variant")
                
                success, msg = pay_bill_in_db(bill_id, pay_date, custom_amount, new_method=n_method, new_bank=n_bank, new_variant=n_variant)

            if success: 
                await update.message.reply_text(msg, parse_mode="Markdown")
            else: 
                await update.message.reply_text(f"❌ {msg}", parse_mode="Markdown")
            context.user_data.clear()
            return

        # FSM: Adding Transaction -> User inputs a fixed Payment Method
        if state == "AGUARDANDO_METODO_PAGAMENTO":
            choice = update.message.text
            t = context.user_data["transacao_pendente_json"]["transacoes"][0]
            choice_lower = choice.lower()
            
            if "aberto" in choice_lower or "não paguei" in choice_lower or "não recebi" in choice_lower: 
                t["metodo_pagamento"] = "Pendente/Aberto"
            else: 
                t["metodo_pagamento"] = choice
                
            context.user_data["estado"] = None
            context.user_data["is_pdf"] = False
            await dispatch_confirmation_triggers(context.bot, chat_id, context.user_data)
            return

        # FSM: Adding Transaction -> LLM missed the location, user provides it
        if state == "AGUARDANDO_LOCAL":
            t = context.user_data["transacao_pendente_json"]["transacoes"][0]
            if "local_compra" not in t or not isinstance(t["local_compra"], dict): t["local_compra"] = {}
            t["local_compra"]["nome"] = update.message.text.strip()
            context.user_data["estado"] = None
            await dispatch_confirmation_triggers(context.bot, chat_id, context.user_data)
            return

        # FSM: Adding Transaction -> User defines Financing/Boleto first installment date
        if state == "AGUARDANDO_DATA_PRIMEIRA_PARCELA":
            ans = update.message.text.strip()

            if re.match(r'^\d{2}/\d{2}$', ans):
                ans = f"{ans}/{datetime.now(timezone(timedelta(hours=-3))).year}"
            if not re.match(r'\d{2}/\d{2}/\d{4}', ans):
                await update.message.reply_text("❌ Formato inválido. Use DD/MM/YYYY (Ex: 15/05/2026).")
                return
            context.user_data["primeira_parcela_definida"] = ans
            context.user_data["estado"] = None
            await dispatch_confirmation_triggers(context.bot, chat_id, context.user_data)
            return

        # FSM: Adding Transaction -> User picks the Credit Card
        if state == "AGUARDANDO_SELECAO_CARTAO":
            choice = update.message.text
            if choice == "➕ Adicionar Novo Cartão":
                context.user_data["estado"] = "AGUARDANDO_NOME_NOVO_CARTAO"
                await update.message.reply_text("Qual o nome do cartão? (Ex: Nubank Ultravioleta, Itaú Black, Caju Benefício):", reply_markup=ReplyKeyboardRemove())
                return
            parts = choice.split(" ", 1)
            t = context.user_data["transacao_pendente_json"]["transacoes"][0]
            t["cartao"] = {"banco": parts[0], "variante": parts[1] if len(parts) > 1 else ""}
            context.user_data["estado"] = None
            await dispatch_confirmation_triggers(context.bot, chat_id, context.user_data)
            return

        # FSM: Adding Transaction -> Upserting a new card (Name)
        if state == "AGUARDANDO_NOME_NOVO_CARTAO":
            parts = update.message.text.split(" ", 1)
            context.user_data.update({"pendente_banco": parts[0], "pendente_variante": parts[1] if len(parts) > 1 else "", "estado": "AGUARDANDO_DATAS_CARTAO"})
            context.user_data["transacao_pendente_json"]["transacoes"][0]["cartao"] = {"banco": context.user_data["pendente_banco"], "variante": context.user_data["pendente_variante"]}
            await update.message.reply_text(f"Fechamento e vencimento? (Ex: 1 e 8)")
            return

        # FSM: Adding Transaction -> Upserting a new card (Dates)
        if state == "AGUARDANDO_DATAS_CARTAO":
            numbers = re.findall(r'\d+', update.message.text)
            if len(numbers) >= 2:
                save_card_to_db(context.user_data["pendente_banco"], context.user_data["pendente_variante"], int(numbers[0]), int(numbers[1]))
                await update.message.reply_text("✅ Cartão salvo!")
                context.user_data["estado"] = None
                await dispatch_confirmation_triggers(context.bot, chat_id, context.user_data)
            else: await update.message.reply_text("Responda com dois números (ex: 5 e 12).")
            return

        # FSM: Adding Transaction -> Final 'Yes/No' approval before inserting into PostgreSQL
        if state == "AGUARDANDO_CONFIRMACAO":
            if update.message.text.lower() in ["sim", "s"]:
                success, db_msg = save_transactions_to_db(context.user_data["transacao_pendente_json"])
                await update.message.reply_text("✅ Salvo!" if success else f"❌ Erro: {db_msg}", reply_markup=ReplyKeyboardRemove())
            else: await update.message.reply_text("🚫 Cancelado.", reply_markup=ReplyKeyboardRemove())
            context.user_data.clear()
            return

    except Exception as e:
        print(f"Panel Error: {e}")
        await update.message.reply_text("❌ Erro. Cancelado.", reply_markup=ReplyKeyboardRemove())
        context.user_data.clear()
        return

    # If the user has no active state, the text is a new receipt/invoice. Inject it into the Queue.
    if not state:
        add_to_queue(chat_id, update.message.text, is_pdf=False)
        await update.message.reply_text("📥 Recebido! A IA está analisando.")

@security_check
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Mande seus gastos ou PDFs de contas para análise.")

@security_check
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Renders the instruction manual for the user.
    Accessible via the /help command.
    """

    text = (
        "🤖 *Manual do Zotto — ERP Financeiro Pessoal*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Bem-vindo à central de ajuda!\n"
        "Escolha um tópico abaixo para ver os detalhes:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📥 Como lançar transações", callback_data="help_lancamentos")],
        [InlineKeyboardButton("🗓️ Painel de Contas (/contas)", callback_data="help_painel")],
        [InlineKeyboardButton("📊 Painel de Extrato (/extrato)", callback_data="help_extrato")],
        [InlineKeyboardButton("💸 Como Pagar / Baixar", callback_data="help_pagamentos")],
        [InlineKeyboardButton("🔍 Recursos Avançados", callback_data="help_avancado")],
        [InlineKeyboardButton("🛑 Cancelar Ações (/cancelar)", callback_data="help_cancelar")],
        [InlineKeyboardButton("❌ Fechar Ajuda", callback_data="close_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Verifica se foi chamado pelo comando /help ou pelo botão "Voltar"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# --- Application Entry Point ---
if __name__ == '__main__':
    create_tables()
    print(f"🚀 Iniciando app em ({ENV.upper()})...")
    
    # Builds the Telegram Bot application loop
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Hooks the background worker queue_processor to run every 10 seconds asynchronously 
    app.job_queue.run_repeating(queue_processor, interval=10, first=5)
    
    # Registers command routers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("cancelar", cancel_command))
    app.add_handler(CommandHandler("contas", list_pending_bills))
    app.add_handler(CommandHandler("extrato", extrato_command))
    app.add_handler(CommandHandler("help", help_command))
    
    # Registers payload routers
    app.add_handler(CallbackQueryHandler(handle_inline_button)) 
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Starts Long Polling (listening to Telegram servers)
    app.run_polling()