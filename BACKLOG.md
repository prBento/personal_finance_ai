# 📋 Product Backlog

> 🌐 **Bilingual Documentation:** English (US) | Português (BR)

---

## 🇺🇸 [EN-US] Mapped Scenarios & Roadmap

### 🟢 Active Scenario: Roadmap 2 (The AI Data App)
*Focus: Software Engineering, Data Products, and Cloud Deployment.*
- [x] **Task 1:** Configure Python virtual environment and base dependencies (`requirements.txt`).
- [x] **Task 2:** Establish Telegram API connection (`python-telegram-bot`).
- [x] **Task 3:** Integrate Groq API (Open-source LLMs) for JSON extraction.
- [x] **Task 4:** Develop advanced AI logic: Agent routing, Categorization prompts, and parsing.
- [x] **Task 5:** Spin up PostgreSQL via Docker Compose.
- [x] **Task 6:** Connect Backend to Postgres and design relational schema.
- [x] **Task 7:** Implement Async Queue (Transactional Outbox) to handle AI Rate Limits.
- [x] **Task 8:** Implement web scraping (BeautifulSoup) and PDF parsing (PyPDF).
- [x] **Task 9:** Create governance locks: Anti-duplication heuristics and prepaid card validation.
- [ ] **Task 10:** Develop Data Visualization Layer: Interactive Dashboard using Streamlit.
- [ ] **Task 11:** API & Webhook Transition: Implement FastAPI to handle Telegram Webhooks, replacing Long Polling.
- [ ] **Task 12:** Cloud Deployment: Containerize and deploy the app (FastAPI, Bot, Streamlit, DB) to a Cloud PaaS (Render/Railway/Fly.io) for 24/7 availability.

### ⚪ Future Scenario: Roadmap 1 (Modern Data Stack)
*Focus: Classic Data Engineering and Governance.*
- [ ] Migrate orchestration to Dagster.
- [ ] Implement dbt for data transformation (Bronze -> Silver -> Gold).
- [ ] Replace Dashboard reading with an OLAP database (DuckDB).

### ⚪ Future Scenario: Roadmap 3 (Agentic System & Human-in-the-Loop)
*Focus: Autonomous Agents.*
- [ ] Create an Analyst Agent to send proactive weekly summaries and alerts via Telegram.
- [ ] Implement budget limits (Alerts when hitting 80% of category goals).

---

## 🇧🇷 [PT-BR] Cenários Mapeados e Roadmap

### 🟢 Cenário Ativo: Roadmap 2 (The AI Data App)
*Foco: Engenharia de Software, Produtos de Dados e Deploy em Nuvem.*
- [x] **Task 1:** Configurar ambiente virtual Python e dependências base (`requirements.txt`).
- [x] **Task 2:** Criar conexão com a API do Telegram (via `python-telegram-bot`).
- [x] **Task 3:** Integrar API do Groq (LLMs Open-source) para extração de JSON.
- [x] **Task 4:** Desenvolver lógicas avançadas de IA: Roteamento de agentes, Prompts de Categorização e Parsing.
- [x] **Task 5:** Subir o PostgreSQL via Docker Compose.
- [x] **Task 6:** Conectar o Backend ao Postgres e criar o esquema relacional.
- [x] **Task 7:** Implementar Fila Assíncrona (Transactional Outbox) para lidar com Rate Limits da IA.
- [x] **Task 8:** Implementar web scraping (BeautifulSoup) e leitura de PDFs (PyPDF).
- [x] **Task 9:** Criar travas de governança: Heurística Anti-duplicidade e validação de cartões de benefício.
- [ ] **Task 10:** Criar a camada de visualização: Dashboard interativo em Streamlit lendo do PostgreSQL.
- [ ] **Task 11:** Transição para API & Webhooks: Implementar FastAPI para receber mensagens do Telegram via Webhook, aposentando o Long Polling.
- [ ] **Task 12:** Cloud Deploy (Nuvem): Empacotar a aplicação (FastAPI, Bot, Streamlit) e hospedar em um Cloud PaaS (Render/Railway/Fly.io) para rodar 24/7 sem depender do localhost.

### ⚪ Cenário Futuro: Roadmap 1 (Modern Data Stack)
*Foco: Engenharia de Dados Clássica e Governança.*
- [ ] Migrar orquestração para o Dagster.
- [ ] Implementar dbt para transformação de dados (Bronze -> Silver -> Gold).
- [ ] Substituir leitura do Dashboard por um banco OLAP (DuckDB).

### ⚪ Cenário Futuro: Roadmap 3 (Agentic System & Human-in-the-Loop)
*Foco: Agentes Autônomos.*
- [ ] Criar Agente Analista para enviar resumos e alertas proativos semanais no Telegram.
- [ ] Implementar limite de orçamentos (Alertas ao bater 80% da meta da categoria).