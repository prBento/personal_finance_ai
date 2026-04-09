# 🏛️ Technical Specification & System Architecture
*(Para a versão em Português, [clique aqui](#-versão-em-português-brasileiro))*

## 👨‍💻 Author
**Bento** — GitHub: [@prBento](https://github.com/prBento)

---

## 🇺🇸 English Version

**Project:** Zotto — Finance AI Data App

---

### 1. Architecture Overview

**Hybrid AI Architecture** with strict separation between intelligence and determinism. LLMs handle unstructured-to-structured translation only. Python handles all financial math, state management, and governance.

**Dual-mode deployment:** In `prod`, FastAPI + Uvicorn serves a Telegram Webhook endpoint on the Railway-provisioned PORT. In `dev`, the same codebase falls back to Long Polling — no Ngrok required. Branch: `if ENV == "prod": uvicorn.run(api)` else `telegram_app.run_polling()`.

---

### 2. Core Components

| # | Component | Technology | Responsibility |
|---|-----------|------------|----------------|
| 1 | **Entry Interface** | `python-telegram-bot` | Async handlers, State Machine, Inline UI |
| 2 | **Web Server (prod)** | FastAPI + Uvicorn | `POST /webhook`, `GET /health` |
| 3 | **Outbox Queue** | PostgreSQL `process_queue` | Decouples ingestion from processing. Guaranteed delivery. |
| 4 | **Document Intelligence** | `BeautifulSoup4`, `PyPDF` | NFC-e URL scraping and PDF text extraction |
| 5 | **AI Agent 1** | Groq `llama-4-scout-17b` | Raw entity extraction. `temperature=0.0`. Chain-of-Thought date parsing. |
| 6 | **AI Agent 2** | Groq `llama-4-scout-17b` | Categorization with disambiguation rules. `temperature=0.1`. |
| 7 | **AP/AR Dashboard** | Telegram Inline UI | Accordion invoice view, isolated view, income/expense differentiation |
| 8 | **Cash Flow Statement** | Telegram Inline UI | `/extrato` with benefit wallet separation and dynamic installment index |
| 9 | **Payment Engine** | `database.py` | Anticipation logic, cash-basis reallocation, dynamic method override |
| 10 | **Database** | PostgreSQL | Relational AP/AR ledger. SCD audit columns. CTE-powered queries. |

---

### 3. Functional Requirements (FRs)

* **FR01** — Multimodal ingestion: free-text, NFC-e URL, PDF.
* **FR02** — Dual LLM pipeline with disambiguation ruleset (NF-e → always DESPESA; Total Pass → Academia; iFood → Alimentação; streaming → Assinaturas).
* **FR03** — Hidden discount detection: `if sum(items) > invoice_total` → auto-register difference as discount.
* **FR04** — Custom installment engine with Brazilian credit card billing rules (fechamento/vencimento cycles).
* **FR05** — Human-in-the-Loop confirmation before every database write. Summary shows discount breakdown when applicable.
* **FR06** — AP/AR Dashboard (`/contas`): accordion credit card grouping, income vs expense visual differentiation, overdue alerts, isolated view, fast-forward navigation, escape hatches.
* **FR07** — Smart payment settlement: dynamic method override at pay time. Credit card anticipation moves installment to next invoice cycle (stays PENDING). Cash/Pix marks PAID and reallocates `month` field.
* **FR08** — Group invoice payment with proportional discount distribution across all items.
* **FR09** — Installment soft-delete (`CANCELED`) for bank reconciliation.
* **FR10** — Cash Flow Statement (`/extrato`): Saldo Atual + Projetado, benefit wallet isolation, `[B]` tag in monospaced list, dynamic installment index (`8/10`), pending item `*` indicator.
* **FR11** — Interactive help system: inline button menu with topic-specific sub-pages and back navigation.
* **FR12** — Duplicate detection: exact `invoice_number` match + fuzzy `(location ILIKE + amount + date)`.

---

### 4. Non-Functional Requirements (NFRs)

* **NFR01** — Resilience: Outbox Pattern + `FOR UPDATE SKIP LOCKED` for concurrent processing safety.
* **NFR02** — Exponential Backoff: standard errors 60s–3600s; TPD rate limit defers 90 minutes.
* **NFR03** — Dead item prevention: `max_attempts` (default 5) → status `DEAD`.
* **NFR04** — Busy-state deferral: `reschedule_queue_item_busy` defers without consuming a retry attempt.
* **NFR05** — Connection Pool: `ThreadedConnectionPool` (1–10).
* **NFR06** — Fault-tolerant JSON: strips LLM hallucinations before `json.loads(..., strict=False)`.
* **NFR07** — Math validation: recalculates totals from items post-LLM; detects hidden discounts.
* **NFR08** — Access control: `ALLOWED_CHAT_IDS` via `security_check` decorator on all public handlers.
* **NFR09** — Cash Basis Accounting: paid installment `month` updated to payment month. `/extrato` shows when money moved; `/contas` retains original `due_date` for bill management.
* **NFR10** — CTE installment indexing: `ROW_NUMBER() OVER (PARTITION BY transaction_id ORDER BY id ASC)` survives `month` field updates.
* **NFR11** — Dual deployment: `if ENV == "prod": uvicorn.run(api)` else `telegram_app.run_polling()`.

---

### 5. Architectural Decisions: The "Why?"

#### 5.1. Dual-Agent LLM Pipeline
Isolated failure modes and calibrated temperatures per task. Chain-of-Thought date reasoning via `_raciocinio_vencimento` field prevents the most common PDF extraction error (emission date vs. due date).

#### 5.2. Transactional Outbox Pattern
Instant UX (< 100ms "Received"). Guaranteed delivery. `FOR UPDATE SKIP LOCKED` prevents race conditions without distributed locks.

#### 5.3. Custom Installment Engine
Brazilian credit card billing (fechamento/vencimento) is not modeled by any standard financial library.

#### 5.4. Credit Card Anticipation vs. Cash Payment
Paying a credit card installment early recalculates the target invoice cycle and moves the debt there — stays PENDING. This models how credit cards actually work. All non-card payments mark PAID and reallocate `month` for cash-basis reporting.

#### 5.5. FastAPI + Long Polling Dual Mode
Webhook requires a public HTTPS URL that doesn't exist locally. The `if ENV == "prod"` branch keeps the same codebase working in both environments with zero extra tooling for local dev.

#### 5.6. `month` vs `due_date` — Two Date Fields by Design
`due_date` is immutable (original contractual date). Used by `/contas` for overdue calculation. `month` is mutable (updated to payment month for cash-basis). Used by `/extrato` for financial reporting. They intentionally diverge after payment.

#### 5.7. Benefit Wallet Separation
VA/VR/prepaid balances are not fungible with cash. Mixing them gives a misleading picture of available liquidity.

#### 5.8. CTE `ROW_NUMBER()` for Installment Index
The sequence must survive cash-basis `month` field updates. Computing from the immutable `id` column at query time always returns the correct "8 of 10".

---

### 6. Database Schema

```
credit_cards
    id, bank, variant, closing_day, due_day

process_queue
    id, chat_id, received_text, is_pdf
    status [PENDING | PROCESSING | COMPLETED | DEAD | CANCELLED]
    attempts, max_attempts, next_attempt

transactions  ←─────────────────────────────────────────┐
    id, transaction_type, invoice_number                 │ FK ON DELETE CASCADE
    transaction_date (DATE), location_name               │
    card_bank, card_variant                              │
    status [Ativa | PAID]                                │
    original_amount, discount_applied, total_amount      │
    macro_category, payment_method                       │
    is_installment, installment_count                    │
                                                         │
transaction_items ─── transaction_id (FK) ───────────────┤
    description, brand, unit_price, quantity             │
    cat_macro, cat_category, cat_subcategory             │
                                                         │
installments ──────── transaction_id (FK) ───────────────┘
    month (MM/YYYY)  ← mutable: updated to payment month (cash basis)
    due_date (DATE)  ← immutable: original contractual date
    amount, payment_status [PENDING | PAID | CANCELED]
    payment_date (DATE), paid_amount

Indexes:
  idx_installments_month_status ON installments(month, payment_status)
  idx_queue_status_next         ON process_queue(status, next_attempt)
  idx_transactions_date_type    ON transactions(transaction_date, transaction_type)
```

---

### 7. Deployment Architecture

```
Railway (prod)
├── Service type: web  ← requires Procfile: "web: python bot.py"
│   ├── FastAPI app binds to PORT env var
│   ├── GET  /health   → Railway liveness probe
│   └── POST /webhook  → telegram_app.process_update(update)
│                          └── job_queue (10s) → queue_processor()
└── Plugin: PostgreSQL (internal DATABASE_URL)

Local (dev)
└── python bot.py
    └── telegram_app.run_polling()
        └── job_queue (10s) → queue_processor()
```

---

### 8. Security Strategy

- **Secrets:** `.env` locally, Railway Variables panel in production. Never hardcoded.
- **Access control:** `ALLOWED_CHAT_IDS` whitelist via `security_check` decorator on all public handlers.
- **Stateless:** PDFs deleted in `finally` blocks. No sensitive state written to disk.
- **SQL injection:** All queries use parameterized `%s` placeholders.
- **Webhook security:** `/webhook` endpoint only accepts updates routed from Telegram's registered URL.

---
---

## 🇧🇷 Versão em Português Brasileiro

**Projeto:** Zotto — Finance AI Data App

---

### 1. Visão Geral

**Arquitetura de IA Híbrida.** LLMs traduzem inputs desestruturados. Python lida com toda a matemática financeira, estados e governança.

**Deploy de dois modos:** Em `prod`, FastAPI + Uvicorn recebe Webhook do Telegram na PORT do Railway. Em `dev`, o mesmo código usa Long Polling sem configuração extra.

---

### 2. Componentes Principais

| # | Componente | Tecnologia | Responsabilidade |
|---|-----------|------------|----------------|
| 1 | **Interface** | `python-telegram-bot` | Handlers assíncronos, Máquina de Estados, UI inline |
| 2 | **Servidor Web (prod)** | FastAPI + Uvicorn | `POST /webhook`, `GET /health` |
| 3 | **Fila Outbox** | PostgreSQL `process_queue` | Garante entrega desacoplando ingestão do processamento |
| 4 | **Inteligência de Docs** | `BeautifulSoup4`, `PyPDF` | Scraping NFC-e e extração de PDF |
| 5 | **IA Agente 1** | Groq `llama-4-scout-17b` | Extração bruta. `temperature=0.0`. Chain-of-Thought para datas. |
| 6 | **IA Agente 2** | Groq `llama-4-scout-17b` | Categorização com regras de desambiguação. `temperature=0.1`. |
| 7 | **Dashboard AP/AR** | Telegram Inline UI | Acordeon de faturas, modo isolado, diferenciação Receita/Despesa |
| 8 | **Extrato** | Telegram Inline UI | Saldo benefício, índice de parcela, regime de caixa |
| 9 | **Motor de Pagamento** | `database.py` | Antecipação, regime de caixa, sobrescrita de método |
| 10 | **Banco de Dados** | PostgreSQL | Livro Caixa AP/AR com SCD e queries CTE |

---

### 3–8.

Os Requisitos Funcionais, RNFs, Decisões Arquiteturais, Schema e Segurança seguem a mesma estrutura da versão em inglês acima. Destaques para o contexto brasileiro:

**Decisão 5.4 — Antecipação de Cartão vs. Pagamento à Vista:**
Pagar antecipado num cartão de crédito move a parcela para o ciclo de fatura alvo (permanece PENDENTE). Isso modela o comportamento real — pagar antes do fechamento não quita a dívida, muda para a próxima fatura. Pagamentos à vista marcam PAGO e realocam `month` para o mês do pagamento real (Regime de Caixa).

**Decisão 5.6 — `month` vs. `due_date`:**
`due_date` é imutável (data contratual). Usada pelo `/contas` para cálculo de vencimento. `month` é mutável (atualizado pelo regime de caixa). Usado pelo `/extrato` para relatórios financeiros. Os dois campos divergem intencionalmente após o pagamento.