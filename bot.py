import os
import json
import re
import traceback
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import AsyncGroq # <-- NOVO: Cliente Assíncrono para não travar o bot!

from database import criar_tabelas, salvar_transacoes_no_banco, buscar_cartao_db, salvar_cartao_db, listar_cartoes_db

# ==========================================
# 1. CONFIGURAÇÕES E CHAVES
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Agora o cliente é Async!
groq_client = AsyncGroq(api_key=GROQ_API_KEY)


# ==========================================
# 2. PROMPTS DOS AGENTES
# ==========================================
PROMPT_AGENTE_1 = """
Você é um extrator de dados de notas fiscais e textos financeiros. Hoje é [DATA_ATUAL].
Sua única função é ler o texto bruto e transcrever os dados exatos para um JSON.
NÃO categorize. NÃO invente dados. 
Retorne valores numéricos SEMPRE com ponto (.) como separador decimal.

ESTRUTURA DE SAÍDA OBRIGATÓRIA (Apenas JSON):
{
  "sucesso": true,
  "mensagem_interacao": "Ok",
  "cabecalho": {
    "local": "Nome da Empresa/Razão Social",
    "data_compra": "DD/MM/YYYY",
    "numero_nota": "Número da nota ou null",
    "serie_nota": "Série ou null",
    "valor_total_bruto": 0.00,
    "desconto_total": 0.00,
    "valor_total_pago": 0.00,
    "metodo_pagamento": "Dinheiro, Cartão de Crédito, Cartão de Débito, Pix, Boleto ou null",
    "quantidade_parcelas": 1,
    "cartao": {
       "banco": "Nome do Banco (Ex: Itaú, Nubank, Caju) ou null",
       "variante": "Variante do cartão (Ex: Uniclass, Benefício) ou null"
    }
  },
  "itens": [
    {
      "codigo": "Código do produto/serviço ou null",
      "nome": "Nome exato do item",
      "quantidade": 1.0,
      "valor_unitario": 0.00
    }
  ]
}
"""

PROMPT_AGENTE_2 = f"""
Você é um Analista Financeiro Sênior. Hoje é [DATA_ATUAL].
Sua missão é enriquecer e categorizar o JSON recebido.

MAPA DE CATEGORIAS:
- Alimentação > Hortifruti | Carnes e Peixes | Mercearia | Frios e Laticínios | Bebidas | Padaria | Refeição
- Limpeza > Cuidados com a Casa
- Higiene > Cuidados Pessoais
- Moradia > Contas Residenciais | Aluguel e Impostos
- Serviços > Assinaturas

REGRAS:
- valor_original: Copie o "valor_total_bruto".
- desconto_aplicado: Copie o "desconto_total" (se null, use 0.0).
- valor_total_pago: Copie o "valor_total_pago".
- quantidade_parcelas: Se null ou 0, assuma 1.
- metodo_pagamento: Se null, retorne "Desconhecido".
- parcelado: true se quantidade_parcelas > 1.

ESTRUTURA DO JSON FINAL:
{{
  "sucesso": true,
  "mensagem_interacao": "Ok",
  "transacoes": [
    {{
      "numero_nota": "Número ou null",
      "serie_nota": "Série ou null",
      "data_compra": "DD/MM/YYYY",
      "local_compra": {{ "nome": "Nome", "tipo": "Físico | Online | App | Boleto/Fatura" }},
      "status": "Ativa",
      "cartao": {{ "banco": "Nome ou null", "variante": "Nome ou null" }},
      "valor_original": float,
      "desconto_aplicado": float,
      "valor_total_pago": float,
      "categoria_macro": "Categoria principal",
      "metodo_pagamento": "String",
      "parcelado": boolean,
      "quantidade_parcelas": int,
      "itens": [
        {{
          "numero_item_nota": null,
          "item": "Nome do item",
          "codigo_produto": "Código ou null",
          "marca": "Marca ou null",
          "valor_unitario": float,
          "quantidade": float,
          "hierarquia_categorias": {{ "macro": "Mapa", "categoria": "Mapa", "subcategoria": "Mapa", "produto": "Nome", "detalhe": "Detalhe ou null" }}
        }}
      ]
    }}
  ]
}}
"""

# ==========================================
# 3. FUNÇÕES AUXILIARES E DE NEGÓCIO
# ==========================================
def extrair_texto_de_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        for script_or_style in soup(['script', 'style']):
            script_or_style.extract()
        texto = soup.get_text(separator=' ')
        return '\n'.join([linha.strip() for linha in texto.splitlines() if linha.strip()])
    except Exception as e:
        return f"Erro ao acessar link: {str(e)}"

def extrair_json_da_resposta(texto_bruto):
    """Caçador de JSON blindado."""
    match = re.search(r'\{.*\}', texto_bruto, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass
    return None

async def atualizar_status(mensagem, texto):
    """Tenta editar a mensagem. Se o Telegram bloquear, envia uma nova para não ficar mudo."""
    try:
        await mensagem.edit_text(texto)
    except Exception:
        try:
            # Se não der para editar, manda como uma resposta nova na conversa!
            await mensagem.chat.send_message(texto)
        except:
            pass

def calcular_vencimento_fatura(data_compra, dia_fechamento, dia_vencimento):
    mes_fatura = data_compra.month
    ano_fatura = data_compra.year
    if data_compra.day >= dia_fechamento:
        mes_fatura += 1
        if mes_fatura > 12:
            mes_fatura = 1
            ano_fatura += 1

    mes_vencimento = mes_fatura
    ano_vencimento = ano_fatura
    if dia_vencimento < dia_fechamento:
        mes_vencimento += 1
        if mes_vencimento > 12:
            mes_vencimento = 1
            ano_vencimento += 1
    return datetime(ano_vencimento, mes_vencimento, dia_vencimento)

def gerar_detalhamento_parcelas(valor_total, qtd_parcelas, data_compra_str, regra_cartao, metodo_pagamento):
    detalhamento = []
    qtd_real = max(1, qtd_parcelas)
    valor_parcela = round(valor_total / qtd_real, 2)
    
    try:
        data_compra = datetime.strptime(data_compra_str, "%d/%m/%Y")
    except:
        data_compra = datetime.now()
        
    fechamento = int(regra_cartao.get("fechamento", 0)) if regra_cartao else 0
    vencimento = int(regra_cartao.get("vencimento", 0)) if regra_cartao else 0
    
    if regra_cartao and fechamento == 0 and vencimento == 0:
        data_base = data_compra
    elif "crédito" in str(metodo_pagamento).lower() or "credito" in str(metodo_pagamento).lower():
        if regra_cartao:
            data_base = calcular_vencimento_fatura(data_compra, fechamento, vencimento)
        else:
            data_base = data_compra + relativedelta(months=1)
    else:
        data_base = data_compra

    for i in range(qtd_real):
        data_parcela = data_base + relativedelta(months=i)
        detalhamento.append({
            "mes": data_parcela.strftime("%m/%Y"),
            "data_vencimento": data_parcela.strftime("%d/%m/%Y"),
            "valor": valor_parcela
        })
    return detalhamento

async def gerar_resumo_e_pedir_confirmacao(update: Update, context: ContextTypes.DEFAULT_TYPE, msg_edit=None):
    dados_json = context.user_data["transacao_pendente_json"]
    t = dados_json["transacoes"][0]
    
    local = t.get("local_compra", {}).get("nome", "Local Desconhecido")
    valor = t.get("valor_total_pago", 0.0)
    metodo = t.get("metodo_pagamento", "Não identificado")
    parcelas = t.get("quantidade_parcelas", 1)
    categoria_principal = t.get("categoria_macro", "Não classificada") # Puxa a Macro
    
    # Cabeçalho atualizado com a Categoria
    resumo = f"🛒 **Resumo da Transação**\n"
    resumo += f"📍 **Local:** {local}\n"
    resumo += f"🏷️ **Categoria:** {categoria_principal}\n"
    resumo += f"💰 **Valor:** R$ {valor:.2f}\n"
    resumo += f"💳 **Método:** {metodo}"
    
    banco = t.get("cartao", {}).get("banco")
    variante = t.get("cartao", {}).get("variante")
    if banco: resumo += f" ({banco} {variante})\n"
    else: resumo += "\n"
        
    resumo += f"📅 **Parcelas:** {parcelas}x\n\n"
    
    # Itens atualizados com a Subcategoria
    itens = t.get("itens", [])
    if itens:
        resumo += "🛍️ **Itens:**\n"
        for item in itens[:5]:
            qtd = item.get("quantidade", 1)
            nome = item.get("item", "Produto")
            valor_u = item.get("valor_unitario", 0.0)
            
            # Tenta pegar a subcategoria ou categoria para dar contexto ao item
            hierarquia = item.get("hierarquia_categorias") or {}
            cat_item = hierarquia.get("subcategoria") or hierarquia.get("categoria") or ""
            tag_cat = f" _({cat_item})_" if cat_item else ""
            
            resumo += f"🔸 {qtd}x {nome} (R$ {valor_u:.2f}){tag_cat}\n"
            
        if len(itens) > 5: resumo += f"   *(...e mais {len(itens) - 5} itens)*\n"
        resumo += "\n"
        
    resumo += "**Vencimentos:**\n"
    for p in t.get("detalhamento_parcelas", [])[:3]:
        resumo += f"🔹 {p['data_vencimento']} - R$ {p['valor']:.2f}\n"
    if parcelas > 3: resumo += f"...e mais {parcelas - 3} parcelas.\n"
        
    resumo += "\n⚠️ **Deseja salvar no banco de dados?**"

    teclado = ReplyKeyboardMarkup([["Sim", "Não"]], resize_keyboard=True, one_time_keyboard=True)
    if msg_edit:
        try: await msg_edit.delete()
        except: pass
        
    if update.message:
        await update.message.reply_text(resumo, parse_mode="Markdown", reply_markup=teclado)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=resumo, parse_mode="Markdown", reply_markup=teclado)

# ==========================================
# 4. HANDLERS DO TELEGRAM
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Sou seu Assistente Financeiro Sênior. Envie seus gastos ou notas fiscais!")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensagem_espera = await update.message.reply_text("Recebi o arquivo! Lendo o PDF... 📄", reply_markup=ReplyKeyboardRemove())
    file = await update.message.document.get_file()
    caminho_pdf = "temp_fatura.pdf"
    await file.download_to_drive(caminho_pdf)
    
    try:
        reader = PdfReader(caminho_pdf)
        if reader.is_encrypted:
            try: reader.decrypt("")
            except: pass
        texto_pdf = "".join([page.extract_text() + "\n" for page in reader.pages])
        os.remove(caminho_pdf)
        texto_recebido = f"Extraia os dados desta fatura/nota fiscal em PDF:\n\n{texto_pdf}"
        await handle_message(update, context, texto_pdf=texto_recebido, mensagem_pdf=mensagem_espera)
    except Exception as e:
        await mensagem_espera.edit_text(f"❌ Erro ao ler o PDF: {str(e)}")
        if os.path.exists(caminho_pdf): os.remove(caminho_pdf)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, texto_pdf=None, mensagem_pdf=None):
    estado_atual = context.user_data.get("estado")

    fuso_br = timezone(timedelta(hours=-3))
    data_hoje = datetime.now(fuso_br).strftime("%d/%m/%Y")
    
    # === BLOQUEADOR DE MENSAGENS CURTAS ("Sim" acidental) ===
    texto_recebido_limpo = update.message.text.strip() if update.message.text else ""
    if not estado_atual and not texto_pdf and len(texto_recebido_limpo) < 4:
        if not texto_recebido_limpo.startswith("http"):
            await update.message.reply_text("🤔 Por favor, envie a frase completa do seu gasto ou um arquivo/link de nota fiscal.")
            return

    # === ESCUDO DA MÁQUINA DE ESTADOS ===
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
                t["detalhamento_parcelas"] = gerar_detalhamento_parcelas(t.get("valor_total_pago", 0.0), t.get("quantidade_parcelas", 1), t.get("data_compra", data_hoje), None, escolha)
                context.user_data["estado"] = "AGUARDANDO_CONFIRMACAO"
                await gerar_resumo_e_pedir_confirmacao(update, context)
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
                t["detalhamento_parcelas"] = gerar_detalhamento_parcelas(t.get("valor_total_pago", 0.0), t.get("quantidade_parcelas", 1), t.get("data_compra", data_hoje), cartao_db, t.get("metodo_pagamento", ""))
                context.user_data["estado"] = "AGUARDANDO_CONFIRMACAO"
                await gerar_resumo_e_pedir_confirmacao(update, context)
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
                t["detalhamento_parcelas"] = gerar_detalhamento_parcelas(t.get("valor_total_pago", 0.0), t.get("quantidade_parcelas", 1), t.get("data_compra", data_hoje), {"fechamento": fechamento, "vencimento": vencimento}, t.get("metodo_pagamento", ""))
                context.user_data["estado"] = "AGUARDANDO_CONFIRMACAO"
                await gerar_resumo_e_pedir_confirmacao(update, context)
            else:
                await update.message.reply_text("Não entendi as datas. Responda com dois números (ex: 5 e 12).")
            return

        if estado_atual == "AGUARDANDO_CONFIRMACAO":
            resposta = update.message.text.lower()
            if resposta in ["sim", "s"]:
                sucesso, msg_banco = salvar_transacoes_no_banco(context.user_data["transacao_pendente_json"])
                if sucesso:
                    await update.message.reply_text("✅ Salvo no banco com sucesso!", reply_markup=ReplyKeyboardRemove())
                else:
                    await update.message.reply_text(f"❌ Erro ao salvar no banco: {msg_banco}", reply_markup=ReplyKeyboardRemove())
            else:
                await update.message.reply_text("🚫 Operação cancelada. Não salvei nada.", reply_markup=ReplyKeyboardRemove())
            context.user_data.clear()
            return

    except Exception as e:
        print(f"Erro na Máquina de Estados: {traceback.format_exc()}")
        await update.message.reply_text("❌ Ocorreu um erro no painel. O fluxo foi reiniciado.", reply_markup=ReplyKeyboardRemove())
        context.user_data.clear()
        return

    # ====================================
    # --- FLUXO DA INTELIGÊNCIA ARTIFICIAL ---
    # ====================================
    if texto_pdf:
        context.user_data["is_pdf"] = True
        texto_original = texto_pdf
        mensagem_espera = mensagem_pdf
        texto_recebido = texto_original
    else:
        texto_original = update.message.text
        if texto_original.startswith("http"):
            mensagem_espera = await update.message.reply_text("Acessando o link da nota fiscal... 🌐", reply_markup=ReplyKeyboardRemove())
            texto_recebido = extrair_texto_de_url(texto_original)
        else:
            mensagem_espera = await update.message.reply_text("Agente 1 Extraindo dados... 🕵️‍♂️", reply_markup=ReplyKeyboardRemove())
            texto_recebido = texto_original

    try:
        if texto_pdf or texto_original.startswith("http"):
            await atualizar_status(mensagem_espera, "Agente 1 Extraindo dados... 🕵️‍♂️")

        prompt_1_dinamico = PROMPT_AGENTE_1.replace("[DATA_ATUAL]", data_hoje)
        prompt_2_dinamico = PROMPT_AGENTE_2.replace("[DATA_ATUAL]", data_hoje)   
            
        # AGORA É AWAIT! Assíncrono e muito mais rápido
        chat_extrator = await groq_client.chat.completions.create(
            messages=[{"role": "system", "content": prompt_1_dinamico}, {"role": "user", "content": texto_recebido}],
            model="llama-3.3-70b-versatile", temperature=0.0, max_tokens=8000
        )
        
        json_agente_1 = extrair_json_da_resposta(chat_extrator.choices[0].message.content)
        print(f"🤖 Agente 1 extraiu: {json.dumps(json_agente_1, ensure_ascii=False, indent=2)}") 
        
        if not json_agente_1:
            await atualizar_status(mensagem_espera, "❌ A IA não conseguiu extrair os dados. Tente reescrever o gasto.")
            return
            
        valor_verificacao = json_agente_1.get("cabecalho", {}).get("valor_total_pago")
        local_verificacao = json_agente_1.get("cabecalho", {}).get("local")
        
        # Verifica se o local é nulo ou se o valor é nulo/zero
        if not local_verificacao or not valor_verificacao or float(valor_verificacao) == 0.0:
            await atualizar_status(mensagem_espera, "⚠️ Não consegui identificar o **valor** ou o **local** da compra nessa mensagem. Pode dar mais detalhes?")
            return

        await atualizar_status(mensagem_espera, "Agente 2 Analisando Finanças... 💼")
        
        chat_enriquecedor = await groq_client.chat.completions.create(
            messages=[{"role": "system", "content": prompt_2_dinamico}, {"role": "user", "content": json.dumps(json_agente_1, ensure_ascii=False)}],
            model="llama-3.3-70b-versatile", temperature=0.1, max_tokens=8000
        )
        
        dados_json = extrair_json_da_resposta(chat_enriquecedor.choices[0].message.content)
        if not dados_json:
            await atualizar_status(mensagem_espera, "❌ A IA de análise falhou ao formatar o JSON. Tente novamente.")
            return

        for transacao in dados_json.get("transacoes", []):
            itens = transacao.get("itens", [])
            if len(itens) == 1 and itens[0].get("valor_unitario", 0.0) == 0.0:
                itens[0]["valor_unitario"] = round(float(transacao.get("valor_original") or 0.0) / max(1, float(itens[0].get("quantidade") or 1)), 2)

            cartao = transacao.get("cartao") or {}
            banco = cartao.get("banco")
            variante = cartao.get("variante")
            
            metodo_bruto = transacao.get("metodo_pagamento")
            metodo = str(metodo_bruto).lower() if metodo_bruto and str(metodo_bruto).strip().lower() != "null" else "desconhecido"
            transacao["metodo_pagamento"] = metodo_bruto if metodo_bruto else "Desconhecido"

            is_pdf = context.user_data.get("is_pdf", False)
            
            if is_pdf or metodo in ["boleto", "desconhecido", ""]:
                context.user_data.update({"estado": "AGUARDANDO_METODO_PAGAMENTO", "transacao_pendente_json": dados_json})
                await atualizar_status(mensagem_espera, "📄 Compra/Fatura identificada!")
                teclado = ReplyKeyboardMarkup([["Cartão de Crédito", "Cartão de Débito"], ["Pix", "Dinheiro"]], resize_keyboard=True, one_time_keyboard=True)
                await update.message.reply_text("Como você realizou (ou vai realizar) o pagamento?", reply_markup=teclado) if update.message else await context.bot.send_message(chat_id=update.effective_chat.id, text="Como vai pagar?", reply_markup=teclado)
                return 

            cartao_db = None
            if "cartão" in metodo or "cartao" in metodo or "crédito" in metodo or "débito" in metodo:
                if not banco:
                    botoes = [[f"{c['banco']} {c['variante']}".strip()] for c in listar_cartoes_db()]
                    botoes.append(["➕ Adicionar Novo Cartão"])
                    context.user_data.update({"estado": "AGUARDANDO_SELECAO_CARTAO", "transacao_pendente_json": dados_json})
                    await atualizar_status(mensagem_espera, "💳 Cartão não identificado!")
                    teclado = ReplyKeyboardMarkup(botoes, resize_keyboard=True, one_time_keyboard=True)
                    await update.message.reply_text("Identifiquei uma compra no Cartão, mas não sei qual. Escolha abaixo:", reply_markup=teclado) if update.message else await context.bot.send_message(chat_id=update.effective_chat.id, text="Qual cartão?", reply_markup=teclado)
                    return 
                else:
                    cartao_db = buscar_cartao_db(banco, variante)
                    if not cartao_db:
                        context.user_data.update({"estado": "AGUARDANDO_DATAS_CARTAO", "transacao_pendente_json": dados_json, "pendente_banco": banco, "pendente_variante": variante})
                        await atualizar_status(mensagem_espera, f"💳 Cartão Novo: **{banco} {variante}**!")
                        texto_pergunta = f"Qual o **dia de fechamento** e o **dia de vencimento**? (Ex: 1 e 8. Se for benefício/pré-pago, mande 0 e 0)"
                        await update.message.reply_text(texto_pergunta) if update.message else await context.bot.send_message(chat_id=update.effective_chat.id, text=texto_pergunta)
                        return 

            transacao["detalhamento_parcelas"] = gerar_detalhamento_parcelas(float(transacao.get("valor_total_pago") or 0.0), int(transacao.get("quantidade_parcelas") or 1), transacao.get("data_compra", data_hoje), cartao_db, metodo)

        context.user_data.update({"transacao_pendente_json": dados_json, "estado": "AGUARDANDO_CONFIRMACAO"})
        await gerar_resumo_e_pedir_confirmacao(update, context, mensagem_espera)

    except Exception as e:
        print(traceback.format_exc())
        await atualizar_status(mensagem_espera, f"❌ Erro na comunicação com a IA: {str(e)}")

# ==========================================
# 5. INICIALIZAÇÃO
# ==========================================
if __name__ == '__main__':
    criar_tabelas()
    print("Iniciando o bot do Telegram...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.run_polling()