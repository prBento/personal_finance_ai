# Product Backlog

## [PT-BR] Cenários Mapeados

### 🟢 Cenário Ativo: Roadmap 2 (The AI Data App)
Foco em Engenharia de Software e Produtos de Dados.
- [ ] **Task 1:** Configurar ambiente virtual Python e dependências base.
- [ ] **Task 2:** Criar script de conexão básica com a API do Telegram (BotFather).
- [ ] **Task 3:** Integrar API do Groq para extrair JSON de texto livre (Ex: "Comprei chocolate por R$5").
- [ ] **Task 4:** Criar a API com FastAPI para receber webhooks do Telegram.
- [ ] **Task 5:** Subir o PostgreSQL via Docker Compose.
- [ ] **Task 6:** Conectar FastAPI ao Postgres (usando SQLAlchemy ou SQLModel).
- [ ] **Task 7:** Criar o Dashboard base em Streamlit lendo do banco.

### ⚪ Cenário Futuro: Roadmap 1 (Modern Data Stack)
Foco em Engenharia de Dados Clássica e Governança.
- [ ] Migrar orquestração do FastAPI para o Dagster.
- [ ] Implementar dbt para transformação de dados (Bronze -> Silver -> Gold).
- [ ] Substituir leitura do Dashboard por um banco OLAP (DuckDB).
- [ ] Plugar Metabase para Self-Service BI.

### ⚪ Cenário Futuro: Roadmap 3 (Agentic System & Human-in-the-Loop)
Foco em Agentes Autônomos.
- [ ] Refatorar extração única para múltiplos agentes (Roteador, Extrator, Validador).
- [ ] Implementar fluxo de aprovação via Telegram (Botões Inline de Sim/Não) para categorias com baixa confiança da IA.
- [ ] Criar Agente Analista para enviar resumos proativos semanais.

---

## [EN-US] Mapped Scenarios

### 🟢 Active Scenario: Roadmap 2 (The AI Data App)
Focus on Software Engineering and Data Products.
- [ ] **Task 1:** Setup Python virtual environment and core dependencies.
- [ ] **Task 2:** Create basic connection script with Telegram API.
- [ ] **Task 3:** Integrate Groq API to extract JSON from raw text (e.g., "Bought chocolate for $5").
- [ ] **Task 4:** Create FastAPI backend to handle Telegram webhooks.
- [ ] **Task 5:** Deploy PostgreSQL via Docker Compose.
- [ ] **Task 6:** Connect FastAPI to Postgres (using SQLAlchemy or SQLModel).
- [ ] **Task 7:** Build base Streamlit Dashboard reading from the database.

### ⚪ Future Scenario: Roadmap 1 (Modern Data Stack)
Focus on Classic Data Engineering and Governance.
- [ ] Migrate orchestration from FastAPI to Dagster.
- [ ] Implement dbt for data transformation (Bronze -> Silver -> Gold).
- [ ] Replace Dashboard reading layer with an OLAP database (DuckDB).
- [ ] Connect Metabase for Self-Service BI.

### ⚪ Future Scenario: Roadmap 3 (Agentic System & Human-in-the-Loop)
Focus on Autonomous Agents.
- [ ] Refactor single extraction into multi-agent workflow (Router, Extractor, Validator).
- [ ] Implement Telegram approval flow (Inline Yes/No buttons) for low-confidence AI categorizations.
- [ ] Create Analyst Agent to send proactive weekly summaries.