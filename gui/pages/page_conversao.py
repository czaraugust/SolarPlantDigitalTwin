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
            'timestamps': [],
            'csv_irr': [],
            'csv_irr': [],
            'real_p': []
        }
        
        # Variáveis para exibição numérica
        self.str_irr = tk.StringVar(value="0.0")
        self.str_power = tk.StringVar(value="0.0")
        
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

        # Frame de Métricas (Ao lado do botão limpar)
        metrics_frame = ttk.Frame(top_frame)
        metrics_frame.pack(side="right", padx=10)

        # Irradiância
        ttk.Label(metrics_frame, text="Irradiância (W/m²):", font=('TkDefaultFont', 9, 'bold')).pack(side="left", padx=(0, 5))
        ttk.Label(metrics_frame, textvariable=self.str_irr, font=('TkDefaultFont', 9), width=8, relief="sunken", anchor="center").pack(side="left", padx=(0, 15))

        # Potência
        ttk.Label(metrics_frame, text="Potência (W):", font=('TkDefaultFont', 9, 'bold')).pack(side="left", padx=(0, 5))
        ttk.Label(metrics_frame, textvariable=self.str_power, font=('TkDefaultFont', 9), width=8, relief="sunken", anchor="center").pack(side="left")
        
        # Container do Gráfico
        graph_frame = ttk.LabelFrame(
            main_frame, text="Conversão: Irradiância x Potência", padding=10)
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
        self.ax_irr.set_ylabel("Irradiância Global (W/m²)", color='orange')
        self.ax_power.set_ylabel("Potência Real (W)", color='green')
        
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

            # Coleta Irradiância Global (CSV)
            irr_csv_str = self.controller.dados_painel['irradiancia_ghi'].get()
            irr_csv = float(irr_csv_str) if irr_csv_str else 0.0
            
            # Coleta Dados Reais (Tensão e Corrente) para Potência Real (Dual String)
            try:
                v_real = float(self.controller.dados_painel['tensao_real'].get() or 0)
                i_real = float(self.controller.dados_painel['corrente_real'].get() or 0)
                
                v_real_s2 = float(self.controller.dados_painel['tensao_real_s2'].get() or 0)
                i_real_s2 = float(self.controller.dados_painel['corrente_real_s2'].get() or 0)
                
                p_real = (v_real * i_real) + (v_real_s2 * i_real_s2)
            except ValueError:
                p_real = 0.0

            # Atualiza display numérico
            self.str_irr.set(f"{irr_csv:.1f}")
            self.str_power.set(f"{p_real:.1f}")

            # Adiciona ao histórico

            # Adiciona ao histórico
            self.trail_data['timestamps'].append(solar.data_hora)
            self.trail_data['csv_irr'].append(irr_csv)
            self.trail_data['real_p'].append(p_real)
            
            self._atualizar_grafico()
            
        except Exception:
            traceback.print_exc()

    def _atualizar_grafico(self):
        self.ax_irr.clear()
        self.ax_power.clear()
        
        # Re-configura labels já que o clear() limpa tudo
        self._configurar_eixos()

        timestamps = self.trail_data['timestamps']
        timestamps = self.trail_data['timestamps']
        irradiances = self.trail_data['csv_irr']
        powers_real = self.trail_data['real_p']
        
        if timestamps:
            # Plot Irradiância (Eixo Esquerdo) - Laranja
            line1, = self.ax_irr.plot(
                timestamps, irradiances, color='orange', label="Irradiância Real", linewidth=1.5)
            
            # Plot Potência Real (Eixo Direito) - Verde
            line2, = self.ax_power.plot(
                timestamps, powers_real, color='green', label="Potência Real", linewidth=1.5)
            
            # Formatação de Data no Eixo X
            self.ax_irr.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            self.fig.autofmt_xdate()
            
            # Legenda Unificada
            lines = [line1, line2]
            labels = [l.get_label() for l in lines]
            self.ax_irr.legend(lines, labels, loc='upper left')

        self.canvas.draw()

    def reset_history_ask(self):
        if messagebox.askyesno("Confirmar Reinicialização", "Deseja reiniciar o gráfico de conversão?"):
            self.reset_history(confirm=False)

    def reset_history(self, confirm=False):
        # O argumento confirm é mantido para compatibilidade com a assinatura do app.py se necessário
        self.trail_data = {
            'timestamps': [],
            'csv_irr': [],
            'real_p': []
        }
        self._atualizar_grafico()