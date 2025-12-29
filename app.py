import streamlit as st
import pandas as pd
import io

# Configuração da página
st.set_page_config(page_title="Análise Fiscal ICMS/CST", layout="wide")

st.title("📊 Analisador Fiscal de ICMS por CST")
st.markdown("""
Esta ferramenta processa o arquivo fiscal, separa **Entradas e Saídas** pelo CFOP 
e agrupa os valores de ICMS baseados no CST (Código de Situação Tributária).
""")

# Upload do arquivo
uploaded_file = st.file_uploader("Carregue seu arquivo CSV ou Excel", type=["csv", "xlsx"])

if uploaded_file:
    try:
        # Carregamento inteligente (tenta ler CSV ou Excel)
        if uploaded_file.name.endswith('.csv'):
            # Arquivos fiscais brasileiros geralmente usam encoding latin1 e separador ; ou ,
            try:
                df = pd.read_csv(uploaded_file, encoding='latin1', sep=',')
            except:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding='latin1', sep=';')
        else:
            df = pd.read_excel(uploaded_file)

        st.success("Arquivo carregado com sucesso!")

        # --- PROCESSAMENTO DOS DADOS ---
        
        # 1. Garantir que as colunas sejam strings para manipulação
        # Ajuste os nomes das colunas conforme seu arquivo real se necessário
        col_cfop = 'COD_CFO'
        col_cst_a = 'COD_SITUACAO_A' # Origem
        col_cst_b = 'COD_SITUACAO_B' # Tributação
        
        # Cria CST Completo (Ex: 0 + 00 = 000)
        df['CST_COMPLETO'] = df[col_cst_a].astype(str) + df[col_cst_b].astype(str).str.zfill(2)
        
        # 2. Lógica de Entrada vs Saída baseada no primeiro dígito do CFOP
        # 1, 2, 3 -> Entrada
        # 5, 6, 7 -> Saída
        def definir_tipo(cfop):
            cfop_str = str(cfop)
            if cfop_str.startswith(('1', '2', '3')):
                return 'ENTRADA'
            elif cfop_str.startswith(('5', '6', '7')):
                return 'SAIDA'
            else:
                return 'OUTROS'

        df['TIPO_OPERACAO'] = df[col_cfop].apply(definir_tipo)

        # 3. Converter colunas numéricas (caso venham como texto com vírgula)
        cols_valores = ['VLR_CONTAB_ITEM', 'VLR_BASE_ICMS_1', 'VLR_TRIBUTO_ICMS']
        for col in cols_valores:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.replace(',', '.').astype(float)

        # --- ANÁLISE E VISUALIZAÇÃO ---

        # Abas para separar a visão
        tab1, tab2, tab3 = st.tabs(["Resumo Geral", "Análise por CST", "Dados Brutos"])

        with tab1:
            st.header("Totais por Tipo de Operação")
            resumo_tipo = df.groupby('TIPO_OPERACAO')[cols_valores].sum().reset_index()
            st.dataframe(resumo_tipo.style.format("R$ {:,.2f}"))

            # Métricas rápidas
            col1, col2 = st.columns(2)
            total_entradas = resumo_tipo[resumo_tipo['TIPO_OPERACAO'] == 'ENTRADA']['VLR_TRIBUTO_ICMS'].sum()
            total_saidas = resumo_tipo[resumo_tipo['TIPO_OPERACAO'] == 'SAIDA']['VLR_TRIBUTO_ICMS'].sum()
            
            col1.metric("Total ICMS (Entradas)", f"R$ {total_entradas:,.2f}")
            col2.metric("Total ICMS (Saídas)", f"R$ {total_saidas:,.2f}")

        with tab2:
            st.header("Detalhamento por CST")
            
            tipo_filtro = st.radio("Selecione o fluxo:", ["ENTRADA", "SAIDA"], horizontal=True)
            
            # Filtrar e Agrupar
            df_filtered = df[df['TIPO_OPERACAO'] == tipo_filtro]
            
            analise_cst = df_filtered.groupby(['CST_COMPLETO'])[cols_valores].sum().reset_index()
            analise_cst = analise_cst.sort_values(by='VLR_TRIBUTO_ICMS', ascending=False)
            
            st.subheader(f"ICMS por CST ({tipo_filtro})")
            st.dataframe(analise_cst.style.format({
                'VLR_CONTAB_ITEM': 'R$ {:,.2f}', 
                'VLR_BASE_ICMS_1': 'R$ {:,.2f}', 
                'VLR_TRIBUTO_ICMS': 'R$ {:,.2f}'
            }), use_container_width=True)

            # Botão de Download
            csv = analise_cst.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"Baixar Relatório CST ({tipo_filtro})",
                data=csv,
                file_name=f'analise_icms_{tipo_filtro.lower()}.csv',
                mime='text/csv',
            )

        with tab3:
            st.write("Amostra dos dados processados:")
            st.dataframe(df.head())

    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {e}")