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
    add_to_queue, get_next_in_queue, reschedule_queue_item, complete_queue_item, check_existing_invoice,
    check_similar_transaction, cancel_queue_items, get_pending_bills_by_month, pay_bill_in_db
)

# --- Environment & Credentials Setup ---
ENV = os.getenv("ENVIRONMENT", "dev").lower()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN_PROD") if ENV == "prod" else os.getenv("TELEGRAM_TOKEN_DEV")
GROQ_API_KEY = os.getenv("GROQ_API_KEY_PROD") if ENV == "prod" else os.getenv("GROQ_API_KEY_DEV")

groq_client = AsyncGroq(api_key=GROQ_API_KEY)
TEMP_SESSION = {} # In-memory session tracking for State Machine

# --- Prompts (Kept in Portuguese to guide the LLM output language) ---
PROMPT_AGENTE_1 = """
Você é um extrator de dados de notas fiscais e textos financeiros. Hoje é [DATA_ATUAL].
Sua função é ler o texto e extrair os dados. Se o texto for informal, deduza o local e os itens.

ESTRUTURA DE SAÍDA OBRIGATÓRIA (Apenas JSON):
{
  "sucesso": true,
  "mensagem_interacao": "Ok",
  "cabecalho": {
    "tipo_transacao": "RECEITA ou DESPESA (Analise o contexto: 'recebi', 'salário' = RECEITA. 'comprei', 'paguei' = DESPESA)",
    "local": "NOME DA EMPRESA fornecedora (Ex: Ultragaz, Copel, Vivo). 🚨 REGRA: NUNCA use o endereço residencial do cliente. Se a empresa não estiver clara no topo, deduza pela URL do site descrita no texto (ex: 'minhaultragaz' = Ultragaz).",
    "_raciocinio_vencimento": "1. O documento é um PDF convertido, então a palavra 'Vencimento' perdeu a formatação. 2. É ESTTRITAMENTE PROIBIDO usar a 'DATA DE EMISSÃO'. Ignore a data que aparece junto com 'SÉRIE', 'Protocolo' ou 'Chave de Acesso'. 3. O vencimento real costuma estar em uma linha com o padrão 'Mês/Ano Data Valor' (Ex: '03/2026 10/04/2026 R$83,41') ou nas instruções do banco (Ex: 'PAGAVEL PREFERENCIALMENTE... 10/04/2026'). Qual é a data de vencimento real encontrada e por quê?",
    "dt_transacao": "DD/MM/YYYY (Use a data de VENCIMENTO descoberta no raciocínio acima. Para compras diárias, use a data da compra)",
    "numero_nota": "Número da nota ou null",
    "serie_nota": "Série ou null",
    "valor_total_bruto": 0.00,
    "desconto_total": 0.00,
    "valor_total": 0.00,
    "metodo_pagamento": "Dinheiro, Cartão de Crédito, Cartão de Débito, Pix, Boleto, Conta Corrente ou null",
    "quantidade_parcelas": 1,
    "cartao": { "banco": "Banco ou null", "variante": "Variante ou null" }
  },
  "itens": [
    {
      "codigo": "Código ou null",
      "nome": "Nome exato do item ou motivo do recebimento",
      "quantidade": 1.0,
      "valor_unitario": 0.00
    }
  ]
}
"""

PROMPT_AGENTE_2 = """
Você é um Analista Financeiro Sênior. Hoje é [DATA_ATUAL].
Sua missão é enriquecer e categorizar o JSON recebido.

MAPA DE CATEGORIAS (DESPESAS):
- Alimentação > Hortifruti | Carnes | Mercearia | Laticínios | Bebidas | Padaria | Restaurante/Lanche | Limpeza
- Moradia > Contas Residenciais | Aluguel | Manutenção
- Transporte > Combustível | App de Transporte | Passagens | Manutenção Veicular
- Saúde e Beleza > Farmácia | Consultas/Exames | Cuidados Pessoais
- Lazer e Cultura > Livros e Revistas | Ingressos/Eventos | Jogos | Viagem
- Educação > Cursos | Material Escolar
- Compras > Vestuário | Eletrônicos | Casa/Móveis
- Serviços > Assinaturas | Manutenção Geral | Limpeza
- Outros > Despesas diversas

MAPA DE CATEGORIAS (RECEITAS):
- Entradas > Salário | Rendimentos | Aluguel | Reembolso | Vendas | Cashback | Outros

REGRAS DE CLASSIFICAÇÃO:
- Se "tipo_transacao" for RECEITA, use EXCLUSIVAMENTE o mapa de RECEITAS.
- Se "tipo_transacao" for DESPESA, use o mapa de DESPESAS.
- valor_original: Copie "valor_total_bruto".
- desconto_aplicado: Copie "desconto_total" (se null, 0.0).
- valor_total: Copie "valor_total".
- quantidade_parcelas: Se null ou 0, assuma 1.
- metodo_pagamento: Se null, retorne "Desconhecido".
- parcelado: true se > 1.

REGRAS DE FORMATAÇÃO JSON (CRÍTICAS E OBRIGATÓRIAS):
1. Retorne APENAS o JSON válido. Nenhuma frase antes ou depois.
2. NÃO use comentários (//) dentro do JSON.
3. NÃO use aspas duplas (") dentro dos valores de texto para não quebrar a estrutura da string.

ESTRUTURA DO JSON FINAL:
{
  "sucesso": true,
  "mensagem_interacao": "Ok",
  "transacoes": [
    {
      "tipo_transacao": "String",
      "numero_nota": "Número ou null",
      "serie_nota": "Série ou null",
      "dt_transacao": "DD/MM/YYYY (Preserve a DATA DE VENCIMENTO extraída)",
      "local_compra": { "nome": "Nome", "tipo": "Físico | Online | App | Boleto/Fatura | Depósito" },
      "status": "Ativa",
      "cartao": { "banco": "Nome ou null", "variante": "Nome ou null" },
      "valor_original": 0.00,
      "desconto_aplicado": 0.00,
      "valor_total": 0.00,
      "categoria_macro": "Categoria principal do mapa",
      "metodo_pagamento": "String",
      "parcelado": false,
      "quantidade_parcelas": 1,
      "itens": [
        {
          "numero_item_nota": null,
          "item": "Nome do item",
          "codigo_produto": "Código ou null",
          "marca": "Marca ou null",
          "valor_unitario": 0.00,
          "quantidade": 1.0,
          "hierarquia_categorias": { "macro": "Mapa", "categoria": "Mapa", "subcategoria": "Mapa", "produto": "Nome" }
        }
      ]
    }
  ]
}
"""

def extract_text_from_url(url):
    """Scrapes raw text from a given URL (e.g., NFC-e electronic invoices)."""
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        for script_or_style in soup(['script', 'style']): script_or_style.extract()
        return '\n'.join([linha.strip() for linha in soup.get_text(separator=' ').splitlines() if linha.strip()])
    except Exception as e: 
        return f"Erro ao acessar link: {str(e)}"

def extract_json_from_response(raw_text):
    """Extracts and sanitizes JSON payload from LLM unstructured output."""
    match = re.search(r'\{[\s\S]*\}', raw_text)
    if not match:
        print(f"\n⚠️ NENHUM JSON ENCONTRADO. Texto Bruto:\n{raw_text}\n")
        return None
        
    json_text = match.group(0)
    
    # Strip LLM hallucinations (comments) and boolean artifacts
    json_text = re.sub(r'(?<![:"\/])\/\/.*', '', json_text)
    json_text = json_text.replace(": False", ": false").replace(": True", ": true").replace(": None", ": null")
    json_text = json_text.replace(":False", ":false").replace(":True", ":true").replace(":None", ":null")
    
    try: 
        # strict=False allows parsing unescaped control characters (e.g., raw \n in PDF bills)
        return json.loads(json_text, strict=False)
    except Exception as e:
        print(f"\n⚠️ ERRO DE DECODIFICAÇÃO JSON: {e}")
        print(f"Texto que a IA gerou e o Python não conseguiu ler:\n{json_text}\n")
        return None

def calculate_invoice_due_date(purchase_date, closing_day, due_day):
    """Calculates the specific due date based on credit card closing rules."""
    invoice_month = purchase_date.month
    invoice_year = purchase_date.year
    
    if purchase_date.day >= closing_day:
        invoice_month = 1 if invoice_month == 12 else invoice_month + 1
        if invoice_month == 1: invoice_year += 1
        
    due_month = invoice_month
    due_year = invoice_year
    
    if due_day < closing_day:
        due_month = 1 if due_month == 12 else due_month + 1
        if due_month == 1: due_year += 1
        
    return datetime(due_year, due_month, due_day)

def generate_installment_details(total_amount, total_installments, transaction_date_str, card_rules, payment_method, transaction_type="DESPESA"):
    """Splits transactions into detailed installments (AP/AR Ledger structure)."""
    details = []
    actual_installments = max(1, total_installments)
    installment_value = round(total_amount / actual_installments, 2)
    
    try: tx_date = datetime.strptime(transaction_date_str, "%d/%m/%Y")
    except: tx_date = datetime.now(timezone(timedelta(hours=-3)))
        
    closing = int(card_rules.get("closing", 0)) if card_rules else 0
    due = int(card_rules.get("due", 0)) if card_rules else 0
    method_str = str(payment_method).lower()
    
    if card_rules and closing == 0 and due == 0: 
        base_date = tx_date
    elif "crédito" in method_str or "credito" in method_str:
        if card_rules: base_date = calculate_invoice_due_date(tx_date, closing, due)
        else: base_date = tx_date + relativedelta(months=1)
    else:
        base_date = tx_date

    # Automatic Payment Status Logic
    cash_keywords = ["débito", "debito", "pix", "dinheiro", "conta corrente", "poupança", "benefício", "pré-pago"]
    is_cash_payment = any(word in method_str for word in cash_keywords)
    is_income = str(transaction_type).upper() == "RECEITA"
    is_open = "aberto" in method_str 
    
    payment_status = "PAID" if (is_cash_payment or is_income) and not is_open else "PENDING"
    date_paid = tx_date.strftime("%d/%m/%Y") if payment_status == "PAGO" else None
    paid_value = installment_value if payment_status == "PAGO" else 0.0

    for i in range(actual_installments):
        installment_date = base_date + relativedelta(months=i)
        details.append({
            "mes": installment_date.strftime("%m/%Y"), 
            "data_vencimento": installment_date.strftime("%d/%m/%Y"), 
            "valor": installment_value,
            "status_pagamento": payment_status,
            "dt_pagamento": date_paid,
            "valor_pago": paid_value
        })
    return details

def extract_backoff_time(error_str):
    """Extracts wait time from API rate limit error messages."""
    minutes, seconds = 0, 60
    match_m = re.search(r'(\d+)m', error_str)
    match_s = re.search(r'(\d+)(?:\.\d+)?s', error_str)
    if match_m or match_s:
        if match_m: minutes = int(match_m.group(1))
        if match_s: seconds = float(match_s.group(1))
        return int((minutes * 60) + seconds)
    return 60

async def queue_processor(context: ContextTypes.DEFAULT_TYPE):
    """Background Worker: Fetches, processes, and handles LLM Outbox transactions."""
    item = get_next_in_queue()
    if not item: return

    chat_id = item['chat_id']
    br_timezone = timezone(timedelta(hours=-3))
    today_str = datetime.now(br_timezone).strftime("%d/%m/%Y")
    current_attempt = item['attempts']
    
    try:
        # UX Rule: Reduced messaging. No "Processing..." spam. Silent background execution.
        text_to_process = item['text']
        
        if text_to_process.startswith("http://") or text_to_process.startswith("https://"):
            text_to_process = extract_text_from_url(text_to_process)
            if "Erro ao acessar link" in text_to_process:
                raise Exception("Não consegui ler o conteúdo do site.")

        dynamic_prompt_1 = PROMPT_AGENTE_1.replace("[DATA_ATUAL]", today_str)
        dynamic_prompt_2 = PROMPT_AGENTE_2.replace("[DATA_ATUAL]", today_str)
        
        # Agent 1: Extraction
        chat_extractor = await groq_client.chat.completions.create(
            messages=[{"role": "system", "content": dynamic_prompt_1}, {"role": "user", "content": text_to_process}],
            model="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0.0, max_tokens=8000
        )
        json_agent_1 = extract_json_from_response(chat_extractor.choices[0].message.content)
        if not json_agent_1: raise Exception("A IA falhou ao estruturar os dados da Extração.")

        # Agent 2: Enrichment
        chat_enricher = await groq_client.chat.completions.create(
            messages=[{"role": "system", "content": dynamic_prompt_2}, {"role": "user", "content": json.dumps(json_agent_1, ensure_ascii=False)}],
            model="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0.1, max_tokens=8000
        )
        final_json = extract_json_from_response(chat_enricher.choices[0].message.content)
        if not final_json: raise Exception("A IA falhou ao categorizar os dados finais.")

        # Data Governance & Heuristics applied post-LLM
        for tx in final_json.get("transacoes", []):
            invoice_num = tx.get("numero_nota")
            if invoice_num and str(invoice_num).lower() != "null":
                if check_existing_invoice(invoice_num):
                    await context.bot.send_message(chat_id, f"🚫 **Registro Duplicado!**\nO documento nº `{invoice_num}` já foi salvo.")
                    complete_queue_item(item['id'])
                    return 
            else:
                random_invoice = random.randint(100000000, 999999999)
                tx["numero_nota"] = f"M-{random_invoice}"
                
                loc_check = str(tx.get("local_compra", {}).get("nome", "DESCONHECIDO")).upper()
                amount_check = float(tx.get("valor_total") or 0.0)
                date_check = tx.get("dt_transacao") or today_str
                
                if check_similar_transaction(loc_check, amount_check, date_check):
                    tx["alerta_duplicidade"] = True

            if not tx.get("dt_transacao") or tx.get("dt_transacao") == "null":
                tx["dt_transacao"] = today_str
                
            # Math Validation to prevent LLM hallucinations
            for idx, it in enumerate(tx.get("itens", []), start=1):
                it["numero_item_nota"] = str(idx)
                if it.get("valor_unitario", 0.0) == 0.0:
                    base_val = float(tx.get("valor_original") or tx.get("valor_total") or 0.0)
                    it["valor_unitario"] = round(base_val / max(1, float(it.get("quantidade") or 1)), 2)

            curr_total = float(tx.get("valor_total") or 0.0)
            if curr_total == 0.0:
                items_sum = sum(float(i.get("quantidade") or 1) * float(i.get("valor_unitario") or 0.0) for i in tx.get("itens", []))
                tx["valor_total"] = round(items_sum, 2)
                if float(tx.get("valor_original") or 0.0) == 0.0:
                    tx["valor_original"] = round(items_sum, 2)

        complete_queue_item(item['id'])
        TEMP_SESSION[chat_id] = {"transacao_pendente_json": final_json, "is_pdf": item['is_pdf']}
        await dispatch_confirmation_triggers(context.bot, chat_id, TEMP_SESSION[chat_id])

    except Exception as e:
        error_msg = str(e).lower()
        
        # Terminal Logging
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ❌ ERRO NA FILA - ID {item['id']} | Tentativa {current_attempt + 1}")
        print(f"Motivo: {e}")
        
        # Exponential Backoff Strategy
        if "429" in error_msg or "rate limit" in error_msg or "tokens" in error_msg:
            wait_time = extract_backoff_time(error_msg)
            print(f"Ação: Rate Limit detectado. Aguardando {wait_time}s exigidos pela API.")
        else:
            wait_time = min(60 * (2 ** current_attempt), 3600)
            print(f"Ação: Aplicando Backoff Exponencial. Aguardando {wait_time}s.")
            
        print("-" * 50)
            
        reschedule_queue_item(item['id'], wait_time, current_attempt)
        
        # UX Rule: Only alert the user softly on the first failure. Keep subsequent retries silent.
        if current_attempt == 0:
            if "429" in error_msg or "rate limit" in error_msg:
                await context.bot.send_message(chat_id, "⚠️ A IA atingiu o limite de requisições. O bot vai aguardar o tempo necessário e tentar sozinho em background até conseguir!")
            else:
                await context.bot.send_message(chat_id, "⚠️ Ocorreu um pequeno erro na extração. O bot vai aplicar esperas exponenciais e continuar tentando em background.")

async def dispatch_confirmation_triggers(bot, chat_id, user_data):
    """Generates the Telegram UX Summary and Interactive Menus for Human Confirmation."""
    json_data = user_data["transacao_pendente_json"]
    tx = json_data["transacoes"][0]
    
    tx_type = str(tx.get("tipo_transacao", "DESPESA")).upper()
    raw_method = tx.get("metodo_pagamento")
    method = str(raw_method).lower() if raw_method and str(raw_method).strip().lower() != "null" else "desconhecido"
    
    card_info = tx.get("cartao") or {}
    bank = card_info.get("banco")
    variant = card_info.get("variante")

    clean_words = ["null", "none", "não informado", "nao informado", "desconhecido", ""]
    if bank and str(bank).strip().lower() in clean_words:
        bank = None
    if variant and str(variant).strip().lower() in clean_words:
        variant = None

    formatted_date = tx.get("dt_transacao")
    current_state = user_data.get("estado")

    # Flow 1: Ask for payment method if unknown
    if current_state != "AGUARDANDO_CONFIRMACAO":
        if user_data.get("is_pdf") or method in ["boleto", "desconhecido", ""]:
            user_data["estado"] = "AGUARDANDO_METODO_PAGAMENTO"
            if tx_type == "RECEITA":
                keyboard = ReplyKeyboardMarkup([["Pix", "Conta Corrente/Poupança"], ["Dinheiro"]], resize_keyboard=True, one_time_keyboard=True)
                await bot.send_message(chat_id, "📄 Recebimento identificado! Onde esse valor entrou?", reply_markup=keyboard)
            else:
                keyboard = ReplyKeyboardMarkup([
                    ["Cartão de Crédito", "Cartão de Débito"], 
                    ["Pix", "Dinheiro"],
                    ["⏳ Ainda não paguei (Aberto)"]
                ], resize_keyboard=True, one_time_keyboard=True)
                await bot.send_message(chat_id, "📄 Transação extraída! Como você realizou o pagamento?", reply_markup=keyboard)
            return

        # Flow 2: Ask for Card Details if required
        if "cartão" in method or "cartao" in method or "crédito" in method or "débito" in method:
            if not bank:
                buttons = [[f"{c['bank']} {c['variant']}".strip()] for c in list_cards_from_db()]
                buttons.append(["➕ Adicionar Novo Cartão"])
                user_data["estado"] = "AGUARDANDO_SELECAO_CARTAO"
                keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
                await bot.send_message(chat_id, "💳 Qual cartão foi usado?", reply_markup=keyboard)
                return
            else:
                db_card = get_card_from_db(bank, variant)
                if not db_card:
                    user_data.update({"estado": "AGUARDANDO_DATAS_CARTAO", "pendente_banco": bank, "pendente_variante": variant})
                    await bot.send_message(chat_id, f"💳 Cartão Novo: **{bank} {variant}**!\nQual o **fechamento e vencimento**? (Ex: 1 e 8. Se for pré-pago, mande 0 e 0)")
                    return

    db_card = get_card_from_db(bank, variant) if bank else None

    # Force Prepaid logic to avoid phantom installments
    is_prepaid = db_card and db_card.get("closing") == 0 and db_card.get("due") == 0
    is_cash = method in ["débito", "debito", "pix", "dinheiro", "boleto", "conta corrente", "poupança"]
    
    if is_prepaid or is_cash or tx_type == "RECEITA":
        tx["quantidade_parcelas"] = 1
        tx["parcelado"] = False
        if is_prepaid and ("crédito" in method or "credito" in method):
            tx["metodo_pagamento"] = "Cartão de Benefício/Pré-pago"
            method = "benefício"

    # Pre-compute installments for review
    tx["detalhamento_parcelas"] = generate_installment_details(float(tx.get("valor_total") or 0.0), int(tx.get("quantidade_parcelas") or 1), formatted_date, db_card, method, tx_type)
    user_data["estado"] = "AGUARDANDO_CONFIRMACAO"
    
    # Building the Final Markdown Summary
    loc_info = tx.get("local_compra") or {}
    loc_name = loc_info.get("nome", "Local Desconhecido")
    cat = tx.get("categoria_macro", "Não classificada")
    parcels = int(tx.get("quantidade_parcelas") or 1)
    
    if tx_type == "RECEITA":
        summary = f"📈 **Resumo do Recebimento**\n🏢 **Origem:** {loc_name}\n"
    else:
        summary = f"🛒 **Resumo da Transação**\n📍 **Local:** {loc_name}\n"
        
    summary += f"🏷️ **Categoria:** {cat}\n💰 **Valor:** R$ {float(tx.get('valor_total') or 0):.2f}\n"
    summary += f"💳 **Método:** {tx.get('metodo_pagamento')}"
    if bank: summary += f" ({bank} {variant})\n"
    else: summary += "\n"
        
    if tx_type != "RECEITA": summary += f"📅 **Parcelas:** {parcels}x\n\n"
    else: summary += "\n"
    
    items_list = tx.get("itens", [])
    if items_list:
        summary += "📋 **Itens/Detalhes:**\n"
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
        summary += "**Vencimentos:**\n"
        for p in tx.get("detalhamento_parcelas", [])[:3]:
            icon = "✅" if p['status_pagamento'] == 'PAID' else "🔹"
            summary += f"{icon} {p['data_vencimento']} - R$ {float(p.get('valor') or 0):.2f}\n"
        if parcels > 3: summary += f"...e mais {parcels - 3} parcelas.\n"
        
    summary += f"\n📋 **ID Transação:** `{tx.get('numero_nota')}`\n"
    
    if tx.get("alerta_duplicidade"):
        summary += f"\n🚨 **ALERTA DE POSSÍVEL DUPLICIDADE:**\nJá existe registro de `R$ {tx.get('valor_total'):.2f}` em `{loc_name}` nesta exata data (`{formatted_date}`).\n\n⚠️ **Deseja salvar NOVAMENTE?**"
    else:
        summary += "\n⚠️ **Deseja salvar no banco de dados?**"
    
    keyboard = ReplyKeyboardMarkup([["Sim", "Não"]], resize_keyboard=True, one_time_keyboard=True)
    await bot.send_message(chat_id, summary, parse_mode="Markdown", reply_markup=keyboard)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Interrupts any pending workflow or queue for the user."""
    chat_id = update.effective_chat.id
    cancel_queue_items(chat_id)
    TEMP_SESSION.pop(chat_id, None)
    context.user_data.clear()
    await update.message.reply_text("🛑 **Operação Cancelada!**\nFila limpa.", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

async def list_pending_bills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /contas: Renders an inline UI with current month pending installments."""
    current_month = datetime.now(timezone(timedelta(hours=-3))).strftime("%m/%Y")
    bills = get_pending_bills_by_month(current_month)

    if not bills:
        await update.message.reply_text(f"🎉 Tudo pago! Você não tem contas pendentes registradas para {current_month}.")
        return

    keyboard = []
    for b in bills:
        btn_text = f"❌ {b['location'][:15]} - R$ {b['amount']:.2f} (Vence: {b['due_date'][:5]})"
        callback_data = f"pagar_{b['id']}" 
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"🗓️ **Contas Pendentes - {current_month}**\nClique no botão para marcar como pago:", reply_markup=reply_markup, parse_mode="Markdown")

async def handle_inline_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listens to Inline Button clicks (AP/AR Payments)."""
    query = update.callback_query
    await query.answer() 
    data = query.data

    if data.startswith("pagar_"):
        bill_id = int(data.split("_")[1])
        context.user_data["estado"] = "WAITING_FOR_PAYMENT_DATE"
        context.user_data["parcela_pagamento_id"] = bill_id
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="📅 **Quando você pagou essa conta?**\n\nResponda com a data (ex: `15/04/2026`) ou apenas digite `hoje`.",
            parse_mode="Markdown"
        )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """File entrypoint (PDFs). Reads text and queues for extraction."""
    try:
        file = await update.message.document.get_file()
        pdf_path = f"temp_{uuid.uuid4().hex}.pdf" 
        await file.download_to_drive(pdf_path)
        
        try:
            reader = PdfReader(pdf_path)
            if reader.is_encrypted:
                raise Exception("PDF_CRIPTOGRAFADO")
            pdf_text = "".join([page.extract_text() + "\n" for page in reader.pages if page.extract_text()])
            
            if not pdf_text.strip():
                raise Exception("ARQUIVO_VAZIO")
                
        except Exception as e:
            if "PDF_CRIPTOGRAFADO" in str(e) or "PasswordRequiredException" in str(e):
                await update.message.reply_text("❌ **Erro:** O PDF enviado está protegido por senha (comum em faturas bancárias ou de celular). Por favor, baixe a versão 'desbloqueada' do arquivo e envie novamente.", parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ **Erro ao ler o PDF:** O arquivo pode estar corrompido ou ser uma imagem escaneada sem texto.", parse_mode="Markdown")
            if os.path.exists(pdf_path): os.remove(pdf_path)
            return
            
        os.remove(pdf_path)
        add_to_queue(update.effective_chat.id, f"Extraia:\n\n{pdf_text}", is_pdf=True)
        # UX: Silent queueing
        await update.message.reply_text("📥 Recebido! Já enviei para a Inteligência Artificial analisar.")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Erro interno ao processar o arquivo: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Text entrypoint & State Machine Controller."""
    chat_id = update.effective_chat.id
    if chat_id in TEMP_SESSION: context.user_data.update(TEMP_SESSION.pop(chat_id))

    current_state = context.user_data.get("estado")
    try:
        if current_state == "WAITING_FOR_PAYMENT_DATE":
            answer = update.message.text.lower().strip()
            bill_id = context.user_data.get("parcela_pagamento_id")

            if answer == "hoje":
                pay_date = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y")
            else:
                if re.match(r'\d{2}/\d{2}/\d{4}', answer):
                    pay_date = answer
                else:
                    await update.message.reply_text("❌ Formato inválido. Digite no formato DD/MM/YYYY (ex: 15/04/2026) ou 'hoje'.")
                    return

            success = pay_bill_in_db(bill_id, pay_date)

            if success:
                await update.message.reply_text(f"✅ **Conta Baixada!**\nO pagamento foi registrado com a data de `{pay_date}`.\n\n_(Dica: Digite /contas para ver o que ainda falta)_", parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Erro ao atualizar o banco de dados.")

            context.user_data.clear()
            return
        
        if current_state == "AGUARDANDO_METODO_PAGAMENTO":
            choice = update.message.text
            t = context.user_data["transacao_pendente_json"]["transacoes"][0]
            
            if "Ainda não paguei" in choice or "Aberto" in choice:
                t["metodo_pagamento"] = "Fatura Aberta/Boleto"
                t["cartao"] = {"banco": None, "variante": None}
                t["detalhamento_parcelas"] = generate_installment_details(t.get("valor_total", 0.0), t.get("quantidade_parcelas", 1), t.get("dt_transacao"), None, "Boleto", t.get("tipo_transacao", "DESPESA"))
                context.user_data["estado"] = "AGUARDANDO_CONFIRMACAO"
                await dispatch_confirmation_triggers(context.bot, chat_id, context.user_data)
                return

            t["metodo_pagamento"] = choice
            if "Cartão" in choice:
                buttons = [[f"{c['bank']} {c['variant']}".strip()] for c in list_cards_from_db()]
                buttons.append(["➕ Adicionar Novo Cartão"])
                await update.message.reply_text("Qual cartão você usou?", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True))
                context.user_data["estado"] = "AGUARDANDO_SELECAO_CARTAO"
            else:
                t["cartao"] = {"banco": None, "variante": None}
                t["detalhamento_parcelas"] = generate_installment_details(t.get("valor_total", 0.0), t.get("quantidade_parcelas", 1), t.get("dt_transacao"), None, choice, t.get("tipo_transacao", "DESPESA"))
                context.user_data["estado"] = "AGUARDANDO_CONFIRMACAO"
                await dispatch_confirmation_triggers(context.bot, chat_id, context.user_data)
            return

        if current_state == "AGUARDANDO_SELECAO_CARTAO":
            choice = update.message.text
            if choice == "➕ Adicionar Novo Cartão":
                context.user_data["estado"] = "AGUARDANDO_NOME_NOVO_CARTAO"
                await update.message.reply_text("Digite o nome do banco e variante\n*(Ex: Nubank Ultravioleta, Caju Benefício)*:", reply_markup=ReplyKeyboardRemove())
            else:
                parts = choice.split(" ", 1)
                bank = parts[0]
                variant = parts[1] if len(parts) > 1 else ""
                t = context.user_data["transacao_pendente_json"]["transacoes"][0]
                t["cartao"] = {"banco": bank, "variante": variant}
                
                db_card = get_card_from_db(bank, variant)
                if not db_card:
                    context.user_data.update({"estado": "AGUARDANDO_DATAS_CARTAO", "pendente_banco": bank, "pendente_variante": variant})
                    await update.message.reply_text(f"💳 Cartão Novo: **{bank} {variant}**!\nQual o **fechamento e vencimento**? (Ex: 1 e 8. Se for benefício, responda 0 e 0)", reply_markup=ReplyKeyboardRemove())
                    return
                    
                t["detalhamento_parcelas"] = generate_installment_details(t.get("valor_total", 0.0), t.get("quantidade_parcelas", 1), t.get("dt_transacao"), db_card, t.get("metodo_pagamento", ""), t.get("tipo_transacao", "DESPESA"))
                context.user_data["estado"] = "AGUARDANDO_CONFIRMACAO"
                await dispatch_confirmation_triggers(context.bot, chat_id, context.user_data)
            return

        if current_state == "AGUARDANDO_NOME_NOVO_CARTAO":
            choice = update.message.text
            parts = choice.split(" ", 1)
            bank = parts[0]
            variant = parts[1] if len(parts) > 1 else ""
            context.user_data.update({"pendente_banco": bank, "pendente_variante": variant, "estado": "AGUARDANDO_DATAS_CARTAO"})
            context.user_data["transacao_pendente_json"]["transacoes"][0]["cartao"] = {"banco": bank, "variante": variant}
            await update.message.reply_text(f"Qual o **fechamento e vencimento** do {bank} {variant}?\n*(Ex: '1 e 8'. Se for benefício, responda '0 e 0')*")
            return

        if current_state == "AGUARDANDO_DATAS_CARTAO":
            numbers = re.findall(r'\d+', update.message.text)
            if len(numbers) >= 2:
                bank = context.user_data["pendente_banco"]
                variant = context.user_data["pendente_variante"]
                save_card_to_db(bank, variant, int(numbers[0]), int(numbers[1]))
                
                await update.message.reply_text(f"✅ Legal! Gravei o cartão {bank} {variant} (Fecha: {numbers[0]}, Vence: {numbers[1]}).")
                
                t = context.user_data["transacao_pendente_json"]["transacoes"][0]
                t["detalhamento_parcelas"] = generate_installment_details(t.get("valor_total", 0.0), t.get("quantidade_parcelas", 1), t.get("dt_transacao"), {"closing": int(numbers[0]), "due": int(numbers[1])}, t.get("metodo_pagamento", ""), t.get("tipo_transacao", "DESPESA"))
                context.user_data["estado"] = "AGUARDANDO_CONFIRMACAO"
                await dispatch_confirmation_triggers(context.bot, chat_id, context.user_data)
            else:
                await update.message.reply_text("Não entendi as datas. Responda com dois números (ex: 5 e 12).")
            return

        if current_state == "AGUARDANDO_CONFIRMACAO":
            if update.message.text.lower() in ["sim", "s"]:
                success, db_msg = save_transactions_to_db(context.user_data["transacao_pendente_json"])
                await update.message.reply_text("✅ Salvo no banco!" if success else f"❌ Erro: {db_msg}", reply_markup=ReplyKeyboardRemove())
            else: 
                await update.message.reply_text("🚫 Cancelado.", reply_markup=ReplyKeyboardRemove())
            context.user_data.clear()
            return

    except Exception as e:
        print(f"State Machine Error: {traceback.format_exc()}")
        await update.message.reply_text("❌ Ocorreu um erro no painel. Operação cancelada.", reply_markup=ReplyKeyboardRemove())
        context.user_data.clear()
        return

    # If no state is active, treat as raw text ingestion
    if not current_state:
        add_to_queue(chat_id, update.message.text, is_pdf=False)
        # UX: Silent queueing
        await update.message.reply_text("📥 Recebido! Já enviei para a Inteligência Artificial analisar.")

if __name__ == '__main__':
    create_tables()
    print(f"🚀 Iniciando o bot no ambiente: {ENV.upper()}...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.job_queue.run_repeating(queue_processor, interval=10, first=5)
    
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("Olá! Mande seus gastos ou receitas.")))
    app.add_handler(CommandHandler("cancelar", cancel_command))
    app.add_handler(CommandHandler("contas", list_pending_bills)) 
    app.add_handler(CallbackQueryHandler(handle_inline_button)) 
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    app.run_polling()