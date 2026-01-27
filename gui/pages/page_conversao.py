import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates
import traceback

class PaginaConversao(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        
        # Armazena os dados do traço (histórico)
        self.trail_data = {
            'timestamps': [],
            'fixo_irr': [],
            'fixo_p': []
        }
        
        self._criar_widgets()
        
    def _criar_widgets(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Título / Controles simpres
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill="x", pady=(0, 10))
        
        btn_limpar = ttk.Button(
            top_frame, text="Reiniciar Gráfico", command=self.reset_history_ask)
        btn_limpar.pack(side="left")
        
        # Container do Gráfico
        graph_frame = ttk.LabelFrame(
            main_frame, text="Conversão: Irradiância x Potência (Painel Fixo)", padding=10)
        graph_frame.pack(fill="both", expand=True)

        self.fig = Figure(dpi=100)
        self.ax_irr = self.fig.add_subplot(111)
        self.ax_power = self.ax_irr.twinx() # Eixo Y secundário
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        
        # Config inicial dos eixos
        self._configurar_eixos()

    def _configurar_eixos(self):
        self.ax_irr.set_xlabel("Hora")
        self.ax_irr.set_ylabel("Irradiância (W/m²)", color='orange')
        self.ax_power.set_ylabel("Potência (W)", color='green')
        
        self.ax_irr.tick_params(axis='y', labelcolor='orange')
        self.ax_power.tick_params(axis='y', labelcolor='green')
        
        self.ax_irr.grid(True, linestyle='--', linewidth=0.5)

    def atualizar_conversao(self):
        """
        Coleta dados das outras páginas (Irradiância e Potência) e atualiza o gráfico.
        Deve ser chamado APÓS as outras páginas terem atualizado seus cálculos.
        """
        try:
            solar = self.controller.solar_object
            if not solar:
                return

            # Coleta Irradiância do Painel Fixo (POA)
            # A variável está em PaginaPainel.saidas_irradiancia
            irr_fixo_str = self.controller.pagina_painel.saidas_irradiancia['POA_fixo_global'].get()
            irr_fixo = float(irr_fixo_str) if irr_fixo_str else 0.0
            
            # Coleta Potência do Painel Fixo
            # A variável está em PaginaPotencia.mpp_outputs
            p_fixo_str = self.controller.pagina_potencia.mpp_outputs['fixo_p'].get()
            p_fixo = float(p_fixo_str) if p_fixo_str else 0.0

            # Adiciona ao histórico
            self.trail_data['timestamps'].append(solar.data_hora)
            self.trail_data['fixo_irr'].append(irr_fixo)
            self.trail_data['fixo_p'].append(p_fixo)
            
            self._atualizar_grafico()
            
        except Exception:
            traceback.print_exc()

    def _atualizar_grafico(self):
        self.ax_irr.clear()
        self.ax_power.clear()
        
        # Re-configura labels já que o clear() limpa tudo
        self._configurar_eixos()

        timestamps = self.trail_data['timestamps']
        irradiances = self.trail_data['fixo_irr']
        powers = self.trail_data['fixo_p']
        
        if timestamps:
            # Plot Irradiância (Eixo Esquerdo) - Laranja
            line1, = self.ax_irr.plot(
                timestamps, irradiances, color='orange', label="Irradiância (Fixo)")
            
            # Plot Potência (Eixo Direito) - Verde
            line2, = self.ax_power.plot(
                timestamps, powers, color='green', label="Potência (Fixo)")
            
            # Formatação de Data no Eixo X
            self.ax_irr.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            self.fig.autofmt_xdate()
            
            # Legenda Unificada (opcional, mas bom pra clareza)
            # lines = [line1, line2]
            # labels = [l.get_label() for l in lines]
            # self.ax_irr.legend(lines, labels, loc='upper left')

        self.canvas.draw()

    def reset_history_ask(self):
        if messagebox.askyesno("Confirmar Reinicialização", "Deseja reiniciar o gráfico de conversão?"):
            self.reset_history(confirm=False)

    def reset_history(self, confirm=False):
        # O argumento confirm é mantido para compatibilidade com a assinatura do app.py se necessário
        self.trail_data = {
            'timestamps': [],
            'fixo_irr': [],
            'fixo_p': []
        }
        self._atualizar_grafico()
