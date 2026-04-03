import os
import psycopg2
from dotenv import load_dotenv

# Carrega as variáveis de ambiente
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def conectar():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"Erro ao conectar ao banco: {e}")
        return None

def criar_tabelas():
    conn = conectar()
    if not conn: return
    try:
        cursor = conn.cursor()
        
        # --- TABELA DE FILA (NOVO) ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fila_processamento (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                texto_recebido TEXT,
                is_pdf BOOLEAN,
                status VARCHAR(20) DEFAULT 'PENDENTE',
                tentativas INT DEFAULT 0,
                proxima_tentativa TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resultado_json TEXT
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transacoes (
                id SERIAL PRIMARY KEY,
                numero_nota VARCHAR(50),
                serie_nota VARCHAR(50),
                data_compra VARCHAR(20),
                cartao_banco VARCHAR(100),
                cartao_variante VARCHAR(100),
                local_nome VARCHAR(255),
                local_tipo VARCHAR(50),
                status VARCHAR(50),
                valor_original DECIMAL(10, 2),
                desconto_aplicado DECIMAL(10, 2),
                valor_total_pago DECIMAL(10, 2),
                categoria_macro VARCHAR(100),
                metodo_pagamento VARCHAR(50),
                parcelado BOOLEAN,
                quantidade_parcelas INT
            );
        """)
        
        # --- ITENS SEM CAT_DETALHE ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS itens (
                id SERIAL PRIMARY KEY,
                transacao_id INT REFERENCES transacoes(id) ON DELETE CASCADE,
                numero_item_nota VARCHAR(50),
                codigo_produto VARCHAR(100),
                item VARCHAR(255),
                marca VARCHAR(100),
                valor_unitario DECIMAL(10, 2),
                quantidade DECIMAL(10, 3),
                cat_macro VARCHAR(100),
                cat_categoria VARCHAR(100),
                cat_subcategoria VARCHAR(100),
                cat_produto VARCHAR(100)
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parcelas (
                id SERIAL PRIMARY KEY,
                transacao_id INT REFERENCES transacoes(id) ON DELETE CASCADE,
                mes VARCHAR(20),
                data_vencimento VARCHAR(20),
                valor DECIMAL(10, 2)
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cartoes (
                id SERIAL PRIMARY KEY,
                banco VARCHAR(100),
                variante VARCHAR(100),
                dia_fechamento INT,
                dia_vencimento INT
            );
        """)
        conn.commit()
    except Exception as e:
        print(f"Erro ao criar tabelas: {e}")
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

# ==========================================
# FUNÇÕES DA FILA DE PROCESSAMENTO
# ==========================================
def adicionar_na_fila(chat_id, texto, is_pdf):
    conn = conectar()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO fila_processamento (chat_id, texto_recebido, is_pdf, status)
            VALUES (%s, %s, %s, 'PENDENTE')
        """, (chat_id, texto, is_pdf))
        conn.commit()
        return True
    finally:
        if conn: conn.close()

def buscar_proximo_fila():
    conn = conectar()
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, chat_id, texto_recebido, is_pdf, tentativas 
            FROM fila_processamento 
            WHERE status = 'PENDENTE' AND proxima_tentativa <= CURRENT_TIMESTAMP
            ORDER BY proxima_tentativa ASC LIMIT 1
            FOR UPDATE SKIP LOCKED;
        """)
        resultado = cursor.fetchone()
        if resultado:
            cursor.execute("UPDATE fila_processamento SET status = 'PROCESSANDO' WHERE id = %s", (resultado[0],))
            conn.commit()
            return {"id": resultado[0], "chat_id": resultado[1], "texto": resultado[2], "is_pdf": resultado[3], "tentativas": resultado[4]}
        return None
    finally:
        if conn: conn.close()

def reagendar_fila(id_fila, segundos_espera, tentativas):
    conn = conectar()
    if not conn: return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE fila_processamento 
            SET status = 'PENDENTE', tentativas = %s, proxima_tentativa = CURRENT_TIMESTAMP + INTERVAL '%s seconds'
            WHERE id = %s
        """, (tentativas + 1, segundos_espera, id_fila))
        conn.commit()
    finally:
        if conn: conn.close()

def concluir_fila(id_fila):
    conn = conectar()
    if not conn: return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE fila_processamento SET status = 'CONCLUIDO' WHERE id = %s", (id_fila,))
        conn.commit()
    finally:
        if conn: conn.close()

# ==========================================
# FUNÇÕES DO DOMÍNIO
# ==========================================
def salvar_transacoes_no_banco(dados_json):
    conn = conectar()
    if not conn: return False, "Falha na conexão com o DB."
    try:
        cursor = conn.cursor()
        for t in dados_json.get("transacoes", []):
            cartao = t.get("cartao") or {}
            local = t.get("local_compra") or {}

            v_orig = float(t.get("valor_original") or 0.0)
            v_desc = float(t.get("desconto_aplicado") or 0.0)
            v_pago = float(t.get("valor_total_pago") or 0.0)
            parcelado = bool(t.get("parcelado"))
            qtd_parc = int(t.get("quantidade_parcelas") or 1)

            sql_transacao = """
                INSERT INTO transacoes (
                    numero_nota, serie_nota, data_compra, cartao_banco, cartao_variante,
                    local_nome, local_tipo, status, valor_original, desconto_aplicado,
                    valor_total_pago, categoria_macro, metodo_pagamento, parcelado,
                    quantidade_parcelas
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """
            valores_transacao = (
                t.get("numero_nota"), t.get("serie_nota"), t.get("data_compra"),
                cartao.get("banco"), cartao.get("variante"),
                str(local.get("nome") or "DESCONHECIDO").upper(), local.get("tipo"), t.get("status", "Ativa"),
                v_orig, v_desc, v_pago, str(t.get("categoria_macro") or "").upper(),
                t.get("metodo_pagamento"), parcelado, qtd_parc
            )
            cursor.execute(sql_transacao, valores_transacao)
            transacao_id = cursor.fetchone()[0]

            # ITENS (AGORA 100% MAIÚSCULO E SEM CAT_DETALHE)
            sql_item = """
                INSERT INTO itens (
                    transacao_id, numero_item_nota, codigo_produto, item, marca, valor_unitario,
                    quantidade, cat_macro, cat_categoria, cat_subcategoria, cat_produto
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            for item in t.get("itens", []):
                cat = item.get("hierarquia_categorias") or {}
                valores_item = (
                    transacao_id, 
                    str(item.get("numero_item_nota") or "").upper(), 
                    str(item.get("codigo_produto") or "").upper(),
                    str(item.get("item") or "PRODUTO DESCONHECIDO").upper(), 
                    str(item.get("marca") or "").upper(), 
                    float(item.get("valor_unitario") or 0.0), 
                    float(item.get("quantidade") or 1.0), 
                    str(cat.get("macro") or "").upper(), 
                    str(cat.get("categoria") or "").upper(), 
                    str(cat.get("subcategoria") or "").upper(), 
                    str(cat.get("produto") or "").upper()
                )
                cursor.execute(sql_item, valores_item)

            sql_parcela = """
                INSERT INTO parcelas (transacao_id, mes, data_vencimento, valor)
                VALUES (%s, %s, %s, %s);
            """
            for parcela in t.get("detalhamento_parcelas", []):
                valores_parcela = (
                    transacao_id, parcela.get("mes"), parcela.get("data_vencimento"), float(parcela.get("valor") or 0.0)
                )
                cursor.execute(sql_parcela, valores_parcela)

        conn.commit()
        return True, "Sucesso"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

def buscar_cartao_db(banco, variante):
    conn = conectar()
    if not conn: return None
    try:
        cursor = conn.cursor()
        if variante and str(variante).strip():
            cursor.execute("SELECT dia_fechamento, dia_vencimento FROM cartoes WHERE banco ILIKE %s AND variante ILIKE %s LIMIT 1", (banco, variante))
        else:
            cursor.execute("SELECT dia_fechamento, dia_vencimento FROM cartoes WHERE banco ILIKE %s AND (variante IS NULL OR variante = '') LIMIT 1", (banco,))
        resultado = cursor.fetchone()
        if resultado:
            return {"fechamento": int(resultado[0]), "vencimento": int(resultado[1])}
        return None
    except:
        return None
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

def salvar_cartao_db(banco, variante, fechamento, vencimento):
    conn = conectar()
    if not conn: return False
    try:
        cursor = conn.cursor()
        if variante and str(variante).strip():
            cursor.execute("SELECT id FROM cartoes WHERE banco ILIKE %s AND variante ILIKE %s", (banco, variante))
        else:
            cursor.execute("SELECT id FROM cartoes WHERE banco ILIKE %s AND (variante IS NULL OR variante = '')", (banco,))
        existe = cursor.fetchone()

        if existe:
            cursor.execute("UPDATE cartoes SET dia_fechamento = %s, dia_vencimento = %s WHERE id = %s", (int(fechamento), int(vencimento), existe[0]))
        else:
            cursor.execute("INSERT INTO cartoes (banco, variante, dia_fechamento, dia_vencimento) VALUES (%s, %s, %s, %s)", (banco, variante if variante else "", int(fechamento), int(vencimento)))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        return False
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

def listar_cartoes_db():
    conn = conectar()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT banco, variante FROM cartoes ORDER BY banco")
        resultados = cursor.fetchall()
        return [{"banco": r[0], "variante": r[1] if r[1] else ""} for r in resultados]
    except:
        return []
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

def verificar_nota_existente(numero_nota):
    """Verifica se o número da nota fiscal já foi salvo no banco de dados."""
    conn = conectar()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM transacoes WHERE numero_nota = %s LIMIT 1", (numero_nota,))
        resultado = cursor.fetchone()
        return bool(resultado) # Retorna True se a nota já existir, False se for nova
    except:
        return False
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

def verificar_transacao_semelhante(local_nome, valor_total_pago, data_compra):
    """Verifica se já existe uma transação manual com o mesmo local, valor e data."""
    conn = conectar()
    if not conn: return False
    try:
        cursor = conn.cursor()
        # Procura transações com mesmo local, valor e data
        cursor.execute("""
            SELECT id FROM transacoes 
            WHERE local_nome = %s 
            AND valor_total_pago = %s 
            AND data_compra = %s
            LIMIT 1
        """, (local_nome.upper(), float(valor_total_pago), data_compra))
        
        resultado = cursor.fetchone()
        return bool(resultado) # True se achar uma compra igualzinha
    except Exception as e:
        print(f"Erro na busca de similaridade: {e}")
        return False
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()