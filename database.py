import os
import psycopg2
from dotenv import load_dotenv

# Carrega as variáveis de ambiente
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    """Cria e retorna uma conexão com o banco de dados."""
    return psycopg2.connect(DATABASE_URL)

def criar_tabelas():
    """Cria as tabelas relacionais no banco de dados."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Nosso script SQL que cria as 3 tabelas amarradas por Foreign Keys (Chaves Estrangeiras)
    sql_tabelas = """
    CREATE TABLE IF NOT EXISTS transacoes (
        id SERIAL PRIMARY KEY,
        numero_nota VARCHAR(255),
        serie_nota VARCHAR(50),
        data_compra VARCHAR(20),
        local_nome VARCHAR(255),
        local_tipo VARCHAR(50),
        status VARCHAR(50),
        valor_original DECIMAL(10, 2),
        desconto_aplicado DECIMAL(10, 2),
        valor_total_pago DECIMAL(10, 2),
        categoria_macro VARCHAR(100),
        metodo_pagamento VARCHAR(50),
        parcelado BOOLEAN,
        quantidade_parcelas INT,
        mes_inicio_parcelas VARCHAR(10),
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS itens (
        id SERIAL PRIMARY KEY,
        transacao_id INT REFERENCES transacoes(id) ON DELETE CASCADE,
        numero_item_nota INT,
        codigo_produto VARCHAR(100),
        item VARCHAR(255),
        marca VARCHAR(255),
        valor_unitario DECIMAL(10, 2),
        quantidade DECIMAL(10, 2),
        cat_macro VARCHAR(100),
        cat_categoria VARCHAR(100),
        cat_subcategoria VARCHAR(100),
        cat_produto VARCHAR(100),
        cat_detalhe VARCHAR(100)
    );

    CREATE TABLE IF NOT EXISTS parcelas (
        id SERIAL PRIMARY KEY,
        transacao_id INT REFERENCES transacoes(id) ON DELETE CASCADE,
        mes VARCHAR(10),
        valor DECIMAL(10, 2)
    );
    """
    
    try:
        cursor.execute(sql_tabelas)
        conn.commit()
        print("✅ Banco de Dados estruturado com sucesso! As tabelas estão prontas.")
    except Exception as e:
        print(f"❌ Erro ao criar tabelas: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

# Executa a criação das tabelas quando rodarmos este arquivo diretamente
if __name__ == "__main__":
    criar_tabelas()        

def salvar_transacoes_no_banco(dados_json):
    """Recebe o JSON validado e insere nas tabelas transacoes, itens e parcelas."""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Pega a lista de transações do JSON
        transacoes = dados_json.get("transacoes", [])
        
        for t in transacoes:
            # 1. INSERE A TRANSAÇÃO PRINCIPAL (Capa)
            sql_transacao = """
                INSERT INTO transacoes (
                    numero_nota, serie_nota, data_compra, local_nome, local_tipo, status, 
                    valor_original, desconto_aplicado, valor_total_pago, 
                    categoria_macro, metodo_pagamento, parcelado, 
                    quantidade_parcelas, mes_inicio_parcelas
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """
            valores_transacao = (
                t.get("numero_nota"),
                t.get("serie_nota"),
                t.get("data_compra"),
                t.get("local_compra", {}).get("nome"),
                t.get("local_compra", {}).get("tipo"),
                t.get("status"),
                t.get("valor_original"),
                t.get("desconto_aplicado"),
                t.get("valor_total_pago"),
                t.get("categoria_macro"),
                t.get("metodo_pagamento"),
                t.get("parcelado"),
                t.get("quantidade_parcelas"),
                t.get("mes_inicio_parcelas")
            )
            
            # Executa e pega o ID gerado pelo banco para esta transação
            cursor.execute(sql_transacao, valores_transacao)
            transacao_id = cursor.fetchone()[0]
            
            # 2. INSERE OS ITENS (Amarrados ao ID da Transação)
            sql_item = """
                INSERT INTO itens (
                    transacao_id, numero_item_nota, codigo_produto, item, marca, valor_unitario, 
                    quantidade, cat_macro, cat_categoria, cat_subcategoria, 
                    cat_produto, cat_detalhe
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            for item in t.get("itens", []):
                cat = item.get("hierarquia_categorias", {})
                valores_item = (
                    transacao_id,
                    item.get("numero_item_nota"),
                    item.get("codigo_produto"),
                    item.get("item"),
                    item.get("marca"),
                    item.get("valor_unitario"),
                    item.get("quantidade"),
                    cat.get("macro"),
                    cat.get("categoria"),
                    cat.get("subcategoria"),
                    cat.get("produto"),
                    cat.get("detalhe")
                )
                cursor.execute(sql_item, valores_item)
            
            # 3. INSERE AS PARCELAS (Amarradas ao ID da Transação)
            sql_parcela = """
                INSERT INTO parcelas (transacao_id, mes, valor)
                VALUES (%s, %s, %s);
            """
            for parcela in t.get("detalhamento_parcelas", []):
                valores_parcela = (
                    transacao_id,
                    parcela.get("mes"),
                    parcela.get("valor")
                )
                cursor.execute(sql_parcela, valores_parcela)
        
        # Se chegou até aqui sem dar erro, "commita" (salva definitivamente)
        conn.commit()
        return True, "Transação salva com sucesso no banco de dados!"
        
    except Exception as e:
        # Se der qualquer erro no meio do caminho, desfaz tudo (rollback) para não ter dado pela metade
        conn.rollback()
        return False, f"Erro ao salvar no banco: {str(e)}"
        
    finally:
        cursor.close()
        conn.close()

