import tkinter as tk
from tkinter import ttk, messagebox
import datetime
import traceback

# Importa as classes dos CÁLCULOS
# Importa as classes dos CÁLCULOS
from core.solar_calculator import CalculadoraSolar
from core.csv_player import CsvPlayer  # <-- Importação do Player
from core.solar_analyst import SolarAnalyst # <-- Importação do Analista IA

# Importa as classes das PÁGINAS DA INTERFACE
from gui.pages.page_seguidor import PaginaGrafico
from gui.pages.page_irradiancia import PaginaPainel
from gui.pages.page_modelo_fv import PaginaPlantaSolar
from gui.pages.page_potencia import PaginaPotencia
from gui.pages.page_meteorologia import PaginaMeteorologia
from gui.pages.page_previsao import PaginaPrevisao
from gui.pages.page_conversao import PaginaConversao # <--- Import Nova Aba
from gui.pages.page_analise import PaginaAnalise # <--- Import Nova Aba Análise

# --- CONFIGURAÇÃO DE SIMULAÇÃO ---
USA_DADOS_CSV = True  # Altere para True para usar dados do CSV
CAMINHO_ARQUIVO_CSV = r"C:\Users\55829\Downloads\PESSOAIS\MESTRADO\PESQUISA\PROJETO_GEMEO_DIGITAL_SOLAR\DATASET_MESTRE_COMPLETO.csv"


class SolarApp(tk.Tk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title("Gêmeo Digital Solar")
        self.geometry("1300x850") # Ajuste leve para caber melhor os novos gráficos

        # --- DADOS E VARIÁVEIS CENTRALIZADOS ---
        self.solar_object = None
        self.dados_painel = {
            "painel_inclinacao": tk.StringVar(value="10.0"),
            "painel_azimute": tk.StringVar(value="0.0"),
            "irradiancia_ghi": tk.StringVar(value="850"),
            "albedo": tk.StringVar(value="0.2"),
            "tensao_real": tk.StringVar(value="0.0"),   # <--- NOVO
            "corrente_real": tk.StringVar(value="0.0")  # <--- NOVO
        }
        self.dados_usina = {
            'modules_per_string': tk.StringVar(value="10"),
            'strings_in_parallel': tk.StringVar(value="1")
        }
        self.dados_ambientais = {
            'temp_air': tk.StringVar(value="25.0"),
            'wind_speed': tk.StringVar(value="1.0")
        }
        self.dados_datasheet = {
            'v_oc': tk.StringVar(value="39.4"), 'i_sc': tk.StringVar(value="9.09"),
            'v_mp': tk.StringVar(value="31.7"), 'i_mp': tk.StringVar(value="8.52"),
            'alpha_sc': tk.StringVar(value="0.00523"), 'beta_voc': tk.StringVar(value="-0.15438"),
            'gamma_pmp': tk.StringVar(value="-0.38"), 'cells_in_series': tk.StringVar(value="60"),
            'cell_type': tk.StringVar(value='polySi')
        }
        self.entradas_globais = {
            "latitude": tk.StringVar(value="-9.55762188835476"),
            "longitude": tk.StringVar(value="-35.78094625196216"),
            "utc": tk.StringVar(value="-3"), "dia": tk.StringVar(value="17"),
            "mes": tk.StringVar(value="10"), "ano": tk.StringVar(value="2025"),
            "hora": tk.StringVar(value="12"), "minuto": tk.StringVar(value="00"), "segundo": tk.StringVar(value="00")
        }
        self.time_slider_var = tk.IntVar()
        self.day_of_year_slider_var = tk.IntVar()
        self.irradiance_slider_var = tk.DoubleVar()  # <-- NOVA VARIÁVEL GLOBAL

        self.editar_data_var = tk.BooleanVar(value=False)
        self.editar_local_var = tk.BooleanVar(value=False)  # <-- NOVA VARIÁVEL
        self.editar_hora_var = tk.BooleanVar(value=False)
        self.editar_irradiancia_var = tk.BooleanVar(value=False)
        self.editar_painel_var = tk.BooleanVar(value=False)
        self.editar_ambientais_var = tk.BooleanVar(value=False)

        # --- MONTAGEM DA INTERFACE ---
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(side="top", fill="both",
                           expand=True, padx=10, pady=10)

        # Instancia cada página a partir dos arquivos importados
        self.pagina_grafico = PaginaGrafico(self.notebook, self)
        self.pagina_painel = PaginaPainel(self.notebook, self)
        self.pagina_planta_solar = PaginaPlantaSolar(self.notebook, self)
        self.pagina_potencia = PaginaPotencia(self.notebook, self)
        self.pagina_previsao = PaginaPrevisao(self.notebook, self) # Nova aba

        self.pagina_conversao = PaginaConversao(self.notebook, self) # Nova aba Conversão
        self.pagina_analise = PaginaAnalise(self.notebook, self) # Nova aba Análise
        self.pagina_meteorologia = PaginaMeteorologia(self.notebook, self)

        # Adiciona as páginas como abas (Meteorologia é a segunda)
        self.notebook.add(self.pagina_grafico, text="Posição Solar")
        self.notebook.add(self.pagina_meteorologia, text="Meteorologia") # <--- AQUI
        self.notebook.add(self.pagina_painel, text="Irradiância")
        self.notebook.add(self.pagina_potencia, text="Potência")
        self.notebook.add(self.pagina_conversao, text="Conversão") # Nova aba Conversão
        self.notebook.add(self.pagina_planta_solar, text="Curvas de Operação")
        self.notebook.add(self.pagina_previsao, text="Previsão") # Nova aba
        self.notebook.add(self.pagina_analise, text="Análise") # Nova aba Análise
        
        # OTIMIZAÇÃO: Atualizar aba ao mudar o foco (pois paramos de desenhar quando escondida)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # --- INTEGRAÇÃO COM CSV ---
        self.csv_player = None
        if USA_DADOS_CSV:
            try:
                self.csv_player = CsvPlayer(self)
                if self.csv_player.load_csv(CAMINHO_ARQUIVO_CSV):
                    print("CSV carregado. A reprodução iniciará em 15 segundos...")
                    print("CSV carregado. A reprodução iniciará em 15 segundos...")
                    self.after(15000, self.start_csv_playback)
                else:
                    print("Falha ao carregar CSV. Verifique o caminho.")
            except Exception as e:
                print(f"Erro ao iniciar Player CSV: {e}")

        # --- GÊMEO DIGITAL ANALISTA (IA) ---
        self.solar_analyst = SolarAnalyst()
        self.solar_analyst.on_analysis_callback = self._on_new_analysis
        self.last_analysis_time = datetime.datetime.now()

        self._atualizar_em_tempo_real()

    def _atualizar_em_tempo_real(self):
        deve_recalcular = False
        agora = datetime.datetime.now()
        if not self.editar_data_var.get():
            self.entradas_globais["dia"].set(str(agora.day))
            self.entradas_globais["mes"].set(str(agora.month))
            self.entradas_globais["ano"].set(str(agora.year))
            try:
                # Tenta atualizar o slider, mas não falha se a UI ainda não estiver pronta
                self.day_of_year_slider_var.set(agora.timetuple().tm_yday)
            except tk.TclError:
                pass
            deve_recalcular = True

        if not self.editar_hora_var.get():
            self.entradas_globais["hora"].set(f"{agora.hour:02d}")
            self.entradas_globais["minuto"].set(f"{agora.minute:02d}")
            self.entradas_globais["segundo"].set(f"{agora.second:02d}")
            try:
                # Tenta atualizar o slider, mas não falha se a UI ainda não estiver pronta
                self.time_slider_var.set(agora.hour * 60 + agora.minute)
            except tk.TclError:
                pass
            deve_recalcular = True

        if deve_recalcular:
            self.atualizar_calculos_e_telas()
            
        # --- INTEGRAÇÃO ANALISTA IA ---
        try:
            self._feed_solar_analyst()
        except Exception as e:
            print(f"Erro no feed do analista: {e}")

        self.after(1000, self._atualizar_em_tempo_real)

    def _on_new_analysis(self, timestamp, text):
        """Callback chamado pelo SolarAnalyst (em thread separada)"""
        # Agenda atualização na UI (Main Thread)
        self.after(0, lambda: self.pagina_analise.add_log(timestamp, text))

    def _feed_solar_analyst(self):
        # 1. Verificar se o CSV está tocando (Requisito do Usuário)
        if not self.csv_player or not self.csv_player.is_playing:
            return

        # 2. Coletar dados atuais do sistema
        # Se os objetos ainda não foram criados, retorna
        if not self.solar_object:
            return

        try:
            ano = int(self.entradas_globais['ano'].get())
            mes = int(self.entradas_globais['mes'].get())
            dia = int(self.entradas_globais['dia'].get())
            hora = int(self.entradas_globais['hora'].get())
            minuto = int(self.entradas_globais['minuto'].get())
            segundo = int(self.entradas_globais['segundo'].get())
            agora = datetime.datetime(ano, mes, dia, hora, minuto, segundo)
        except Exception:
            agora = datetime.datetime.now()
        
        # Helper para pegar valor float seguramento
        def get_float(tk_var):
            try: return float(tk_var.get())
            except: return 0.0

        # Dados Climáticos (Vem do Controller ou da PaginaMeteorologia se disponivel)
        temp_amb = get_float(self.dados_ambientais['temp_air']) 
        wind_vel = get_float(self.dados_ambientais['wind_speed']) 
        # Se CSV/Meteorologia estiver ativo, pega de lá (já que pode ser diferente do dados_ambientais se não estiver sync)
        # Na verdade, o ideal é pegar exatamente o que está sendo visualizado.
        # Vamos pegar da PaginaMeteorologia se possível para ter chuva e umidade
        if hasattr(self, 'pagina_meteorologia'):
            pm = self.pagina_meteorologia
            temp_painel = get_float(pm.meteo_vars['temp_painel'])
            umidade = get_float(pm.meteo_vars['umidade'])
            vento_dir = get_float(pm.meteo_vars['vento_dir'])
            chuva = get_float(pm.meteo_vars['chuva'])
            # Se a pag meteorologia tiver valores mais atuais de temp/vento, usa eles
            t_amb_meteo = get_float(pm.meteo_vars['temp_amb'])
            v_vel_meteo = get_float(pm.meteo_vars['vento_vel'])
        else:
            temp_painel, umidade, vento_dir, chuva = 0, 0, 0, 0
            t_amb_meteo, v_vel_meteo = temp_amb, wind_vel

        # Dados Elétricos e Métricas (Vêm da PaginaPrevisao)
        pp = self.pagina_previsao
        if not pp: return

        data_snapshot = {
            'timestamp': str(agora),
            
            # Clima
            'irradiancia_ghi': get_float(self.pagina_painel.saidas_irradiancia['GHI_global']),
            'temp_amb': t_amb_meteo,
            'temp_painel': temp_painel,
            'umidade': umidade,
            'vento_vel': v_vel_meteo,
            'vento_dir': vento_dir,
            'chuva': chuva,
            
            # Localização e Configuração
            'latitude': get_float(self.entradas_globais['latitude']),
            'longitude': get_float(self.entradas_globais['longitude']),
            'painel_tilt': get_float(self.dados_painel['painel_inclinacao']),
            'painel_azimute_config': get_float(self.dados_painel['painel_azimute']),
            
            # Sol
            'elevacao': self.solar_object.elevacao,
            'azimute': self.solar_object.azimute,
            
            # Elétricos
            'tensao_real': get_float(self.dados_painel['tensao_real']),
            'corrente_real': get_float(self.dados_painel['corrente_real']),
            'potencia_real': get_float(pp.mpp_outputs['real_p']),
            'potencia_meteo': get_float(pp.mpp_outputs['meteo_p']),
            
            # Métricas (Do modelo Meteo)
            'mse': get_float(pp.mpp_outputs['meteo_mse']),
            'mae': get_float(pp.mpp_outputs['meteo_mae']),
            'mape': float(pp.mpp_outputs['meteo_mape'].get().replace('%','')) if '%' in pp.mpp_outputs['meteo_mape'].get() else 0.0,
            'rmse': get_float(pp.mpp_outputs['meteo_rmse']),
        }

        # 2. Adicionar ao buffer
        self.solar_analyst.add_data_point(data_snapshot)

        # 3. Verificar trigger (a cada 60s)
        # Em simulação acelerada, 1 minuto real? O usuario pediu "1 minuto real".
        if (agora - self.last_analysis_time).total_seconds() >= 60:
            import threading
            self.last_analysis_time = agora
            # Thread para não travar a UI
            threading.Thread(target=self.solar_analyst.analyze, daemon=True).start()

    def atualizar_calculos_e_telas(self):
        try:
            # Converte entradas para os tipos corretos
            hora = int(self.entradas_globais["hora"].get() or 0)
            minuto = int(self.entradas_globais["minuto"].get() or 0)
            segundo = int(self.entradas_globais["segundo"].get() or 0)
            ano = int(self.entradas_globais["ano"].get() or 1)
            mes = int(self.entradas_globais["mes"].get() or 1)
            dia = int(self.entradas_globais["dia"].get() or 1)

            lat = float(self.entradas_globais["latitude"].get())
            lon = float(self.entradas_globais["longitude"].get())
            utc = int(self.entradas_globais["utc"].get())

            data_hora_base = datetime.datetime(
                year=ano, month=mes, day=dia, hour=hora, minute=minuto, second=segundo)

            # --- PONTO CENTRAL DE CÁLCULO ---
            self.solar_object = CalculadoraSolar(
                data_hora=data_hora_base, latitude=lat, longitude=lon, utc=utc)

            # --- ATUALIZAÇÃO EM CASCATA DAS PÁGINAS ---
            self.pagina_grafico.atualizar_interface()
            self.pagina_painel.calcular_e_atualizar_tabela()
            self.pagina_planta_solar.atualizar_modelo_pv()
            self.pagina_potencia.atualizar_modelo_pv()
            self.pagina_conversao.atualizar_conversao() # <--- Atualiza Conversão
            self.pagina_previsao.atualizar_previsao() # Atualiza previsao
            self.pagina_meteorologia.atualizar_meteorologia()

        except (ValueError, AttributeError, tk.TclError):
            pass  # Ignora erros de digitação temporários
        except Exception:
            # traceback.print_exc() # Descomente para depuração detalhada
            pass  # Evita pop-ups de erro contínuos em caso de falha de cálculo


    def reset_all_graphs(self):
        """Reinicia os gráficos de todas as páginas."""
        if hasattr(self, 'pagina_meteorologia'):
            self.pagina_meteorologia.reset_history(confirm=False)
        if hasattr(self, 'pagina_potencia'):
            self.pagina_potencia.reset_history(confirm=False)
        if hasattr(self, 'pagina_previsao'):
            self.pagina_previsao.reset_history(confirm=False)
        if hasattr(self, 'pagina_painel'):
            self.pagina_painel.reset_history(confirm=False)
        if hasattr(self, 'pagina_conversao'):
            self.pagina_conversao.reset_history(confirm=False)
        if hasattr(self, 'pagina_analise'):
            self.pagina_analise.reset_history(confirm=False)

    def start_csv_playback(self):
        print("Iniciando reprodução do CSV agora.")
        try:
            self.reset_all_graphs()
        except Exception as e:
            print(f"Erro ao reiniciar gráficos: {e}")
            traceback.print_exc()
        
        try:
            if self.csv_player:
                self.csv_player.start()
        except Exception as e:
            print(f"Erro ao iniciar player: {e}")

    def _on_tab_changed(self, event):
        """Chamado quando o usuário troca de aba no notebook."""
        try:
            # Identifica qual aba está selecionada
            selected_tab_id = self.notebook.select()
            if not selected_tab_id:
                return
            
            # Mapeia ID do widget (aba) para o objeto da página
            # O .select() retorna o nome do widget interno (ex: .!notebook.!frame2)
            # Precisamos encontrar qual de nossos objetos self.pagina_* corresponde a isso
            
            # Lista de todas as páginas
            pages = [
                self.pagina_grafico, self.pagina_meteorologia, self.pagina_painel,
                self.pagina_potencia, self.pagina_conversao, self.pagina_planta_solar,
                self.pagina_previsao, self.pagina_analise
            ]
            
            for page in pages:
                if str(page) == selected_tab_id:
                    # Força atualização imediata da página selecionada
                    # Verifica qual método de atualização ela tem
                    if hasattr(page, 'atualizar_interface'):
                        page.atualizar_interface()
                    elif hasattr(page, 'atualizar_meteorologia'):
                        page.atualizar_meteorologia()
                    elif hasattr(page, 'calcular_e_atualizar_tabela'):
                        page.calcular_e_atualizar_tabela()
                    elif hasattr(page, 'atualizar_modelo_pv'):
                        page.atualizar_modelo_pv()
                    elif hasattr(page, 'atualizar_conversao'):
                        page.atualizar_conversao()
                    elif hasattr(page, 'atualizar_previsao'):
                        page.atualizar_previsao()
                        
                    # Se tiver grafico historico, força redraw tb
                    if hasattr(page, '_atualizar_grafico_potencia'):
                        page._atualizar_grafico_potencia()
                    if hasattr(page, '_atualizar_grafico_previsao'):
                        page._atualizar_grafico_previsao()
                    if hasattr(page, '_plot_graphs'):
                        page._plot_graphs()
                        
                    break
                    
        except Exception as e:
            print(f"Erro ao trocar aba: {e}")

if __name__ == "__main__":
    app = SolarApp()
    app.mainloop()
