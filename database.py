import os
import psycopg2
from psycopg2 import pool
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# --- PROD-01: Connection Pool ---
# Cria um pool de conexões (Mínimo 1, Máximo 10) para reaproveitamento rápido
try:
    db_pool = psycopg2.pool.ThreadedConnectionPool(1, 10, DATABASE_URL)
except Exception as e:
    print(f"Error initializing connection pool: {e}")
    db_pool = None

def parse_br_date(date_str):
    """Helper para converter string DD/MM/YYYY para objeto DATE do banco."""
    if not date_str or date_str.lower() == "null": return None
    try: return datetime.strptime(date_str, "%d/%m/%Y").date()
    except: return datetime.now().date()

def create_tables():
    """Creates all necessary relational tables, indexes, and constraints."""
    if not db_pool: return
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS process_queue (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                received_text TEXT,
                is_pdf BOOLEAN,
                status VARCHAR(20) DEFAULT 'PENDING',
                attempts INT DEFAULT 0,
                max_attempts INT DEFAULT 5, -- PROD-03: Fila Zumbi
                next_attempt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                json_result TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                transaction_type VARCHAR(20) DEFAULT 'DESPESA',
                invoice_number VARCHAR(50),
                invoice_serial VARCHAR(50),
                transaction_date DATE,
                card_bank VARCHAR(100),
                card_variant VARCHAR(100),
                location_name VARCHAR(255),
                location_type VARCHAR(50),
                status VARCHAR(50),
                original_amount DECIMAL(10, 2),
                discount_applied DECIMAL(10, 2),
                total_amount DECIMAL(10, 2),
                macro_category VARCHAR(100),
                payment_method VARCHAR(50),
                is_installment BOOLEAN,
                installment_count INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transaction_items (
                id SERIAL PRIMARY KEY,
                transaction_id INT REFERENCES transactions(id) ON DELETE CASCADE,
                item_type VARCHAR(20),
                item_number VARCHAR(50),
                product_code VARCHAR(100),
                description VARCHAR(255),
                brand VARCHAR(100),
                unit_price DECIMAL(10, 2),
                quantity DECIMAL(10, 3),
                cat_macro VARCHAR(100),
                cat_category VARCHAR(100),
                cat_subcategory VARCHAR(100),
                cat_product VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS installments (
                id SERIAL PRIMARY KEY,
                transaction_id INT REFERENCES transactions(id) ON DELETE CASCADE,
                month VARCHAR(7) CHECK (month ~ '^\\d{2}/\\d{4}$'), -- BARRAS DUPLAS AQUI
                due_date DATE,
                amount DECIMAL(10, 2),
                payment_status VARCHAR(20) DEFAULT 'PENDING',
                payment_date DATE,
                paid_amount DECIMAL(10, 2) DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS credit_cards (
                id SERIAL PRIMARY KEY,
                bank VARCHAR(100),
                variant VARCHAR(100),
                closing_day INT,
                due_day INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_installments_month_status ON installments(month, payment_status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_status_next ON process_queue(status, next_attempt);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date_type ON transactions(transaction_date, transaction_type);")

        conn.commit()
    except Exception as e:
        print(f"Error creating tables: {e}")
        if conn: conn.rollback()
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def add_to_queue(chat_id, text, is_pdf):
    if not db_pool: return False
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO process_queue (chat_id, received_text, is_pdf, status) VALUES (%s, %s, %s, 'PENDING')", (chat_id, text, is_pdf))
        conn.commit()
        return True
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def get_next_in_queue():
    if not db_pool: return None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, chat_id, received_text, is_pdf, attempts, max_attempts 
            FROM process_queue 
            WHERE status = 'PENDING' AND next_attempt <= CURRENT_TIMESTAMP
            ORDER BY next_attempt ASC LIMIT 1
            FOR UPDATE SKIP LOCKED;
        """)
        result = cursor.fetchone()
        if result:
            cursor.execute("UPDATE process_queue SET status = 'PROCESSING' WHERE id = %s", (result[0],))
            conn.commit()
            return {"id": result[0], "chat_id": result[1], "text": result[2], "is_pdf": result[3], "attempts": result[4], "max_attempts": result[5]}
        return None
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def reschedule_queue_item(item_id, wait_seconds, attempts, max_attempts):
    if not db_pool: return
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        if attempts + 1 >= max_attempts:
            cursor.execute("UPDATE process_queue SET status = 'DEAD', attempts = %s WHERE id = %s", (attempts + 1, item_id))
        else:
            cursor.execute("""
                UPDATE process_queue 
                SET status = 'PENDING', attempts = %s, next_attempt = CURRENT_TIMESTAMP + INTERVAL '%s seconds'
                WHERE id = %s
            """, (attempts + 1, wait_seconds, item_id))
        conn.commit()
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def complete_queue_item(item_id):
    if not db_pool: return
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("UPDATE process_queue SET status = 'COMPLETED' WHERE id = %s", (item_id,))
        conn.commit()
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def cancel_queue_items(chat_id):
    if not db_pool: return False
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("UPDATE process_queue SET status = 'CANCELLED' WHERE chat_id = %s AND status IN ('PENDING', 'PROCESSING')", (chat_id,))
        conn.commit()
        return True
    except:
        return False
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def save_transactions_to_db(json_data):
    if not db_pool: return False, "DB Connection Failed."
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        for t in json_data.get("transacoes", []):
            card = t.get("cartao") or {}
            location = t.get("local_compra") or {}

            t_type = str(t.get("tipo_transacao") or "DESPESA").upper()
            tx_date = parse_br_date(t.get("dt_transacao"))

            sql_transaction = """
                INSERT INTO transactions (
                    transaction_type, invoice_number, invoice_serial, transaction_date, card_bank, card_variant,
                    location_name, location_type, status, original_amount, discount_applied,
                    total_amount, macro_category, payment_method, is_installment, installment_count
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
            """
            tx_values = (
                t_type, t.get("numero_nota"), t.get("serie_nota"), tx_date, card.get("banco"), card.get("variante"),
                str(location.get("nome") or "DESCONHECIDO").upper(), location.get("tipo"), t.get("status", "Ativa"),
                float(t.get("valor_original") or 0), float(t.get("desconto_aplicado") or 0), float(t.get("valor_total") or 0), 
                str(t.get("categoria_macro") or "").upper(), t.get("metodo_pagamento"), bool(t.get("parcelado")), int(t.get("quantidade_parcelas") or 1)
            )
            cursor.execute(sql_transaction, tx_values)
            transaction_id = cursor.fetchone()[0]

            sql_item = """
                INSERT INTO transaction_items (transaction_id, item_type, item_number, product_code, description, brand, unit_price, quantity, cat_macro, cat_category, cat_subcategory, cat_product)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            for item in t.get("itens", []):
                cat = item.get("hierarquia_categorias") or {}
                cursor.execute(sql_item, (
                    transaction_id, t_type, str(item.get("numero_item_nota") or "").upper(), str(item.get("codigo_produto") or "").upper(),
                    str(item.get("item") or "PRODUTO DESCONHECIDO").upper(), str(item.get("marca") or "").upper(), 
                    float(item.get("valor_unitario") or 0), float(item.get("quantidade") or 1), 
                    str(cat.get("macro") or "").upper(), str(cat.get("categoria") or "").upper(), 
                    str(cat.get("subcategoria") or "").upper(), str(cat.get("produto") or "").upper()
                ))

            sql_installment = """
                INSERT INTO installments (transaction_id, month, due_date, amount, payment_status, payment_date, paid_amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """
            for inst in t.get("detalhamento_parcelas", []):
                cursor.execute(sql_installment, (
                    transaction_id, inst.get("mes"), parse_br_date(inst.get("data_vencimento")), 
                    float(inst.get("valor") or 0), inst.get("status_pagamento", "PENDING"),
                    parse_br_date(inst.get("dt_pagamento")), float(inst.get("valor_pago") or 0)
                ))

        conn.commit()
        return True, "Success"
    except Exception as e:
        if conn: conn.rollback()
        return False, str(e)
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def get_card_from_db(bank, variant):
    if not db_pool: return None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        if variant and str(variant).strip():
            cursor.execute("SELECT closing_day, due_day FROM credit_cards WHERE bank ILIKE %s AND variant ILIKE %s LIMIT 1", (bank, variant))
        else:
            cursor.execute("SELECT closing_day, due_day FROM credit_cards WHERE bank ILIKE %s AND (variant IS NULL OR variant = '') LIMIT 1", (bank,))
        result = cursor.fetchone()
        return {"closing": int(result[0]), "due": int(result[1])} if result else None
    except: return None
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def save_card_to_db(bank, variant, closing, due):
    if not db_pool: return False
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        query = "SELECT id FROM credit_cards WHERE bank ILIKE %s " + ("AND variant ILIKE %s" if variant else "AND (variant IS NULL OR variant = '')")
        cursor.execute(query, (bank, variant) if variant else (bank,))
        exists = cursor.fetchone()

        if exists: cursor.execute("UPDATE credit_cards SET closing_day = %s, due_day = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (int(closing), int(due), exists[0]))
        else: cursor.execute("INSERT INTO credit_cards (bank, variant, closing_day, due_day) VALUES (%s, %s, %s, %s)", (bank, variant if variant else "", int(closing), int(due)))
        conn.commit()
        return True
    except:
        if conn: conn.rollback()
        return False
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def list_cards_from_db():
    if not db_pool: return []
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT bank, variant FROM credit_cards ORDER BY bank")
        return [{"bank": r[0], "variant": r[1] if r[1] else ""} for r in cursor.fetchall()]
    except: return []
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def check_existing_invoice(invoice_number):
    if not db_pool: return False
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM transactions WHERE invoice_number = %s LIMIT 1", (invoice_number,))
        return bool(cursor.fetchone())
    except: return False
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def check_similar_transaction(location, amount, t_date_str):
    if not db_pool: return False
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        t_date = parse_br_date(t_date_str)
        # QUAL-04: ILIKE para case-insensitive
        cursor.execute("""
            SELECT id FROM transactions 
            WHERE location_name ILIKE %s AND total_amount = %s AND transaction_date = %s LIMIT 1
        """, (location, float(amount), t_date))
        return bool(cursor.fetchone()) 
    except: return False
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def get_pending_bills_by_month(month_year):
    if not db_pool: return []
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.id, t.location_name, to_char(i.due_date, 'DD/MM/YYYY'), i.amount 
            FROM installments i JOIN transactions t ON i.transaction_id = t.id
            WHERE i.month = %s AND i.payment_status = 'PENDING' ORDER BY i.due_date ASC
        """, (month_year,))
        return [{"id": r[0], "location": r[1], "due_date": r[2], "amount": float(r[3])} for r in cursor.fetchall()]
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def pay_bill_in_db(installment_id, payment_date_str):
    if not db_pool: return False
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        pay_date = parse_br_date(payment_date_str)
        
        cursor.execute("""
            UPDATE installments SET payment_status = 'PAID', payment_date = %s, paid_amount = amount, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s RETURNING transaction_id
        """, (pay_date, installment_id))
        
        transaction_id = cursor.fetchone()[0]
        
        cursor.execute("SELECT count(*) FROM installments WHERE transaction_id = %s AND payment_status = 'PENDING'", (transaction_id,))
        pending_count = cursor.fetchone()[0]
        if pending_count == 0:
            cursor.execute("UPDATE transactions SET status = 'Paga', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (transaction_id,))
            
        conn.commit()
        return True
    except Exception as e:
        if conn: conn.rollback()
        return False
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)