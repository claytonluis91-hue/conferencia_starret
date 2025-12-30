import streamlit as st
import pandas as pd
from processador_fiscal import ProcessadorFiscal

def formatar_br(valor):
    if pd.isna(valor) or valor == '': return "R$ 0,00"
    try:
        v = f"{float(valor):,.2f}"
        v = v.replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"R$ {v}"
    except: return valor

st.set_page_config(page_title="Auditoria Fiscal Premium", layout="wide", page_icon="📊")

st.title("📊 Auditoria Fiscal & Apuração de Impostos")
st.markdown("Análise completa: ICMS, PIS, COFINS e Regras de Negócio.")

with st.sidebar:
    st.header("Upload de Arquivo")
    uploaded_file = st.file_uploader("Arquivo Fiscal (CSV/Excel)", type=["csv", "xlsx"])

if uploaded_file:
    try:
        processador = ProcessadorFiscal(uploaded_file)
        
        with st.spinner('Realizando apuração de impostos...'):
            df = processador.processar_dados()
            divergencias = processador.obter_divergencias()
            excel_data = processador.gerar_excel_consolidado()

        st.success("Processamento e Apuração concluídos!")

        # --- RESUMO EXECUTIVO ---
        st.subheader("Resumo da Apuração")
        
        # Criação de métricas de ICMS
        tot_ent_icms = df[df['TIPO_OPERACAO'] == 'ENTRADA']['VLR_TRIBUTO_ICMS'].sum()
        tot_sai_icms = df[df['TIPO_OPERACAO'] == 'SAIDA']['VLR_TRIBUTO_ICMS'].sum()
        saldo_icms = tot_sai_icms - tot_ent_icms
        lbl_icms = "A Recolher" if saldo_icms > 0 else "Saldo Credor"

        # Métricas PIS/COFINS
        cols_pc = ['VLR_PIS', 'VLR_COFINS']
        tot_ent_pc = df[df['TIPO_OPERACAO'] == 'ENTRADA'][cols_pc].sum().sum()
        tot_sai_pc = df[df['TIPO_OPERACAO'] == 'SAIDA'][cols_pc].sum().sum()
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("ICMS (Débitos)", formatar_br(tot_sai_icms))
        col2.metric("ICMS (Créditos)", formatar_br(tot_ent_icms))
        col3.metric(f"Saldo ICMS ({lbl_icms})", formatar_br(abs(saldo_icms)), delta_color="off")
        col4.metric("Total PIS/COFINS (Saídas)", formatar_br(tot_sai_pc))

        # Botão Download
        st.download_button(
            label="📥 BAIXAR RELATÓRIO DE APURAÇÃO (COM ABAS)",
            data=excel_data,
            file_name="apuracao_fiscal_completa.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.divider()
        
        # Abas de visualização
        tab1, tab2 = st.tabs(["🚨 Divergências", "📋 Base de Dados"])
        
        with tab1:
            if not divergencias.empty:
                st.error(f"{len(divergencias)} notas com inconsistências encontradas.")
                st.dataframe(divergencias.head(100), use_container_width=True)
            else:
                st.success("Tudo certo! Nenhuma divergência encontrada.")
        
        with tab2:
            st.dataframe(df.head(50))

    except Exception as e:
        st.error(f"Erro: {e}")
