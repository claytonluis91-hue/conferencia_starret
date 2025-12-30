import pandas as pd
import io
import numpy as np

class ProcessadorFiscal:
    def __init__(self, arquivo):
        self.df = self._carregar_arquivo(arquivo)
        self.cols_valores = ['VLR_CONTAB_ITEM', 'VLR_BASE_ICMS_1', 'VLR_TRIBUTO_ICMS']

    def _carregar_arquivo(self, arquivo):
        """Carrega CSV ou Excel e retorna DataFrame bruto."""
        if hasattr(arquivo, 'name') and arquivo.name.endswith('.csv'):
            try:
                return pd.read_csv(arquivo, encoding='latin1', sep=',')
            except:
                arquivo.seek(0)
                return pd.read_csv(arquivo, encoding='latin1', sep=';')
        elif hasattr(arquivo, 'name'): 
            return pd.read_excel(arquivo)
        else:
            try:
                return pd.read_excel(arquivo)
            except:
                return pd.read_csv(arquivo, encoding='latin1', sep=';')

    def _converter_moeda_smart(self, valor):
        """Conversão inteligente de moeda."""
        if pd.isna(valor): return 0.0
        s = str(valor).strip()
        if ',' in s:
            s = s.replace('.', '').replace(',', '.')
        try:
            return float(s)
        except ValueError:
            return 0.0

    def _limpar_cst(self, valor):
        if pd.isna(valor): return ""
        # Remove .0 e espaços
        return str(valor).replace('.0', '').strip()

    def processar_dados(self):
        df = self.df.copy()

        # 1. Tratamento de Valores
        cols_existentes = [col for col in self.cols_valores if col in df.columns]
        for col in cols_existentes:
            df[col] = df[col].apply(self._converter_moeda_smart)

        # 2. Tratamento de CST e Natureza
        col_cst_a = 'COD_SITUACAO_A'
        col_cst_b = 'COD_SITUACAO_B'
        
        # Garante colunas de texto limpo para análise
        if col_cst_a in df.columns:
            df[col_cst_a] = df[col_cst_a].apply(self._limpar_cst)
        if col_cst_b in df.columns:
            df[col_cst_b] = df[col_cst_b].apply(self._limpar_cst)
            
        # Cria CST Completo
        cst_a = df[col_cst_a] if col_cst_a in df.columns else ""
        cst_b = df[col_cst_b] if col_cst_b in df.columns else ""
        df['CST_COMPLETO'] = cst_a + cst_b.str.zfill(2)

        # 3. Definição de Tipo (Entrada/Saída)
        col_cfop = 'COD_CFO'
        def definir_tipo(cfop):
            cfop_str = str(cfop)
            if cfop_str.startswith(('1', '2', '3')): return 'ENTRADA'
            elif cfop_str.startswith(('5', '6', '7')): return 'SAIDA'
            else: return 'OUTROS'
        
        if col_cfop in df.columns:
            df['TIPO_OPERACAO'] = df[col_cfop].apply(definir_tipo)
            # Cria coluna auxiliar de CFOP limpo (sem pontos) para comparação
            df['CFOP_LIMPO'] = df[col_cfop].astype(str).str.replace('.', '', regex=False).str.strip()
        else:
            df['TIPO_OPERACAO'] = 'INDEFINIDO'
            df['CFOP_LIMPO'] = ''

        self.df_processado = df
        return df

    def obter_divergencias(self):
        """
        Regra 1: CSTs tributados (00, 10, 20, 70) com ICMS zerado.
        Regra 2: CFOP 5102/6102 com COD_NATUREZA_OP ou COD_SITUACAO_B vazios/nulos.
        """
        if not hasattr(self, 'df_processado'):
            self.processar_dados()
            
        df = self.df_processado
        
        # --- REGRA 1: Validação de Valor de ICMS ---
        saidas = df[df['TIPO_OPERACAO'] == 'SAIDA']
        csts_tributados = ['00', '10', '20', '70']
        
        mask_cst = saidas['CST_COMPLETO'].str[-2:].isin(csts_tributados)
        mask_valor = saidas['VLR_TRIBUTO_ICMS'] <= 0.01 # Margem de segurança para float
        
        div_valor = saidas[mask_cst & mask_valor].copy()
        if not div_valor.empty:
            div_valor['MOTIVO_DIVERGENCIA'] = 'CST Tributado com ICMS Zerado'

        # --- REGRA 2: Validação de Cadastro (5102/6102) ---
        target_cfops = ['5102', '6102']
        
        # Verifica se o CFOP está na lista alvo
        mask_cfop = df['CFOP_LIMPO'].isin(target_cfops)
        
        # Função auxiliar para checar "Vazio" (NaN, None, "", "0", 0)
        def is_empty(series):
            return (series.isna()) | \
                   (series.astype(str).str.strip() == '') | \
                   (series.astype(str).str.strip() == 'nan') | \
                   (series == 0)

        mask_nat = is_empty(df['COD_NATUREZA_OP']) if 'COD_NATUREZA_OP' in df.columns else True
        mask_cst_b = is_empty(df['COD_SITUACAO_B']) if 'COD_SITUACAO_B' in df.columns else True
        
        div_cadastro = df[mask_cfop & (mask_nat | mask_cst_b)].copy()
        if not div_cadastro.empty:
            div_cadastro['MOTIVO_DIVERGENCIA'] = 'CFOP 5102/6102 com Natureza ou CST vazios'

        # Junta as duas listas de problemas
        resultado = pd.concat([div_valor, div_cadastro]).drop_duplicates()
        
        return resultado

    def gerar_excel_consolidado(self):
        """Gera Excel consolidado."""
        if not hasattr(self, 'df_processado'):
            self.processar_dados()
            
        output = io.BytesIO()
        df = self.df_processado
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df[df['TIPO_OPERACAO'] == 'ENTRADA'].to_excel(writer, sheet_name='Entradas', index=False)
            df[df['TIPO_OPERACAO'] == 'SAIDA'].to_excel(writer, sheet_name='Saidas', index=False)
            
            if 'COD_CFO' in df.columns:
                pvt_cfop = df.groupby(['TIPO_OPERACAO', 'COD_CFO'])[self.cols_valores].sum().reset_index()
                pvt_cfop.to_excel(writer, sheet_name='Resumo CFOP', index=False)
            
            pvt_cst = df.groupby(['TIPO_OPERACAO', 'CST_COMPLETO'])[self.cols_valores].sum().reset_index()
            pvt_cst.to_excel(writer, sheet_name='Resumo CST', index=False)
            
            divergencias = self.obter_divergencias()
            if not divergencias.empty:
                divergencias.to_excel(writer, sheet_name='Divergencias', index=False)
            else:
                pd.DataFrame({'Status': ['Tudo OK']}).to_excel(writer, sheet_name='Divergencias', index=False)

        return output.getvalue()
