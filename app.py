import streamlit as st
import pandas as pd
# AQUI ESTÁ O SEGREDO: Importamos a classe do outro arquivo
from processador_fiscal import ProcessadorFiscal

# ==============================================================================
# 🎨 VISUAL (INTERFACE STREAMLIT)
# ==============================================================================

st.set_page_config(page_title="Auditoria Fiscal ICMS", layout="wide", page_icon="📊")

st.title("📊 Auditoria e Análise Fiscal de ICMS")
st.markdown("Sistema de separação de Entradas/Saídas e validação de regras de negócio.")

# Sidebar para upload
with st.sidebar:
    st.header("Upload de Arquivo")
    uploaded_file = st.file_uploader("Arquivo Fiscal (CSV/Excel)", type=["csv", "xlsx"])
    st.info("Formatos suportados: CSV e Excel (.xlsx)")

if uploaded_file:
    try:
        # Instancia a classe que importamos do outro arquivo
        processador = ProcessadorFiscal(uploaded_file)
        
        with st.spinner('O motor fiscal está trabalhando...'):
            df = processador.processar_dados()
            divergencias = processador.obter_divergencias()
            excel_data = processador.gerar_excel_consolidado()

        st.success("Processamento concluído com sucesso!")

        # --- DASHBOARD ---
        
        # Métricas
        col1, col2, col3 = st.columns(3)
        
        # Tratamento de erro caso o dataframe esteja vazio
        total_ent = df[df['TIPO_OPERACAO'] == 'ENTRADA']['VLR_TRIBUTO_ICMS'].sum() if not df.empty else 0
        total_sai = df[df['TIPO_OPERACAO'] == 'SAIDA']['VLR_TRIBUTO_ICMS'].sum() if not df.empty else 0
        total_div = len(divergencias)
        
        col1.metric("ICMS Entradas", f"R$ {total_ent:,.2f}")
        col2.metric("ICMS Saídas", f"R$ {total_sai:,.2f}")
        col3.metric("Divergências Encontradas", f"{total_div} notas", delta_color="inverse")

        # Botão de Download
        st.download_button(
            label="📥 BAIXAR RELATÓRIO COMPLETO (EXCEL)",
            data=excel_data,
            file_name="relatorio_fiscal_consolidado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Excel com abas: Entradas, Saídas, Resumos e Divergências."
        )

        st.divider()

        # Visualização Detalhada
        tab1, tab2, tab3 = st.tabs(["🔍 Divergências", "📈 Análise CST", "📋 Base de Dados"])

        with tab1:
            if not divergencias.empty:
                st.error(f"Atenção: {len(divergencias)} notas de SAÍDA com CST tributado mas sem destaque de ICMS.")
                st.dataframe(divergencias.style.format({'VLR_TRIBUTO_ICMS': 'R$ {:,.2f}'}))
            else:
                st.success("Nenhuma divergência de tributação encontrada nas saídas.")

        with tab2:
            st.subheader("Agrupamento por CST")
            if not df.empty:
                pvt_cst = df.groupby(['TIPO_OPERACAO', 'CST_COMPLETO'])[['VLR_CONTAB_ITEM', 'VLR_TRIBUTO_ICMS']].sum().reset_index()
                st.dataframe(pvt_cst.style.format({'VLR_CONTAB_ITEM': 'R$ {:,.2f}', 'VLR_TRIBUTO_ICMS': 'R$ {:,.2f}'}), use_container_width=True)

        with tab3:
            st.dataframe(df.head(50))

    except Exception as e:
        st.error(f"Ocorreu um erro no processamento: {e}")
