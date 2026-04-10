# 📋 Product Backlog & Roadmap
*(Para a versão em Português, [clique aqui](#-versão-em-português-brasileiro))*

## 👨‍💻 Author
**Bento**
- GitHub: [@prBento](https://github.com/prBento)

---

## 🇺🇸 English Version

### ✅ Phase 1: The MVP (Completed)
- [x] **Core Ingestion:** Telegram Bot integration & Groq LLM parsing.
- [x] **Data Resiliency:** PostgreSQL Outbox Pattern with Exponential Backoff.
- [x] **Document Intelligence:** Scrapers for NFC-e and PDF (Utility bills).
- [x] **Financial Logic:** Multi-agent routing for Cash-In (Income) and Cash-Out (Expenses).
- [x] **Interactive AP/AR:** Telegram Inline buttons to track and pay pending bills.

### ✅ Phase 2: Accounting Engine & UX (Completed)
- [x] **Task 12 (Cloud):** Deploy to Cloud PaaS (Railway) with proper Secret Management and production environment separation (dev = Long Polling / prod = FastAPI Webhook).
- [x] **Task 13 (Anticipation):** Commands for early installment payments with discount yields. Credit card anticipation correctly moves the installment to the next invoice cycle (stays PENDING); cash/Pix payments mark immediately as PAID and reallocate the month field for cash-basis reporting.
- [x] **Task 14 (UX/UI AP/AR):** Enhanced the `/contas` command with accordion-style credit card invoice grouping. Cards expand/collapse showing individual items below, with a "Pay Full Invoice" button when open.
- [x] **Task 15 (Cash Flow Ledger):** Built the `/extrato` command. A monospaced, bank-like ledger that shows Saldo Atual and Saldo Projetado, projects end-of-month balances, isolates Corporate Benefit cards (VR/VA/prepaid) from liquid cash, and displays dynamic installment index (e.g., `8/10`) via CTE ROW_NUMBER().
- [x] **Task 16 (Dynamic AP Override):** Allowed users to override the payment method at the exact moment of settling a pending bill, including card selection and proper anticipation logic per payment type.
- [x] **Webhook Architecture:** FastAPI + Uvicorn webhook server implemented for production. Long Polling retained for local dev. `if ENV == "prod": uvicorn.run()` else `run_polling()`.
- [x] **Interactive Help System:** `/help` rebuilt as an inline button menu with topic-specific sub-pages and back navigation.
- [x] **Disambiguation Ruleset (Agent 2):** Explicit rules preventing common LLM misclassifications (Total Pass → Academy, iFood → Food, streaming → Subscriptions, NF-e → always Expense).
- [x] **Hidden Discount Detector:** Post-LLM math validation catches discounts the AI missed by comparing item sum to invoice total.
- [x] **Income Support in AP/AR:** `/contas` visually differentiates incomes (🟢/🟡) from expenses (🔹/🔴) with adapted action texts throughout all payment flows.

### 🟢 Phase 3: Scale & Visualization (Active)
- [ ] **Task 10 (Streamlit):** Build a real-time Financial Dashboard for spend analysis, category breakdowns, and monthly cash flow.
- [ ] **Task 11 (Procfile Fix):** Update `Procfile` from `worker:` to `web:` so Railway correctly provisions a public URL and PORT for the FastAPI webhook server.
- [ ] **DEBT-03 (Analytics View):** `CREATE VIEW monthly_summary` in PostgreSQL to feed Streamlit aggregations without complex runtime joins.
- [ ] **QUAL-02 (Structured Logging):** Replace all `print()` calls with `logging.getLogger()` for log-level filtering in Railway's log panel.
- [ ] **QUAL-05 (Prompts File):** Extract `PROMPT_AGENTE_1` and `PROMPT_AGENTE_2` strings to a dedicated `prompts.py` module.
- [ ] **BACK-01 (Multi-transaction):** Process arrays of multiple transactions from a single LLM response (e.g., multi-purchase PDFs).
- [ ] **BACK-03 (PDF Decrypt):** Request PDF password mid-conversation via State Machine and decrypt in-memory.
- [ ] **FIX-01 (Benefit Detection):** Add `card_bank` and `card_variant` columns to `get_cash_flow_by_month` query so benefit wallet isolation works for transactions where the method field alone doesn't identify VA/VR.
- [ ] **PROD-04 (Async DB):** Replace `psycopg2` with `asyncpg` to stop blocking the FastAPI/Telegram event loop on database calls.


---

## 🇧🇷 Versão em Português Brasileiro

### ✅ Fase 1: O MVP (Concluído)
- [x] **Ingestão Base:** Integração com Telegram Bot e parsing via Groq LLM.
- [x] **Resiliência de Dados:** Padrão Outbox no PostgreSQL com Backoff Exponencial.
- [x] **Inteligência de Documentos:** Scrapers para NFC-e e leitura de PDFs.
- [x] **Lógica Financeira:** Roteamento multi-agente para Receitas e Despesas.
- [x] **Contas a Pagar Interativo:** Botões Inline no Telegram para rastrear e baixar dívidas.

### ✅ Fase 2: Motor Contábil e UX (Concluído)
- [x] **Task 12 (Nuvem):** Deploy para Railway com separação de ambientes (dev = Long Polling / prod = FastAPI Webhook).
- [x] **Task 13 (Antecipação):** Pagamento antecipado com lógica diferenciada por tipo: cartão de crédito move a parcela para a fatura alvo (permanece PENDING); pagamentos à vista marcam como PAID e realocam o mês no regime de caixa.
- [x] **Task 14 (UX/UI Contas a Pagar):** Painel `/contas` com acordeon — cartões expandem/recolhem exibindo itens individuais com botão "Pagar Fatura Fechada" embutido.
- [x] **Task 15 (Extrato/Fluxo de Caixa):** Comando `/extrato` com Saldo Atual, Projetado, isolamento matemático de cartões Benefício (VR/VA) e índice dinâmico de parcela (`8/10`) via CTE ROW_NUMBER().
- [x] **Task 16 (Sobrescrita Dinâmica):** Usuário pode alterar o método de pagamento no ato da baixa, com seleção de cartão e lógica de antecipação correta por tipo de pagamento.
- [x] **Arquitetura Webhook:** FastAPI + Uvicorn em produção. Long Polling mantido para desenvolvimento local.
- [x] **Sistema de Ajuda Interativo:** `/help` reconstruído como menu inline com sub-páginas por tópico.
- [x] **Regras de Desambiguação (Agente 2):** Previne erros comuns de classificação do LLM.
- [x] **Detector de Desconto Oculto:** Validação matemática pós-LLM captura descontos que a IA perdeu.
- [x] **Suporte a Receitas no AP/AR:** Diferenciação visual e textual em todo o fluxo de pagamentos.

### 🟢 Fase 3: Escala e Visualização (Ativo)
- [ ] **Task 10 (Streamlit):** Dashboard Financeiro em tempo real.
- [ ] **Task 11 (Procfile Fix):** Atualizar `Procfile` de `worker:` para `web:` para o Railway provisionar URL pública e PORT para o webhook FastAPI.
- [ ] **DEBT-03:** `CREATE VIEW monthly_summary` para o Streamlit.
- [ ] **QUAL-02:** Substituir `print()` por `logging.getLogger()`.
- [ ] **QUAL-05:** Extrair prompts para `prompts.py`.
- [ ] **BACK-01:** Processar múltiplas transações por resposta do LLM.
- [ ] **BACK-03:** Descriptografar PDF com senha via chat.
- [ ] **FIX-01:** Adicionar `card_bank`/`card_variant` na query `get_cash_flow_by_month` para detecção correta de benefício.
- [ ] **PROD-04:** Substituir `psycopg2` por `asyncpg` para não bloquear o event loop do FastAPI.
- [ ] **DEBT-04 (Padrão ASGI):** Mover a inicialização do banco (`create_tables()`) do bloco `__main__` para dentro do `@asynccontextmanager lifespan` do FastAPI. Isso permitirá alterar o Procfile para `web: uvicorn bot:api` no futuro, habilitando o uso de múltiplos *workers* de processamento no Uvicorn.