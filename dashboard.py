import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone, timedelta
from database import db_pool

st.set_page_config(page_title="Zotto BI | Inteligência Financeira", page_icon="📊", layout="wide")

def normalize_text_series(series):
    """Higienizador Pandas: Remove acentos, cedilhas e padroniza o texto para não quebrar filtros."""
    return series.astype(str).str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('utf-8').str.strip().str.title()

@st.cache_data(ttl=60)
def load_all_data():
    """Busca as duas camadas do banco: O financeiro (Parcelas) e o Operacional (Itens)."""
    conn = db_pool.getconn()
    try:
       # 1. Camada Financeira (Regime de Caixa e Competência)
        query_inst = """
            SELECT 
                i.id, i.month, i.amount as expected_amount, i.paid_amount, i.payment_status, i.due_date,
                t.id as transaction_id, t.transaction_type, t.macro_category, t.location_name, t.payment_method, t.is_installment, t.installment_count
            FROM installments i
            JOIN transactions t ON i.transaction_id = t.id
            WHERE i.payment_status != 'CANCELED'
        """
        df_inst = pd.read_sql_query(query_inst, conn)
        
        # 2. Camada Operacional (Os itens comprados nas notas)
        query_items = """
            SELECT 
                t.transaction_date, t.location_name, t.macro_category,
                ti.description as item_name, ti.unit_price, ti.quantity, (ti.unit_price * ti.quantity) as item_total
            FROM transaction_items ti
            JOIN transactions t ON ti.transaction_id = t.id
        """
        df_items = pd.read_sql_query(query_items, conn)
        
        return df_inst, df_items
    finally:
        db_pool.putconn(conn)

def main():
    st.title("📊 Zotto BI - Inteligência Financeira")
    df_inst, df_items = load_all_data()

    if df_inst.empty:
        st.warning("Ainda não há dados suficientes no banco para gerar o painel.")
        return

    # --- HIGIENIZAÇÃO DE DADOS ---
    df_inst['location_name'] = normalize_text_series(df_inst['location_name'])
    df_items['location_name'] = normalize_text_series(df_items['location_name'])

    # --- TRATAMENTO DE TEMPO E ORDENAÇÃO ---
    df_inst['month_dt'] = pd.to_datetime(df_inst['month'], format='%m/%Y')
    df_inst['year'] = df_inst['month_dt'].dt.year.astype(str)
    
    br_tz = timezone(timedelta(hours=-3))
    hoje = datetime.now(br_tz)
    ano_atual_str = str(hoje.year)
    mes_atual_str = hoje.strftime("%m/%Y")

    # --- MENU LATERAL (FILTROS) ---
    with st.sidebar:
        st.header("⚙️ Filtros Globais")
        
        # 1. Filtro de Ano
        anos_disponiveis = sorted(df_inst['year'].unique().tolist(), reverse=True)
        idx_ano = anos_disponiveis.index(ano_atual_str) if ano_atual_str in anos_disponiveis else 0
        ano_selecionado = st.selectbox("📅 Ano", anos_disponiveis, index=idx_ano)
        
        df_ano = df_inst[df_inst['year'] == ano_selecionado]
        
        # 2. Filtro de Mês (Em ordem crescente, default no atual)
        meses_disponiveis = sorted(df_ano['month'].unique().tolist(), key=lambda x: datetime.strptime(x, "%m/%Y"))
        idx_mes = meses_disponiveis.index(mes_atual_str) if mes_atual_str in meses_disponiveis else len(meses_disponiveis) - 1
        mes_selecionado = st.selectbox("🗓️ Mês", meses_disponiveis, index=idx_mes)

        # 3. Filtro de Local
        locais_disponiveis = sorted(df_inst['location_name'].unique().tolist())
        locais_selecionados = st.multiselect("🏢 Excluir/Incluir Locais (Vazio = Todos)", locais_disponiveis)
        
        st.markdown("---")
        st.markdown("💡 *Dica:* O painel de Projeção ignora o filtro de mês para mostrar todo o seu futuro, mas respeita o filtro de Locais!")

    # --- APLICAÇÃO DOS FILTROS GLOBAIS ---
    if locais_selecionados:
        df_inst = df_inst[df_inst['location_name'].isin(locais_selecionados)]
        df_items = df_items[df_items['location_name'].isin(locais_selecionados)]

    df_mes = df_inst[df_inst['month'] == mes_selecionado].copy()

    # Cria as 5 Abas do BI
    tab_curto, tab_raiox, tab_operacional, tab_tatico, tab_longo = st.tabs([
        "🎯 Saúde do Mês", 
        "🔍 Raio-X de Hábitos", 
        "📋 Visão Operacional (Itens)",
        "💳 Gestão de Parcelas",
        "🔭 Projeção de Longo Prazo"
    ])

    # ==========================================
    # ABA 1: SAÚDE DO MÊS (Curto Prazo)
    # ==========================================
    with tab_curto:
        st.subheader(f"Resumo Executivo — {mes_selecionado}")
        
        df_rec = df_mes[df_mes['transaction_type'] == 'RECEITA']
        df_desp = df_mes[df_mes['transaction_type'] == 'DESPESA']
        
        rec_prevista = df_rec['expected_amount'].sum()
        desp_prevista = df_desp['expected_amount'].sum()
        saldo_projetado = rec_prevista - desp_prevista
        saldo_atual = df_rec['paid_amount'].sum() - df_desp['paid_amount'].sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Receitas (A Receber)", f"R$ {rec_prevista:,.2f}")
        c2.metric("Despesas (A Pagar)", f"R$ {desp_prevista:,.2f}")
        # AQUI: Arredondamento perfeito do Delta para 2 casas decimais
        c3.metric("Saldo Líquido Projetado", f"R$ {saldo_projetado:,.2f}", delta=round(float(saldo_projetado), 2))
        c4.metric("Saldo Dinheiro Hoje", f"R$ {saldo_atual:,.2f}")
        
        st.markdown("---")
        
        col_pacing1, col_pacing2 = st.columns(2)
        with col_pacing1:
            st.markdown("**Ritmo de Pagamento (Contas Pagas vs Pendentes)**")
            if desp_prevista > 0:
                fig_pacing = px.pie(df_desp, values='expected_amount', names='payment_status', 
                                    hole=0.6, color='payment_status',
                                    color_discrete_map={'PAID':'#4CAF50', 'PENDING':'#F44336'})
                fig_pacing.update_traces(textinfo='percent+label')
                st.plotly_chart(fig_pacing, use_container_width=True)

        with col_pacing2:
            st.markdown("**Meios de Pagamento Utilizados**")
            if not df_desp.empty:
                df_metodo = df_desp.groupby('payment_method')['expected_amount'].sum().reset_index()
                fig_metodo = px.bar(df_metodo, x='expected_amount', y='payment_method', orientation='h',
                                    labels={'expected_amount': 'Valor (R$)', 'payment_method': ''})
                st.plotly_chart(fig_metodo, use_container_width=True)

    # ==========================================
    # ABA 2: RAIO-X DE HÁBITOS (Micro Gestão)
    # ==========================================
    with tab_raiox:
        st.subheader("Para onde seu dinheiro está indo?")
        if not df_desp.empty:
            col_cat, col_loc = st.columns(2)
            with col_cat:
                st.markdown("**Participação por Categoria (Treemap)**")
                fig_tree = px.treemap(df_desp, path=[px.Constant("Despesas"), 'macro_category', 'location_name'], 
                                      values='expected_amount', color='expected_amount', color_continuous_scale='Reds')
                fig_tree.update_layout(margin=dict(t=10, l=10, r=10, b=10))
                st.plotly_chart(fig_tree, use_container_width=True)
                
            with col_loc:
                st.markdown("**Top 10 Maiores Gastos (Estabelecimentos)**")
                df_top_loc = df_desp.groupby('location_name')['expected_amount'].sum().reset_index()
                df_top_loc = df_top_loc.sort_values('expected_amount', ascending=False).head(10)
                st.dataframe(df_top_loc.rename(columns={'location_name': 'Local/Empresa', 'expected_amount': 'Total Gasto (R$)'}), 
                             use_container_width=True, hide_index=True)

    # ==========================================
    # ABA 3: VISÃO OPERACIONAL (Detalhe dos Itens)
    # ==========================================
    with tab_operacional:
        st.subheader(f"🛒 Produtos e Serviços Adquiridos em {mes_selecionado}")
        st.markdown("Auditoria de notas fiscais: Veja exatamente o que foi comprado dentro deste mês.")
        
        # Filtra os itens baseado na data da compra (Competência)
        df_items['mes_compra'] = pd.to_datetime(df_items['transaction_date']).dt.strftime('%m/%Y')
        df_items_mes = df_items[df_items['mes_compra'] == mes_selecionado].copy()
        
        if not df_items_mes.empty:
            df_items_view = df_items_mes[['transaction_date', 'location_name', 'item_name', 'quantity', 'unit_price', 'item_total']].copy()
            df_items_view.columns = ['Data', 'Local', 'Item/Produto', 'Qtd', 'Valor Unitário (R$)', 'Valor Total (R$)']
            df_items_view = df_items_view.sort_values('Data', ascending=False)
            
            # Tabela pesquisável (nativa do Streamlit)
            st.dataframe(df_items_view, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum item detalhado encontrado para as compras deste mês.")

    # ==========================================
    # ABA 4: VISÃO TÁTICA (Gestão de Parcelas e Recebíveis)
    # ==========================================
    with tab_tatico:
        st.subheader("💳 Mapa Tático (Gestão de Parcelas e Entradas)")
        st.markdown("Acompanhe o detalhamento das suas dívidas longas e a projeção de todos os recebimentos futuros. **Clique em um item para abrir o detalhamento de parcelas.**")
        
        # Filtra apenas o que está PENDENTE no banco
        df_pendentes = df_inst[df_inst['payment_status'] == 'PENDING'].copy()
        
        # Garante que a data de vencimento seja um objeto datetime manipulável
        df_pendentes['due_date'] = pd.to_datetime(df_pendentes['due_date'])
        
        # Separa Dívidas Longas (Despesas > 1 parcela) e Recebimentos (Todas as Receitas)
        df_dividas = df_pendentes[(df_pendentes['transaction_type'] == 'DESPESA') & (df_pendentes['installment_count'] > 1)]
        df_receber = df_pendentes[df_pendentes['transaction_type'] == 'RECEITA']
        
        col_div, col_rec = st.columns(2)
        
        # --- COLUNA 1: DÍVIDAS LONGAS ---
        with col_div:
            st.markdown("### 🔴 Dívidas (Parcelamentos Ativos)")
            if not df_dividas.empty:
                # Agrupa pela transação pai para juntar as parcelas
                agrupado_div = df_dividas.groupby(['transaction_id', 'location_name', 'macro_category'])
                
                for (tx_id, loc, cat), group in agrupado_div:
                    qtd = len(group)
                    total = group['expected_amount'].sum()
                    prox_venc = group['due_date'].min().strftime('%d/%m/%Y')
                    
                    # Cria o Acordeão (Expander)
                    with st.expander(f"🏢 {loc} — R$ {total:,.2f} ({qtd} parcelas)"):
                        st.caption(f"Categoria: {cat} | Próx. Vencimento: {prox_venc}")
                        
                        # Prepara a tabelinha interna do Drill-down
                        df_show = group[['due_date', 'expected_amount']].sort_values('due_date')
                        df_show['due_date'] = df_show['due_date'].dt.strftime('%d/%m/%Y')
                        df_show.columns = ['Vencimento', 'Valor (R$)']
                        st.dataframe(df_show, hide_index=True, use_container_width=True)
            else:
                st.success("🎉 Nenhuma compra parcelada ativa!")

        # --- COLUNA 2: RECEBIMENTOS FUTUROS ---
        with col_rec:
            st.markdown("### 🟢 A Receber (Lançamentos Futuros)")
            if not df_receber.empty:
                agrupado_rec = df_receber.groupby(['transaction_id', 'location_name', 'macro_category'])
                
                for (tx_id, loc, cat), group in agrupado_rec:
                    qtd = len(group)
                    total = group['expected_amount'].sum()
                    prox_venc = group['due_date'].min().strftime('%d/%m/%Y')
                    
                    tag_parcela = f" ({qtd} repetições)" if qtd > 1 else " (Único)"
                    
                    with st.expander(f"💰 {loc} — R$ {total:,.2f}{tag_parcela}"):
                        st.caption(f"Categoria: {cat} | Próx. Entrada: {prox_venc}")
                        
                        df_show = group[['due_date', 'expected_amount']].sort_values('due_date')
                        df_show['due_date'] = df_show['due_date'].dt.strftime('%d/%m/%Y')
                        df_show.columns = ['Data Prevista', 'Valor (R$)']
                        st.dataframe(df_show, hide_index=True, use_container_width=True)
            else:
                st.info("Nenhum recebimento futuro projetado.")

    # ==========================================
    # ABA 5: PROJEÇÃO DE LONGO PRAZO
    # ==========================================
    with tab_longo:
        st.subheader("🔭 Fluxo de Caixa Futuro (Burn Rate)")
        
        # Filtra do mês selecionado PARA FRENTE
        df_futuro = df_inst[df_inst['month_dt'] >= pd.to_datetime(mes_selecionado, format='%m/%Y')]
        
        if not df_futuro.empty:
            df_trend = df_futuro.groupby(['month', 'month_dt', 'transaction_type'])['expected_amount'].sum().unstack(fill_value=0).reset_index()
            df_trend = df_trend.sort_values('month_dt')
            
            if 'RECEITA' not in df_trend.columns: df_trend['RECEITA'] = 0
            if 'DESPESA' not in df_trend.columns: df_trend['DESPESA'] = 0
            df_trend['SALDO_PROJETADO'] = df_trend['RECEITA'] - df_trend['DESPESA']

            fig_futuro = go.Figure()
            fig_futuro.add_trace(go.Bar(x=df_trend['month'], y=df_trend['RECEITA'], name='Receitas Previstas', marker_color='#4CAF50'))
            fig_futuro.add_trace(go.Bar(x=df_trend['month'], y=df_trend['DESPESA'], name='Despesas Compromissadas', marker_color='#F44336'))
            fig_futuro.add_trace(go.Scatter(x=df_trend['month'], y=df_trend['SALDO_PROJETADO'], 
                                            name='Saldo do Mês', mode='lines+markers',
                                            line=dict(color='#2196F3', width=3)))

            fig_futuro.update_layout(barmode='group', xaxis_title="Meses Futuros", yaxis_title="Valores (R$)", hovermode="x unified")
            st.plotly_chart(fig_futuro, use_container_width=True)
        else:
            st.info("Nenhuma projeção futura encontrada.")

if __name__ == "__main__":
    main()