import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re

# Importações estatísticas
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.stattools import adfuller, acf, pacf

# Configuração da página
st.set_page_config(
    page_title="Dashboard Financeiro",
    page_icon="💳",
    layout="wide"
)

st.title("💳 Acompanhamento de Gastos - Cartão de Crédito")

# -------------------------------------------------------------
# LINK DA SUA PLANILHA (PRÉ-CONFIGURADO)
# -------------------------------------------------------------
URL_PADRAO_SHEETS = "https://docs.google.com/spreadsheets/d/1IOeKzmexKfS_qpqi4zzxDEEnptr0Hdqeme5_HURLPzc/edit?usp=sharing"

st.sidebar.subheader("🔗 Fonte de Dados (Google Sheets)")

url_input = st.sidebar.text_input(
    "Link da Planilha do Google Sheets:",
    value=URL_PADRAO_SHEETS,
    help="O link da sua planilha já está configurado. Qualquer alteração feita no Google Sheets será refletida aqui."
)

if st.sidebar.button("🔄 Atualizar Dados do Sheets"):
    st.cache_data.clear()
    st.rerun()

def converter_url_google_sheets(url):
    if not url:
        return None
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
    if not match:
        return url
    sheet_id = match.group(1)
    
    gid_match = re.search(r'gid=([0-9]+)', url)
    gid = gid_match.group(1) if gid_match else "0"
    
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

@st.cache_data(ttl=300)
def carregar_dados_sheets(url_csv):
    try:
        df = pd.read_csv(url_csv)
        
        colunas_str = " ".join([str(c) for c in df.columns]).lower()
        if "html" in colunas_str or "doctype" in colunas_str or "google" in colunas_str:
            st.error("🔒 **Acesso Negado:** A planilha precisa estar com acesso público (Qualquer pessoa com o link).")
            return None
            
        return df
    except Exception as e:
        st.error(f"Erro ao acessar o Google Sheets: {e}")
        return None

url_csv = converter_url_google_sheets(url_input)
df = carregar_dados_sheets(url_csv) if url_csv else None

def formatar_moeda(valor):
    if pd.isna(valor):
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def auto_mapear_colunas(colunas):
    def buscar_coluna(keywords):
        for col in colunas:
            col_clean = str(col).strip().lower()
            if any(k in col_clean for k in keywords):
                return col
        return colunas[0] if colunas else None

    c_data = buscar_coluna(["data", "dt", "date"])
    c_desc = buscar_coluna(["descri", "estab", "local", "maquininha", "historico", "titulo"])
    c_cat = buscar_coluna(["categ", "cat"])
    c_tipo = buscar_coluna(["tipo", "classif"])
    c_valor = buscar_coluna(["valor", "vlr", "r$", "monto", "preco"])

    return c_data, c_desc, c_cat, c_tipo, c_valor


if df is not None:
    colunas = list(df.columns)
    col_data, col_desc, col_cat, col_tipo, col_valor = auto_mapear_colunas(colunas)

    # --- TRATAMENTO DE VALORES ---
    def tratar_valores(coluna):
        if pd.api.types.is_numeric_dtype(coluna):
            return coluna
        s = coluna.astype(str)
        s = s.str.replace(r'[^\d,\.\-]', '', regex=True)
        has_comma = s.str.contains(',')
        s_formatted = s.copy()
        s_formatted[has_comma] = s[has_comma].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        return pd.to_numeric(s_formatted, errors='coerce')

    # --- TRATAMENTO DE DATAS ---
    def tratar_datas(coluna):
        meses_pt = {
            'janeiro': '01', 'fevereiro': '02', 'março': '03', 'marco': '03',
            'abril': '04', 'maio': '05', 'junho': '06',
            'julho': '07', 'agosto': '08', 'setembro': '09',
            'outubro': '10', 'novembro': '11', 'dezembro': '12'
        }
        
        def parse_single(val):
            if pd.isna(val):
                return pd.NaT
            val_str = str(val).lower().strip()
            
            match = re.search(r'(\d{1,2})\s+de\s+([a-zà-ú]+)\s+de\s+(\d{4})', val_str)
            if match:
                dia, mes_nome, ano = match.groups()
                mes_num = meses_pt.get(mes_nome)
                if mes_num:
                    res = pd.to_datetime(f"{ano}-{mes_num}-{dia.zfill(2)}", errors='coerce')
                    if not pd.isna(res):
                        return res
            
            return pd.to_datetime(val_str, dayfirst=True, errors='coerce')

        return coluna.apply(parse_single)

    df["_valor_limpo"] = tratar_valores(df[col_valor])
    df["_data_limpa"] = tratar_datas(df[col_data])

    df_base = df.dropna(subset=["_data_limpa", "_valor_limpo"]).copy()

    if not df_base.empty:
        # -------------------------------------------------------------
        # PAINEL DE FILTROS INTERATIVOS (SIDEBAR)
        # -------------------------------------------------------------
        st.sidebar.divider()
        st.sidebar.subheader("🔍 Filtros de Dados")

        data_min_base = df_base["_data_limpa"].min().date()
        data_max_base = df_base["_data_limpa"].max().date()

        periodo_selecionado = st.sidebar.date_input(
            "📅 Período (Data Inicial e Final):",
            value=(data_min_base, data_max_base),
            min_value=data_min_base,
            max_value=data_max_base,
            format="DD/MM/YYYY"
        )

        tipos_unicos = sorted(df_base[col_tipo].dropna().unique().tolist())
        tipos_selecionados = st.sidebar.multiselect(
            "📌 Tipo de Gasto:",
            options=tipos_unicos,
            default=tipos_unicos
        )

        if tipos_selecionados:
            df_para_categorias = df_base[df_base[col_tipo].isin(tipos_selecionados)]
        else:
            df_para_categorias = df_base.iloc[0:0] 

        cats_unicas = sorted(df_para_categorias[col_cat].dropna().unique().tolist())
        cats_selecionadas = st.sidebar.multiselect(
            "🏷️ Categoria:",
            options=cats_unicas,
            default=cats_unicas
        )

        val_min_base = float(df_base["_valor_limpo"].min())
        val_max_base = float(df_base["_valor_limpo"].max())

        if val_min_base < val_max_base:
            faixa_valor = st.sidebar.slider(
                "💰 Intervalo de Valor (R$):",
                min_value=val_min_base,
                max_value=val_max_base,
                value=(val_min_base, val_max_base),
                step=5.0,
                format="R$ %.2f"
            )
        else:
            faixa_valor = (val_min_base, val_max_base)

        if isinstance(periodo_selecionado, (list, tuple)) and len(periodo_selecionado) == 2:
            dt_ini, dt_fim = periodo_selecionado
            cond_data = (df_base["_data_limpa"].dt.date >= dt_ini) & (df_base["_data_limpa"].dt.date <= dt_fim)
        else:
            cond_data = True

        cond_tipo = df_base[col_tipo].isin(tipos_selecionados)
        cond_cat = df_base[col_cat].isin(cats_selecionadas)
        cond_valor = (df_base["_valor_limpo"] >= faixa_valor[0]) & (df_base["_valor_limpo"] <= faixa_valor[1])

        df_filtrado = df_base[cond_data & cond_tipo & cond_cat & cond_valor].copy()

        st.sidebar.caption(f"📊 **{len(df_filtrado)}** de **{len(df_base)}** compras selecionadas.")

        # -------------------------------------------------------------
        # ESTRUTURA DE ABAS
        # -------------------------------------------------------------
        aba_dados, aba_resumo, aba_mensal, aba_semanal = st.tabs([
            "📋 Dados Brutos", 
            "📊 Resumo Geral", 
            "📅 Análise Mensal",
            "🗓️ Análise Semanal"
        ])

        # --- ABA 1: DADOS BRUTOS ---
        with aba_dados:
            st.subheader("Visualização da Planilha (Filtrada)")
            st.dataframe(
                df_filtrado.drop(columns=["_valor_limpo", "_data_limpa"], errors="ignore"), 
                use_container_width=True
            )

        # --- ABA 2: RESUMO GERAL ---
        with aba_resumo:
            st.subheader("Análise Geral dos Dados Filtrados")

            if not df_filtrado.empty:
                st.markdown("### 💰 1. Resumo dos Valores Gastos")
                valores = df_filtrado["_valor_limpo"]

                v1, v2, v3, v4, v5 = st.columns(5)
                v1.metric("Total Gasto", formatar_moeda(valores.sum()))
                v2.metric("Média por Compra", formatar_moeda(valores.mean()))
                v3.metric("Mediana", formatar_moeda(valores.median()))
                v4.metric("Maior Compra", formatar_moeda(valores.max()))
                v5.metric("Menor Compra", formatar_moeda(valores.min()))

                st.divider()

                st.markdown("### 📅 2. Frequência pelos Dias do Mês")
                datas = df_filtrado["_data_limpa"]
                compras_por_dia = datas.dt.day.value_counts().reindex(range(1, 32), fill_value=0)
                st.bar_chart(compras_por_dia)

                st.divider()

                st.markdown("### 🏪 3. Principais Estabelecimentos")
                st.dataframe(df_filtrado[col_desc].value_counts().head(5), use_container_width=True)

                st.divider()

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("### 🏷️ Top 10 Categorias Mais Frequentes")
                    st.bar_chart(df_filtrado[col_cat].value_counts().head(10))
                with c2:
                    st.markdown("### 📌 Gastos por Tipo")
                    st.bar_chart(df_filtrado[col_tipo].value_counts())
            else:
                st.warning("Nenhuma compra encontrada para os filtros selecionados.")

        # --- ABA 3: ANÁLISE MENSAL ---
        with aba_mensal:
            st.subheader("📈 Evolução Mensal dos Gastos")

            if not df_filtrado.empty:
                df_filtrado["Ano_Mes_Sort"] = df_filtrado["_data_limpa"].dt.to_period("M")
                df_filtrado["Ano_Mes_Texto"] = df_filtrado["_data_limpa"].dt.strftime("%m/%Y")

                df_mensal = (
                    df_filtrado.groupby(["Ano_Mes_Sort", "Ano_Mes_Texto"])["_valor_limpo"]
                    .sum()
                    .reset_index()
                    .sort_values("Ano_Mes_Sort")
                )
                df_mensal.rename(columns={"_valor_limpo": "Total Gasto"}, inplace=True)

                m1, m2, m3, m4 = st.columns(4)
                mes_maior_gasto = df_mensal.loc[df_mensal["Total Gasto"].idxmax()]
                mes_menor_gasto = df_mensal.loc[df_mensal["Total Gasto"].idxmin()]

                m1.metric("Média Mensal de Gastos", formatar_moeda(df_mensal["Total Gasto"].mean()))
                m2.metric("Total no Período", formatar_moeda(df_mensal["Total Gasto"].sum()))
                m3.metric("Maior Fatura", f"{mes_maior_gasto['Ano_Mes_Texto']}", formatar_moeda(mes_maior_gasto["Total Gasto"]))
                m4.metric("Menor Fatura", f"{mes_menor_gasto['Ano_Mes_Texto']}", formatar_moeda(mes_menor_gasto["Total Gasto"]))

                st.divider()

                fig = px.line(
                    df_mensal,
                    x="Ano_Mes_Texto",
                    y="Total Gasto",
                    text="Total Gasto",
                    markers=True,
                    title="Evolução do Gasto Total por Mês (Cartão de Crédito)",
                    labels={"Ano_Mes_Texto": "Mês/Ano", "Total Gasto": "Valor Total (R$)"}
                )

                fig.update_traces(
                    textposition="top center",
                    texttemplate="R$ %{y:,.2f}",
                    line=dict(color="#1f77b4", width=3),
                    marker=dict(size=8)
                )
                fig.update_layout(
                    yaxis_tickprefix="R$ ",
                    hovermode="x unified",
                    xaxis=dict(type='category')
                )

                st.plotly_chart(fig, use_container_width=True)

                st.markdown("### 📄 Tabela Resumida por Mês")
                df_tabela = df_mensal[["Ano_Mes_Texto", "Total Gasto"]].copy()
                df_tabela["Total Gasto"] = df_tabela["Total Gasto"].apply(formatar_moeda)
                df_tabela.columns = ["Mês/Ano", "Total Gasto"]
                
                st.dataframe(df_tabela, use_container_width=True)
            else:
                st.warning("Nenhum dado disponível para a Análise Mensal com os filtros atuais.")

        # --- ABA 4: ANÁLISE SEMANAL E SÉRIES TEMPORAIS ---
        with aba_semanal:
            st.subheader("🗓️ Análise Semanal e Séries Temporais")

            if not df_filtrado.empty:
                df_filtrado["Semana_Num"] = ((df_filtrado["_data_limpa"].dt.day - 1) // 7) + 1
                df_filtrado["Semana_Nome"] = "Semana " + df_filtrado["Semana_Num"].astype(str)
                df_filtrado["Ano_Mes_Sort"] = df_filtrado["_data_limpa"].dt.to_period("M")
                df_filtrado["Ano_Mes_Texto"] = df_filtrado["_data_limpa"].dt.strftime("%m/%Y")

                ordem_semanas = ["Semana 1", "Semana 2", "Semana 3", "Semana 4", "Semana 5"]

                df_semana_acumulado = (
                    df_filtrado.groupby(["Semana_Num", "Semana_Nome"])["_valor_limpo"]
                    .sum()
                    .reset_index()
                    .sort_values("Semana_Num")
                )
                df_semana_acumulado.rename(columns={"_valor_limpo": "Total Gasto"}, inplace=True)

                df_semana_mes = (
                    df_filtrado.groupby(["Ano_Mes_Sort", "Ano_Mes_Texto", "Semana_Num", "Semana_Nome"])["_valor_limpo"]
                    .sum()
                    .reset_index()
                    .sort_values(["Ano_Mes_Sort", "Semana_Num"])
                )
                df_semana_mes.rename(columns={"_valor_limpo": "Total Gasto"}, inplace=True)

                meses_ordenados = (
                    df_semana_mes[["Ano_Mes_Sort", "Ano_Mes_Texto"]]
                    .drop_duplicates()
                    .sort_values("Ano_Mes_Sort")["Ano_Mes_Texto"]
                    .tolist()
                )

                k1, k2, k3 = st.columns(3)
                semana_maior = df_semana_acumulado.loc[df_semana_acumulado["Total Gasto"].idxmax()]

                k1.metric("Total Acumulado", formatar_moeda(df_semana_acumulado["Total Gasto"].sum()))
                k2.metric("Média por Semana", formatar_moeda(df_semana_acumulado["Total Gasto"].mean()))
                k3.metric("Semana com Maior Gasto", semana_maior["Semana_Nome"], formatar_moeda(semana_maior["Total Gasto"]))

                st.divider()

                st.markdown("### 📈 Evolução do Gasto das 5 Semanas ao Longo dos Meses")
                fig_linhas = px.line(
                    df_semana_mes,
                    x="Ano_Mes_Texto",
                    y="Total Gasto",
                    color="Semana_Nome",
                    markers=True,
                    title="Evolução dos Gastos por Semana ao Longo dos Meses (Semana 1 a 5)",
                    labels={
                        "Ano_Mes_Texto": "Mês/Ano",
                        "Total Gasto": "Valor Gasto (R$)",
                        "Semana_Nome": "Semana"
                    },
                    category_orders={
                        "Semana_Nome": ordem_semanas,
                        "Ano_Mes_Texto": meses_ordenados
                    }
                )

                fig_linhas.update_traces(
                    marker=dict(size=8),
                    hovertemplate="<b>%{x}</b> - %{fullData.name}<br>Gasto: R$ %{y:,.2f}"
                )
                fig_linhas.update_layout(
                    yaxis_tickprefix="R$ ",
                    hovermode="x unified",
                    xaxis=dict(type='category')
                )

                st.plotly_chart(fig_linhas, use_container_width=True)

                st.divider()

                # =========================================================
                # DECOMPOSIÇÃO E ANÁLISE DE SÉRIES TEMPORAIS TRANSFORMADAS
                # =========================================================
                st.markdown("## 🔍 Decomposição Estatística com Transformação Logarítmica e Diferenciação")

                # 1. Série temporal agregada por semana
                ts_semanal = (
                    df_filtrado.set_index("_data_limpa")
                    .resample("W")["_valor_limpo"]
                    .sum()
                    .fillna(0)
                )

                # 2. Aplicação da Transformação Logarítmica: log(1 + X)
                ts_log = np.log1p(ts_semanal)

                # 3. Aplicação da Primeira Diferença: Δ log(1 + X_t) = log(1 + X_t) - log(1 + X_{t-1})
                ts_diff = ts_log.diff().dropna()

                if len(ts_diff) >= 12:
                    periodo_sazonal = 4 # Ciclo de 4 semanas
                    decomposicao = seasonal_decompose(ts_diff, model="additive", period=periodo_sazonal)

                    # Subplots da decomposição
                    fig_decomp = make_subplots(
                        rows=4, cols=1,
                        shared_xaxes=True,
                        subplot_titles=(
                            "Série Transformada & Diferenciada: Δ log(1 + X)", 
                            "Tendência da Série Transformada", 
                            "Sazonalidade (Ciclo Mensal de 4 Semanas)", 
                            "Ruído / Resíduos"
                        )
                    )

                    fig_decomp.add_trace(go.Scatter(x=ts_diff.index, y=decomposicao.observed, name="Observado (Transformado)", line=dict(color="#1f77b4")), row=1, col=1)
                    fig_decomp.add_trace(go.Scatter(x=ts_diff.index, y=decomposicao.trend, name="Tendência", line=dict(color="#ff7f0e", width=2.5)), row=2, col=1)
                    fig_decomp.add_trace(go.Scatter(x=ts_diff.index, y=decomposicao.seasonal, name="Sazonalidade", line=dict(color="#2ca02c")), row=3, col=1)
                    fig_decomp.add_trace(go.Scatter(x=ts_diff.index, y=decomposicao.resid, name="Ruído", mode="markers", marker=dict(color="#d62728", size=5)), row=4, col=1)

                    fig_decomp.update_layout(
                        height=800,
                        showlegend=False,
                        title_text="Decomposição da Série Temporal Transformada (Log + 1ª Diferença)"
                    )
                    st.plotly_chart(fig_decomp, use_container_width=True)

                    st.divider()

                    # Gráficos de Autocorrelação (ACF e PACF da série transformada)
                    st.markdown("### 📊 Autocorrelação da Série Transformada (ACF e PACF)")
                    c_acf, c_pacf = st.columns(2)

                    nlags = min(20, len(ts_diff) // 2 - 1)
                    acf_vals = acf(ts_diff, nlags=nlags)
                    pacf_vals = pacf(ts_diff, nlags=nlags)

                    with c_acf:
                        fig_acf = px.bar(
                            x=list(range(len(acf_vals))),
                            y=acf_vals,
                            labels={"x": "Lags (Semanas)", "y": "Autocorrelação"},
                            title="ACF - Série Transformada [Δ log(1 + X)]"
                        )
                        fig_acf.update_traces(marker_color="#1f77b4")
                        st.plotly_chart(fig_acf, use_container_width=True)

                    with c_pacf:
                        fig_pacf = px.bar(
                            x=list(range(len(pacf_vals))),
                            y=pacf_vals,
                            labels={"x": "Lags (Semanas)", "y": "Autocorrelação Parcial"},
                            title="PACF - Série Transformada [Δ log(1 + X)]"
                        )
                        fig_pacf.update_traces(marker_color="#ff7f0e")
                        st.plotly_chart(fig_pacf, use_container_width=True)

                    st.divider()

                    # Teste ADF na série transformada
                    st.markdown("### 🧪 Teste de Dickey-Fuller Aumentado na Série Transformada")
                    
                    adf_resultado = adfuller(ts_diff)
                    adf_stat = adf_resultado[0]
                    p_valor = adf_resultado[1]
                    crit_vals = adf_resultado[4]

                    col_adf1, col_adf2, col_adf3 = st.columns(3)
                    col_adf1.metric("Estatística ADF", f"{adf_stat:.4f}")
                    col_adf2.metric("p-valor", f"{p_valor:.4f}")
                    
                    is_estacionaria = p_valor < 0.05
                    col_adf3.metric(
                        "Status de Estacionariedade", 
                        "Estacionária" if is_estacionaria else "Não-Estacionária",
                        delta="Média e Variância Estáveis" if is_estacionaria else "Requer Maior Diferenciação",
                        delta_color="normal" if is_estacionaria else "inverse"
                    )

                    with st.expander("ℹ️ Detalhes e Interpretação do Teste na Série Transformada"):
                        st.write(r"**Equação Aplicada:** $Y^*_t = \ln(1 + X_t) - \ln(1 + X_{t-1})$")
                        st.write(f"**Hipótese Nula (H0):** A série transformada possui raiz unitária (Não-Estacionária).")
                        st.write(f"**Hipótese Alternativa (H1):** A série transformada é Estacionária.")
                        
                        if is_estacionaria:
                            st.success(
                                f"Com p-valor de **{p_valor:.4f}** (menor que 0.05), **rejeitamos a hipótese nula**. "
                                f"Após aplicar a transformação logarítmica e a 1ª diferença, a série tornou-se **estacionária**, com média e variância estabilizadas."
                            )
                        else:
                            st.warning(
                                f"Com p-valor de **{p_valor:.4f}** (maior ou igual a 0.05), **não rejeitamos a hipótese nula**. "
                                f"A série ainda apresenta comportamentos não-estacionários."
                            )

                        st.write("**Valores Críticos de Rejeição:**")
                        st.json({k: round(v, 4) for k, v in crit_vals.items()})

                else:
                    st.info("Selecione um período com pelo menos 12 semanas para gerar a análise de série temporal transformada.")

            else:
                st.warning("Nenhum dado disponível para a Análise Semanal com os filtros atuais.")

    else:
        st.error("Não foram encontrados dados válidos na planilha informada.")

else:
    st.info("Carregando planilha do Google Sheets...")
