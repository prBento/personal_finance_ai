import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone, timedelta
from database import db_pool

# ==============================================================================
# --- Streamlit Page Configuration ---
# ==============================================================================
st.set_page_config(
    page_title="Zotto BI | Inteligência Financeira",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# --- Utility Helpers & Constants ---
# ==============================================================================

# Keywords used to identify Corporate Benefit Cards (Food/Meal vouchers)
# This is crucial to separate restricted funds from actual liquid cash.
BENEFIT_KEYWORDS = ["benefício", "beneficio", "pré-pago", "pre-pago", "vr", "va", "caju", "alelo", "sodexo", "ticket"]
BEN_BANKS = ["caju", "alelo", "sodexo", "ticket", "flash", "ifood benefícios", "pluxee"]

def fmt_brl(value: float) -> str:
    """Formats a float into Brazilian Real currency string (e.g., 1,234.56 -> R$ 1.234,56)."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def normalize_series(s: pd.Series) -> pd.Series:
    """
    Sanitizes pandas text columns to prevent UI bugs and grouping errors.
    Removes accents, weird encodings (Mojibake), and standardizes to Title Case.
    """
    return (
        s.astype(str)
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("utf-8")
        .str.strip()
        .str.title()
    )

def is_benefit_row(method: str, bank: str) -> bool:
    """Evaluates if a transaction belongs to a Benefit Card based on its method or bank name."""
    m = str(method).lower()
    b = str(bank).lower()
    return any(k in m for k in BENEFIT_KEYWORDS) or any(k in b for k in BEN_BANKS)


# ==============================================================================
# --- Data Loading Queries (The Two-Layer Architecture) ---
# ==============================================================================

@st.cache_data(ttl=60)
def load_installments() -> pd.DataFrame:
    """
    LAYER 1: FINANCIAL LAYER (Cash Basis / Regime de Caixa)
    Focuses on *when the money actually moves*. 
    It pulls data from the 'installments' table (which dictates the exact month the bill hits the account),
    joined with the parent 'transactions' table to get metadata (location, category).
    """
    sql = """
        SELECT
            i.id                                        AS inst_id,
            i.month,
            i.due_date,
            i.payment_date,
            i.amount                                    AS expected_amount,
            COALESCE(i.paid_amount, 0)                  AS paid_amount,
            i.payment_status,
            t.id                                        AS transaction_id,
            t.transaction_type,
            t.macro_category,
            t.location_name,
            t.payment_method,
            COALESCE(t.card_bank,    '')                AS card_bank,
            COALESCE(t.card_variant, '')                AS card_variant,
            t.is_installment,
            t.installment_count,
            COALESCE(t.discount_applied, 0)             AS discount_applied,
            t.original_amount,
            t.total_amount,
            t.transaction_date
        FROM installments i
        JOIN transactions t ON i.transaction_id = t.id
        WHERE i.payment_status != 'CANCELED'
        ORDER BY i.due_date
    """
    conn = db_pool.getconn()
    try:
        df = pd.read_sql_query(sql, conn)
    finally:
        db_pool.putconn(conn)

    # Data Sanitization
    df["location_name"] = normalize_series(df["location_name"])
    df["macro_category"] = normalize_series(df["macro_category"])
    
    # Date Casting for Time-Series Analysis
    df["month_dt"] = pd.to_datetime(df["month"], format="%m/%Y")
    df["year"] = df["month_dt"].dt.year.astype(str)
    df["due_date"] = pd.to_datetime(df["due_date"], errors="coerce")
    df["real_month"] = df["due_date"].dt.strftime("%m/%Y")
    df["real_year"] = df["due_date"].dt.year.astype(str)
    df["payment_date"] = pd.to_datetime(df["payment_date"], errors="coerce")
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")

    # The 'real_amount' logic:
    # If the bill is paid, we care about the exact 'paid_amount' (which might include discounts).
    # If it's pending, we rely on the 'expected_amount' mapped by the LLM.
    df["real_amount"] = df.apply(
        lambda r: r["paid_amount"] if r["payment_status"] == "PAID" else r["expected_amount"],
        axis=1,
    )

    # Flags transactions that shouldn't mix with liquid cash
    df["is_benefit"] = df.apply(
        lambda r: is_benefit_row(r["payment_method"], r["card_bank"]), axis=1
    )

    return df


@st.cache_data(ttl=60)
def load_items() -> pd.DataFrame:
    """
    LAYER 2: OPERATIONAL LAYER (Accrual Basis / Regime de Competência)
    Focuses on *what was bought and when it was bought*, regardless of how many months it will take to pay.
    Pulls line-by-line item details from receipts to feed the micro-management tabs (Treemaps, Top Items).
    """
    sql = """
        SELECT
            t.id                                        AS transaction_id,
            t.transaction_date,
            TO_CHAR(t.transaction_date, 'MM/YYYY')      AS month_compra,
            t.location_name,
            t.macro_category                            AS tx_macro,
            t.payment_method,
            COALESCE(t.card_bank, '')                   AS card_bank,
            ti.description                              AS item_name,
            COALESCE(ti.brand, '')                      AS brand,
            ti.unit_price,
            ti.quantity,
            (ti.unit_price * ti.quantity)               AS item_total,
            COALESCE(ti.cat_macro,       'Sem categoria')   AS cat_macro,
            COALESCE(ti.cat_category,    'Sem categoria')   AS cat_category,
            COALESCE(ti.cat_subcategory, 'Sem subcategoria') AS cat_subcategory,
            COALESCE(ti.cat_product,     '')                AS cat_product
        FROM transaction_items ti
        JOIN transactions t ON ti.transaction_id = t.id
        WHERE t.transaction_type = 'DESPESA'
        ORDER BY t.transaction_date DESC
    """
    conn = db_pool.getconn()
    try:
        df = pd.read_sql_query(sql, conn)
    finally:
        db_pool.putconn(conn)

    # Data Sanitization
    df["location_name"]  = normalize_series(df["location_name"])
    df["item_name"]      = normalize_series(df["item_name"])
    df["brand"]          = normalize_series(df["brand"])
    df["cat_macro"]      = normalize_series(df["cat_macro"])
    df["cat_category"]   = normalize_series(df["cat_category"])
    df["cat_subcategory"]= normalize_series(df["cat_subcategory"])
    
    # Date Casting
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
    df["month_dt"]       = pd.to_datetime(df["month_compra"], format="%m/%Y", errors="coerce")

    return df


# ==============================================================================
# --- Main Dashboard Application ---
# ==============================================================================

def main():
    st.title("📊 Zotto BI — Inteligência Financeira")

    # Load data from PostgreSQL
    df_inst = load_installments()
    df_items = load_items()

    if df_inst.empty:
        st.warning("Ainda não há dados no banco para gerar o painel.")
        return

    # Determine current real-world time to set default selections intelligently
    br_tz = timezone(timedelta(hours=-3))
    hoje = datetime.now(br_tz)
    ano_atual = str(hoje.year)
    mes_atual = hoje.strftime("%m/%Y")

    # ==========================================
    # --- Sidebar (Global Filters) ---
    # ==========================================
    with st.sidebar:
        st.header("⚙️ Filtros Globais")

        # 1. Date Filters (Chronological order)
        anos = sorted(df_inst["year"].unique().tolist())
        idx_ano = anos.index(ano_atual) if ano_atual in anos else (len(anos) - 1)
        ano_sel = st.selectbox("Ano", anos, index=idx_ano)

        # Update available months based on the selected year
        df_ano = df_inst[df_inst["year"] == ano_sel]
        meses = sorted(df_ano["month"].unique().tolist(), key=lambda x: datetime.strptime(x, "%m/%Y"))
        idx_mes = meses.index(mes_atual) if mes_atual in meses else len(meses) - 1
        mes_sel = st.selectbox("Mês (para análises mensais)", meses, index=idx_mes)

        st.markdown("---")
        
        # 2. Location Filter (Blacklist UX Approach)
        # Instead of pre-selecting everything (which causes a massive wall of tags in Streamlit),
        # we start empty. The user only selects locations they want to EXCLUDE from the analysis.
        locais_disp = sorted(df_inst["location_name"].dropna().unique().tolist())
        locais_excluidos = st.multiselect(
            "🏢 Ocultar locais específicos:", 
            options=locais_disp, 
            default=[], 
            help="Por padrão, o painel analisa TODOS os locais. Adicione aqui as empresas que você deseja ESCONDER dos gráficos."
        )

        st.markdown("---")
        
        # 3. Liquidity Filter
        excluir_beneficio = st.checkbox("Excluir Carteira Benefício (VA/VR)", value=False,
            help="Marque para analisar apenas o dinheiro líquido, sem VA/VR.")

        st.markdown("---")
        st.caption("💡 Abas de tendência e projeção ignoram o filtro de mês e usam o ano selecionado.")

    # ==========================================
    # --- Apply Global Filters ---
    # ==========================================

    # Apply Location Blacklist
    if locais_excluidos:
        df_inst = df_inst[~df_inst["location_name"].isin(locais_excluidos)]
        df_items = df_items[~df_items["location_name"].isin(locais_excluidos)]

    # Apply Benefits Exclusion
    if excluir_beneficio:
        df_inst  = df_inst[~df_inst["is_benefit"]]
        df_items = df_items[~df_items["card_bank"].str.lower().apply(
            lambda b: any(k in b for k in BEN_BANKS))]

    # Create a specific dataframe for single-month views
    df_mes = df_inst[df_inst["month"] == mes_sel].copy()

    # ==========================================
    # --- Tabs Configuration ---
    # ==========================================
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🎯  Saúde do Mês",
        "📈  Tendências",
        "💳  Cartões & Parcelas",
        "🔭  Projeção de Caixa",
        "🛒  Operacional — Itens",
        "🧮  Matriz de Conferência",
    ])

    # ==========================================
    # TAB 1: EXECUTIVE SUMMARY (Current Month)
    # ==========================================
    with tab1:
        st.subheader(f"Resumo Executivo — {mes_sel}")

        df_rec  = df_mes[df_mes["transaction_type"] == "RECEITA"]
        df_desp = df_mes[df_mes["transaction_type"] == "DESPESA"]

        # Accurate aggregation separating Realized (Cash in hand) vs Pending (Future commitments)
        rec_realizada  = df_rec[df_rec["payment_status"] == "PAID"]["paid_amount"].sum()
        rec_pendente   = df_rec[df_rec["payment_status"] == "PENDING"]["expected_amount"].sum()
        desp_realizada = df_desp[df_desp["payment_status"] == "PAID"]["paid_amount"].sum()
        desp_pendente  = df_desp[df_desp["payment_status"] == "PENDING"]["expected_amount"].sum()

        rec_total   = rec_realizada + rec_pendente
        desp_total  = desp_realizada + desp_pendente
        saldo_atual = rec_realizada - desp_realizada
        saldo_proj  = rec_total - desp_total
        taxa_poup   = ((rec_total - desp_total) / rec_total * 100) if rec_total > 0 else 0
        desc_total  = df_desp["discount_applied"].sum()

        # Row 1: High-level KPIs
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Receita Total (Prevista)", fmt_brl(rec_total),
                  delta=fmt_brl(rec_realizada) + " realizado")
        c2.metric("Despesa Total (Prevista)", fmt_brl(desp_total),
                  delta=fmt_brl(desp_realizada) + " realizado", delta_color="inverse")
        c3.metric("Saldo Projetado", fmt_brl(saldo_proj),
                  delta=fmt_brl(saldo_atual) + " hoje")
        c4.metric("Taxa de Poupança", f"{taxa_poup:.1f}%",
                  help="(Receita − Despesa) / Receita × 100. Meta saudável: ≥ 20%.")

        # Row 2: Secondary KPIs
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Realizado Receitas", fmt_brl(rec_realizada))
        c6.metric("Realizado Despesas", fmt_brl(desp_realizada), delta_color="inverse")
        c7.metric("A Receber", fmt_brl(rec_pendente))
        c8.metric("Economia c/ Descontos", fmt_brl(desc_total),
                  help="Soma de discount_applied — inclui antecipações e descontos negociados.")

        # Optional Benefit Card KPIs (only shows if there's benefit activity)
        df_ben = df_mes[df_mes["is_benefit"]]
        if not df_ben.empty:
            st.markdown("---")
            b1, b2, b3 = st.columns(3)
            ben_rec  = df_ben[df_ben["transaction_type"] == "RECEITA"]["paid_amount"].sum()
            ben_desp = df_ben[df_ben["transaction_type"] == "DESPESA"]["paid_amount"].sum()
            b1.metric("🎫 Saldo Benefício (VA/VR)", fmt_brl(ben_rec - ben_desp))
            b2.metric("🎫 Crédito Benefício", fmt_brl(ben_rec))
            b3.metric("🎫 Gasto Benefício", fmt_brl(ben_desp))

        st.markdown("---")

        # Row 3: Main Charts (Category Composition & Pacing)
        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("**Composição das Despesas por Categoria**")
            if not df_desp.empty:
                df_cat = (df_desp.groupby("macro_category")["real_amount"]
                          .sum().reset_index()
                          .sort_values("real_amount", ascending=False))
                fig = px.bar(df_cat, x="real_amount", y="macro_category", orientation="h",
                             color="real_amount", color_continuous_scale="Reds",
                             labels={"real_amount": "R$", "macro_category": ""})
                fig.update_layout(showlegend=False, coloraxis_showscale=False,
                                  margin=dict(l=0, r=0, t=10, b=0), height=300)
                st.plotly_chart(fig, use_container_width=True)

        with col_b:
            st.markdown("**Status dos Pagamentos do Mês**")
            if not df_desp.empty:
                df_status = pd.DataFrame({
                    "Status": ["Pago", "Pendente"],
                    "Valor":  [desp_realizada, desp_pendente]
                })
                fig2 = px.pie(df_status, values="Valor", names="Status",
                              hole=0.55, color="Status",
                              color_discrete_map={"Pago": "#1D9E75", "Pendente": "#E24B4A"})
                fig2.update_traces(textinfo="percent+label")
                fig2.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=300)
                st.plotly_chart(fig2, use_container_width=True)

        # Row 4: Operational Charts (Locations & Methods)
        col_c, col_d = st.columns(2)

        with col_c:
            st.markdown("**Top 10 Estabelecimentos**")
            if not df_desp.empty:
                df_top = (df_desp.groupby("location_name")["real_amount"]
                          .sum().reset_index()
                          .sort_values("real_amount", ascending=False).head(10))
                fig3 = px.bar(df_top, x="location_name", y="real_amount",
                              labels={"real_amount": "R$", "location_name": ""},
                              color="real_amount", color_continuous_scale="Blues")
                fig3.update_layout(showlegend=False, coloraxis_showscale=False,
                                   xaxis_tickangle=-35, height=280,
                                   margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig3, use_container_width=True)

        with col_d:
            st.markdown("**Meios de Pagamento Utilizados**")
            if not df_desp.empty:
                df_met = (df_desp.groupby("payment_method")["real_amount"]
                          .sum().reset_index()
                          .sort_values("real_amount", ascending=False))
                fig4 = px.pie(df_met, values="real_amount", names="payment_method",
                              hole=0.4)
                fig4.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=280)
                st.plotly_chart(fig4, use_container_width=True)

    # ==========================================
    # TAB 2: HISTORICAL TRENDS (Yearly Series)
    # ==========================================
    with tab2:
        st.subheader(f"Tendências — {ano_sel}")

        # Slice data for the entire selected year
        df_y = df_inst[df_inst["year"] == ano_sel].copy()
        df_y_desp = df_y[df_y["transaction_type"] == "DESPESA"]
        df_y_rec  = df_y[df_y["transaction_type"] == "RECEITA"]

        # --- Income vs Expense Time Series ---
        st.markdown("### Receita vs Despesa mês a mês")
        trend = (df_y.groupby(["month", "month_dt", "transaction_type"])["real_amount"]
                 .sum().unstack(fill_value=0).reset_index().sort_values("month_dt"))
        
        # Ensure columns exist even if data is missing
        if "RECEITA" not in trend.columns: trend["RECEITA"] = 0
        if "DESPESA" not in trend.columns: trend["DESPESA"] = 0
        
        trend["Saldo"] = trend["RECEITA"] - trend["DESPESA"]
        
        # Savings Rate Calculation (Protects against division by zero using Python's native float('nan'))
        trend["Taxa Poupança (%)"] = (trend["Saldo"] / trend["RECEITA"].replace(0, float('nan')) * 100).round(1)

        fig_trend = go.Figure()
        fig_trend.add_trace(go.Bar(x=trend["month"], y=trend["RECEITA"], name="Receitas",
                                   marker_color="#1D9E75"))
        fig_trend.add_trace(go.Bar(x=trend["month"], y=trend["DESPESA"], name="Despesas",
                                   marker_color="#E24B4A"))
        fig_trend.add_trace(go.Scatter(x=trend["month"], y=trend["Saldo"], name="Saldo",
                                       mode="lines+markers", line=dict(color="#378ADD", width=2.5)))
        fig_trend.update_layout(barmode="group", hovermode="x unified",
                                xaxis_title="", yaxis_title="R$",
                                margin=dict(t=10, b=0), height=320)
        st.plotly_chart(fig_trend, use_container_width=True)

        # Savings Rate Evolution
        st.markdown("### Taxa de Poupança — evolução mensal")
        fig_poup = px.line(trend, x="month", y="Taxa Poupança (%)", markers=True,
                           color_discrete_sequence=["#534AB7"])
        fig_poup.add_hline(y=20, line_dash="dash", line_color="#E24B4A",
                           annotation_text="Meta mínima 20%", annotation_position="top right")
        fig_poup.update_layout(height=220, margin=dict(t=10, b=0))
        st.plotly_chart(fig_poup, use_container_width=True)

        st.markdown("---")

        # --- Dynamic Category Evolution ---
        st.markdown("### Gastos por Categoria — evolução mensal")
        if not df_y_desp.empty:
            cats_disp = sorted(df_y_desp["macro_category"].unique().tolist())
            cats_sel  = st.multiselect("Categorias", cats_disp, default=cats_disp[:5] if len(cats_disp) >= 5 else cats_disp)

            if cats_sel:
                df_cat_trend = (df_y_desp[df_y_desp["macro_category"].isin(cats_sel)]
                                .groupby(["month", "month_dt", "macro_category"])["real_amount"]
                                .sum().reset_index().sort_values("month_dt"))
                fig_cat = px.line(df_cat_trend, x="month", y="real_amount",
                                  color="macro_category", markers=True,
                                  labels={"real_amount": "R$", "macro_category": "Categoria", "month": ""})
                fig_cat.update_layout(height=300, margin=dict(t=10, b=0))
                st.plotly_chart(fig_cat, use_container_width=True)

        st.markdown("---")

        # --- Credit Card Reliance ---
        st.markdown("### Participação por Cartão no Total Gasto")
        if not df_y_desp.empty:
            df_cards = df_y_desp.copy()
            df_cards["cartao"] = (df_cards["card_bank"].str.strip() + " " +
                                  df_cards["card_variant"].str.strip()).str.strip()
            df_cards["cartao"] = df_cards["cartao"].replace("", "Sem cartão / À vista")
            df_c = (df_cards.groupby("cartao")["real_amount"].sum().reset_index()
                    .sort_values("real_amount", ascending=False))
            col_c1, col_c2 = st.columns([1, 1])
            with col_c1:
                fig_card = px.pie(df_c, values="real_amount", names="cartao",
                                  hole=0.45, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_card.update_layout(height=280, margin=dict(t=10, b=0))
                st.plotly_chart(fig_card, use_container_width=True)
            with col_c2:
                df_c["Participação (%)"] = (df_c["real_amount"] / df_c["real_amount"].sum() * 100).round(1)
                df_c.columns = ["Cartão", "Total (R$)", "Participação (%)"]
                df_c["Total (R$)"] = df_c["Total (R$)"].apply(lambda v: f"{v:,.2f}")
                st.dataframe(df_c, use_container_width=True, hide_index=True)

        st.markdown("---")

        # --- Cumulative Savings (Gamification metric) ---
        st.markdown("### Economia Acumulada — Descontos & Antecipações")
        df_disc = (df_inst[df_inst["year"] == ano_sel]
                   .groupby(["month", "month_dt"])["discount_applied"]
                   .sum().reset_index().sort_values("month_dt"))
        df_disc["Acumulado"] = df_disc["discount_applied"].cumsum()
        
        if df_disc["discount_applied"].sum() > 0:
            fig_disc = go.Figure()
            fig_disc.add_trace(go.Bar(x=df_disc["month"], y=df_disc["discount_applied"],
                                      name="Desconto no mês", marker_color="#1D9E75"))
            fig_disc.add_trace(go.Scatter(x=df_disc["month"], y=df_disc["Acumulado"],
                                          name="Acumulado", mode="lines+markers",
                                          line=dict(color="#534AB7", width=2)))
            fig_disc.update_layout(hovermode="x unified", height=250,
                                   margin=dict(t=10, b=0))
            st.plotly_chart(fig_disc, use_container_width=True)
        else:
            st.info("Nenhum desconto registrado no ano selecionado.")

    # ==========================================
    # TAB 3: DEBT & CREDIT MANAGEMENT
    # ==========================================
    with tab3:
        st.subheader("Gestão de Cartões e Parcelamentos")

        # Focuses entirely on unpaid, pending commitments
        df_pend = df_inst[df_inst["payment_status"] == "PENDING"].copy()

        # --- Income Commitment Gauge ---
        st.markdown("### Índice de Comprometimento de Renda")
        meses_horizonte = st.slider("Horizonte (meses futuros)", 1, 12, 3)
        hoje_dt = pd.Timestamp(hoje.date())
        limite_dt = hoje_dt + pd.DateOffset(months=meses_horizonte)

        # Sum of all debt within the user-defined horizon
        df_comp = df_pend[
            (df_pend["transaction_type"] == "DESPESA") &
            (df_pend["due_date"].notna()) &
            (df_pend["due_date"] <= limite_dt)
        ]
        comprometido = df_comp["expected_amount"].sum()

        # Assumes the selected month's income is the baseline for the future
        rec_mes_ref = (df_inst[(df_inst["month"] == mes_sel) &
                               (df_inst["transaction_type"] == "RECEITA")]["real_amount"].sum())

        if rec_mes_ref > 0:
            idx_comp = comprometido / (rec_mes_ref * meses_horizonte) * 100
            cor = "🟢" if idx_comp < 40 else ("🟡" if idx_comp < 70 else "🔴")
            st.markdown(f"**{cor} {idx_comp:.1f}%** da renda dos próximos {meses_horizonte} meses já está comprometida")
            st.caption(f"Total comprometido: {fmt_brl(comprometido)} | Renda de referência ({meses_horizonte}x {mes_sel}): {fmt_brl(rec_mes_ref * meses_horizonte)}")
            
            # Visual Gauge logic
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number", value=round(idx_comp, 1),
                number={"suffix": "%"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar":  {"color": "#E24B4A" if idx_comp > 70 else ("#EF9F27" if idx_comp > 40 else "#1D9E75")},
                    "steps": [
                        {"range": [0,  40], "color": "#EAF3DE"},
                        {"range": [40, 70], "color": "#FAEEDA"},
                        {"range": [70,100], "color": "#FCEBEB"},
                    ],
                    "threshold": {"line": {"color": "#E24B4A", "width": 3}, "value": 70}
                }
            ))
            fig_gauge.update_layout(height=220, margin=dict(t=10, b=0, l=20, r=20))
            st.plotly_chart(fig_gauge, use_container_width=True)

        st.markdown("---")

        # --- Debt Curve ---
        st.markdown("### Curva de Dívida — Total Pendente por Mês")
        df_curva = (df_pend[df_pend["transaction_type"] == "DESPESA"]
                    .groupby(["month", "month_dt"])["expected_amount"]
                    .sum().reset_index().sort_values("month_dt"))
        if not df_curva.empty:
            df_curva["Acumulado"] = df_curva["expected_amount"].cumsum()
            fig_curva = go.Figure()
            fig_curva.add_trace(go.Bar(x=df_curva["month"], y=df_curva["expected_amount"],
                                       name="Vencimento no mês", marker_color="#E24B4A"))
            fig_curva.add_trace(go.Scatter(x=df_curva["month"], y=df_curva["Acumulado"],
                                           name="Acumulado", mode="lines+markers",
                                           line=dict(color="#533AB7", width=2)))
            fig_curva.update_layout(barmode="group", hovermode="x unified",
                                    height=280, margin=dict(t=10, b=0))
            st.plotly_chart(fig_curva, use_container_width=True)

        st.markdown("---")

        # --- Long-term Financing & Installments List ---
        st.markdown("### Parcelamentos Ativos")
        df_parc = df_pend[
            (df_pend["transaction_type"] == "DESPESA") &
            (df_pend["installment_count"] > 1)
        ].copy()

        if not df_parc.empty:
            agrupado = (df_parc
                        .groupby(["transaction_id", "location_name", "macro_category"])
                        .agg(
                            parcelas_restantes=("expected_amount", "count"),
                            total_restante=("expected_amount", "sum"),
                            prox_vencimento=("due_date", "min"),
                            ult_vencimento=("due_date", "max"),
                        ).reset_index()
                        .sort_values("total_restante", ascending=False))

            # Streamlit Accordions for tactical drill-downs
            for _, row in agrupado.iterrows():
                with st.expander(
                    f"🏢 {row['location_name']} — {fmt_brl(row['total_restante'])} "
                    f"({int(row['parcelas_restantes'])} parcelas restantes)"
                ):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total restante", fmt_brl(row["total_restante"]))
                    c2.metric("Próx. vencimento", row["prox_vencimento"].strftime("%d/%m/%Y") if pd.notna(row["prox_vencimento"]) else "—")
                    c3.metric("Último vencimento", row["ult_vencimento"].strftime("%d/%m/%Y") if pd.notna(row["ult_vencimento"]) else "—")

                    df_det = (df_parc[df_parc["transaction_id"] == row["transaction_id"]]
                              [["due_date", "expected_amount", "month"]]
                              .sort_values("due_date").copy())
                    df_det["due_date"] = df_det["due_date"].dt.strftime("%d/%m/%Y")
                    df_det.columns = ["Vencimento", "Valor (R$)", "Mês (Caixa)"]
                    st.dataframe(df_det, use_container_width=True, hide_index=True)
        else:
            st.success("🎉 Nenhum parcelamento ativo no momento.")

    # ==========================================
    # TAB 4: LONG-TERM PROJECTION (Burn Rate)
    # ==========================================
    with tab4:
        st.subheader("Projeção de Caixa — Burn Rate")

        # Filters from the selected month ONWARD to plot the future
        df_fut = df_inst[df_inst["month_dt"] >= pd.to_datetime(mes_sel, format="%m/%Y")].copy()

        if df_fut.empty:
            st.info("Nenhuma projeção disponível.")
        else:
            trend_fut = (df_fut.groupby(["month", "month_dt", "transaction_type"])["expected_amount"]
                         .sum().unstack(fill_value=0).reset_index().sort_values("month_dt"))
            if "RECEITA" not in trend_fut.columns: trend_fut["RECEITA"] = 0
            if "DESPESA" not in trend_fut.columns: trend_fut["DESPESA"] = 0
            
            trend_fut["Saldo"] = trend_fut["RECEITA"] - trend_fut["DESPESA"]
            trend_fut["Saldo Acumulado"] = trend_fut["Saldo"].cumsum()

            fig_fut = go.Figure()
            fig_fut.add_trace(go.Bar(x=trend_fut["month"], y=trend_fut["RECEITA"],
                                     name="Receitas previstas", marker_color="#1D9E75"))
            fig_fut.add_trace(go.Bar(x=trend_fut["month"], y=trend_fut["DESPESA"],
                                     name="Despesas comprometidas", marker_color="#E24B4A"))
            fig_fut.add_trace(go.Scatter(x=trend_fut["month"], y=trend_fut["Saldo"],
                                         name="Saldo do mês", mode="lines+markers",
                                         line=dict(color="#378ADD", width=2.5)))
            fig_fut.add_trace(go.Scatter(x=trend_fut["month"], y=trend_fut["Saldo Acumulado"],
                                         name="Saldo acumulado", mode="lines",
                                         line=dict(color="#534AB7", width=1.5, dash="dot")))
            fig_fut.update_layout(barmode="group", hovermode="x unified",
                                  height=360, margin=dict(t=10, b=0))
            st.plotly_chart(fig_fut, use_container_width=True)

            st.markdown("### Detalhamento mensal")
            df_resumo = trend_fut[["month", "RECEITA", "DESPESA", "Saldo", "Saldo Acumulado"]].copy()
            df_resumo.columns = ["Mês", "Receitas (R$)", "Despesas (R$)", "Saldo (R$)", "Saldo Acumulado (R$)"]
            for col in ["Receitas (R$)", "Despesas (R$)", "Saldo (R$)", "Saldo Acumulado (R$)"]:
                df_resumo[col] = df_resumo[col].apply(lambda v: f"{v:,.2f}")
            st.dataframe(df_resumo, use_container_width=True, hide_index=True)

    # ==========================================
    # TAB 5: ITEM-LEVEL AUDITING (Accrual Data)
    # ==========================================
    with tab5:
        st.subheader("Visão Operacional — Produtos e Serviços")
        st.caption(
            "Análise por item de NFC-e/PDF. Regime de **competência** (data da compra). "
            "Use o filtro de mês do sidebar para focar no período desejado."
        )

        # Filters by the purchase date (Accrual Basis) - Not the payment date
        df_op = df_items[df_items["month_compra"] == mes_sel].copy()

        if df_op.empty:
            st.info(f"Nenhum item detalhado encontrado para {mes_sel}. "
                    "Verifique se há NFC-e ou PDFs com itens cadastrados neste mês.")
        else:
            total_itens = df_op["item_total"].sum()
            qtd_notas   = df_op["transaction_id"].nunique()
            ticket_medio = total_itens / qtd_notas if qtd_notas > 0 else 0

            # Operational KPIs
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total em Itens (NF-e)", fmt_brl(total_itens))
            k2.metric("Notas Fiscais c/ Itens", qtd_notas)
            k3.metric("Ticket Médio por Nota", fmt_brl(ticket_medio))
            k4.metric("Itens Únicos", df_op["item_name"].nunique())

            st.markdown("---")

            # --- Block 1: Hierarchical Treemap ---
            st.markdown("### Treemap — Hierarquia de Categorias")
            st.caption("Macro → Categoria → Subcategoria. O tamanho representa o valor gasto.")
            df_tree = df_op[df_op["item_total"] > 0].copy()
            if not df_tree.empty:
                fig_tree = px.treemap(
                    df_tree,
                    path=[px.Constant("Todos"), "cat_macro", "cat_category", "cat_subcategory"],
                    values="item_total",
                    color="item_total",
                    color_continuous_scale="Reds",
                    hover_data={"item_total": ":,.2f"},
                )
                fig_tree.update_layout(margin=dict(t=10, l=0, r=0, b=0), height=380)
                st.plotly_chart(fig_tree, use_container_width=True)

            st.markdown("---")

            # --- Block 2: Sunburst Drill-down ---
            st.markdown("### Drill-down por Categoria")
            col_l, col_r = st.columns([1, 2])

            with col_l:
                macros_disp = sorted(df_op["cat_macro"].unique().tolist())
                macro_sel = st.radio("Macro categoria", macros_disp)

            df_macro = df_op[df_op["cat_macro"] == macro_sel]

            with col_r:
                cats_disp2 = sorted(df_macro["cat_category"].unique().tolist())
                cat_sel = st.selectbox("Categoria", ["Todas"] + cats_disp2)

            df_drill = df_macro if cat_sel == "Todas" else df_macro[df_macro["cat_category"] == cat_sel]

            if not df_drill.empty:
                fig_sun = px.sunburst(
                    df_drill,
                    path=["cat_category", "cat_subcategory", "item_name"],
                    values="item_total",
                    color="item_total",
                    color_continuous_scale="Blues",
                )
                fig_sun.update_layout(margin=dict(t=10, l=0, r=0, b=0), height=360)
                st.plotly_chart(fig_sun, use_container_width=True)

            st.markdown("---")

            # --- Block 3: Top Items and Brands ---
            st.markdown("### Top Itens & Marcas")
            col_t1, col_t2 = st.columns(2)

            with col_t1:
                st.markdown("**Top 15 Itens por Valor Total**")
                df_top_item = (df_op.groupby(["item_name", "cat_subcategory"])["item_total"]
                               .sum().reset_index()
                               .sort_values("item_total", ascending=False).head(15))
                df_top_item["item_total_fmt"] = df_top_item["item_total"].apply(lambda v: f"{v:,.2f}")
                df_top_item.columns = ["Item", "Subcategoria", "Total (R$)", "_sort"]
                st.dataframe(df_top_item[["Item", "Subcategoria", "Total (R$)"]],
                             use_container_width=True, hide_index=True)

            with col_t2:
                st.markdown("**Top 10 Marcas por Gasto**")
                df_brand = df_op[df_op["brand"].str.strip() != ""]
                if not df_brand.empty:
                    df_top_brand = (df_brand.groupby("brand")["item_total"]
                                    .sum().reset_index()
                                    .sort_values("item_total", ascending=False).head(10))
                    fig_brand = px.bar(df_top_brand, x="item_total", y="brand",
                                       orientation="h", color="item_total",
                                       color_continuous_scale="Purples",
                                       labels={"item_total": "R$", "brand": ""})
                    fig_brand.update_layout(showlegend=False, coloraxis_showscale=False,
                                            height=320, margin=dict(t=10, b=0))
                    st.plotly_chart(fig_brand, use_container_width=True)
                else:
                    st.info("Nenhuma marca registrada nos itens.")

            st.markdown("---")

            # --- Block 4: Behavioral Analysis (Scatter) ---
            st.markdown("### Frequência vs Ticket Médio por Estabelecimento")
            st.caption("Estabelecimentos com muitas visitas e ticket alto são candidatos a revisão de hábito.")
            
            df_scatter = (df_op.groupby("location_name")
                          .agg(
                              visitas=("transaction_id", "nunique"),
                              total_gasto=("item_total", "sum"),
                          ).reset_index())
            df_scatter["ticket_medio"] = df_scatter["total_gasto"] / df_scatter["visitas"]
            
            if not df_scatter.empty:
                fig_sc = px.scatter(
                    df_scatter, x="visitas", y="ticket_medio",
                    size="total_gasto", text="location_name",
                    color="total_gasto", color_continuous_scale="Oranges",
                    labels={
                        "visitas": "Nº de visitas",
                        "ticket_medio": "Ticket médio (R$)",
                        "total_gasto": "Total Gasto (R$)"
                    },
                )
                fig_sc.update_traces(textposition="top center", textfont_size=10)
                fig_sc.update_layout(height=360, margin=dict(t=10, b=0),
                                     coloraxis_showscale=False)
                st.plotly_chart(fig_sc, use_container_width=True)

            st.markdown("---")

            # --- Block 5: Temporal Heatmap ---
            st.markdown("### Padrão de Gastos por Dia do Mês")
            st.caption("Concentração de gastos ao longo do mês por categoria.")
            
            df_op["dia"] = df_op["transaction_date"].dt.day
            df_heat = (df_op.groupby(["dia", "cat_macro"])["item_total"]
                       .sum().reset_index())
            if not df_heat.empty:
                pivot = df_heat.pivot(index="cat_macro", columns="dia", values="item_total").fillna(0)
                fig_heat = px.imshow(
                    pivot,
                    color_continuous_scale="YlOrRd",
                    aspect="auto",
                    labels={"x": "Dia do mês", "y": "Categoria", "color": "R$"},
                )
                fig_heat.update_layout(height=280, margin=dict(t=10, b=0))
                st.plotly_chart(fig_heat, use_container_width=True)

            st.markdown("---")

            # --- Block 6: Full Data Table ---
            st.markdown("### Auditoria Completa de Itens")
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                macros_f = ["Todos"] + sorted(df_op["cat_macro"].unique().tolist())
                macro_f = st.selectbox("Filtrar por macro", macros_f, key="audit_macro")
            with col_f2:
                cats_f_opt = ["Todas"]
                if macro_f != "Todos":
                    cats_f_opt += sorted(df_op[df_op["cat_macro"] == macro_f]["cat_category"].unique().tolist())
                cat_f = st.selectbox("Filtrar por categoria", cats_f_opt, key="audit_cat")
            with col_f3:
                locsf = ["Todos"] + sorted(df_op["location_name"].unique().tolist())
                loc_f = st.selectbox("Filtrar por local", locsf, key="audit_loc")

            df_audit = df_op.copy()
            if macro_f != "Todos":
                df_audit = df_audit[df_audit["cat_macro"] == macro_f]
            if cat_f != "Todas":
                df_audit = df_audit[df_audit["cat_category"] == cat_f]
            if loc_f != "Todos":
                df_audit = df_audit[df_audit["location_name"] == loc_f]

            df_view = df_audit[[
                "transaction_date", "location_name",
                "item_name", "brand",
                "cat_macro", "cat_category", "cat_subcategory",
                "quantity", "unit_price", "item_total"
            ]].copy()
            df_view["transaction_date"] = df_view["transaction_date"].dt.strftime("%d/%m/%Y")
            df_view.columns = [
                "Data", "Local",
                "Item", "Marca",
                "Macro", "Categoria", "Subcategoria",
                "Qtd", "Valor Unit. (R$)", "Total (R$)"
            ]
            df_view = df_view.sort_values("Data", ascending=False)

            st.dataframe(df_view, use_container_width=True, hide_index=True)
            st.caption(f"{len(df_view)} itens exibidos — Total: {fmt_brl(df_audit['item_total'].sum())}")

    # ==========================================
    # TAB 6: MATRIZ DE CONFERÊNCIA (Audit Mode)
    # ==========================================
    with tab6:
        st.subheader(f"Matriz de Conferência — {ano_sel}")
        st.caption(
            "Visão de competência: os lançamentos aparecem no mês do Vencimento Original. "
            "Valores refletem o que foi efetivamente pago ou o previsto atualizado."
        )
        
        # Filtro inicial pelo ano de competência (Vencimento)
        df_matriz = df_inst[df_inst["real_year"] == ano_sel].copy()
        
        if df_matriz.empty:
            st.info(f"Nenhum dado com vencimento em {ano_sel} encontrado.")
        else:
            # Preparação de colunas auxiliares
            df_matriz["Cartão"] = df_matriz.apply(
                lambda r: f"{r['card_bank']} {r['card_variant']}".strip() if r['card_bank'] else "À Vista / Pix",
                axis=1
            )

            # --- FILTROS LOCAIS DA ABA ---
            st.markdown("##### 🔍 Filtros de Auditoria")
            f1, f2, f3 = st.columns(3)
            
            with f1:
                locais_f = sorted(df_matriz["location_name"].unique().tolist())
                sel_locais = st.multiselect("Filtrar por Local:", locais_f, placeholder="Todos os locais")
            
            with f2:
                cartoes_f = sorted(df_matriz["Cartão"].unique().tolist())
                sel_cartoes = st.multiselect("Filtrar por Cartão/Método:", cartoes_f, placeholder="Todos os métodos")
                
            with f3:
                categorias_f = sorted(df_matriz["macro_category"].unique().tolist())
                sel_cats = st.multiselect("Filtrar por Categoria:", categorias_f, placeholder="Todas as categorias")

            # Aplicação dos filtros dinâmicos
            if sel_locais: df_matriz = df_matriz[df_matriz["location_name"].isin(sel_locais)]
            if sel_cartoes: df_matriz = df_matriz[df_matriz["Cartão"].isin(sel_cartoes)]
            if sel_cats: df_matriz = df_matriz[df_matriz["macro_category"].isin(sel_cats)]

            # Ordenação cronológica das colunas de meses
            meses_colunas = sorted(
                df_matriz["real_month"].unique().tolist(), 
                key=lambda x: datetime.strptime(str(x), "%m/%Y")
            )

            for tx_type, label in [("RECEITA", "Receitas"), ("DESPESA", "Despesas")]:
                st.markdown(f"### 📋 {label}")
                df_tipo = df_matriz[df_matriz["transaction_type"] == tx_type]

                if df_tipo.empty:
                    st.write(f"_Nenhum registro de {label.lower()} encontrado com os filtros aplicados._")
                    continue

                # PIVOT TABLE: Apenas macro_category, garantindo que o valor nunca seja multiplicado
                pivot = pd.pivot_table(
                    df_tipo,
                    values='real_amount',
                    index=['macro_category', 'location_name', 'Cartão', 'transaction_id'],
                    columns='real_month', 
                    aggfunc='sum',
                    fill_value=0
                )

                # Proteção anti-crash caso os filtros esvaziem a visualização
                if pivot.empty:
                    st.write(f"_Nenhum dado válido para exibir nesta seção._")
                    continue

                # Força todas as colunas de meses a aparecerem, preenchendo com 0 onde não há dados
                pivot = pivot.reindex(columns=meses_colunas, fill_value=0)
                
                # Calcula o total anual da linha
                pivot['Total Ano'] = pivot.sum(axis=1)
                
                # Tira o index agrupado para formatar como dataframe comum
                pivot = pivot.reset_index()
                
                pivot.rename(columns={
                    'macro_category': 'Categoria',
                    'location_name': 'Estabelecimento / Origem',
                    'transaction_id': 'Ref. ID'
                }, inplace=True)

                pivot = pivot.sort_values(by=['Categoria', 'Estabelecimento / Origem'])

                # Formatação Monetária Interativa
                for col in meses_colunas + ['Total Ano']:
                    pivot[col] = pivot[col].apply(
                        lambda x: f"R$ {x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') if x != 0 else "-"
                    )

                st.dataframe(
                    pivot, 
                    use_container_width=True, 
                    hide_index=True,
                    height=500 if tx_type == "DESPESA" else 300
                )

if __name__ == "__main__":
    main()