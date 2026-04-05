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
    check_similar_transaction, cancel_queue_items, get_pending_bills_by_month, pay_bill_in_db
)

ENV = os.getenv("ENVIRONMENT", "dev").lower()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN_PROD") if ENV == "prod" else os.getenv("TELEGRAM_TOKEN_DEV")
GROQ_API_KEY = os.getenv("GROQ_API_KEY_PROD") if ENV == "prod" else os.getenv("GROQ_API_KEY_DEV")

ALLOWED_CHAT_IDS = [int(x.strip()) for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()]

groq_client = AsyncGroq(api_key=GROQ_API_KEY)
TEMP_SESSION = {}
ACTIVE_CHATS = set()

# --- Prompts ---
PROMPT_AGENTE_1 = """
Você é um extrator de dados de notas fiscais e textos financeiros. Hoje é [DATA_ATUAL].
Sua função é ler o texto e extrair os dados. Se o texto for informal, deduza o local e os itens.

ESTRUTURA DE SAÍDA OBRIGATÓRIA (Apenas JSON):
{
  "sucesso": true,
  "mensagem_interacao": "Ok",
  "cabecalho": {
    "tipo_transacao": "RECEITA ou DESPESA",
    "local": "NOME DA EMPRESA fornecedora. 🚨 Se não souber ou não for claro, retorne 'Não Informado'.",
    "_raciocinio_vencimento": "1. PDF convertido perde formatação. 2. PROIBIDO usar 'DATA DE EMISSÃO'. Ignore datas perto de SÉRIE/Protocolo. 3. Vencimento costuma ser linha com 'Mês/Ano Data Valor'. Qual é o vencimento real e por quê?",
    "dt_transacao": "DD/MM/YYYY (Use a data de VENCIMENTO descoberta no raciocínio. Para compras normais, a data da compra)",
    "numero_nota": "Número da nota ou null",
    "serie_nota": "Série ou null",
    "valor_total_bruto": 0.00,
    "desconto_total": 0.00,
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

PROMPT_AGENTE_2 = """
Você é um Analista Financeiro Sênior. Hoje é [DATA_ATUAL].
Sua missão é enriquecer e categorizar o JSON recebido.

MAPA DE CATEGORIAS (DESPESAS):
- Alimentação > Hortifruti | Carnes | Mercearia | Laticínios | Bebidas | Padaria | Restaurante | Limpeza
- Moradia > Contas Residenciais (Contas de Gás, Energia, Água, etc.) | Aluguel | Manutenção
- Transporte > Combustível | App de Transporte | Passagens | Manutenção Veicular
- Saúde e Beleza > Farmácia | Consultas/Exames | Cuidados Pessoais | Higiene Pessoal
- Lazer e Cultura > Livros | Ingressos | Jogos | Viagem
- Educação > Cursos | Material Escolar
- Compras > Vestuário | Eletrônicos | Casa/Móveis
- Serviços > Assinaturas | Manutenção Geral
- Outros > Despesas diversas
MAPA DE CATEGORIAS (RECEITAS):
- Entradas > Salário | Rendimentos | Aluguel | Reembolso | Vendas | Cashback | Outros

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
    """Decorator to enforce Whitelist Security."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if ALLOWED_CHAT_IDS and update.effective_chat.id not in ALLOWED_CHAT_IDS:
            print(f"🚨 Acesso negado para ID: {update.effective_chat.id}")
            return
        return await func(update, context)
    return wrapper

def extract_text_from_url(url):
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        for script_or_style in soup(['script', 'style']): script_or_style.extract()
        return '\n'.join([linha.strip() for linha in soup.get_text(separator=' ').splitlines() if linha.strip()])
    except Exception as e: return f"Erro ao acessar link: {str(e)}"

def extract_json_from_response(raw_text):
    match = re.search(r'\{[\s\S]*\}', raw_text)
    if not match: return None
    json_text = match.group(0)
    json_text = re.sub(r'(?<![:"\/])\/\/.*', '', json_text)
    json_text = json_text.replace(": False", ": false").replace(": True", ": true").replace(": None", ": null")
    json_text = json_text.replace(":False", ":false").replace(":True", ":true").replace(":None", ":null")
    try: return json.loads(json_text, strict=False)
    except: return None

def calculate_invoice_due_date(purchase_date, closing_day, due_day):
    base_month = purchase_date.replace(day=1)
    if purchase_date.day >= closing_day:
        base_month += relativedelta(months=1)
    if due_day < closing_day:
        base_month += relativedelta(months=1)
    return base_month + relativedelta(day=due_day)

def generate_installment_details(total_amount, total_installments, transaction_date_str, card_rules, payment_method, transaction_type="DESPESA", first_inst_date=None):
    details = []
    actual_installments = max(1, total_installments)
    installment_value = round(total_amount / actual_installments, 2)
    
    try: tx_date = datetime.strptime(transaction_date_str, "%d/%m/%Y")
    except: tx_date = datetime.now(timezone(timedelta(hours=-3)))
        
    closing = int(card_rules.get("closing", 0)) if card_rules else 0
    due = int(card_rules.get("due", 0)) if card_rules else 0
    method_str = str(payment_method).lower()
    
    # --- LOGICA DA PRIMEIRA PARCELA PARA FINANCIAMENTO ---
    if first_inst_date:
        try: base_date = datetime.strptime(first_inst_date, "%d/%m/%Y")
        except: base_date = tx_date
    elif card_rules and closing == 0 and due == 0: base_date = tx_date
    elif "crédito" in method_str or "credito" in method_str:
        if card_rules: base_date = calculate_invoice_due_date(tx_date, closing, due)
        else: base_date = tx_date + relativedelta(months=1)
    else: base_date = tx_date

    cash_keywords = ["débito", "debito", "pix", "dinheiro", "conta corrente", "poupança", "benefício", "pré-pago"]
    is_cash_payment = any(word in method_str for word in cash_keywords)
    
    payment_status = "PAID" if (is_cash_payment or str(transaction_type).upper() == "RECEITA") and "aberto" not in method_str else "PENDING"
    date_paid = tx_date.strftime("%d/%m/%Y") if payment_status == "PAID" else None
    paid_value = installment_value if payment_status == "PAID" else 0.0

    for i in range(actual_installments):
        installment_date = base_date + relativedelta(months=i)
        details.append({
            "mes": installment_date.strftime("%m/%Y"), 
            "data_vencimento": installment_date.strftime("%d/%m/%Y"), 
            "valor": installment_value, "status_pagamento": payment_status,
            "dt_pagamento": date_paid, "valor_pago": paid_value
        })
    return details

async def queue_processor(context: ContextTypes.DEFAULT_TYPE):
    item = get_next_in_queue()
    if not item: return

    chat_id = item['chat_id']

    user_state = context.application.user_data.get(chat_id, {}).get("estado")
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
        
        chat_ext = await groq_client.chat.completions.create(
            messages=[{"role": "system", "content": prompt_1}, {"role": "user", "content": text_to_process}],
            model="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0.0, max_tokens=8000
        )
        json_ext = extract_json_from_response(chat_ext.choices[0].message.content)
        if not json_ext: raise Exception("Falha na Estruturação.")

        chat_enr = await groq_client.chat.completions.create(
            messages=[{"role": "system", "content": prompt_2}, {"role": "user", "content": json.dumps(json_ext, ensure_ascii=False)}],
            model="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0.1, max_tokens=8000
        )
        final_json = extract_json_from_response(chat_enr.choices[0].message.content)
        if not final_json: raise Exception("Falha na Categorização.")

        for tx in final_json.get("transacoes", []):
            inv_num = tx.get("numero_nota")
            
            if inv_num and str(inv_num).lower() != "null":
                if check_existing_invoice(inv_num):
                    await context.bot.send_message(chat_id, f"🚫 *Duplicado!* A nota `{inv_num}` já foi enviada.", parse_mode="Markdown")
                    complete_queue_item(item['id'])
                    return
            else:
                tx["numero_nota"] = f"M-{random.randint(100000000, 999999999)}"
                loc_check = str(tx.get("local_compra", {}).get("nome", "DESCONHECIDO")).upper()
                if check_similar_transaction(loc_check, float(tx.get("valor_total") or 0.0), tx.get("dt_transacao") or today_str):
                    tx["alerta_duplicidade"] = True

            val_total = float(tx.get("valor_total") or 0.0)
            if val_total == 0.0 and tx.get("itens"):
                val_total = sum(float(i.get("valor_unitario", 0)) * float(i.get("quantidade", 1)) for i in tx["itens"])
                tx["valor_total"] = round(val_total, 2)
                
            if not tx.get("dt_transacao") or tx.get("dt_transacao") == "null": tx["dt_transacao"] = today_str
            
            for idx, it in enumerate(tx.get("itens", []), start=1):
                it["numero_item_nota"] = str(idx)
                if it.get("valor_unitario", 0.0) == 0.0:
                    it["valor_unitario"] = round(float(tx.get("valor_total") or 0) / max(1, float(it.get("quantidade") or 1)), 2)

        complete_queue_item(item['id'])
        
        TEMP_SESSION[chat_id] = {"transacao_pendente_json": final_json, "is_pdf": item['is_pdf'], "estado": None}
        await dispatch_confirmation_triggers(context.bot, chat_id, TEMP_SESSION[chat_id])

    except Exception as e:
        error_msg = str(e).lower()
        print(f"\n[ERRO FILA {item['id']}] Tentativa {current_attempt + 1}: {e}")
        
        if "429" in error_msg or "rate limit" in error_msg: 
            wait_seconds = 60
            match = re.search(r'try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?', error_msg)
            if match:
                h = float(match.group(1) or 0)
                m = float(match.group(2) or 0)
                s = float(match.group(3) or 0)
                wait_seconds = int(h * 3600 + m * 60 + s) + 15
            
            br_time = datetime.now(timezone(timedelta(hours=-3))) + timedelta(seconds=wait_seconds)
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

    trusted_methods = ["pix", "dinheiro", "conta", "poupança", "crédito", "credito", "débito", "debito", "cartão", "cartao", "benefício", "financiamento", "boleto", "aberta"]
    is_method_trusted = any(tm in method for tm in trusted_methods)
    is_missing_loc = str(loc_name).strip().lower() in clean_words or "desconhecido" in str(loc_name).strip().lower()

    if current_state != "AGUARDANDO_CONFIRMACAO":
        if user_data.get("is_pdf") or method in clean_words or not is_method_trusted:
            user_data["estado"] = "AGUARDANDO_METODO_PAGAMENTO"
            if tx_type == "RECEITA":
                keyboard = ReplyKeyboardMarkup([["Pix", "Conta Corrente/Poupança"], ["Dinheiro", "Cartão de Benefício"]], resize_keyboard=True, one_time_keyboard=True)
                await bot.send_message(chat_id, f"📄 Recebimento de *{loc_name}* (R$ {tx_val:.2f})\nOnde esse valor entrou?", reply_markup=keyboard, parse_mode="Markdown")
            else:
                keyboard = ReplyKeyboardMarkup([["Cartão de Crédito", "Cartão de Débito"], ["Pix", "Dinheiro"], ["Financiamento", "⏳ Ainda não paguei (Aberto)"]], resize_keyboard=True, one_time_keyboard=True)
                await bot.send_message(chat_id, f"📄 Compra em *{loc_name}* (R$ {tx_val:.2f})\nComo você pagou?", reply_markup=keyboard, parse_mode="Markdown")
            return

        if is_missing_loc:
            user_data["estado"] = "AGUARDANDO_LOCAL"
            await bot.send_message(chat_id, f"🏢 Qual foi o *Local/Nome* dessa transação no valor de R$ {tx_val:.2f}?", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
            return

        if ("cartão" in method or "cartao" in method or "crédito" in method or "débito" in method) and "benefício" not in method:
            if not bank:
                buttons = [[f"{c['bank']} {c['variant']}".strip()] for c in list_cards_from_db()]
                buttons.append(["➕ Adicionar Novo Cartão"])
                user_data["estado"] = "AGUARDANDO_SELECAO_CARTAO"
                await bot.send_message(chat_id, f"💳 Compra em *{loc_name}* (R$ {tx_val:.2f})\nQual cartão foi usado?", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True), parse_mode="Markdown")
                return
            else:
                db_card = get_card_from_db(bank, variant)
                if not db_card:
                    user_data.update({"estado": "AGUARDANDO_DATAS_CARTAO", "pendente_banco": bank, "pendente_variante": variant})
                    await bot.send_message(chat_id, f"💳 Cartão Novo: *{bank} {variant}*!\nQual *fechamento e vencimento*? (Ex: 1 e 8)", parse_mode="Markdown")
                    return

        parcels = int(tx.get("quantidade_parcelas") or 1)
        needs_first_date = "financiamento" in method or (parcels > 1 and "boleto" in method)
        if needs_first_date and not user_data.get("primeira_parcela_definida"):
            user_data["estado"] = "AGUARDANDO_DATA_PRIMEIRA_PARCELA"
            await bot.send_message(chat_id, f"📅 Qual a *Data de Vencimento da 1ª Parcela*?\n*(As outras {parcels-1} parcelas cairão no mesmo dia nos meses seguintes)*\n\nExemplo: `15/05/2026`", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
            return

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
    
    cat = tx.get("categoria_macro", "Não classificada")
    parcels = int(tx.get("quantidade_parcelas") or 1)
    
    summary = f"📈 *Resumo*\n🏢 *Origem:* {loc_name}\n📅 *Data:* {tx_date}\n" if tx_type == "RECEITA" else f"🛒 *Resumo*\n📍 *Local:* {loc_name}\n📅 *Data:* {tx_date}\n"
    summary += f"🏷️ *Categoria:* {cat}\n💰 *Valor:* R$ {float(tx.get('valor_total') or 0):.2f}\n💳 *Método:* {tx.get('metodo_pagamento')}"
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
    chat_id = update.effective_chat.id
    cancel_queue_items(chat_id)
    TEMP_SESSION.pop(chat_id, None)
    ACTIVE_CHATS.discard(chat_id)
    context.user_data.clear()
    await update.message.reply_text("🛑 *Cancelado!* Fila limpa.", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

@security_check
async def list_pending_bills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_month = datetime.now(timezone(timedelta(hours=-3))).strftime("%m/%Y")
    bills = get_pending_bills_by_month(current_month)

    if not bills:
        await update.message.reply_text(f"🎉 Tudo pago para {current_month}!")
        return

    keyboard = [[InlineKeyboardButton(f"❌ {b['location'][:15]} - R$ {b['amount']:.2f} ({b['due_date'][:5]})", callback_data=f"pagar_{b['id']}")] for b in bills]
    await update.message.reply_text(f"🗓️ *Pendentes {current_month}*\nClique para pagar:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

@security_check
async def handle_inline_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() 
    if query.data.startswith("pagar_"):
        context.user_data["estado"] = "WAITING_FOR_PAYMENT_DATE"
        context.user_data["parcela_pagamento_id"] = int(query.data.split("_")[1])
        await context.bot.send_message(update.effective_chat.id, "📅 *Quando pagou?* (Ex: `15/04/2026` ou `hoje`).", parse_mode="Markdown")

@security_check
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    chat_id = update.effective_chat.id

    if chat_id in TEMP_SESSION:
        context.user_data.update(TEMP_SESSION.pop(chat_id))

    state = context.user_data.get("estado")
    try:
        if state == "WAITING_FOR_PAYMENT_DATE":
            ans = update.message.text.lower().strip()
            bill_id = context.user_data.get("parcela_pagamento_id")
            pay_date = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y") if ans == "hoje" else ans
            if not re.match(r'\d{2}/\d{2}/\d{4}', pay_date):
                await update.message.reply_text("❌ Formato inválido.")
                return

            if pay_bill_in_db(bill_id, pay_date): await update.message.reply_text(f"✅ Baixado em `{pay_date}`!", parse_mode="Markdown")
            else: await update.message.reply_text("❌ Erro no banco.")
            context.user_data.clear()
            return
        
        if state == "AGUARDANDO_METODO_PAGAMENTO":
            choice = update.message.text
            t = context.user_data["transacao_pendente_json"]["transacoes"][0]
            if "aberto" in choice.lower() or "não paguei" in choice.lower(): t["metodo_pagamento"] = "Fatura Aberta/Boleto"
            else: t["metodo_pagamento"] = choice
            context.user_data["estado"] = None
            await dispatch_confirmation_triggers(context.bot, chat_id, context.user_data)
            return

        if state == "AGUARDANDO_LOCAL":
            t = context.user_data["transacao_pendente_json"]["transacoes"][0]
            if "local_compra" not in t or not isinstance(t["local_compra"], dict): t["local_compra"] = {}
            t["local_compra"]["nome"] = update.message.text.strip()
            context.user_data["estado"] = None
            await dispatch_confirmation_triggers(context.bot, chat_id, context.user_data)
            return

        if state == "AGUARDANDO_DATA_PRIMEIRA_PARCELA":
            ans = update.message.text.strip()
            if not re.match(r'\d{2}/\d{2}/\d{4}', ans):
                await update.message.reply_text("❌ Formato inválido. Use DD/MM/YYYY (Ex: 15/05/2026).")
                return
            context.user_data["primeira_parcela_definida"] = ans
            context.user_data["estado"] = None
            await dispatch_confirmation_triggers(context.bot, chat_id, context.user_data)
            return

        if state == "AGUARDANDO_SELECAO_CARTAO":
            choice = update.message.text
            if choice == "➕ Adicionar Novo Cartão":
                context.user_data["estado"] = "AGUARDANDO_NOME_NOVO_CARTAO"
                await update.message.reply_text("Qual o nome do cartão? (Ex: Nubank Ultravioleta, Itaú Black):", reply_markup=ReplyKeyboardRemove())
                return
            parts = choice.split(" ", 1)
            t = context.user_data["transacao_pendente_json"]["transacoes"][0]
            t["cartao"] = {"banco": parts[0], "variante": parts[1] if len(parts) > 1 else ""}
            context.user_data["estado"] = None
            await dispatch_confirmation_triggers(context.bot, chat_id, context.user_data)
            return

        if state == "AGUARDANDO_NOME_NOVO_CARTAO":
            parts = update.message.text.split(" ", 1)
            context.user_data.update({"pendente_banco": parts[0], "pendente_variante": parts[1] if len(parts) > 1 else "", "estado": "AGUARDANDO_DATAS_CARTAO"})
            context.user_data["transacao_pendente_json"]["transacoes"][0]["cartao"] = {"banco": context.user_data["pendente_banco"], "variante": context.user_data["pendente_variante"]}
            await update.message.reply_text(f"Fechamento e vencimento? (Ex: 1 e 8)")
            return

        if state == "AGUARDANDO_DATAS_CARTAO":
            numbers = re.findall(r'\d+', update.message.text)
            if len(numbers) >= 2:
                save_card_to_db(context.user_data["pendente_banco"], context.user_data["pendente_variante"], int(numbers[0]), int(numbers[1]))
                await update.message.reply_text("✅ Cartão salvo!")
                context.user_data["estado"] = None
                await dispatch_confirmation_triggers(context.bot, chat_id, context.user_data)
            else: await update.message.reply_text("Responda com dois números (ex: 5 e 12).")
            return

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

    if not state:
        add_to_queue(chat_id, update.message.text, is_pdf=False)
        await update.message.reply_text("📥 Recebido! A IA está analisando.")

@security_check
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Mande seus gastos ou PDFs de contas para análise.")

if __name__ == '__main__':
    create_tables()
    print(f"🚀 Iniciando app em ({ENV.upper()})...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.job_queue.run_repeating(queue_processor, interval=10, first=5)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("cancelar", cancel_command))
    app.add_handler(CommandHandler("contas", list_pending_bills)) 
    app.add_handler(CallbackQueryHandler(handle_inline_button)) 
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.run_polling()