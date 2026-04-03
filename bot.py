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

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import AsyncGroq

from database import criar_tabelas, salvar_transacoes_no_banco, buscar_cartao_db, salvar_cartao_db, listar_cartoes_db, adicionar_na_fila, buscar_proximo_fila, reagendar_fila, concluir_fila, verificar_nota_existente, verificar_transacao_semelhante

# ==========================================
# 1. CONFIGURAÇÕES E CHAVES
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Agora o cliente é Async!
groq_client = AsyncGroq(api_key=GROQ_API_KEY)
SESSAO_TEMP = {}

# ==========================================
# 2. PROMPTS DOS AGENTES
# ==========================================
PROMPT_AGENTE_1 = """
Você é um extrator de dados de notas fiscais e textos financeiros. Hoje é [DATA_ATUAL].
Sua função é ler o texto e extrair os dados. Se o texto for informal (texto livre), deduza o local e os itens pelo contexto da frase.

ESTRUTURA DE SAÍDA OBRIGATÓRIA (Apenas JSON):
{
  "sucesso": true,
  "mensagem_interacao": "Ok",
  "cabecalho": {
    "local": "Nome da Empresa ou Local (Ex: Sebo, Vendedor, Mercado)",
    "data_compra": "DD/MM/YYYY",
    "numero_nota": "Número da nota ou null",
    "serie_nota": "Série ou null",
    "valor_total_bruto": 0.00,
    "desconto_total": 0.00,
    "valor_total_pago": 0.00,
    "metodo_pagamento": "Dinheiro, Cartão de Crédito, Cartão de Débito, Pix, Boleto ou null",
    "quantidade_parcelas": 1,
    "cartao": { "banco": "Banco ou null", "variante": "Variante ou null" }
  },
  "itens": [
    {
      "codigo": "Código ou null",
      "nome": "Nome exato do item",
      "quantidade": 1.0,
      "valor_unitario": 0.00
    }
  ]
}
"""

PROMPT_AGENTE_2 = """
Você é um Analista Financeiro Sênior. Hoje é [DATA_ATUAL].
Sua missão é enriquecer e categorizar o JSON recebido.

MAPA DE CATEGORIAS:
- Alimentação > Hortifruti | Carnes | Mercearia | Laticínios | Bebidas | Padaria | Restaurante/Lanche
- Moradia > Contas Residenciais | Aluguel | Manutenção
- Transporte > Combustível | App de Transporte | Passagens | Manutenção Veicular
- Saúde e Beleza > Farmácia | Consultas/Exames | Cuidados Pessoais
- Lazer e Cultura > Livros e Revistas | Ingressos/Eventos | Jogos | Viagem
- Educação > Cursos | Material Escolar
- Compras > Vestuário | Eletrônicos | Casa/Móveis
- Serviços > Assinaturas | Manutenção Geral | Limpeza
- Outros > Despesas diversas

REGRAS:
- valor_original: Copie "valor_total_bruto".
- desconto_aplicado: Copie "desconto_total" (se null, 0.0).
- valor_total_pago: Copie "valor_total_pago".
- quantidade_parcelas: Se null ou 0, assuma 1.
- metodo_pagamento: Se null, retorne "Desconhecido".
- parcelado: true se > 1.

ESTRUTURA DO JSON FINAL:
{
  "sucesso": true,
  "mensagem_interacao": "Ok",
  "transacoes": [
    {
      "numero_nota": "Número ou null",
      "serie_nota": "Série ou null",
      "data_compra": "DD/MM/YYYY",
      "local_compra": { "nome": "Nome", "tipo": "Físico | Online | App | Boleto/Fatura" },
      "status": "Ativa",
      "cartao": { "banco": "Nome ou null", "variante": "Nome ou null" },
      "valor_original": float,
      "desconto_aplicado": float,
      "valor_total_pago": float,
      "categoria_macro": "Categoria principal do mapa",
      "metodo_pagamento": "String",
      "parcelado": boolean,
      "quantidade_parcelas": int,
      "itens": [
        {
          "numero_item_nota": null,
          "item": "Nome do item",
          "codigo_produto": "Código ou null",
          "marca": "Marca ou null",
          "valor_unitario": float,
          "quantidade": float,
          "hierarquia_categorias": { "macro": "Mapa", "categoria": "Mapa", "subcategoria": "Mapa", "produto": "Nome" }
        }
      ]
    }
  ]
}
"""

# ==========================================
# 3. FUNÇÕES AUXILIARES
# ==========================================
def extrair_texto_de_url(url):
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        for script_or_style in soup(['script', 'style']): script_or_style.extract()
        return '\n'.join([linha.strip() for linha in soup.get_text(separator=' ').splitlines() if linha.strip()])
    except Exception as e: return f"Erro ao acessar link: {str(e)}"

def extrair_json_da_resposta(texto_bruto):
    match = re.search(r'\{.*\}', texto_bruto, re.DOTALL)
    if match:
        try: return json.loads(match.group(0))
        except: pass
    return None

def calcular_vencimento_fatura(data_compra, dia_fechamento, dia_vencimento):
    mes_fatura = data_compra.month
    ano_fatura = data_compra.year
    if data_compra.day >= dia_fechamento:
        mes_fatura = 1 if mes_fatura == 12 else mes_fatura + 1
        if mes_fatura == 1: ano_fatura += 1
    mes_vencimento = mes_fatura
    ano_vencimento = ano_fatura
    if dia_vencimento < dia_fechamento:
        mes_vencimento = 1 if mes_vencimento == 12 else mes_vencimento + 1
        if mes_vencimento == 1: ano_vencimento += 1
    return datetime(ano_vencimento, mes_vencimento, dia_vencimento)

def gerar_detalhamento_parcelas(valor_total, qtd_parcelas, data_compra_str, regra_cartao, metodo_pagamento):
    detalhamento = []
    qtd_real = max(1, qtd_parcelas)
    valor_parcela = round(valor_total / qtd_real, 2)
    
    try: data_compra = datetime.strptime(data_compra_str, "%d/%m/%Y")
    except: data_compra = datetime.now(timezone(timedelta(hours=-3)))
        
    fechamento = int(regra_cartao.get("fechamento", 0)) if regra_cartao else 0
    vencimento = int(regra_cartao.get("vencimento", 0)) if regra_cartao else 0
    
    if regra_cartao and fechamento == 0 and vencimento == 0: data_base = data_compra
    elif "crédito" in str(metodo_pagamento).lower() or "credito" in str(metodo_pagamento).lower():
        if regra_cartao: data_base = calcular_vencimento_fatura(data_compra, fechamento, vencimento)
        else: data_base = data_compra + relativedelta(months=1)
    else:
        data_base = data_compra

    for i in range(qtd_real):
        data_parcela = data_base + relativedelta(months=i)
        detalhamento.append({"mes": data_parcela.strftime("%m/%Y"), "data_vencimento": data_parcela.strftime("%d/%m/%Y"), "valor": valor_parcela})
    return detalhamento

# ==========================================
# 4. PROCESSADOR DE FILA (WORKER)
# ==========================================
def extrair_tempo_espera(erro_str):
    minutos, segundos = 0, 60
    match_m = re.search(r'(\d+)m', erro_str)
    match_s = re.search(r'(\d+)(?:\.\d+)?s', erro_str)
    if match_m or match_s:
        if match_m: minutos = int(match_m.group(1))
        if match_s: segundos = float(match_s.group(1))
        return int((minutos * 60) + segundos)
    return 60

async def processador_de_fila(context: ContextTypes.DEFAULT_TYPE):
    item = buscar_proximo_fila()
    if not item: return

    chat_id = item['chat_id']
    fuso_br = timezone(timedelta(hours=-3))
    data_hoje = datetime.now(fuso_br).strftime("%d/%m/%Y")
    
    try:
        await context.bot.send_message(chat_id, "⚙️ Processando seu item da fila...")
        
        texto_para_processar = item['texto']
        if texto_para_processar.startswith("http://") or texto_para_processar.startswith("https://"):
            await context.bot.send_message(chat_id, "🌐 Acessando o site da nota fiscal...")
            texto_para_processar = extrair_texto_de_url(texto_para_processar)
            if "Erro ao acessar link" in texto_para_processar:
                raise Exception("Não consegui ler o conteúdo do site da nota fiscal. O link pode estar quebrado.")

        prompt_1_dinamico = PROMPT_AGENTE_1.replace("[DATA_ATUAL]", data_hoje)
        prompt_2_dinamico = PROMPT_AGENTE_2.replace("[DATA_ATUAL]", data_hoje)
        
        chat_extrator = await groq_client.chat.completions.create(
            messages=[{"role": "system", "content": prompt_1_dinamico}, {"role": "user", "content": texto_para_processar}],
            model="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0.0, max_tokens=8000
        )
        json_agente_1 = extrair_json_da_resposta(chat_extrator.choices[0].message.content)
        
        if not json_agente_1:
            raise Exception("A IA falhou ao estruturar os dados. O texto pode estar confuso.")

        chat_enriquecedor = await groq_client.chat.completions.create(
            messages=[{"role": "system", "content": prompt_2_dinamico}, {"role": "user", "content": json.dumps(json_agente_1, ensure_ascii=False)}],
            model="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0.1, max_tokens=8000
        )
        dados_json = extrair_json_da_resposta(chat_enriquecedor.choices[0].message.content)
        
        if not dados_json:
            raise Exception("A IA falhou ao categorizar os dados.")

        # ==========================================
        # GOVERNANÇA DE DADOS
        # ==========================================
        for transacao in dados_json.get("transacoes", []):
            
            # --- PROTEÇÃO CONTRA DUPLICIDADE DE NOTAS ---
            numero_nota = transacao.get("numero_nota")
            if numero_nota and str(numero_nota).lower() != "null":
                if verificar_nota_existente(numero_nota):
                    await context.bot.send_message(chat_id, f"🚫 **Nota Duplicada!**\nA nota nº `{numero_nota}` já foi salva anteriormente. Não processarei novamente.")
                    concluir_fila(item['id'])
                    return 
            else:
                # --- NOVO PADRÃO DE ID MANUAL ---
                numero_aleatorio = random.randint(100000000, 999999999)
                transacao["numero_nota"] = f"M-{numero_aleatorio}"
                
                # --- NOVO: VERIFICAÇÃO DE SIMILARIDADE ---
                local_verif = str(transacao.get("local_compra", {}).get("nome", "DESCONHECIDO")).upper()
                valor_verif = float(transacao.get("valor_total_pago") or 0.0)
                data_verif = transacao.get("data_compra") or data_hoje
                
                if verificar_transacao_semelhante(local_verif, valor_verif, data_verif):
                    transacao["alerta_duplicidade"] = True # Acende o alerta na memória!

            if not transacao.get("data_compra") or transacao.get("data_compra") == "null":
                transacao["data_compra"] = data_hoje
                
            for index, it in enumerate(transacao.get("itens", []), start=1):
                it["numero_item_nota"] = str(index)
                if it.get("valor_unitario", 0.0) == 0.0:
                    it["valor_unitario"] = round(float(transacao.get("valor_original") or 0.0) / max(1, float(it.get("quantidade") or 1)), 2)

        concluir_fila(item['id'])
        
        SESSAO_TEMP[chat_id] = {
            "transacao_pendente_json": dados_json,
            "is_pdf": item['is_pdf']
        }
        
        await despachar_gatilhos_de_confirmacao(context.bot, chat_id, SESSAO_TEMP[chat_id])

    except Exception as e:
        erro_str = str(e).lower()
        if "429" in erro_str or "rate limit" in erro_str or "tokens" in erro_str:
            tempo = extrair_tempo_espera(erro_str)
            reagendar_fila(item['id'], tempo, item['tentativas'])
            await context.bot.send_message(chat_id, f"⚠️ IA sobrecarregada. Sua nota será processada em {tempo} segundos.")
        else:
            reagendar_fila(item['id'], 60, item['tentativas'])
            print(f"Erro na fila: {traceback.format_exc()}")
            await context.bot.send_message(chat_id, f"❌ Erro interno: {e}. Tentarei novamente em breve.")

# ==========================================
# 5. GATILHOS E HANDLERS
# ==========================================
async def despachar_gatilhos_de_confirmacao(bot, chat_id, user_data):
    dados_json = user_data["transacao_pendente_json"]
    transacao = dados_json["transacoes"][0]
    
    metodo_bruto = transacao.get("metodo_pagamento")
    metodo = str(metodo_bruto).lower() if metodo_bruto and str(metodo_bruto).strip().lower() != "null" else "desconhecido"
    
    cartao_info = transacao.get("cartao") or {}
    banco = cartao_info.get("banco")
    variante = cartao_info.get("variante")
    data_formatada = transacao.get("data_compra")

    if user_data.get("is_pdf") or metodo in ["boleto", "desconhecido", ""]:
        user_data["estado"] = "AGUARDANDO_METODO_PAGAMENTO"
        teclado = ReplyKeyboardMarkup([["Cartão de Crédito", "Cartão de Débito"], ["Pix", "Dinheiro"]], resize_keyboard=True, one_time_keyboard=True)
        await bot.send_message(chat_id, "📄 Transação extraída! Como você realizou o pagamento?", reply_markup=teclado)
        return

    cartao_db = None
    if "cartão" in metodo or "cartao" in metodo or "crédito" in metodo or "débito" in metodo:
        if not banco:
            botoes = [[f"{c['banco']} {c['variante']}".strip()] for c in listar_cartoes_db()]
            botoes.append(["➕ Adicionar Novo Cartão"])
            user_data["estado"] = "AGUARDANDO_SELECAO_CARTAO"
            teclado = ReplyKeyboardMarkup(botoes, resize_keyboard=True, one_time_keyboard=True)
            await bot.send_message(chat_id, "💳 Qual cartão foi usado?", reply_markup=teclado)
            return
        else:
            cartao_db = buscar_cartao_db(banco, variante)
            if not cartao_db:
                user_data.update({"estado": "AGUARDANDO_DATAS_CARTAO", "pendente_banco": banco, "pendente_variante": variante})
                await bot.send_message(chat_id, f"💳 Cartão Novo: **{banco} {variante}**!\nQual o **fechamento e vencimento**? (Ex: 1 e 8. Se for pré-pago, mande 0 e 0)")
                return

    # ==========================================
    # TRAVA DE SEGURANÇA: ANTI-PARCELAMENTO
    # ==========================================
    is_pre_pago = cartao_db and cartao_db.get("fechamento") == 0 and cartao_db.get("vencimento") == 0
    is_a_vista = metodo in ["débito", "debito", "pix", "dinheiro", "boleto"]
    
    if is_pre_pago or is_a_vista:
        transacao["quantidade_parcelas"] = 1
        transacao["parcelado"] = False
        
        # Bônus: Melhora a visualização se a IA tiver chamado de Crédito
        if is_pre_pago and ("crédito" in metodo or "credito" in metodo):
            transacao["metodo_pagamento"] = "Cartão de Benefício/Pré-pago"
            metodo = "benefício"
    # ==========================================

    transacao["detalhamento_parcelas"] = gerar_detalhamento_parcelas(float(transacao.get("valor_total_pago") or 0.0), int(transacao.get("quantidade_parcelas") or 1), data_formatada, cartao_db, metodo)
    user_data["estado"] = "AGUARDANDO_CONFIRMACAO"
    
    local_info = transacao.get("local_compra") or {}
    nome_local = local_info.get("nome", "Local Desconhecido")
    cat = transacao.get("categoria_macro", "Não classificada")
    parcelas = int(transacao.get("quantidade_parcelas") or 1)
    
    resumo = f"🛒 **Resumo da Transação**\n"
    resumo += f"📍 **Local:** {nome_local}\n"
    resumo += f"🏷️ **Categoria:** {cat}\n"
    resumo += f"💰 **Valor:** R$ {float(transacao.get('valor_total_pago') or 0):.2f}\n"
    
    # Exibe o método já corrigido pela trava
    resumo += f"💳 **Método:** {transacao.get('metodo_pagamento')}"
    if banco:
        resumo += f" ({banco} {variante})\n"
    else:
        resumo += "\n"
        
    resumo += f"📅 **Parcelas:** {parcelas}x\n\n"
    
    itens = transacao.get("itens", [])
    if itens:
        resumo += "🛍️ **Itens:**\n"
        for item_data in itens[:5]:
            qtd = float(item_data.get("quantidade") or 1)
            nome = str(item_data.get("item") or "Produto")
            valor_u = float(item_data.get("valor_unitario") or 0.0)
            
            hierarquia = item_data.get("hierarquia_categorias") or {}
            cat_item = hierarquia.get("subcategoria") or hierarquia.get("categoria") or ""
            tag_cat = f" _({cat_item})_" if cat_item else ""
            
            resumo += f"🔸 {qtd}x {nome} (R$ {valor_u:.2f}){tag_cat}\n"
            
        if len(itens) > 5:
            resumo += f"   *(...e mais {len(itens) - 5} itens)*\n"
        resumo += "\n"
        
    resumo += "**Vencimentos:**\n"
    for p in transacao.get("detalhamento_parcelas", [])[:3]:
        resumo += f"🔹 {p['data_vencimento']} - R$ {float(p.get('valor') or 0):.2f}\n"
    if parcelas > 3:
        resumo += f"...e mais {parcelas - 3} parcelas.\n"
        
    resumo += f"\n📋 **ID Único:** `{transacao.get('numero_nota')}`\n"
    
    if transacao.get("alerta_duplicidade"):
        resumo += f"\n🚨 **ALERTA DE POSSÍVEL DUPLICIDADE:**\n"
        resumo += f"Já existe uma compra no mesmo valor (`R$ {transacao.get('valor_total_pago'):.2f}`) para `{nome_local}` nesta exata data (`{data_formatada}`).\n"
        resumo += "\n⚠️ **Deseja salvar essa compra NOVAMENTE?**"
    else:
        resumo += "\n⚠️ **Deseja salvar no banco de dados?**"
    
    teclado = ReplyKeyboardMarkup([["Sim", "Não"]], resize_keyboard=True, one_time_keyboard=True)
    await bot.send_message(chat_id, resumo, parse_mode="Markdown", reply_markup=teclado)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    caminho_pdf = "temp.pdf"
    await file.download_to_drive(caminho_pdf)
    texto_pdf = "".join([page.extract_text() + "\n" for page in PdfReader(caminho_pdf).pages])
    os.remove(caminho_pdf)
    adicionar_na_fila(update.effective_chat.id, f"Extraia:\n\n{texto_pdf}", is_pdf=True)
    await update.message.reply_text("📥 PDF Recebido! Colocado na fila da Inteligência Artificial.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if chat_id in SESSAO_TEMP:
        context.user_data.update(SESSAO_TEMP.pop(chat_id))

    estado_atual = context.user_data.get("estado")
    
    try:
        if estado_atual == "AGUARDANDO_METODO_PAGAMENTO":
            escolha = update.message.text
            t = context.user_data["transacao_pendente_json"]["transacoes"][0]
            t["metodo_pagamento"] = escolha
            if "Cartão" in escolha:
                botoes = [[f"{c['banco']} {c['variante']}".strip()] for c in listar_cartoes_db()]
                botoes.append(["➕ Adicionar Novo Cartão"])
                await update.message.reply_text("Qual cartão você usou?", reply_markup=ReplyKeyboardMarkup(botoes, resize_keyboard=True, one_time_keyboard=True))
                context.user_data["estado"] = "AGUARDANDO_SELECAO_CARTAO"
            else:
                t["cartao"] = {"banco": None, "variante": None}
                t["detalhamento_parcelas"] = gerar_detalhamento_parcelas(t.get("valor_total_pago", 0.0), t.get("quantidade_parcelas", 1), t.get("data_compra"), None, escolha)
                context.user_data["estado"] = "AGUARDANDO_CONFIRMACAO"
                await despachar_gatilhos_de_confirmacao(context.bot, chat_id, context.user_data)
            return

        if estado_atual == "AGUARDANDO_SELECAO_CARTAO":
            escolha = update.message.text
            if escolha == "➕ Adicionar Novo Cartão":
                context.user_data["estado"] = "AGUARDANDO_NOME_NOVO_CARTAO"
                await update.message.reply_text("Digite o nome do banco e variante\n*(Ex: Nubank Ultravioleta, Caju Benefício)*:", reply_markup=ReplyKeyboardRemove())
            else:
                partes = escolha.split(" ", 1)
                banco = partes[0]
                variante = partes[1] if len(partes) > 1 else ""
                t = context.user_data["transacao_pendente_json"]["transacoes"][0]
                t["cartao"] = {"banco": banco, "variante": variante}
                
                cartao_db = buscar_cartao_db(banco, variante)
                if not cartao_db:
                    context.user_data["estado"] = "AGUARDANDO_DATAS_CARTAO"
                    context.user_data["pendente_banco"] = banco
                    context.user_data["pendente_variante"] = variante
                    await update.message.reply_text(f"Qual o fechamento e vencimento do {banco} {variante}? (Ex: 1 e 8. Se for benefício, responda 0 e 0)", reply_markup=ReplyKeyboardRemove())
                    return
                t["detalhamento_parcelas"] = gerar_detalhamento_parcelas(t.get("valor_total_pago", 0.0), t.get("quantidade_parcelas", 1), t.get("data_compra"), cartao_db, t.get("metodo_pagamento", ""))
                context.user_data["estado"] = "AGUARDANDO_CONFIRMACAO"
                await despachar_gatilhos_de_confirmacao(context.bot, chat_id, context.user_data)
            return

        if estado_atual == "AGUARDANDO_NOME_NOVO_CARTAO":
            escolha = update.message.text
            partes = escolha.split(" ", 1)
            banco = partes[0]
            variante = partes[1] if len(partes) > 1 else ""
            context.user_data.update({"pendente_banco": banco, "pendente_variante": variante})
            context.user_data["transacao_pendente_json"]["transacoes"][0]["cartao"] = {"banco": banco, "variante": variante}
            context.user_data["estado"] = "AGUARDANDO_DATAS_CARTAO"
            await update.message.reply_text(f"Qual o **fechamento e vencimento** do {banco} {variante}?\n*(Ex: '1 e 8'. Se for benefício, responda '0 e 0')*")
            return

        if estado_atual == "AGUARDANDO_DATAS_CARTAO":
            numeros = re.findall(r'\d+', update.message.text)
            if len(numeros) >= 2:
                fechamento, vencimento = int(numeros[0]), int(numeros[1])
                banco = context.user_data["pendente_banco"]
                variante = context.user_data["pendente_variante"]
                salvar_cartao_db(banco, variante, fechamento, vencimento)
                await update.message.reply_text(f"✅ Legal! Gravei o cartão {banco} {variante} (Fecha: {fechamento}, Vence: {vencimento}).")
                
                t = context.user_data["transacao_pendente_json"]["transacoes"][0]
                t["detalhamento_parcelas"] = gerar_detalhamento_parcelas(t.get("valor_total_pago", 0.0), t.get("quantidade_parcelas", 1), t.get("data_compra"), {"fechamento": fechamento, "vencimento": vencimento}, t.get("metodo_pagamento", ""))
                context.user_data["estado"] = "AGUARDANDO_CONFIRMACAO"
                await despachar_gatilhos_de_confirmacao(context.bot, chat_id, context.user_data)
            else:
                await update.message.reply_text("Não entendi as datas. Responda com dois números (ex: 5 e 12).")
            return

        if estado_atual == "AGUARDANDO_CONFIRMACAO":
            resposta = update.message.text.lower()
            if resposta in ["sim", "s"]:
                sucesso, msg_banco = salvar_transacoes_no_banco(context.user_data["transacao_pendente_json"])
                if sucesso: await update.message.reply_text("✅ Salvo no banco com sucesso!", reply_markup=ReplyKeyboardRemove())
                else: await update.message.reply_text(f"❌ Erro ao salvar: {msg_banco}", reply_markup=ReplyKeyboardRemove())
            else:
                await update.message.reply_text("🚫 Cancelado.", reply_markup=ReplyKeyboardRemove())
            context.user_data.clear()
            return

    except Exception as e:
        print(f"Erro na Máquina de Estados: {traceback.format_exc()}")
        await update.message.reply_text("❌ Ocorreu um erro no painel de botões. Operação cancelada.", reply_markup=ReplyKeyboardRemove())
        context.user_data.clear()
        return

    if not estado_atual:
        adicionar_na_fila(chat_id, update.message.text, is_pdf=False)
        await update.message.reply_text("📥 Recebido! Colocado na fila da Inteligência Artificial.")

# ==========================================
# 6. INICIALIZAÇÃO
# ==========================================
if __name__ == '__main__':
    criar_tabelas()
    print("Iniciando o bot...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.job_queue.run_repeating(processador_de_fila, interval=10, first=5)
    
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("Olá! Mande seus gastos.")))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.run_polling()