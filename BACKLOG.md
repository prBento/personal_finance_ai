# Product Backlog

## [PT-BR] Cenários Mapeados

### 🟢 Cenário Ativo: Roadmap 2 (The AI Data App)
Foco em Engenharia de Software e Produtos de Dados.
- [x] **Task 1:** Configurar ambiente virtual Python e dependências base (`requirements.txt`).
- [x] **Task 2:** Criar conexão com a API do Telegram (via `python-telegram-bot`).
- [x] **Task 3:** Integrar API do Groq (LLMs Open-source) para extração de JSON.
- [x] **Task 4:** Desenvolver lógicas avançadas de IA: Roteamento de agentes, Prompts de Categorização e Parsing.
- [x] **Task 5:** Subir o PostgreSQL via Docker Compose.
- [x] **Task 6:** Conectar o Backend ao Postgres e criar o esquema relacional (Tabelas: transacoes, itens, parcelas, cartoes).
- [x] **Task 7 (Extra):** Implementar Fila Assíncrona (Background Worker) para lidar com Rate Limits da IA.
- [x] **Task 8 (Extra):** Implementar web scraping (BeautifulSoup) e leitura de PDFs (PyPDF).
- [x] **Task 9 (Extra):** Criar travas de governança: Anti-duplicidade e validação de cartões de benefício.
- [ ] **Task 10:** Criar a camada de visualização: Dashboard interativo em Streamlit lendo do PostgreSQL.

### ⚪ Cenário Futuro: Roadmap 1 (Modern Data Stack)
Foco em Engenharia de Dados Clássica e Governança.
- [ ] Migrar orquestração para o Dagster.
- [ ] Implementar dbt para transformação de dados (Bronze -> Silver -> Gold).
- [ ] Substituir leitura do Dashboard por um banco OLAP (DuckDB).

### ⚪ Cenário Futuro: Roadmap 3 (Agentic System & Human-in-the-Loop)
Foco em Agentes Autônomos.
- [ ] Criar Agente Analista para enviar resumos e alertas proativos semanais no Telegram.
- [ ] Implementar limite de orçamentos (Alertas ao bater 80% da meta da categoria).