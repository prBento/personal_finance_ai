# 📋 Product Backlog & Roadmap
*(Para a versão em Português, [clique aqui](#-versão-em-português-brasileiro))*

## 👨‍💻 Autor
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

### 🟢 Phase 2: Scale & Visualization (Active)
- [ ] **Task 10 (Streamlit):** Build a real-time Financial Dashboard for spend analysis.
- [ ] **Task 11 (FastAPI):** Transition from Long Polling to Webhooks.
- [ ] **Task 12 (Cloud):** Deploy to Cloud PaaS (Render/Railway) with proper Secret Management.
- [ ] **Task 13 (Anticipation):** Commands for early installment payments with discount yields.
- [ ] **Task 14 (UX/UI AP/AR):** Enhance the `/contas` command to display credit card information (Bank/Variant) next to pending installments, allowing the user to visually group purchases belonging to the same credit card invoice.

---

## 🇧🇷 Versão em Português Brasileiro

### ✅ Fase 1: O MVP (Concluído)
- [x] **Ingestão Base:** Integração com Telegram Bot e parsing via Groq LLM.
- [x] **Resiliência de Dados:** Padrão Outbox no PostgreSQL com Backoff Exponencial.
- [x] **Inteligência de Documentos:** Scrapers para NFC-e e leitura de PDFs (Contas de consumo).
- [x] **Lógica Financeira:** Roteamento multi-agente para Receitas e Despesas.
- [x] **Contas a Pagar Interativo:** Botões Inline no Telegram para rastrear e baixar dívidas.

### 🟢 Fase 2: Escala e Visualização (Ativo)
- [ ] **Task 10 (Streamlit):** Construir um Dashboard Financeiro em tempo real para análise de gastos.
- [ ] **Task 11 (FastAPI):** Transição de Long Polling para Webhooks.
- [ ] **Task 12 (Nuvem):** Deploy para Cloud PaaS (Render/Railway) com gestão de segredos.
- [ ] **Task 13 (Antecipação):** Comandos para pagamento antecipado de parcelas com cálculo de desconto.
- [ ] **Task 14 (UX/UI Contas a Pagar):** Melhorar o comando `/contas` para exibir a informação do cartão de crédito (Banco/Variante) ao lado da parcela pendente, permitindo agrupar visualmente as compras que pertencem à mesma fatura.