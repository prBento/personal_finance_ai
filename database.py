import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Establishes and returns a connection to the PostgreSQL database."""
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

def create_tables():
    """Creates all necessary relational tables if they do not exist."""
    conn = get_db_connection()
    if not conn: return
    try:
        cursor = conn.cursor()
        
        # Outbox Queue Table for processing messages asynchronously
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS process_queue (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                received_text TEXT,
                is_pdf BOOLEAN,
                status VARCHAR(20) DEFAULT 'PENDING',
                attempts INT DEFAULT 0,
                next_attempt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                json_result TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Main Transactions Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                transaction_type VARCHAR(20) DEFAULT 'DESPESA',
                invoice_number VARCHAR(50),
                invoice_serial VARCHAR(50),
                transaction_date VARCHAR(20),
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
        
        # Transaction Items (1-to-N relationship with transactions)
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
        
        # AP/AR Ledger (Accounts Payable/Receivable)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS installments (
                id SERIAL PRIMARY KEY,
                transaction_id INT REFERENCES transactions(id) ON DELETE CASCADE,
                month VARCHAR(20),
                due_date VARCHAR(20),
                amount DECIMAL(10, 2),
                payment_status VARCHAR(20) DEFAULT 'PENDING',
                payment_date VARCHAR(20),
                paid_amount DECIMAL(10, 2) DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # User's Credit Cards configuration
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
        conn.commit()
    except Exception as e:
        print(f"Error creating tables: {e}")
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

def add_to_queue(chat_id, text, is_pdf):
    """Inserts a new message/document into the Outbox Queue for background processing."""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO process_queue (chat_id, received_text, is_pdf, status)
            VALUES (%s, %s, %s, 'PENDING')
        """, (chat_id, text, is_pdf))
        conn.commit()
        return True
    finally:
        if conn: conn.close()

def get_next_in_queue():
    """Fetches the next pending item from the queue, locking it for processing."""
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, chat_id, received_text, is_pdf, attempts 
            FROM process_queue 
            WHERE status = 'PENDING' AND next_attempt <= CURRENT_TIMESTAMP
            ORDER BY next_attempt ASC LIMIT 1
            FOR UPDATE SKIP LOCKED;
        """)
        result = cursor.fetchone()
        if result:
            cursor.execute("UPDATE process_queue SET status = 'PROCESSING' WHERE id = %s", (result[0],))
            conn.commit()
            return {"id": result[0], "chat_id": result[1], "text": result[2], "is_pdf": result[3], "attempts": result[4]}
        return None
    finally:
        if conn: conn.close()

def reschedule_queue_item(item_id, wait_seconds, attempts):
    """Reschedules a failed queue item using Exponential Backoff."""
    conn = get_db_connection()
    if not conn: return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE process_queue 
            SET status = 'PENDING', attempts = %s, next_attempt = CURRENT_TIMESTAMP + INTERVAL '%s seconds'
            WHERE id = %s
        """, (attempts + 1, wait_seconds, item_id))
        conn.commit()
    finally:
        if conn: conn.close()

def complete_queue_item(item_id):
    """Marks a queue item as fully processed."""
    conn = get_db_connection()
    if not conn: return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE process_queue SET status = 'COMPLETED' WHERE id = %s", (item_id,))
        conn.commit()
    finally:
        if conn: conn.close()

def cancel_queue_items(chat_id):
    """Cancels all pending queue items for a specific user (Cancel Command)."""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE process_queue 
            SET status = 'CANCELLED' 
            WHERE chat_id = %s AND status IN ('PENDING', 'PROCESSING')
        """, (chat_id,))
        conn.commit()
        return True
    except Exception as e:
        return False
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

def save_transactions_to_db(json_data):
    """Parses the LLM JSON output (PT) and saves it into the Database tables (EN)."""
    conn = get_db_connection()
    if not conn: return False, "DB Connection Failed."
    try:
        cursor = conn.cursor()
        for t in json_data.get("transacoes", []):
            card = t.get("cartao") or {}
            location = t.get("local_compra") or {}

            t_type = str(t.get("tipo_transacao") or "DESPESA").upper()
            v_orig = float(t.get("valor_original") or 0.0)
            v_desc = float(t.get("desconto_aplicado") or 0.0)
            v_paid = float(t.get("valor_total") or 0.0)
            is_installment = bool(t.get("parcelado"))
            install_qty = int(t.get("quantidade_parcelas") or 1)

            # Insert Main Transaction
            sql_transaction = """
                INSERT INTO transactions (
                    transaction_type, invoice_number, invoice_serial, transaction_date, card_bank, card_variant,
                    location_name, location_type, status, original_amount, discount_applied,
                    total_amount, macro_category, payment_method, is_installment,
                    installment_count
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """
            tx_values = (
                t_type, t.get("numero_nota"), t.get("serie_nota"), t.get("dt_transacao"),
                card.get("banco"), card.get("variante"),
                str(location.get("nome") or "DESCONHECIDO").upper(), location.get("tipo"), t.get("status", "Ativa"),
                v_orig, v_desc, v_paid, str(t.get("categoria_macro") or "").upper(),
                t.get("metodo_pagamento"), is_installment, install_qty
            )
            cursor.execute(sql_transaction, tx_values)
            transaction_id = cursor.fetchone()[0]

            # Insert Items
            sql_item = """
                INSERT INTO transaction_items (
                    transaction_id, item_type, item_number, product_code, description, brand, unit_price,
                    quantity, cat_macro, cat_category, cat_subcategory, cat_product
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            for item in t.get("itens", []):
                cat = item.get("hierarquia_categorias") or {}
                item_values = (
                    transaction_id, t_type,
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
                cursor.execute(sql_item, item_values)

            # Insert Installments (AP/AR Ledger)
            sql_installment = """
                INSERT INTO installments (
                    transaction_id, month, due_date, amount, payment_status, payment_date, paid_amount
                ) VALUES (%s, %s, %s, %s, %s, %s, %s);
            """
            for inst in t.get("detalhamento_parcelas", []):
                inst_values = (
                    transaction_id, inst.get("mes"), inst.get("data_vencimento"), 
                    float(inst.get("valor") or 0.0), inst.get("status_pagamento", "PENDING"),
                    inst.get("dt_pagamento"), float(inst.get("valor_pago") or 0.0)
                )
                cursor.execute(sql_installment, inst_values)

        conn.commit()
        return True, "Success"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

def get_card_from_db(bank, variant):
    """Retrieves credit card statement rules from DB."""
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        if variant and str(variant).strip():
            cursor.execute("SELECT closing_day, due_day FROM credit_cards WHERE bank ILIKE %s AND variant ILIKE %s LIMIT 1", (bank, variant))
        else:
            cursor.execute("SELECT closing_day, due_day FROM credit_cards WHERE bank ILIKE %s AND (variant IS NULL OR variant = '') LIMIT 1", (bank,))
        result = cursor.fetchone()
        if result:
            return {"closing": int(result[0]), "due": int(result[1])}
        return None
    except:
        return None
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

def save_card_to_db(bank, variant, closing, due):
    """Upserts a credit card configuration into DB."""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        if variant and str(variant).strip():
            cursor.execute("SELECT id FROM credit_cards WHERE bank ILIKE %s AND variant ILIKE %s", (bank, variant))
        else:
            cursor.execute("SELECT id FROM credit_cards WHERE bank ILIKE %s AND (variant IS NULL OR variant = '')", (bank,))
        exists = cursor.fetchone()

        if exists:
            cursor.execute("UPDATE credit_cards SET closing_day = %s, due_day = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (int(closing), int(due), exists[0]))
        else:
            cursor.execute("INSERT INTO credit_cards (bank, variant, closing_day, due_day) VALUES (%s, %s, %s, %s)", (bank, variant if variant else "", int(closing), int(due)))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        return False
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

def list_cards_from_db():
    """Returns a list of all saved credit cards for Telegram Keyboards."""
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT bank, variant FROM credit_cards ORDER BY bank")
        results = cursor.fetchall()
        return [{"bank": r[0], "variant": r[1] if r[1] else ""} for r in results]
    except:
        return []
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

def check_existing_invoice(invoice_number):
    """Heuristic 1: Exact match on Invoice Number to prevent duplicates."""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM transactions WHERE invoice_number = %s LIMIT 1", (invoice_number,))
        return bool(cursor.fetchone())
    except:
        return False
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

def check_similar_transaction(location, amount, t_date):
    """Heuristic 2: Fuzzy match on Location, Amount, and Date to detect shadow duplicates."""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM transactions 
            WHERE location_name = %s 
            AND total_amount = %s 
            AND transaction_date = %s
            LIMIT 1
        """, (location.upper(), float(amount), t_date))
        return bool(cursor.fetchone()) 
    except Exception as e:
        return False
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

def get_pending_bills_by_month(month_year):
    """Retrieves all pending installments for a given month for the Inline UI."""
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.id, t.location_name, i.due_date, i.amount 
            FROM installments i
            JOIN transactions t ON i.transaction_id = t.id
            WHERE i.month = %s AND i.payment_status = 'PENDING'
            ORDER BY i.due_date ASC
        """, (month_year,))
        results = cursor.fetchall()
        return [{"id": r[0], "location": r[1], "due_date": r[2], "amount": float(r[3])} for r in results]
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()

def pay_bill_in_db(installment_id, payment_date):
    """Updates an installment status to PAID (AP/AR Ledger Write)."""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE installments 
            SET payment_status = 'PAID', 
                payment_date = %s, 
                paid_amount = amount,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (payment_date, installment_id))
        conn.commit()
        return True
    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()