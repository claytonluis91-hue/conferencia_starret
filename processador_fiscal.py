import pandas as pd
import io

class ProcessadorFiscal:
    def __init__(self, arquivo):
        self.df = self._carregar_arquivo(arquivo)
        self.cols_valores = [
            'VLR_CONTAB_ITEM', 'VLR_BASE_ICMS_1', 'VLR_TRIBUTO_ICMS',
            'VLR_PIS', 'VLR_COFINS'
        ]
        # Lista Negativa baseada no Anexo Único do PDF (NCMs proibidos no regime)
        self.ncm_negativos_prefixo = [
            '1701', '2207', '2710', '2905', '0901', '2402', # Açucar, Alcool, Combustivel, Café, Cigarro
            '8701', '8702', '8703', '8704', '8705', '8706', '8716' # Veículos
        ]

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
        if pd.isna(valor): return 0.0
        s = str(valor).strip()
        if ',' in s:
            s = s.replace('.', '').replace(',', '.')
        try:
            return float(s)
        except ValueError:
            return 0.0

    def _limpar_texto(self, valor):
        if pd.isna(valor): return ""
        return str(valor).replace('.0', '').strip()

    def processar_dados(self):
        df = self.df.copy()

        # 1. Tratamento de Valores
        cols_existentes = [col for col in self.cols_valores if col in df.columns]
        for col in cols_existentes:
            df[col] = df[col].apply(self._converter_moeda_smart)

        # 2. Tratamento de CST, Natureza e NCM
        cols_texto = ['COD_SITUACAO_A', 'COD_SITUACAO_B', 'COD_NBM', 'ESTADO_UF_FORNEC']
        for col in cols_texto:
            if col in df.columns:
                df[col] = df[col].apply(self._limpar_texto)
            
        # Cria CST Completo
        cst_a = df['COD_SITUACAO_A'] if 'COD_SITUACAO_A' in df.columns else ""
        cst_b = df['COD_SITUACAO_B'] if 'COD_SITUACAO_B' in df.columns else ""
        df['CST_COMPLETO'] = cst_a + cst_b.str.zfill(2)

        # 3. Definição de Tipo
        col_cfop = 'COD_CFO'
        def definir_tipo(cfop):
            cfop_str = str(cfop)
            if cfop_str.startswith(('1', '2', '3')): return 'ENTRADA'
            elif cfop_str.startswith(('5', '6', '7')): return 'SAIDA'
            else: return 'OUTROS'
        
        if col_cfop in df.columns:
            df['TIPO_OPERACAO'] = df[col_cfop].apply(definir_tipo)
            df['CFOP_LIMPO'] = df[col_cfop].astype(str).str.replace('.', '', regex=False).str.strip()
        else:
            df['TIPO_OPERACAO'] = 'INDEFINIDO'
            df['CFOP_LIMPO'] = ''

        self.df_processado = df
        return df

    def calcular_regime_especial(self):
        """Calcula o ICMS considerando as regras do TTS/Corredor de Importação."""
        if not hasattr(self, 'df_processado'):
            self.processar_dados()
        
        df = self.df_processado.copy()
        
        # Filtra apenas SAÍDAS
        tts = df[df['TIPO_OPERACAO'] == 'SAIDA'].copy()
        
        # Lógica para identificar produtos elegíveis (CST Origem 1, 6 ou 2, 7)
        # Assumindo que o regime é para importados
        if 'COD_SITUACAO_A' in tts.columns:
            tts['ELEGIVEL_TTS'] = tts['COD_SITUACAO_A'].isin(['1', '6', '2', '7'])
        else:
            tts['ELEGIVEL_TTS'] = False

        # Verifica Lista Negativa (NCM)
        if 'COD_NBM' in tts.columns:
            def verifica_negativo(ncm):
                ncm_str = str(ncm).replace('.', '')
                for prefixo in self.ncm_negativos_prefixo:
                    if ncm_str.startswith(prefixo):
                        return False # Está na lista negativa, não é elegível
                return True
            
            tts['NCM_VALIDO'] = tts['COD_NBM'].apply(verifica_negativo)
            tts['ELEGIVEL_TTS'] = tts['ELEGIVEL_TTS'] & tts['NCM_VALIDO']

        # Cálculo do Crédito Presumido
        # Regra Geral (Art 9, I):
        # Interestadual (4%) -> Crédito 2.5%
        # Interna (<=18%) -> Crédito 4%
        # Interna (>18%) -> Crédito 5%
        
        tts['CREDITO_PRESUMIDO_CALC'] = 0.0
        tts['ICMS_EFETIVO_RECOLHER'] = 0.0
        
        # Garante que UF existe, senão assume MG
        uf_col = 'ESTADO_UF_FORNEC'
        if uf_col not in tts.columns:
            tts[uf_col] = 'MG'

        for index, row in tts.iterrows():
            if not row['ELEGIVEL_TTS']:
                # Se não é elegível, o imposto é o débito normal (sem crédito presumido)
                tts.at[index, 'ICMS_EFETIVO_RECOLHER'] = row['VLR_TRIBUTO_ICMS']
                continue

            base = row['VLR_BASE_ICMS_1']
            aliq = row['ALIQ_TRIBUTO_ICMS'] if 'ALIQ_TRIBUTO_ICMS' in tts.columns else 0
            uf = str(row[uf_col]).upper()
            debito = row['VLR_TRIBUTO_ICMS']
            credito_presumido = 0.0

            # Lógica MG (Corredor)
            if uf != 'MG': # Interestadual
                if aliq == 4:
                    credito_presumido = base * 0.025
                # Se for CAMEX (alíquota 12% ou 7% não se aplica aqui pela regra I-a, mas mantemos 0 se não casar)
            else: # Interna MG
                if aliq <= 18:
                    credito_presumido = base * 0.04
                else:
                    credito_presumido = base * 0.05
            
            # Ajuste final
            tts.at[index, 'CREDITO_PRESUMIDO_CALC'] = credito_presumido
            # O imposto a recolher é o Débito da Saída - Crédito Presumido
            # (Lembrando que o crédito da entrada foi estornado/diferido)
            imposto_final = debito - credito_presumido
            tts.at[index, 'ICMS_EFETIVO_RECOLHER'] = imposto_final if imposto_final > 0 else 0

        return tts

    def obter_divergencias(self):
        # (Código Mantido igual ao anterior)
        if not hasattr(self, 'df_processado'): self.processar_dados()
        df = self.df_processado
        saidas = df[df['TIPO_OPERACAO'] == 'SAIDA']
        csts_tributados = ['00', '10', '20', '70']
        mask_cst = saidas['CST_COMPLETO'].str[-2:].isin(csts_tributados)
        mask_valor = saidas['VLR_TRIBUTO_ICMS'] <= 0.01
        div_valor = saidas[mask_cst & mask_valor].copy()
        if not div_valor.empty: div_valor['MOTIVO_DIVERGENCIA'] = 'CST Tributado com ICMS Zerado'
        target_cfops = ['5102', '6102']
        mask_cfop = df['CFOP_LIMPO'].isin(target_cfops)
        def is_empty(series): return (series.isna()) | (series.astype(str).str.strip() == '') | (series == 0)
        mask_nat = is_empty(df['COD_NATUREZA_OP']) if 'COD_NATUREZA_OP' in df.columns else True
        mask_cst_b = is_empty(df['COD_SITUACAO_B']) if 'COD_SITUACAO_B' in df.columns else True
        div_cadastro = df[mask_cfop & (mask_nat | mask_cst_b)].copy()
        if not div_cadastro.empty: div_cadastro['MOTIVO_DIVERGENCIA'] = 'CFOP 5102/6102 com Natureza ou CST vazios'
        return pd.concat([div_valor, div_cadastro]).drop_duplicates()

    def gerar_excel_consolidado(self):
        """Gera Excel com abas de apuração e TTS."""
        if not hasattr(self, 'df_processado'): self.processar_dados()
        
        output = io.BytesIO()
        df = self.df_processado
        
        # Calcula dados do Regime Especial
        df_tts = self.calcular_regime_especial()
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # 1. Dados Brutos
            df[df['TIPO_OPERACAO'] == 'ENTRADA'].to_excel(writer, sheet_name='Entradas', index=False)
            df[df['TIPO_OPERACAO'] == 'SAIDA'].to_excel(writer, sheet_name='Saidas', index=False)
            
            # 2. Apuração ICMS (Normal)
            if 'VLR_TRIBUTO_ICMS' in df.columns:
                resumo_icms = df.groupby(['TIPO_OPERACAO', 'COD_CFO'])[['VLR_TRIBUTO_ICMS']].sum().reset_index()
                creditos = resumo_icms[resumo_icms['TIPO_OPERACAO'] == 'ENTRADA'].rename(columns={'VLR_TRIBUTO_ICMS': 'CREDITO_ICMS'})
                debitos = resumo_icms[resumo_icms['TIPO_OPERACAO'] == 'SAIDA'].rename(columns={'VLR_TRIBUTO_ICMS': 'DEBITO_ICMS'})
                
                sheet_icms = 'Apuracao ICMS Normal'
                writer.book.add_worksheet(sheet_icms)
                ws = writer.sheets[sheet_icms]
                ws.write(0, 0, "CRÉDITOS (ENTRADAS)")
                creditos.to_excel(writer, sheet_name=sheet_icms, startrow=1, index=False)
                row = len(creditos) + 3
                ws.write(row, 0, "DÉBITOS (SAÍDAS)")
                debitos.to_excel(writer, sheet_name=sheet_icms, startrow=row+1, index=False)
                
            # 3. Apuração PIS/COFINS
            cols_pc = [c for c in ['VLR_PIS', 'VLR_COFINS'] if c in df.columns]
            if cols_pc:
                resumo_pc = df.groupby(['TIPO_OPERACAO', 'COD_CFO'])[cols_pc].sum().reset_index()
                sheet_pc = 'Apuracao PIS_COFINS'
                resumo_pc.to_excel(writer, sheet_name=sheet_pc, index=False)

            # 4. NOVA ABA: Apuração TTS (Regime Especial)
            # Filtra apenas colunas relevantes para o relatório
            cols_tts = ['COD_CFO', 'DATA_FISCAL', 'NUM_DOCFIS', 'RAZAO_SOCIAL', 'COD_NBM', 'CST_COMPLETO', 
                        'ESTADO_UF_FORNEC', 'VLR_CONTAB_ITEM', 'VLR_BASE_ICMS_1', 'ALIQ_TRIBUTO_ICMS',
                        'VLR_TRIBUTO_ICMS', 'ELEGIVEL_TTS', 'CREDITO_PRESUMIDO_CALC', 'ICMS_EFETIVO_RECOLHER']
            cols_tts_existentes = [c for c in cols_tts if c in df_tts.columns]
            
            df_tts_final = df_tts[cols_tts_existentes]
            
            sheet_tts = 'Apuracao TTS (Regime Esp)'
            writer.book.add_worksheet(sheet_tts)
            ws_tts = writer.sheets[sheet_tts]
            
            ws_tts.write(0, 0, "DEMONSTRATIVO DE CÁLCULO - REGIME ESPECIAL (TTS - CORREDOR IMPORTAÇÃO)")
            ws_tts.write(1, 0, "Filtros aplicados: Produtos Importados (CST 1/6) e fora da Lista Negativa.")
            
            df_tts_final.to_excel(writer, sheet_name=sheet_tts, startrow=3, index=False)
            
            # Resumo do TTS
            total_debito_tts = df_tts[df_tts['ELEGIVEL_TTS']]['VLR_TRIBUTO_ICMS'].sum()
            total_credito_presumido = df_tts['CREDITO_PRESUMIDO_CALC'].sum()
            total_a_pagar = df_tts[df_tts['ELEGIVEL_TTS']]['ICMS_EFETIVO_RECOLHER'].sum()
            
            resumo_tts = pd.DataFrame({
                'CONCEITO': ['DÉBITO SAÍDAS (Elegíveis)', '(-) CRÉDITO PRESUMIDO', '(=) ICMS A RECOLHER (TTS)'],
                'VALOR': [total_debito_tts, total_credito_presumido, total_a_pagar]
            })
            
            ws_tts.write(3, len(cols_tts_existentes) + 2, "RESUMO APURAÇÃO TTS")
            resumo_tts.to_excel(writer, sheet_name=sheet_tts, startrow=4, startcol=len(cols_tts_existentes) + 2, index=False)

            # 5. Divergências
            divergencias = self.obter_divergencias()
            if not divergencias.empty:
                divergencias.to_excel(writer, sheet_name='Divergencias', index=False)

        return output.getvalue()
