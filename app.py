import streamlit as st
import pandas as pd
from processador_fiscal import ProcessadorFiscal

# ==============================================================================
# 🎨 FUNÇÕES AUXILIARES DE ESTILO
# ==============================================================================

def formatar_br(valor):
    """
    Transforma 1234.56 em '1.234,56' apenas para exibição visual.
    """
    if pd.isna(valor) or valor == '':
        return "R$ 0,00"
    try:
        # Formata padrão Python (1,234.56)
        v = f"{float(valor):,.2f}"
        # Inverte os sinais: Vírgula vira X, Ponto vira Vírgula, X vira Ponto
        v = v.replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"R$ {v}"
    except:
        return valor

# ==============================================================================
# 📱 INTERFACE STREAMLIT
# ==============================================================================

st.set_page_config(page_title="Auditoria Fiscal ICMS", layout="wide", page_icon="📊")

st.title("📊 Auditoria e Análise Fiscal de ICMS")
st.markdown("Sistema de separação de Entradas/Saídas e validação de regras de negócio.")

# Sidebar
with st.sidebar:
    st.header("Upload de Arquivo")
    uploaded_file = st.file_uploader("Arquivo Fiscal (CSV/Excel)", type=["csv", "xlsx"])

if uploaded_file:
    try:
        processador = ProcessadorFiscal(uploaded_file)
        
        with st.spinner('Analisando regras fiscais e consistência...'):
            df = processador.processar_dados()
            divergencias = processador.obter_divergencias()
            excel_data = processador.gerar_excel_consolidado()

        st.success("Análise concluída!")

        # --- DASHBOARD DE MÉTRICAS ---
        col1, col2, col3 = st.columns(3)
        
        # Totais
        total_ent = df[df['TIPO_OPERACAO'] == 'ENTRADA']['VLR_TRIBUTO_ICMS'].sum() if not df.empty else 0
        total_sai = df[df['TIPO_OPERACAO'] == 'SAIDA']['VLR_TRIBUTO_ICMS'].sum() if not df.empty else 0
        
        # Exibição com formatação BR nos Cards
        # Usamos uma string formatada manualmente aqui pois metric não aceita função
        col1.metric("ICMS Entradas", formatar_br(total_ent))
        col2.metric("ICMS Saídas", formatar_br(total_sai))
        
        # Métrica de Divergência com cor dinâmica
        cor_delta = "inverse" if len(divergencias) > 0 else "normal"
        col3.metric("Notas com Divergência", f"{len(divergencias)}", delta_color=cor_delta)

        # --- BOTÃO DE DOWNLOAD ---
        st.download_button(
            label="📥 BAIXAR RELATÓRIO EXCEL (COM ABAS)",
            data=excel_data,
            file_name="relatorio_fiscal_completo.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.divider()

        # --- ABAS DE DETALHES ---
        tab1, tab2, tab3 = st.tabs(["🚨 Divergências Encontradas", "📈 Resumo CST", "📋 Base Completa"])

        # Colunas que queremos aplicar a formatação visual
        cols_moeda = ['VLR_CONTAB_ITEM', 'VLR_BASE_ICMS_1', 'VLR_TRIBUTO_ICMS']
        
        with tab1:
            if not divergencias.empty:
                st.error(f"Foram encontradas {len(divergencias)} inconsistências.")
                st.markdown("**Motivos:** ICMS zerado em tributados OU Cadastro incompleto em 5.102/6.102.")
                
                # Aplica formatação visual BR
                st.dataframe(
                    divergencias.style.format({c: formatar_br for c in cols_moeda if c in divergencias.columns}),
                    use_container_width=True
                )
            else:
                st.success("Nenhuma divergência encontrada! O cadastro e os impostos parecem corretos.")

        with tab2:
            st.subheader("Totalização por CST")
            if not df.empty:
                pvt_cst = df.groupby(['TIPO_OPERACAO', 'CST_COMPLETO'])[cols_moeda].sum().reset_index()
                
                # Aplica formatação visual BR
                st.dataframe(
                    pvt_cst.style.format({c: formatar_br for c in cols_moeda}),
                    use_container_width=True
                )

        with tab3:
            st.subheader("Visualização dos Dados (Amostra)")
            # Aplica formatação visual BR
            st.dataframe(
                df.head(100).style.format({c: formatar_br for c in cols_moeda if c in df.columns}),
                use_container_width=True
            )

    except Exception as e:
        st.error(f"Erro no processamento: {e}")
