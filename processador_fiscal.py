import pandas as pd
import io

class ProcessadorFiscal:
    def __init__(self, arquivo):
        self.df = self._carregar_arquivo(arquivo)
        self.cols_valores = ['VLR_CONTAB_ITEM', 'VLR_BASE_ICMS_1', 'VLR_TRIBUTO_ICMS']

    def _carregar_arquivo(self, arquivo):
        """Carrega CSV ou Excel e retorna DataFrame bruto."""
        # Se for string (caminho do arquivo) ou objeto de arquivo (buffer)
        if hasattr(arquivo, 'name') and arquivo.name.endswith('.csv'):
            try:
                return pd.read_csv(arquivo, encoding='latin1', sep=',')
            except:
                arquivo.seek(0)
                return pd.read_csv(arquivo, encoding='latin1', sep=';')
        elif hasattr(arquivo, 'name'): 
            # É um arquivo Excel carregado pelo Streamlit
            return pd.read_excel(arquivo)
        else:
            # Fallback caso seja passado de outra forma (ex: testes locais)
            try:
                return pd.read_excel(arquivo)
            except:
                return pd.read_csv(arquivo, encoding='latin1', sep=';')

    def _converter_moeda_smart(self, valor):
        """Conversão inteligente de moeda (Brasileiro/Internacional)."""
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
        return str(valor).replace('.0', '').strip()

    def processar_dados(self):
        """Executa todas as transformações e regras de negócio."""
        df = self.df.copy()

        # 1. Tratamento de Valores
        cols_existentes = [col for col in self.cols_valores if col in df.columns]
        for col in cols_existentes:
            df[col] = df[col].apply(self._converter_moeda_smart)

        # 2. Tratamento de CST
        col_cst_a = 'COD_SITUACAO_A'
        col_cst_b = 'COD_SITUACAO_B'
        
        # Garante que as colunas existem antes de tentar acessar
        if col_cst_a in df.columns and col_cst_b in df.columns:
            df['CST_COMPLETO'] = df[col_cst_a].apply(self._limpar_cst) + \
                                 df[col_cst_b].apply(self._limpar_cst).str.zfill(2)
        else:
             df['CST_COMPLETO'] = '000' # Fallback para evitar erro se coluna não existir

        # 3. Definição de Tipo (Entrada/Saída)
        col_cfop = 'COD_CFO'
        def definir_tipo(cfop):
            cfop_str = str(cfop)
            if cfop_str.startswith(('1', '2', '3')): return 'ENTRADA'
            elif cfop_str.startswith(('5', '6', '7')): return 'SAIDA'
            else: return 'OUTROS'
        
        if col_cfop in df.columns:
            df['TIPO_OPERACAO'] = df[col_cfop].apply(definir_tipo)
        else:
            df['TIPO_OPERACAO'] = 'INDEFINIDO'

        self.df_processado = df
        return df

    def obter_divergencias(self):
        """
        Regra: CSTs que terminam em 00, 10, 20, 70 (Tributados)
        Mas que possuem Valor de ICMS zerado nas SAÍDAS.
        """
        if not hasattr(self, 'df_processado'):
            self.processar_dados()
            
        df = self.df_processado
        
        # Filtra apenas saídas
        saidas = df[df['TIPO_OPERACAO'] == 'SAIDA']
        
        # Lista de finais de CST que deveriam ter destaque
        csts_tributados = ['00', '10', '20', '70']
        
        # Lógica: CST termina com um dos tributados E valor icms <= 0
        mask_cst = saidas['CST_COMPLETO'].str[-2:].isin(csts_tributados)
        mask_valor = saidas['VLR_TRIBUTO_ICMS'] <= 0
        
        return saidas[mask_cst & mask_valor]

    def gerar_excel_consolidado(self):
        """Gera um arquivo Excel binário com múltiplas abas."""
        if not hasattr(self, 'df_processado'):
            self.processar_dados()
            
        output = io.BytesIO()
        df = self.df_processado
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Abas
            df[df['TIPO_OPERACAO'] == 'ENTRADA'].to_excel(writer, sheet_name='Entradas', index=False)
            df[df['TIPO_OPERACAO'] == 'SAIDA'].to_excel(writer, sheet_name='Saidas', index=False)
            
            # Resumos
            if 'COD_CFO' in df.columns:
                pvt_cfop = df.groupby(['TIPO_OPERACAO', 'COD_CFO'])[self.cols_valores].sum().reset_index()
                pvt_cfop.to_excel(writer, sheet_name='Resumo CFOP', index=False)
            
            pvt_cst = df.groupby(['TIPO_OPERACAO', 'CST_COMPLETO'])[self.cols_valores].sum().reset_index()
            pvt_cst.to_excel(writer, sheet_name='Resumo CST', index=False)
            
            # Divergências
            divergencias = self.obter_divergencias()
            if not divergencias.empty:
                divergencias.to_excel(writer, sheet_name='Divergencias ICMS', index=False)
            else:
                pd.DataFrame({'Status': ['Nenhuma divergência encontrada']}).to_excel(writer, sheet_name='Divergencias ICMS', index=False)

        return output.getvalue()
