# 🏛️ Technical Specification & System Architecture
*(Para a versão em Português, [clique aqui](#-versão-em-português-brasileiro))*

## 👨‍💻 Author
**Bento**
- GitHub: [@prBento](https://github.com/prBento)

---

## 🇺🇸 English Version

**Project:** Zotto — Finance AI Data App
**Role:** Full-Stack Data Engineer & Product Owner

---

### 1. Architecture Overview

This system is a **Full-Stack Data Application** built on a **Hybrid AI Architecture**. The core design philosophy is a strict separation of concerns between intelligence and determinism: LLMs are used exclusively for translating unstructured human language and chaotic documents into structured data, while Python handles all deterministic operations: financial mathematics, state management, and data governance.

The system is cloud-native, deployed on Railway PaaS, and built around an event-driven **Transactional Outbox Pattern** to ensure no user message is ever lost, regardless of API availability.

**Data Flow:** *User input (text, URL, PDF) → Telegram Bot → PostgreSQL Queue → Background Worker → Dual LLM Pipeline (Extract → Enrich) → Human Confirmation UI → Relational Database.*

---

### 2. Core Components

| # | Component | Technology | Responsibility |
|---|-----------|------------|----------------|
| 1 | **Entry Interface** | `python-telegram-bot` | Async user touchpoint. State Machine + Inline UI. |
| 2 | **Outbox Queue** | PostgreSQL `process_queue` | Decouples ingestion from processing. Guarantees delivery. |
| 3 | **Document Intelligence** | `BeautifulSoup4`, `PyPDF` | Scrapes NFC-e URLs and extracts text from PDF utility bills. |
| 4 | **AI Engine — Agent 1** | Groq API (`llama-4-scout-17b`) | Extracts raw entities. `temperature=0.0`. Includes hidden discount detection. |
| 5 | **AI Engine — Agent 2** | Groq API (`llama-4-scout-17b`) | Enriches and categorizes with disambiguation rules. `temperature=0.1`. |
| 6 | **Backend Engine** | Python | Math validation, installment calculation, duplicate detection, discount detection. |
| 7 | **AP/AR Dashboard** | Telegram Inline UI | Grouped invoice view, isolated view, income/expense differentiation. |
| 8 | **Cash Flow Statement** | Telegram Inline UI | Monthly extrato with benefit wallet separation and installment tracking. |
| 9 | **Database** | PostgreSQL | Relational storage with AP/AR Ledger, SCD audit columns, CTE-powered queries. |

---

### 3. Functional Requirements (FRs)

* **FR01 — Multimodal Ingestion:** The bot must accept and process three input types: free-text messages, HTML via NFC-e URLs, and PDF documents.
* **FR02 — AI Extraction & Routing:** Dual LLM pipeline extracts entities, infers missing data, and routes to `RECEITA` or `DESPESA` logic.
* **FR03 — Hidden Discount Detection:** After LLM processing, if the mathematical sum of items exceeds the invoice total, the backend calculates and registers the difference as a discount automatically — catching discounts the LLM missed.
* **FR04 — Installment Calculation (AP/AR Ledger):** Custom engine splits amounts across N installments with correct due dates per Brazilian credit card billing rules.
* **FR05 — Human-in-the-Loop Confirmation:** Structured Markdown summary with explicit user confirmation before any database write.
* **FR06 — AP/AR Management Dashboard (`/contas`):**
  - Groups credit card installments under a consolidated "Fatura" header.
  - Differentiates Incomes (🟢/🟡) from Expenses (🔹/🔴) visually and in all action texts.
  - Overdue bill alerts, month navigation, Fast-Forward (⏭️), and Return to Current Month.
  - Isolated View for tracking a single multi-month purchase timeline.
  - Escape hatches (Close Panel, Cancel Action) at every step.
* **FR07 — Individual Bill Payment:** Pay a single installment/receipt, optionally with discount for early payment.
* **FR08 — Group Invoice Payment (Cash Basis):** Pay all installments of a credit card in one action. The `month` field is updated to the payment month, aligning with **Cash Basis Accounting** so the `/extrato` reflects when money actually moved, not when it was due.
* **FR09 — Installment Cancellation (Reconciliation):** Soft-delete a specific installment (`CANCELED`) for bank reconciliation without affecting other installments of the same purchase.
* **FR10 — Isolated View:** Filter the AP panel to a single transaction's full installment timeline.
* **FR11 — Cash Flow Statement (`/extrato`):**
  - Monthly summary showing Saldo Atual (actual balance) and Saldo Projetado (projected balance).
  - Separates **Main Wallet** (cash, Pix, credit card) from **Benefit Wallet** (VA/VR/prepaid cards) with independent balances.
  - Detailed transaction list in monospaced format with dynamic installment index (e.g., `8/10`), date, and amount columns.
  - Pending/future items marked with `*` indicator.
  - Month navigation with Return to Current Month.
* **FR12 — Duplicate Detection:** Exact `invoice_number` match + fuzzy `(location ILIKE + amount + date)` heuristic.
* **FR13 — Credit Card Management:** Register new cards mid-flow with closing/due day rules for automatic invoice cycle calculation.

---

### 4. Non-Functional Requirements (NFRs)

* **NFR01 — Resilience (Outbox Pattern):** Queue all messages immediately; process asynchronously. No message lost due to API unavailability.
* **NFR02 — Exponential Backoff:** Standard errors: 60s–3600s. TPD (Tokens Per Day) limits: defer to 09:00 AM next day.
* **NFR03 — Dead Item Prevention:** Items beyond `max_attempts` (default: 5) marked as `DEAD`.
* **NFR04 — Busy-State Queue Deferral:** `reschedule_queue_item_busy` defers without consuming a retry attempt when user is in active conversation.
* **NFR05 — Connection Pool:** `ThreadedConnectionPool` (min: 1, max: 10) prevents connection exhaustion on Railway.
* **NFR06 — Fault-Tolerant JSON Parsing:** Strips LLM hallucinations (comments, Python booleans, control chars) before parsing.
* **NFR07 — Math Validation:** Recalculates `valor_total` from items if LLM returns zero; detects hidden discounts via item sum comparison.
* **NFR08 — Access Control (Whitelist):** `ALLOWED_CHAT_IDS` enforced via `security_check` decorator on all public handlers.
* **NFR09 — Stateless Security:** No hardcoded secrets; all via environment variables.
* **NFR10 — Auditability (SCD):** `created_at`/`updated_at` on all tables. `transactions.status` synchronized with child `installments`.
* **NFR11 — Proportional Discount Distribution:** Group invoice discounts distributed proportionally across installments and reflected in each parent transaction.
* **NFR12 — Cash Basis Accounting:** Paid installments have their `month` field updated to the actual payment month, ensuring the `/extrato` reports on when money moved, not when it was scheduled.
* **NFR13 — Dynamic Installment Indexing:** CTE with `ROW_NUMBER()` calculates the original installment sequence (e.g., "8 of 10") dynamically, even after month fields have been updated by cash-basis reconciliation.

---

### 5. Architectural Decisions: The "Why?"

#### 5.1. Why a Dual-Agent LLM Pipeline?
**Decision:** Two sequential calls — Agent 1 extracts (`temperature=0.0`), Agent 2 categorizes (`temperature=0.1`).
**Justification:** Isolated failure modes, calibrated temperatures per task, and auditable stages. The `_raciocinio_vencimento` Chain-of-Thought field in Agent 1 forces deliberate date reasoning, preventing the most common extraction error in PDFs.

#### 5.2. Why the Transactional Outbox Pattern?
**Decision:** Every message hits PostgreSQL before any LLM call.
**Justification:** Guaranteed delivery, instant UX ("Received" in < 100ms), and `FOR UPDATE SKIP LOCKED` for race-condition-safe concurrent processing.

#### 5.3. Why a custom Installment Engine?
**Decision:** `generate_installment_details` built on `dateutil.relativedelta`.
**Justification:** Brazilian credit card billing rules (fechamento/vencimento cycles) are not modeled by standard financial libraries.

#### 5.4. Why Cash Basis Accounting for the `/extrato`?
**Decision:** When a credit card invoice is paid, the `month` field of all its installments is updated to the payment month.
**Justification:** *The extrato reflects reality, not predictions.* Under accrual accounting, a purchase made in April appearing on a June invoice would show in April. Under cash basis, it appears in June when money actually left the account. For personal finance tracking, cash basis is more actionable — it matches your bank statement. The AP/AR panel (`/contas`) retains the original due dates for bill management, while the extrato uses the cash-basis month for financial reporting.

#### 5.5. Why separate the Benefit Wallet?
**Decision:** Transactions paid via VA/VR/benefício/pré-pago are calculated in a separate balance from the main wallet.
**Justification:** *Benefit cards are not fungible with cash.* Money in a meal voucher (VA) cannot pay utilities. Mixing both into a single balance would give a misleading picture of actual cash available. Displaying them separately gives accurate visibility into both pools.

#### 5.6. Why `ROW_NUMBER()` CTE for installment indexing?
**Decision:** `get_cash_flow_by_month` uses a CTE to assign installment numbers dynamically.
**Justification:** *The original sequence must survive month updates.* When cash-basis reconciliation moves an installment's `month` field, the stored installment number would become meaningless. A `ROW_NUMBER() OVER (PARTITION BY transaction_id ORDER BY id ASC)` recalculates the sequence at query time from the immutable `id` column, always returning the correct "8 of 10" regardless of what happened to the `month` field.

#### 5.7. Why group credit card installments under a "Fatura" header in the UI?
**Decision:** Installments sharing `card_bank`/`card_variant` are consolidated under a parent button.
**Justification:** People pay credit card invoices, not individual purchases. The grouped view mirrors how banks present statements.

#### 5.8. Why PostgreSQL?
**Decision:** Relational model with FK constraints and normalized tables.
**Justification:** 1 transaction → N items → N installments. Referential integrity, typed columns, indexed dates, and aggregatable decimals are liabilities in NoSQL but assets here.

---

### 6. Database Schema

```
credit_cards
    id, bank, variant, closing_day, due_day

process_queue
    id, chat_id, received_text, is_pdf, status, attempts, max_attempts, next_attempt

transactions  ←──────────────────────────────────────────────┐
    id, transaction_type, invoice_number                      │ FK
    transaction_date (DATE), location_name                    │
    card_bank, card_variant, status [Ativa | PAID]            │
    original_amount, discount_applied, total_amount           │
    macro_category, payment_method                            │
    is_installment, installment_count                         │
                                                              │
transaction_items  ──── transaction_id (FK) ──────────────────┤
    description, brand, unit_price, quantity                  │
    cat_macro, cat_category, cat_subcategory                  │
                                                              │
installments  ───────── transaction_id (FK) ──────────────────┘
    month (MM/YYYY)  ← updated to payment month on cash-basis pay
    due_date (DATE)  ← original due date, preserved for AP/AR
    amount, payment_status [PENDING | PAID | CANCELED]
    payment_date (DATE), paid_amount
```

**Key behavioral note:** `month` and `due_date` can diverge after a group invoice payment. `due_date` is always the original contractual date; `month` reflects when money actually moved (cash basis). The `/extrato` queries by `month`; the `/contas` panel uses `due_date` for overdue calculation.

---

### 7. Security Strategy

- **Decoupled Secrets:** `.env` locally, Railway Variables panel in production.
- **Access Control:** `ALLOWED_CHAT_IDS` whitelist via `security_check` decorator on all handlers.
- **Stateless Design:** PDFs deleted in `finally` blocks; no sensitive state on disk.
- **SQL Injection Prevention:** All queries use parameterized `%s` placeholders.

---
---

## 🇧🇷 Versão em Português Brasileiro

**Projeto:** Zotto — Finance AI Data App
**Papel:** Engenheiro de Dados Full-Stack & Dono do Produto

---

### 1. Visão Geral da Arquitetura

Sistema **Full-Stack** com **Arquitetura de IA Híbrida**. LLMs traduzem inputs desestruturados em dados; Python lida com matemática financeira, estados e governança. Nativo em nuvem no Railway PaaS, construído em torno do **Padrão de Outbox Transacional**.

**Fluxo de dados:** *Input do usuário → Telegram Bot → Fila PostgreSQL → Worker Background → Pipeline Dual LLM → UI de Confirmação → Banco Relacional.*

---

### 2. Componentes Principais

| # | Componente | Tecnologia | Responsabilidade |
|---|-----------|------------|----------------|
| 1 | **Interface de Entrada** | `python-telegram-bot` | Ponto de contato assíncrono. Máquina de estados + UI inline. |
| 2 | **Fila Outbox** | PostgreSQL `process_queue` | Desacopla ingestão do processamento. Garante entrega. |
| 3 | **Inteligência de Documentos** | `BeautifulSoup4`, `PyPDF` | Scraping NFC-e + extração de PDF. |
| 4 | **Motor de IA — Agente 1** | Groq API (`llama-4-scout-17b`) | Extração bruta. `temperature=0.0`. Detecção de desconto oculto. |
| 5 | **Motor de IA — Agente 2** | Groq API (`llama-4-scout-17b`) | Enriquecimento e categorização com regras de desambiguação. `temperature=0.1`. |
| 6 | **Backend Engine** | Python | Validação matemática, cálculo de parcelas, detecção de duplicatas e descontos. |
| 7 | **Dashboard AP/AR** | Telegram Inline UI | Faturas agrupadas, modo isolado, diferenciação Receita/Despesa. |
| 8 | **Extrato de Fluxo de Caixa** | Telegram Inline UI | Extrato mensal com separação de carteira benefício e índice de parcelas. |
| 9 | **Banco de Dados** | PostgreSQL | Armazenamento relacional com Livro Caixa, SCD e queries com CTE. |

---

### 3. Requisitos Funcionais (RFs)

* **RF01 — Ingestão Multimodal:** Texto livre, URLs NFC-e e PDFs.
* **RF02 — Extração por IA e Roteamento:** Pipeline dual para extração e classificação em `RECEITA`/`DESPESA`.
* **RF03 — Detecção de Desconto Oculto:** Se a soma dos itens exceder o total da nota, a diferença é registrada automaticamente como desconto.
* **RF04 — Cálculo de Parcelas:** Motor customizado com regras de fechamento/vencimento de cartão brasileiro.
* **RF05 — Confirmação Human-in-the-Loop:** Resumo Markdown antes de qualquer escrita no banco.
* **RF06 — Dashboard AP/AR (`/contas`):** Faturas agrupadas por cartão, diferenciação visual Receita/Despesa (🟢/🟡 vs 🔹/🔴), alertas de vencimento, navegação temporal, Modo Isolado, escape hatches.
* **RF07 — Pagamento Individual:** Parcela avulsa com suporte a desconto por antecipação.
* **RF08 — Pagamento em Grupo (Regime de Caixa):** Paga toda a fatura de um cartão; atualiza o campo `month` para o mês do pagamento real.
* **RF09 — Cancelamento de Parcela:** Soft-delete para conciliação bancária sem afetar outros meses.
* **RF10 — Modo Isolado:** Filtrar o painel para a linha do tempo de uma única transação.
* **RF11 — Extrato de Fluxo de Caixa (`/extrato`):** Saldo Atual e Projetado. Separação Carteira Principal vs Carteira Benefício. Lista de lançamentos com índice de parcela dinâmico (`8/10`), marcador `*` para pendências. Navegação mensal.
* **RF12 — Detecção de Duplicatas:** Match exato de `numero_nota` + match fuzzy por local/valor/data.
* **RF13 — Gestão de Cartões:** Cadastro mid-flow com regras de fechamento/vencimento.

---

### 4. Requisitos Não Funcionais (RNFs)

* **RNF01 — Resiliência (Outbox):** Nenhuma mensagem perdida por indisponibilidade da API.
* **RNF02 — Backoff Exponencial:** Erros genéricos: 60s–3600s. Limite TPD: adiar para 09:00 do dia seguinte.
* **RNF03 — Prevenção de Itens Zumbi:** `max_attempts` com status `DEAD`.
* **RNF04 — Adiamento por Estado Ocupado:** `reschedule_queue_item_busy` sem consumir tentativa.
* **RNF05 — Pool de Conexões:** `ThreadedConnectionPool` (1–10).
* **RNF06 — Parsing Tolerante a Falhas:** Limpa alucinações do LLM antes do parsing.
* **RNF07 — Validação Matemática:** Recalcula totais; detecta descontos ocultos via comparação de soma de itens.
* **RNF08 — Controle de Acesso:** Whitelist `ALLOWED_CHAT_IDS` via decorator `security_check`.
* **RNF09 — Segurança Stateless:** Segredos apenas via variáveis de ambiente.
* **RNF10 — Auditabilidade (SCD):** `created_at`/`updated_at` em todas as tabelas.
* **RNF11 — Distribuição Proporcional de Desconto:** Desconto de grupo distribuído proporcionalmente entre as parcelas.
* **RNF12 — Regime de Caixa:** Campo `month` atualizado para o mês do pagamento real ao baixar fatura agrupada.
* **RNF13 — Indexação Dinâmica de Parcelas:** CTE com `ROW_NUMBER()` recalcula o índice em tempo de query, resistente a atualizações do campo `month`.

---

### 5. Decisões Arquiteturais: O "Por Quê?"

#### 5.1. Pipeline Dual de LLM
Responsabilidades cognitivas isoladas. Temperaturas calibradas por tarefa. Chain-of-Thought para datas.

#### 5.2. Padrão Outbox Transacional
Entrega garantida. UX instantânea (< 100ms). `FOR UPDATE SKIP LOCKED` para concorrência segura.

#### 5.3. Motor de Parcelas Customizado
Regras de faturamento de cartão brasileiro (fechamento/vencimento) não são modeladas por bibliotecas padrão.

#### 5.4. Por que Regime de Caixa no `/extrato`?
**Decisão:** Ao pagar uma fatura em grupo, o campo `month` das parcelas é atualizado para o mês do pagamento.
**Justificativa:** O extrato reflete a realidade. No regime de caixa, uma compra de abril que vence em junho aparece em junho, quando o dinheiro saiu de fato. Isso corresponde ao extrato bancário real. O painel `/contas` preserva as datas originais para gestão; o `/extrato` usa o mês de caixa para relatórios.

#### 5.5. Por que separar a Carteira Benefício?
Benefícios (VA/VR) não são fungíveis com dinheiro. Misturar os saldos daria uma visão distorcida do caixa disponível real.

#### 5.6. Por que CTE com `ROW_NUMBER()` para índice de parcelas?
O número da parcela deve sobreviver às atualizações do campo `month` pelo regime de caixa. `ROW_NUMBER() OVER (PARTITION BY transaction_id ORDER BY id ASC)` recalcula o índice a partir do `id` imutável, sempre retornando "8 de 10" corretamente.

#### 5.7. Por que agrupar parcelas por cartão na UI?
As pessoas pagam faturas, não compras individuais. A visão agrupada espelha o comportamento real dos bancos.

#### 5.8. Por que PostgreSQL?
1 transação → N itens → N parcelas. Integridade referencial, colunas tipadas e decimais agregáveis são ativos aqui, não passivos.

---

### 6. Schema do Banco de Dados

```
credit_cards
    id, bank, variant, closing_day, due_day

process_queue
    id, chat_id, received_text, is_pdf, status, attempts, max_attempts, next_attempt

transactions  ←──────────────────────────────────────────────┐
    id, transaction_type, invoice_number                      │ FK
    transaction_date (DATE), location_name                    │
    card_bank, card_variant, status [Ativa | PAID]            │
    original_amount, discount_applied, total_amount           │
    macro_category, payment_method                            │
    is_installment, installment_count                         │
                                                              │
transaction_items  ──── transaction_id (FK) ──────────────────┤
    description, brand, unit_price, quantity                  │
    cat_macro, cat_category, cat_subcategory                  │
                                                              │
installments  ───────── transaction_id (FK) ──────────────────┘
    month (MM/AAAA)  ← atualizado para o mês do pagamento real (regime de caixa)
    due_date (DATE)  ← data original preservada para cálculo de vencimento
    amount, payment_status [PENDING | PAID | CANCELED]
    payment_date (DATE), paid_amount
```

**Nota importante:** `month` e `due_date` podem divergir após pagamento em grupo. `due_date` é sempre a data contratual original; `month` reflete quando o dinheiro se moveu. O `/extrato` filtra por `month`; o `/contas` usa `due_date` para cálculo de vencimento.

---

### 7. Estratégia de Segurança

- **Segredos Desacoplados:** `.env` local, painel de Variables do Railway em produção.
- **Controle de Acesso:** Whitelist `ALLOWED_CHAT_IDS` via decorator `security_check` em todos os handlers.
- **Design Stateless:** PDFs deletados em blocos `finally`. Nenhum estado sensível em disco.
- **Prevenção de SQL Injection:** Todas as queries usam `%s` parametrizado.