import pandas as pd
import io

class ProcessadorFiscal:
    def __init__(self, arquivo):
        self.df = self._carregar_arquivo(arquivo)
        # Adicionei PIS e COFINS na lista de colunas para limpar
        self.cols_valores = [
            'VLR_CONTAB_ITEM', 'VLR_BASE_ICMS_1', 'VLR_TRIBUTO_ICMS',
            'VLR_PIS', 'VLR_COFINS'
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
        return str(valor).replace('.0', '').strip()

    def processar_dados(self):
        df = self.df.copy()

        # 1. Tratamento de Valores
        # Filtra apenas colunas que existem no arquivo para evitar erro
        cols_existentes = [col for col in self.cols_valores if col in df.columns]
        for col in cols_existentes:
            df[col] = df[col].apply(self._converter_moeda_smart)

        # 2. Tratamento de CST e Natureza
        col_cst_a = 'COD_SITUACAO_A'
        col_cst_b = 'COD_SITUACAO_B'
        
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
            df['CFOP_LIMPO'] = df[col_cfop].astype(str).str.replace('.', '', regex=False).str.strip()
        else:
            df['TIPO_OPERACAO'] = 'INDEFINIDO'
            df['CFOP_LIMPO'] = ''

        self.df_processado = df
        return df

    def obter_divergencias(self):
        """Regras de validação de negócio."""
        if not hasattr(self, 'df_processado'):
            self.processar_dados()
        df = self.df_processado
        
        # Regra 1: CST Tributado sem ICMS
        saidas = df[df['TIPO_OPERACAO'] == 'SAIDA']
        csts_tributados = ['00', '10', '20', '70']
        mask_cst = saidas['CST_COMPLETO'].str[-2:].isin(csts_tributados)
        mask_valor = saidas['VLR_TRIBUTO_ICMS'] <= 0.01
        div_valor = saidas[mask_cst & mask_valor].copy()
        if not div_valor.empty:
            div_valor['MOTIVO_DIVERGENCIA'] = 'CST Tributado com ICMS Zerado'

        # Regra 2: Cadastro incompleto em 5102/6102
        target_cfops = ['5102', '6102']
        mask_cfop = df['CFOP_LIMPO'].isin(target_cfops)
        def is_empty(series):
            return (series.isna()) | (series.astype(str).str.strip() == '') | (series == 0)

        mask_nat = is_empty(df['COD_NATUREZA_OP']) if 'COD_NATUREZA_OP' in df.columns else True
        mask_cst_b = is_empty(df['COD_SITUACAO_B']) if 'COD_SITUACAO_B' in df.columns else True
        div_cadastro = df[mask_cfop & (mask_nat | mask_cst_b)].copy()
        if not div_cadastro.empty:
            div_cadastro['MOTIVO_DIVERGENCIA'] = 'CFOP 5102/6102 com Natureza ou CST vazios'

        return pd.concat([div_valor, div_cadastro]).drop_duplicates()

    def gerar_excel_consolidado(self):
        """Gera Excel com abas de apuração."""
        if not hasattr(self, 'df_processado'):
            self.processar_dados()
            
        output = io.BytesIO()
        df = self.df_processado
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Abas Básicas
            df[df['TIPO_OPERACAO'] == 'ENTRADA'].to_excel(writer, sheet_name='Entradas', index=False)
            df[df['TIPO_OPERACAO'] == 'SAIDA'].to_excel(writer, sheet_name='Saidas', index=False)
            
            # --- NOVA ABA: APURAÇÃO ICMS ---
            # Agrupa por CFOP e Tipo
            if 'VLR_TRIBUTO_ICMS' in df.columns:
                resumo_icms = df.groupby(['TIPO_OPERACAO', 'COD_CFO'])[['VLR_TRIBUTO_ICMS']].sum().reset_index()
                
                # Separa em Créditos e Débitos
                creditos = resumo_icms[resumo_icms['TIPO_OPERACAO'] == 'ENTRADA'].rename(columns={'VLR_TRIBUTO_ICMS': 'CREDITO_ICMS'})
                debitos = resumo_icms[resumo_icms['TIPO_OPERACAO'] == 'SAIDA'].rename(columns={'VLR_TRIBUTO_ICMS': 'DEBITO_ICMS'})
                
                # Totais
                total_credito = creditos['CREDITO_ICMS'].sum()
                total_debito = debitos['DEBITO_ICMS'].sum()
                saldo = total_debito - total_credito
                status = "A RECOLHER" if saldo > 0 else "SALDO CREDOR"

                # Escreve no Excel em blocos
                sheet_icms = 'Apuracao ICMS'
                row = 0
                writer.book.add_worksheet(sheet_icms)
                worksheet = writer.sheets[sheet_icms]
                
                worksheet.write(row, 0, "DEMONSTRATIVO DE CRÉDITOS (ENTRADAS)")
                row += 1
                creditos.to_excel(writer, sheet_name=sheet_icms, startrow=row, index=False)
                row += len(creditos) + 3 # Pula linhas
                
                worksheet.write(row, 0, "DEMONSTRATIVO DE DÉBITOS (SAÍDAS)")
                row += 1
                debitos.to_excel(writer, sheet_name=sheet_icms, startrow=row, index=False)
                row += len(debitos) + 3
                
                # Tabela Resumo Final
                resumo_final = pd.DataFrame({
                    'CONCEITO': ['TOTAL DÉBITOS', 'TOTAL CRÉDITOS', f'SALDO ({status})'],
                    'VALOR': [total_debito, total_credito, abs(saldo)]
                })
                worksheet.write(row, 0, "RESUMO FINAL DA APURAÇÃO")
                resumo_final.to_excel(writer, sheet_name=sheet_icms, startrow=row+1, index=False)

            # --- NOVA ABA: APURAÇÃO PIS/COFINS ---
            cols_pc = [c for c in ['VLR_PIS', 'VLR_COFINS'] if c in df.columns]
            if cols_pc:
                resumo_pc = df.groupby(['TIPO_OPERACAO', 'COD_CFO'])[cols_pc].sum().reset_index()
                
                # Créditos
                cred_pc = resumo_pc[resumo_pc['TIPO_OPERACAO'] == 'ENTRADA'].copy()
                cred_pc['TOTAL_CREDITO'] = cred_pc[cols_pc].sum(axis=1)
                
                # Débitos
                deb_pc = resumo_pc[resumo_pc['TIPO_OPERACAO'] == 'SAIDA'].copy()
                deb_pc['TOTAL_DEBITO'] = deb_pc[cols_pc].sum(axis=1)
                
                sheet_pc = 'Apuracao PIS_COFINS'
                row = 0
                writer.book.add_worksheet(sheet_pc)
                worksheet_pc = writer.sheets[sheet_pc]
                
                worksheet_pc.write(row, 0, "CRÉDITOS PIS/COFINS (ENTRADAS)")
                cred_pc.to_excel(writer, sheet_name=sheet_pc, startrow=row+1, index=False)
                row += len(cred_pc) + 4
                
                worksheet_pc.write(row, 0, "DÉBITOS PIS/COFINS (SAÍDAS)")
                deb_pc.to_excel(writer, sheet_name=sheet_pc, startrow=row+1, index=False)
                row += len(deb_pc) + 4
                
                # Resumo
                tot_cred_pis = cred_pc['VLR_PIS'].sum() if 'VLR_PIS' in cred_pc else 0
                tot_cred_cof = cred_pc['VLR_COFINS'].sum() if 'VLR_COFINS' in cred_pc else 0
                tot_deb_pis = deb_pc['VLR_PIS'].sum() if 'VLR_PIS' in deb_pc else 0
                tot_deb_cof = deb_pc['VLR_COFINS'].sum() if 'VLR_COFINS' in deb_pc else 0
                
                resumo_final_pc = pd.DataFrame({
                    'TRIBUTO': ['PIS', 'COFINS'],
                    'TOTAL DÉBITOS': [tot_deb_pis, tot_deb_cof],
                    'TOTAL CRÉDITOS': [tot_cred_pis, tot_cred_cof],
                    'SALDO': [tot_deb_pis - tot_cred_pis, tot_deb_cof - tot_cred_cof]
                })
                worksheet_pc.write(row, 0, "RESUMO CONSOLIDADO")
                resumo_final_pc.to_excel(writer, sheet_name=sheet_pc, startrow=row+1, index=False)

            # Abas antigas de resumo (mantive pois são úteis)
            if 'COD_CFO' in df.columns:
                pvt_cfop = df.groupby(['TIPO_OPERACAO', 'COD_CFO'])[self.cols_valores].sum().reset_index()
                pvt_cfop.to_excel(writer, sheet_name='Resumo Geral CFOP', index=False)
            
            divergencias = self.obter_divergencias()
            if not divergencias.empty:
                divergencias.to_excel(writer, sheet_name='Divergencias', index=False)
            else:
                pd.DataFrame({'Status': ['Tudo OK']}).to_excel(writer, sheet_name='Divergencias', index=False)

        return output.getvalue()
