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
        # --- CARREGAMENTO DO ARQUIVO ---
        # Tenta ler como CSV (com diferentes encodings) ou Excel
        if uploaded_file.name.endswith('.csv'):
            try:
                df = pd.read_csv(uploaded_file, encoding='latin1', sep=',')
            except:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding='latin1', sep=';')
        else:
            df = pd.read_excel(uploaded_file)

        st.success("Arquivo carregado com sucesso!")

        # --- TRATAMENTO DOS DADOS ---
        
        # 1. Ajuste de colunas numéricas (Blindagem contra erros de formatação R$)
        # Converte textos como "1.200,50" para o número 1200.50 que o Python entende
        cols_valores = ['VLR_CONTAB_ITEM', 'VLR_BASE_ICMS_1', 'VLR_TRIBUTO_ICMS']
        
        # Verificamos se as colunas existem antes de tentar converter
        cols_existentes = [col for col in cols_valores if col in df.columns]
        
        for col in cols_existentes:
            # Garante que é string primeiro
            df[col] = df[col].astype(str)
            # Remove ponto de milhar (ex: 1.000 -> 1000)
            df[col] = df[col].str.replace('.', '', regex=False)
            # Troca vírgula por ponto decimal (ex: 50,20 -> 50.20)
            df[col] = df[col].str.replace(',', '.', regex=False)
            # Converte para número (se der erro, vira 0)
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        # 2. Definição de colunas de metadados
        col_cfop = 'COD_CFO'
        col_cst_a = 'COD_SITUACAO_A' # Origem
        col_cst_b = 'COD_SITUACAO_B' # Tributação
        
        # 3. Cria CST Completo (Ex: 0 + 00 = 000)
        # Garante que as colunas de CST sejam strings antes de concatenar
        df['CST_COMPLETO'] = df[col_cst_a].astype(str).str.replace(r'\.0$', '', regex=True) + \
                             df[col_cst_b].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(2)
        
        # 4. Lógica de Entrada vs Saída baseada no CFOP
        def definir_tipo(cfop):
            cfop_str = str(cfop)
            if cfop_str.startswith(('1', '2', '3')):
                return 'ENTRADA'
            elif cfop_str.startswith(('5', '6', '7')):
                return 'SAIDA'
            else:
                return 'OUTROS'

        df['TIPO_OPERACAO'] = df[col_cfop].apply(definir_tipo)

        # --- ANÁLISE E VISUALIZAÇÃO ---

        tab1, tab2, tab3 = st.tabs(["Resumo Geral", "Análise por CST", "Dados Brutos"])

        with tab1:
            st.header("Totais por Tipo de Operação")
            
            # Agrupa por tipo e soma
            resumo_tipo = df.groupby('TIPO_OPERACAO')[cols_existentes].sum().reset_index()
            
            # Mostra tabela formatada
            st.dataframe(resumo_tipo.style.format({col: "R$ {:,.2f}" for col in cols_existentes}))

            # Métricas (Cards)
            col1, col2 = st.columns(2)
            
            # Filtra valores para os cards, garantindo que não quebre se estiver vazio
            mask_ent = resumo_tipo['TIPO_OPERACAO'] == 'ENTRADA'
            mask_sai = resumo_tipo['TIPO_OPERACAO'] == 'SAIDA'
            
            val_ent = resumo_tipo.loc[mask_ent, 'VLR_TRIBUTO_ICMS'].sum() if mask_ent.any() else 0.0
            val_sai = resumo_tipo.loc[mask_sai, 'VLR_TRIBUTO_ICMS'].sum() if mask_sai.any() else 0.0
            
            col1.metric("Total ICMS (Entradas)", f"R$ {val_ent:,.2f}")
            col2.metric("Total ICMS (Saídas)", f"R$ {val_sai:,.2f}")

        with tab2:
            st.header("Detalhamento por CST")
            
            tipo_filtro = st.radio("Selecione o fluxo:", ["ENTRADA", "SAIDA"], horizontal=True)
            
            df_filtered = df[df['TIPO_OPERACAO'] == tipo_filtro]
            
            if not df_filtered.empty:
                analise_cst = df_filtered.groupby(['CST_COMPLETO'])[cols_existentes].sum().reset_index()
                analise_cst = analise_cst.sort_values(by='VLR_TRIBUTO_ICMS', ascending=False)
                
                st.subheader(f"ICMS por CST ({tipo_filtro})")
                st.dataframe(analise_cst.style.format({col: "R$ {:,.2f}" for col in cols_existentes}), use_container_width=True)

                # Botão de Download
                csv = analise_cst.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=f"Baixar Relatório CST ({tipo_filtro})",
                    data=csv,
                    file_name=f'analise_icms_{tipo_filtro.lower()}.csv',
                    mime='text/csv',
                )
            else:
                st.info(f"Nenhum registro de {tipo_filtro} encontrado.")

        with tab3:
            st.write("Amostra dos dados processados:")
            st.dataframe(df.head())

    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {e}")
        st.write("Dica: Verifique se o arquivo possui as colunas 'COD_CFO', 'COD_SITUACAO_A', 'COD_SITUACAO_B' e colunas de valores.")