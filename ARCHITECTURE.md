# 🏗️ Architecture Document: AI Data App

> 🌐 **Bilingual Documentation:** English (US) | Português (BR)

---

## 🇺🇸 [EN-US] System Overview
This system is a Full-Stack Data Application designed for personal finance management. It leverages Large Language Models (LLMs) to transform chaotic, unstructured daily messages (texts, links, and PDFs) into a governed, relational database. The architecture is transitioning towards a cloud-native, event-driven model.

### Core Components
1. **Entry Interface (Telegram Bot & FastAPI):** The asynchronous user touchpoint. Currently operating via Long Polling, but architecturally designed to transition to **FastAPI Webhooks** for event-driven cloud deployment.
2. **Backend Engine (Python):** The brain of the operation. Executes web scraping (`BeautifulSoup`), document extraction (`PyPDF`), and orchestrates background jobs.
3. **Queue System (Transactional Outbox):** A resilient processing queue embedded in PostgreSQL to handle API unavailability and Groq rate limits (Exponential Backoff).
4. **AI Engine (Groq API):** Utilizes lightweight and lightning-fast LLMs (`llama-4-scout-17b`) split into two agentic roles: Extraction Agent and Enrichment/Categorization Agent.
5. **Database (PostgreSQL):** Relational storage ensuring data integrity, featuring heuristic validations against duplicate insertions and strict governance rules.
6. **Visualization Interface (Streamlit):** An interactive dashboard for visualizing cash flow metrics, category breakdowns, and upcoming invoices.
7. **Infrastructure & Deployment:** Containerized via Docker. The target architecture involves deploying the API, Worker, and Streamlit components to a Cloud PaaS (e.g., Render, Railway) for 24/7 serverless operation.

### Resilient Data Flow
1. `User` sends a message -> `Webhook/Bot` saves it to the Queue Table (`PENDING`) -> Returns "Received".
2. `Background Worker` reads the queue -> Sends prompt to `Groq API`.
3. In case of *Rate Limit*, `Worker` reschedules the task to X seconds later.
4. `Groq` returns JSON -> `Worker` applies governance rules (UPPERCASE, UUIDs, anti-installment locks).
5. `Worker` triggers the Telegram UI requesting Human Confirmation (*Human-in-the-loop*).
6. Upon "Yes", data is saved into normalized `PostgreSQL` tables -> Instantly available for `Streamlit`.

---

## 🇧🇷 [PT-BR] Visão Geral do Sistema
Este sistema é uma aplicação Full-Stack focada em dados (Data App) para controle financeiro pessoal. Ele utiliza Modelos de Linguagem de Larga Escala (LLMs) para transformar mensagens caóticas do dia a dia (textos, links e PDFs) em uma base de dados relacional governada. A arquitetura está em transição para um modelo nativo em nuvem (Cloud-Native) e orientado a eventos.

### Componentes Principais
1. **Interface de Entrada (Telegram Bot & FastAPI):** Ponto de contato assíncrono do usuário. Atualmente opera via *Long Polling*, mas estruturado para transição para **FastAPI Webhooks** focando em deploy na nuvem.
2. **Backend Engine (Python):** O cérebro da operação. Executa scrapings (`BeautifulSoup`), extração de documentos (`PyPDF`) e gerencia rotinas em segundo plano.
3. **Queue System (Transactional Outbox):** Fila de processamento embutida no PostgreSQL para garantir resiliência contra indisponibilidades e *Rate Limits* da API de IA (Espera Exponencial).
4. **Motor de IA (Groq API):** Utiliza LLMs leves e rápidos (`llama-4-scout-17b`) divididos em dois agentes: Agente de Extração e Agente de Classificação/Enriquecimento.
5. **Banco de Dados (PostgreSQL):** Armazenamento relacional que garante a integridade dos dados, possuindo validações heurísticas contra inserções duplicadas e regras rígidas de negócio.
6. **Interface de Visualização (Streamlit):** Dashboard interativo para visualização de métricas de fluxo de caixa, divisões por categorias e faturas a pagar.
7. **Infraestrutura e Deploy:** Containerizado via Docker. A arquitetura alvo envolve hospedar a API, o Worker e o Streamlit em um Cloud PaaS (ex: Render, Railway) para operação 24/7 sem dependência de máquina local.

### Fluxo de Dados Resiliente
1. `User` envia Mensagem -> `Webhook/Bot` salva na Tabela de Fila (`PENDENTE`) -> Retorna "Recebido".
2. `Worker` (Rodando em background) lê a fila -> Envia para `Groq API`.
3. Em caso de *Rate Limit*, `Worker` reagenda a tarefa para X segundos no futuro.
4. `Groq` devolve JSON -> `Worker` aplica regras de governança (Maiúsculas, UUIDs, trava de parcelamento).
5. `Worker` invoca a UI do Telegram pedindo Confirmação Humana (*Human-in-the-loop*).
6. Após "Sim", salva nas tabelas normalizadas do `PostgreSQL` -> Dados ficam disponíveis para o `Streamlit`.