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
- [x] **Task 12 (Cloud):** Deploy to Cloud PaaS (Railway) with proper Secret Management and production environment separation.
- [x] **Task 13 (Anticipation):** Commands for early installment payments with discount yields, automatically moving future bills to the current month's cash flow.
- [x] **Task 14 (UX/UI AP/AR):** Enhanced the `/contas` command to display credit card information visually grouping purchases belonging to the same credit card invoice.
- [x] **Task 15 (Cash Flow Ledger):** Built the `/extrato` command. A monospaced, bank-like ledger that projects end-of-month balances and isolates Corporate Benefit cards (VR/VA) from liquid cash.
- [x] **Task 16 (Dynamic AP Override):** Allowed users to seamlessly override the payment method at the exact moment of settling a pending bill.

### 🟢 Phase 3: Scale & Visualization (Active)
- [ ] **Task 10 (Streamlit):** Build a real-time Financial Dashboard for spend analysis.
- [ ] **Task 11 (FastAPI):** Transition the Telegram Bot from Long Polling to Webhooks for better Cloud performance.

---

## 🇧🇷 Versão em Português Brasileiro

### ✅ Fase 1: O MVP (Concluído)
- [x] **Ingestão Base:** Integração com Telegram Bot e parsing via Groq LLM.
- [x] **Resiliência de Dados:** Padrão Outbox no PostgreSQL com Backoff Exponencial.
- [x] **Inteligência de Documentos:** Scrapers para NFC-e e leitura de PDFs (Contas de consumo).
- [x] **Lógica Financeira:** Roteamento multi-agente para Receitas e Despesas.
- [x] **Contas a Pagar Interativo:** Botões Inline no Telegram para rastrear e baixar dívidas.

### ✅ Fase 2: Motor Contábil e UX (Concluído)
- [x] **Task 12 (Nuvem):** Deploy para Cloud PaaS (Railway) com gestão de segredos e separação de ambientes (Dev/Prod).
- [x] **Task 13 (Antecipação):** Fluxo para pagamento antecipado com cálculo de desconto, movendo automaticamente contas futuras para o fluxo de caixa do mês atual.
- [x] **Task 14 (UX/UI Contas a Pagar):** Melhoria no `/contas` para agrupar e consolidar compras que pertencem à mesma fatura de cartão de crédito.
- [x] **Task 15 (Fluxo de Caixa/Extrato):** Criação do `/extrato`. Um painel gerencial (DRE) com projeção de saldos e isolamento matemático de cartões de Benefício (VR/VA).
- [x] **Task 16 (Sobrescrita Dinâmica):** Capacidade de o usuário alterar o método de pagamento no momento exato de dar baixa em uma conta pendente.

### 🟢 Fase 3: Escala e Visualização (Ativo)
- [ ] **Task 10 (Streamlit):** Construir um Dashboard Financeiro em tempo real para análise de gastos.
- [ ] **Task 11 (FastAPI):** Transição da arquitetura do bot de Long Polling para Webhooks para otimização em nuvem.