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

st.set_page_config(page_title="Auditoria Fiscal + TTS", layout="wide", page_icon="🌟")

st.title("🌟 Auditoria Fiscal & Regime Especial (TTS)")
st.markdown("Análise completa: ICMS, PIS/COFINS e **Cálculo do Corredor de Importação**.")

with st.sidebar:
    st.header("Upload de Arquivo")
    uploaded_file = st.file_uploader("Arquivo Fiscal (CSV/Excel)", type=["csv", "xlsx"])
    st.info("O sistema identificará automaticamente os produtos importados para o Regime Especial.")

if uploaded_file:
    try:
        processador = ProcessadorFiscal(uploaded_file)
        
        with st.spinner('Processando Apurações e Regras do TTS...'):
            df = processador.processar_dados()
            df_tts = processador.calcular_regime_especial() # Calcula o TTS
            divergencias = processador.obter_divergencias()
            excel_data = processador.gerar_excel_consolidado()

        st.success("Cálculos Finalizados com Sucesso!")

        # --- APURAÇÃO TTS ---
        st.subheader("Simulação: Regime Especial (TTS)")
        
        # Totais do TTS
        total_debito_tts = df_tts[df_tts['ELEGIVEL_TTS']]['VLR_TRIBUTO_ICMS'].sum()
        total_credito_presumido = df_tts['CREDITO_PRESUMIDO_CALC'].sum()
        total_pagar_tts = df_tts[df_tts['ELEGIVEL_TTS']]['ICMS_EFETIVO_RECOLHER'].sum()
        
        # Cards TTS
        c1, c2, c3 = st.columns(3)
        c1.metric("Débito Saída (Produtos TTS)", formatar_br(total_debito_tts))
        c2.metric("Crédito Presumido (Ganho)", formatar_br(total_credito_presumido), delta="Economia")
        c3.metric("ICMS a Recolher (Efetivo)", formatar_br(total_pagar_tts))

        st.divider()

        # --- APURAÇÃO GERAL ---
        st.subheader("Resumo Geral da Empresa")
        
        tot_sai_icms = df[df['TIPO_OPERACAO'] == 'SAIDA']['VLR_TRIBUTO_ICMS'].sum()
        tot_ent_icms = df[df['TIPO_OPERACAO'] == 'ENTRADA']['VLR_TRIBUTO_ICMS'].sum()
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Débitos (Geral)", formatar_br(tot_sai_icms))
        col2.metric("Total Créditos (Geral)", formatar_br(tot_ent_icms))
        col3.metric("Notas com Divergência", f"{len(divergencias)}", delta_color="inverse")

        # Botão Download
        st.download_button(
            label="📥 BAIXAR RELATÓRIO COM ABA TTS (EXCEL)",
            data=excel_data,
            file_name="relatorio_fiscal_tts_completo.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # Visualização TTS
        with st.expander("Ver Detalhes do Cálculo TTS"):
            cols_show = ['COD_CFO', 'NUM_DOCFIS', 'CST_COMPLETO', 'ESTADO_UF_FORNEC', 
                         'VLR_CONTAB_ITEM', 'ALIQ_TRIBUTO_ICMS', 'CREDITO_PRESUMIDO_CALC', 'ICMS_EFETIVO_RECOLHER']
            st.dataframe(df_tts[df_tts['ELEGIVEL_TTS']][cols_show].head(50).style.format({
                'VLR_CONTAB_ITEM': formatar_br,
                'CREDITO_PRESUMIDO_CALC': formatar_br,
                'ICMS_EFETIVO_RECOLHER': formatar_br
            }))

    except Exception as e:
        st.error(f"Erro: {e}")
