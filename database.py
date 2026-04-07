import os
import psycopg2
from psycopg2 import pool
from datetime import datetime
from dotenv import load_dotenv
from dateutil.relativedelta import relativedelta

# Loads environment variables from the .env file (like DATABASE_URL)
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
conn = None

try:
    # A ThreadedConnectionPool manages multiple database connections simultaneously.
    # Since the Telegram bot uses asynchronous programming and handles multiple users
    # at the same time, we need a thread-safe pool to avoid connection exhaustion.
    # We set a minimum of 1 connection and a maximum of 10.
    db_pool = psycopg2.pool.ThreadedConnectionPool(1, 10, DATABASE_URL)
except Exception as e:
    print(f"Error initializing connection pool: {e}")
    db_pool = None

def parse_br_date(date_str):
    """
    Parses a Brazilian formatted date string into a Python Date object.

    This is crucial for PostgreSQL, which expects dates in a standard format (YYYY-MM-DD).
    If the string is invalid or empty, it defaults to the current date to prevent
    the database from throwing a fatal error.

    Args:
        date_str (str): Date string in "DD/MM/YYYY" format.

    Returns:
        datetime.date: A valid Python date object, or today's date if parsing fails.
    """
    # Checks if the string is empty or explicitly says "null"
    if not date_str or date_str.lower() == "null": return None
    try: 
        # Converts "DD/MM/YYYY" string into a date object
        return datetime.strptime(date_str, "%d/%m/%Y").date()
    except Exception as e: 
        print(f"[WARN] parse_br_date failed for '{date_str}': {e}. Using today's date.")
        # Fallback mechanism: return today's date if the AI hallucinated the format
        return datetime.now().date()

def create_tables():
    """
    Initializes the database schema (Tables, Foreign Keys, and Indexes).

    This function uses 'CREATE TABLE IF NOT EXISTS', meaning it's safe to run
    every time the bot starts. It won't overwrite existing data.
    It builds a relational structure where 'transactions' is the parent,
    and 'transaction_items' and 'installments' are children.

    Returns:
        None
    """
    if not db_pool: return
    conn = None
    try:
        # Grabs an available connection from the pool
        conn = db_pool.getconn()
        cursor = conn.cursor()
        
        # 1. Outbox Queue Table: Used for resilience and handling Groq's API limits
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS process_queue (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                received_text TEXT,
                is_pdf BOOLEAN,
                status VARCHAR(20) DEFAULT 'PENDING',
                attempts INT DEFAULT 0,
                max_attempts INT DEFAULT 5,
                next_attempt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                json_result TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Main Transactions Table: Stores the header info of the receipt/invoice
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
        
        # 3. Items Table: Linked to 'transactions' via Foreign Key
        # 'ON DELETE CASCADE' means if the parent transaction is deleted, its items die with it.
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
        
        # 4. Installments Table (Accounts Payable/Receivable Engine)
        # Includes a CHECK constraint using Regex to ensure the month is always 'MM/YYYY'
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS installments (
                id SERIAL PRIMARY KEY,
                transaction_id INT REFERENCES transactions(id) ON DELETE CASCADE,
                month VARCHAR(7) CHECK (month ~ '^\\d{2}/\\d{4}$'),
                due_date DATE,
                amount DECIMAL(10, 2),
                payment_status VARCHAR(20) DEFAULT 'PENDING',
                payment_date DATE,
                paid_amount DECIMAL(10, 2) DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 5. Credit Cards Registry: Stores card rules (closing/due dates)
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

        # Performance Indexes: Speeds up specific searches in the database (like filtering by month)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_installments_month_status ON installments(month, payment_status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_status_next ON process_queue(status, next_attempt);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date_type ON transactions(transaction_date, transaction_type);")

        conn.commit()  # Saves all changes to the database
    except Exception as e:
        print(f"Error creating tables: {e}")
        if conn: conn.rollback()  # If any error occurs, undo everything to prevent corruption
    finally:
        # Always close the cursor and return the connection back to the pool
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def add_to_queue(chat_id, text, is_pdf):
    """
    Inserts a new raw text or PDF payload into the Outbox Queue.

    Args:
        chat_id (int): The Telegram user ID.
        text (str): The raw text or extracted PDF text.
        is_pdf (bool): Flag indicating if the source was a document.

    Returns:
        bool: True if insertion was successful, False otherwise.
    """
    if not db_pool: return False
    conn = None
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
    """
    Fetches the next available item from the queue safely.

    CRITICAL CONCEPT: 'FOR UPDATE SKIP LOCKED'
    This prevents "Race Conditions". If two bot workers try to read the queue
    at the exact same millisecond, the database locks the row for Worker 1,
    and forces Worker 2 to "skip" and grab the next available row. 
    This ensures the same receipt is never processed twice.

    Returns:
        dict: A dictionary containing the queue item details, or None if empty.
    """
    if not db_pool: return None
    conn = None
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
            # Immediately mark it as 'PROCESSING' so other workers ignore it
            cursor.execute("UPDATE process_queue SET status = 'PROCESSING' WHERE id = %s", (result[0],))
            conn.commit()
            return {"id": result[0], "chat_id": result[1], "text": result[2], "is_pdf": result[3], "attempts": result[4], "max_attempts": result[5]}
        return None
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def reschedule_queue_item(item_id, wait_seconds, attempts, max_attempts):
    """
    Pushes a failed item back into the future for a retry (Exponential Backoff / Rate Limit).

    Args:
        item_id (int): The queue row ID.
        wait_seconds (int): How many seconds into the future to schedule the next attempt.
        attempts (int): Current number of attempts.
        max_attempts (int): Threshold for permanent failure.
    """
    if not db_pool: return
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        
        # If it reached the limit, mark it as DEAD so it stops looping
        if attempts + 1 >= max_attempts:
            cursor.execute("UPDATE process_queue SET status = 'DEAD', attempts = %s WHERE id = %s", (attempts + 1, item_id))
        else:
            # Increment attempts and push the 'next_attempt' timestamp into the future
            cursor.execute("""
                UPDATE process_queue 
                SET status = 'PENDING', attempts = %s, 
                next_attempt = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')
                WHERE id = %s
            """, (attempts + 1, wait_seconds, item_id))
        conn.commit()
    except Exception as e:
        print(f"[DB ERROR] reschedule: {e}")
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def complete_queue_item(item_id):
    """Marks a queue item as successfully processed."""
    if not db_pool: return
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("UPDATE process_queue SET status = 'COMPLETED' WHERE id = %s", (item_id,))
        conn.commit()
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def cancel_queue_items(chat_id):
    """Soft deletes all pending queue items for a specific user (used by the /cancelar command)."""
    if not db_pool: return False
    conn = None
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
    """
    Master function to insert the finalized AI JSON into the relational database.

    This executes a 3-step hierarchical insertion:
    1. Inserts the parent 'transactions' row and retrieves its auto-generated ID using 'RETURNING id'.
    2. Loops through the JSON items, inserting them into 'transaction_items' linked by the parent ID.
    3. Loops through the generated installments, inserting them into 'installments'.

    Args:
        json_data (dict): The deeply nested, validated JSON generated by the AI and bot rules.

    Returns:
        tuple: (bool success, str error_message)
    """
    if not db_pool: return False, "DB Connection Failed."
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        for t in json_data.get("transacoes", []):
            card = t.get("cartao") or {}
            location = t.get("local_compra") or {}

            t_type = str(t.get("tipo_transacao") or "DESPESA").upper()
            tx_date = parse_br_date(t.get("dt_transacao"))

            # Step 1: Insert Parent Transaction
            # RETURNING id allows us to grab the PostgreSQL-generated primary key immediately
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
            transaction_id = cursor.fetchone()[0] # Grabbing the returned ID

            # Step 2: Insert Child Items
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

            # Step 3: Insert Installments (Accounts Payable tracking)
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
    """Fetches credit card closing/due rules to automatically calculate invoice dates."""
    if not db_pool: return None
    conn = None
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
    """Upsert logic: Creates a new credit card or updates an existing one if the rules changed."""
    if not db_pool: return False
    conn = None
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
    """Retrieves all distinct credit cards to build the Telegram Inline Keyboard."""
    if not db_pool: return []
    conn = None
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
    """Idempotency check: Verifies if a specific invoice ID already exists to prevent duplicate ingestion."""
    if not db_pool: return False
    conn = None
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
    """Heuristic check: Triggers a duplicate warning if Location, Amount, and Date match exactly."""
    if not db_pool: return False
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        t_date = parse_br_date(t_date_str)
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
    """
    Core function for the Telegram '/contas' command.
    Includes the 'transaction_id' and 'transaction_type' to isolate specific bills 
    and visually differentiate Incomes from Expenses.
    """
    if not db_pool: return []
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.id, t.location_name, to_char(i.due_date, 'DD/MM/YYYY'), i.amount, 
                   t.card_bank, t.card_variant, (i.due_date < CURRENT_DATE) as is_overdue,
                   t.id as transaction_id, t.transaction_type
            FROM installments i JOIN transactions t ON i.transaction_id = t.id
            WHERE i.month = %s AND i.payment_status = 'PENDING' ORDER BY i.due_date ASC
        """, (month_year,))
        return [{
            "id": r[0], "location": r[1], "due_date": r[2], "amount": float(r[3]),
            "bank": r[4], "variant": r[5], "is_overdue": bool(r[6]),
            "transaction_id": r[7], "type": r[8]
        } for r in cursor.fetchall()]
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)


def get_all_overdue_installments():
    """
    Fetches every pending installment across ALL months that has passed its due date.
    Used to generate a global warning banner on the Telegram UI.
    """
    if not db_pool: return []
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.id, t.location_name, to_char(i.due_date, 'DD/MM/YYYY'), i.amount, i.month
            FROM installments i JOIN transactions t ON i.transaction_id = t.id
            WHERE i.payment_status = 'PENDING' AND i.due_date < CURRENT_DATE
            ORDER BY i.due_date ASC
        """)
        return [{"id": r[0], "location": r[1], "due_date": r[2], "amount": float(r[3]), "month": r[4]} for r in cursor.fetchall()]
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def calculate_invoice_due_date_db(action_date, closing_day, due_day):
    """Calcula a data da fatura alvo baseada no dia da antecipação."""
    if closing_day == 0 and due_day == 0: return action_date
    base_month = action_date.replace(day=1)
    if action_date.day >= closing_day:
        base_month += relativedelta(months=1)
    if due_day < closing_day:
        base_month += relativedelta(months=1)
    return base_month + relativedelta(day=due_day)

def pay_bill_in_db(installment_id, payment_date_str, custom_paid_amount=None):
    """
    Motor Avançado de Pagamento e Antecipação (Regime de Caixa).
    Diferencia antecipação de contas à vista vs cartões de crédito.
    """
    if not db_pool: return False, "Erro de Conexão."
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        pay_date = parse_br_date(payment_date_str)
        pay_month_str = pay_date.strftime("%m/%Y")
        
        # 1. Pega os dados completos da parcela e transação pai
        cursor.execute("""
            SELECT i.amount, i.transaction_id, i.month, i.due_date,
                   t.card_bank, t.card_variant, t.payment_method
            FROM installments i
            JOIN transactions t ON i.transaction_id = t.id
            WHERE i.id = %s
        """, (installment_id,))
        row = cursor.fetchone()
        if not row: return False, "Parcela não encontrada."
        
        original_amount, trans_id, inst_month, inst_due, bank, variant, method = row
        
        final_paid_amount = float(custom_paid_amount) if custom_paid_amount is not None else float(original_amount)
        discount = float(original_amount) - final_paid_amount

        # Verifica se é um pagamento envolvendo cartão de crédito
        is_credit_card = bank and ("crédito" in str(method).lower() or "credito" in str(method).lower())
        
        if is_credit_card:
            # Busca as regras de fechamento do cartão
            cursor.execute("SELECT closing_day, due_day FROM credit_cards WHERE bank ILIKE %s AND COALESCE(variant, '') ILIKE %s LIMIT 1", (bank, variant or ''))
            card_rules = cursor.fetchone()
            closing = int(card_rules[0]) if card_rules else 0
            due = int(card_rules[1]) if card_rules else 0
            
            # Descobre qual é a "Fatura Aberta Atual" baseada no dia da antecipação
            new_due_date = calculate_invoice_due_date_db(pay_date, closing, due)
            
            # Se a fatura atual é antes do vencimento original, caracteriza ANTECIPAÇÃO NO CARTÃO
            if new_due_date < inst_due:
                new_month_str = new_due_date.strftime("%m/%Y")
                
                # Move a parcela para o mês da fatura alvo, reduz o valor (desconto), mas MANTÉM PENDENTE!
                cursor.execute("""
                    UPDATE installments
                    SET due_date = %s,
                        month = %s,
                        amount = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (new_due_date, new_month_str, final_paid_amount, installment_id))
                
                # Ajusta o balanço da transação original
                if discount != 0.0:
                    cursor.execute("""
                        UPDATE transactions 
                        SET discount_applied = COALESCE(discount_applied, 0) + %s,
                            total_amount = total_amount - %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (discount, discount, trans_id))
                
                conn.commit()
                return True, f"⚠️ *Conta antecipada!* Ela foi movida para a fatura de *{new_month_str}* (Ficará pendente até você pagar o cartão)."

        # SE NÃO FOR CARTÃO (ou se for cartão pago em atraso/na data correta): Pagamento Realizado
        cursor.execute("""
            UPDATE installments 
            SET payment_status = 'PAID', payment_date = %s, paid_amount = %s, 
                month = %s, -- REALOCA para o mês de pagamento para refletir no Extrato!
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (pay_date, final_paid_amount, pay_month_str, installment_id))
        
        # Ajusta descontos
        if discount != 0.0:
            cursor.execute("""
                UPDATE transactions 
                SET discount_applied = COALESCE(discount_applied, 0) + %s,
                    total_amount = total_amount - %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (discount, discount, trans_id))
            
        # Cascata de Pai Pago
        cursor.execute("SELECT count(*) FROM installments WHERE transaction_id = %s AND payment_status = 'PENDING'", (trans_id,))
        if cursor.fetchone()[0] == 0:
            cursor.execute("UPDATE transactions SET status = 'PAID', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (trans_id,))
            
        conn.commit()
        return True, f"✅ Baixado com sucesso em {payment_date_str}!"
    except Exception as e:
        print(f"[DB ERROR] pay_bill: {e}")
        if conn: conn.rollback()
        return False, "Erro ao gravar no banco de dados."
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)


def cancel_installment(installment_id):
    """
    Soft Deletes a specific installment by changing its status to 'CANCELED'.

    This is heavily used for Bank Reconciliation. When a user inputs their full
    credit card invoice for the month, they can "Cancel" the individual predicted
    installments for that month so the Streamlit Dashboard doesn't count the expense twice,
    while leaving future installments of the same purchase untouched.

    Args:
        installment_id (int): Target row ID.

    Returns:
        bool: Success status.
    """
    if not db_pool: return False
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("UPDATE installments SET payment_status = 'CANCELED', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (installment_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"[DB ERROR] cancel_installment: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def reschedule_queue_item_busy(item_id, wait_seconds):
    """
    Defers an item without consuming a retry attempt.
    Used when the bot detects the user is currently answering a questionnaire (busy state),
    so the queue pauses silently instead of interrupting the user's flow.
    """
    if not db_pool: return
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE process_queue SET status = 'PENDING',
            next_attempt = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')
            WHERE id = %s
        """, (wait_seconds, item_id))
        conn.commit()
    except Exception as e:
        print(f"[DB ERROR] reschedule_busy: {e}")
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)


def get_max_pending_month():
    """
    Finds the absolute furthest month in the future that contains a pending bill.
    Used for the 'Fast-Forward' (⏭️) button in the AP UI.
    """
    if not db_pool: return None
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        # PostgreSQL trick: Convert MM/YYYY string to a real date to find the max properly
        cursor.execute("""
            SELECT MAX(TO_DATE(month, 'MM/YYYY')) 
            FROM installments 
            WHERE payment_status = 'PENDING'
        """)
        max_date = cursor.fetchone()[0]
        return max_date.strftime("%m/%Y") if max_date else None
    except Exception as e:
        print(f"[DB ERROR] get_max_pending_month: {e}")
        return None
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def pay_grouped_card_bills_in_db(month_year, bank, variant, payment_date_str, custom_paid_amount=None):
    """
    Paga todas as faturas do cartão e realoca os meses das parcelas para o mês de pagamento (Caixa).
    """
    if not db_pool: return False, "Erro de conexão."
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        pay_date = parse_br_date(payment_date_str)
        pay_month_str = pay_date.strftime("%m/%Y")
        
        cursor.execute("""
            SELECT i.id, i.amount, i.transaction_id 
            FROM installments i 
            JOIN transactions t ON i.transaction_id = t.id
            WHERE i.month = %s AND i.payment_status = 'PENDING' 
              AND t.card_bank = %s AND COALESCE(t.card_variant, '') = %s
        """, (month_year, bank, variant if variant else ''))
        
        installments = cursor.fetchall()
        if not installments: return False, "Nenhuma fatura pendente encontrada."
        
        total_original_amount = sum(float(row[1]) for row in installments)
        final_paid_amount = float(custom_paid_amount) if custom_paid_amount is not None else total_original_amount
        total_discount = total_original_amount - final_paid_amount
        discount_ratio = total_discount / total_original_amount if total_original_amount > 0 else 0

        for inst_id, original_amt, trans_id in installments:
            item_discount = float(original_amt) * discount_ratio
            item_paid = float(original_amt) - item_discount
            
            cursor.execute("""
                UPDATE installments 
                SET payment_status = 'PAID', payment_date = %s, paid_amount = %s, 
                    month = %s, -- Alinha com o Regime de Caixa para o Extrato
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (pay_date, item_paid, pay_month_str, inst_id))
            
            if item_discount != 0.0:
                cursor.execute("""
                    UPDATE transactions 
                    SET discount_applied = COALESCE(discount_applied, 0) + %s,
                        total_amount = total_amount - %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (item_discount, item_discount, trans_id))
                
            cursor.execute("SELECT count(*) FROM installments WHERE transaction_id = %s AND payment_status = 'PENDING'", (trans_id,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("UPDATE transactions SET status = 'PAID', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (trans_id,))
                
        conn.commit()
        return True, f"✅ Fatura inteira baixada com sucesso em {payment_date_str}!"
    except Exception as e:
        print(f"[DB ERROR] pay_grouped_card_bills: {e}")
        if conn: conn.rollback()
        return False, "Erro ao gravar no banco."
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def get_max_month_for_transaction(installment_id):
    """
    Finds the absolute last month (due date) for a specific transaction.
    Returns both the month and the transaction_id to build the Isolated View.
    """
    if not db_pool: return None, None
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT transaction_id FROM installments WHERE id = %s", (installment_id,))
        row = cursor.fetchone()
        if not row: return None, None
        transaction_id = row[0]
        
        cursor.execute("""
            SELECT MAX(TO_DATE(month, 'MM/YYYY')) 
            FROM installments 
            WHERE transaction_id = %s AND payment_status = 'PENDING'
        """, (transaction_id,))
        max_date = cursor.fetchone()[0]
        return (max_date.strftime("%m/%Y"), transaction_id) if max_date else (None, None)
    except Exception as e:
        print(f"[DB ERROR] get_max_month_for_transaction: {e}")
        return None, None
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)

def get_cash_flow_by_month(month_year):
    """
    Fetches the complete Cash Flow statement for a specific month.
    Uses a CTE with ROW_NUMBER() to dynamically calculate the original 
    installment index (e.g., 8 of 10) regardless of due date changes.
    """
    if not db_pool: return []
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        
        cursor.execute("""
            WITH InstNums AS (
                SELECT id, ROW_NUMBER() OVER(PARTITION BY transaction_id ORDER BY id ASC) as inst_num
                FROM installments
            )
            SELECT i.id, t.location_name, to_char(i.due_date, 'DD/MM/YYYY'), 
                   to_char(i.payment_date, 'DD/MM/YYYY'), i.amount, i.paid_amount, 
                   t.transaction_type, i.payment_status, t.payment_method,
                   t.is_installment, t.installment_count, n.inst_num
            FROM installments i 
            JOIN transactions t ON i.transaction_id = t.id
            JOIN InstNums n ON i.id = n.id
            WHERE i.month = %s AND i.payment_status != 'CANCELED'
            ORDER BY i.due_date ASC
        """, (month_year,))
        
        return [{
            "id": r[0], 
            "location": r[1], 
            "due_date": r[2], 
            "payment_date": r[3],
            "expected_amount": float(r[4]), 
            "paid_amount": float(r[5] or 0),
            "type": r[6], 
            "status": r[7],
            "method": str(r[8] or ""),
            "is_installment": bool(r[9]),
            "installment_count": int(r[10] or 1),
            "inst_num": int(r[11] or 1)
        } for r in cursor.fetchall()]
    except Exception as e:
        print(f"[DB ERROR] get_cash_flow_by_month: {e}")
        return []
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn: db_pool.putconn(conn)