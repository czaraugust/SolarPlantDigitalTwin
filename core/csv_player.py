import pandas as pd
import datetime
import threading
import time

class CsvPlayer:
    def __init__(self, app_controller):
        """
        Inicializa o player de CSV.
        :param app_controller: Referência para a instância principal do SolarApp.
        """
        self.app = app_controller
        self.df = None
        self.is_playing = False
        self.current_index = 0
        self.playback_speed = 1 # 1 segundo real = 1 passo do CSV
        self.step_size = 1# Pula N linhas por vez para aliviar a CPU (Sampling)
        self.thread = None
        self.stop_event = threading.Event()

    def load_csv(self, filepath):
        """
        Carrega o arquivo CSV e prepara os dados.
        """
        try:
            # Lê o CSV. Assume separador vírgula ou ponto-e-vírgula (ajustar conforme necessidade)
            # Baseado na imagem, parece ser um CSV padrão.
            self.df = pd.read_csv(filepath)
            
            # Garante que as colunas de data e hora sejam strings para concatenação
            # Ajuste os nomes das colunas conforme o CSV real (baseado na imagem)
            # Colunas esperadas: 'Date', 'Time', 'Amb. Temperature', 'Humidity', 'Irradiance', 
            # 'Wind Speed', 'Wind Direction', 'Rain', 'PV Temperature'
            
            # Limpeza básica se necessário
            self.df['Date'] = self.df['Date'].astype(str)
            self.df['Time'] = self.df['Time'].astype(str)

            # --- FILTRO DE HORÁRIO (05:00 - 18:00) ---
            # Mantém apenas registros entre 05h e 18h
            self.df = self.df[
                (self.df['Time'] >= "08:00:00") & 
                (self.df['Time'] <= "16:00:00")
            ]
            
            # Reseta o índice
            self.df = self.df.reset_index(drop=True)
            self.current_index = 0
            print(f"CSV carregado e filtrado (08:00-16:00): {len(self.df)} registros.")
            return True
        except Exception as e:
            print(f"Erro ao carregar CSV: {e}")
            return False

    def start(self):
        """Inicia a simulação em uma thread separada."""
        if self.df is None:
            print("Nenhum CSV carregado.")
            return

        if not self.is_playing:
            self.is_playing = True
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()

    def pause(self):
        """Pausa a simulação."""
        self.is_playing = False

    def stop(self):
        """Para a simulação e reseta o índice."""
        self.is_playing = False
        self.stop_event.set()
        self.current_index = 0

    def _run_loop(self):
        """Loop principal da simulação."""
        while not self.stop_event.is_set() and self.is_playing:
            if self.current_index >= len(self.df):
                self.is_playing = False
                print("Fim do arquivo CSV.")
                break

            # Pega a linha atual
            row = self.df.iloc[self.current_index]
            
            # Atualiza o Gêmeo Digital na Thread Principal (usando after se necessário para thread-safety no Tkinter,
            # mas como estamos apenas setando Var(), geralmente é ok, ou usamos app.after)
            # Para segurança, vamos agendar a atualização na thread da UI
            self.app.after(0, lambda: self._update_app_state(row))

            # Incrementa índice pulando linhas (Sampling)
            self.current_index += self.step_size
            
            # Print de progresso (a cada 10 iterações do loop)
            if (self.current_index / self.step_size) % 10 == 0:
                print(f"Processando índice {self.current_index}/{len(self.df)} -> {row['Date']} {row['Time']}")
            
            # Controle de velocidade (simulação de 1 passo por x tempo)
            time.sleep(1.0 / self.playback_speed)

    def _update_app_state(self, row):
        """Atualiza as variáveis do aplicativo com os dados da linha atual."""
        try:
            # 1. Atualiza Data e Hora
            date_str = row['Date'] # Ex: 2021-02-27
            time_str = row['Time'] # Ex: 00:00:00
            
            # Parse data
            dt_full = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
            
            # Importante: Desabilitar a atualização automática de tempo do app ("Edit Mode")
            self.app.editar_data_var.set(True)
            self.app.editar_hora_var.set(True)

            self.app.entradas_globais['dia'].set(str(dt_full.day))
            self.app.entradas_globais['mes'].set(str(dt_full.month))
            self.app.entradas_globais['ano'].set(str(dt_full.year))
            
            self.app.entradas_globais['hora'].set(f"{dt_full.hour:02d}")
            self.app.entradas_globais['minuto'].set(f"{dt_full.minute:02d}")
            self.app.entradas_globais['segundo'].set(f"{dt_full.second:02d}")

            # 2. Atualiza Meteorologia
            # Mapeamento: 'Amb. Temperature', 'Humidity', 'Wind Speed', 'Wind Direction', 'Rain', 'PV Temperature'
            if hasattr(self.app, 'pagina_meteorologia'):
                page = self.app.pagina_meteorologia
                
                # Ativa modo de edição manual para todos os sliders
                if hasattr(page, 'meteo_checks'):
                    for var_name, bool_var in page.meteo_checks.items():
                        bool_var.set(True)
                        # Força atualização visual do estado (habilitado/desabilitado)
                        # A callback do trace_add ou command pode não disparar se setarmos a Var diretamente
                        # sem passar pelo clique, mas vamos tentar. 
                        # Se não funcionar visualmente, ao menos não crasha.
                        # update: page._toggle_slider_state é chamado pelo checkbutton command.
                        # Precisamos chamar manualmente se quisermos garantir.
                        if hasattr(page, 'meteo_widgets'):
                            # Encontrar o widget correspondente é chato pois meteo_widgets é lista
                            # Mas page._toggle_slider_state requer (key, widget).
                            # Vamos simplificar: Apenas setar o valor. O slider ficar visualmente desabilitado
                            # não impede a atualização da variável subjacente.
                            pass

                # Atualiza as variáveis
                # CSV usage:
                # Amb. Temperature -> temp_amb
                # Humidity -> umidade
                # Wind Speed -> vento_vel
                # Wind Direction -> vento_dir
                # Rain -> chuva
                # PV Temperature -> temp_painel
                
                if 'Amb. Temperature' in row: page.meteo_vars['temp_amb'].set(str(row['Amb. Temperature']))
                if 'Humidity' in row: page.meteo_vars['umidade'].set(str(row['Humidity']))
                if 'Wind Speed' in row: page.meteo_vars['vento_vel'].set(str(row['Wind Speed']))
                if 'Wind Direction' in row: page.meteo_vars['vento_dir'].set(str(row['Wind Direction']))
                if 'Rain' in row: page.meteo_vars['chuva'].set(str(row['Rain']))
                if 'PV Temperature' in row: page.meteo_vars['temp_painel'].set(str(row['PV Temperature']))

            # 3. Atualiza Irradiância Global
            # Coluna 'Irradiance' -> app.dados_painel['irradiancia_ghi'] (ou slider global se houver)
            # O app usa entradas_globais ou dados_painel? App tem self.dados_painel['irradiancia_ghi']
            if 'Irradiance' in row:
                self.app.dados_painel['irradiancia_ghi'].set(str(row['Irradiance']))
                # Se tivermos um controle de 'editar irradiancia', ativamos
                self.app.editar_irradiancia_var.set(True)

            # 4. Atualiza Dados Reais (Tensão e Corrente)
            # String 1
            if 'Voltage S1' in row:
                self.app.dados_painel['tensao_real'].set(str(row['Voltage S1']))
            if 'Current S1' in row:
                self.app.dados_painel['corrente_real'].set(str(row['Current S1']))
            
            # String 2
            if 'Voltage S2' in row:
                self.app.dados_painel['tensao_real_s2'].set(str(row['Voltage S2']))
            if 'Current S2' in row:
                self.app.dados_painel['corrente_real_s2'].set(str(row['Current S2']))

            # Inversor (AC Power)
            if 'Power' in row:
                self.app.dados_painel['potencia_ac'].set(str(row['Power']))

            # Força atualização dos cálculos
            if 'Current S2' in row:
                self.app.dados_painel['corrente_real_s2'].set(str(row['Current S2']))

            # Força atualização dos cálculos
            self.app.atualizar_calculos_e_telas()

        except Exception as e:
            print(f"Erro ao atualizar estado do app: {e}")
