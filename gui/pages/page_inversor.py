import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates
import traceback

class PaginaInversor(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        
        # Armazena os dados do traço (histórico)
        self.trail_data = {
            'timestamps': [],
            'p_dc_s1': [],
            'p_dc_s2': [],
            'p_dc_total': [],
            'p_ac': []
        }
        
        # Variáveis para exibição numérica
        self.str_p_s1 = tk.StringVar(value="0.0")
        self.str_p_s2 = tk.StringVar(value="0.0")
        self.str_p_total = tk.StringVar(value="0.0")
        self.str_p_ac = tk.StringVar(value="0.0")
        self.str_eff = tk.StringVar(value="0.0%")
        
        self._criar_widgets()
        
    def _criar_widgets(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Título / Controles
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill="x", pady=(0, 10))
        
        btn_limpar = ttk.Button(
            top_frame, text="Reiniciar Monitor", command=self.reset_history_ask)
        btn_limpar.pack(side="left")
        
        # Frame de Métricas
        metrics_frame = ttk.Frame(top_frame)
        metrics_frame.pack(side="right", padx=10)

        # Potência String 1
        ttk.Label(metrics_frame, text="S1 (DC) [W]:", font=('TkDefaultFont', 9, 'bold')).pack(side="left", padx=(0, 5))
        ttk.Label(metrics_frame, textvariable=self.str_p_s1, font=('TkDefaultFont', 9), width=8, relief="sunken", anchor="center").pack(side="left", padx=(0, 15))

        # Potência String 2
        ttk.Label(metrics_frame, text="S2 (DC) [W]:", font=('TkDefaultFont', 9, 'bold')).pack(side="left", padx=(0, 5))
        ttk.Label(metrics_frame, textvariable=self.str_p_s2, font=('TkDefaultFont', 9), width=8, relief="sunken", anchor="center").pack(side="left", padx=(0, 15))

        # Potência Total DC
        ttk.Label(metrics_frame, text="Total (DC) [W]:", font=('TkDefaultFont', 9, 'bold')).pack(side="left", padx=(0, 5))
        ttk.Label(metrics_frame, textvariable=self.str_p_total, font=('TkDefaultFont', 9), width=8, relief="sunken", anchor="center").pack(side="left", padx=(0, 15))

        # Potência AC (Inversor)
        ttk.Label(metrics_frame, text="Inversor (AC) [W]:", font=('TkDefaultFont', 9, 'bold')).pack(side="left", padx=(0, 5))
        ttk.Label(metrics_frame, textvariable=self.str_p_ac, font=('TkDefaultFont', 9), width=8, relief="sunken", anchor="center").pack(side="left", padx=(0, 15))

        # Eficiência
        ttk.Label(metrics_frame, text="Eficiência:", font=('TkDefaultFont', 9, 'bold')).pack(side="left", padx=(0, 5))
        ttk.Label(metrics_frame, textvariable=self.str_eff, font=('TkDefaultFont', 9), width=8, relief="sunken", anchor="center").pack(side="left")
        
        # Container do Gráfico
        graph_frame = ttk.LabelFrame(
            main_frame, text="Monitor de Potência: DC vs AC", padding=10)
        graph_frame.pack(fill="both", expand=True)

        self.fig = Figure(dpi=100)
        self.ax = self.fig.add_subplot(111)
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        
        # Config inicial dos eixos
        self._configurar_eixos()

    def _configurar_eixos(self):
        self.ax.set_xlabel("Hora")
        self.ax.set_ylabel("Potência (W)")
        self.ax.grid(True, linestyle='--', linewidth=0.5)

    def atualizar_inversor(self):
        try:
            solar = self.controller.solar_object
            if not solar:
                return

            # Dados String 1
            v_s1 = float(self.controller.dados_painel['tensao_real'].get() or 0)
            i_s1 = float(self.controller.dados_painel['corrente_real'].get() or 0)
            p_s1 = v_s1 * i_s1

            # Dados String 2
            v_s2 = float(self.controller.dados_painel['tensao_real_s2'].get() or 0)
            i_s2 = float(self.controller.dados_painel['corrente_real_s2'].get() or 0)
            p_s2 = v_s2 * i_s2
            
            # Dados AC (Inversor)
            p_ac = float(self.controller.dados_painel['potencia_ac'].get() or 0)
            
            p_total = p_s1 + p_s2

            # Atualiza display numérico
            self.str_p_s1.set(f"{p_s1:.1f}")
            self.str_p_s2.set(f"{p_s2:.1f}")
            self.str_p_total.set(f"{p_total:.1f}")
            self.str_p_ac.set(f"{p_ac:.1f}")
            
            # Eficiência
            if p_total > 50: # Evitar divisões expúrias em baixa potência
                eff = (p_ac / p_total) * 100
                self.str_eff.set(f"{eff:.1f}%")
            else:
                self.str_eff.set("0.0%")

            # Adiciona ao histórico
            self.trail_data['timestamps'].append(solar.data_hora)
            self.trail_data['p_dc_s1'].append(p_s1)
            self.trail_data['p_dc_s2'].append(p_s2)
            self.trail_data['p_dc_total'].append(p_total)
            self.trail_data['p_ac'].append(p_ac)
            
            self._atualizar_grafico()
            
        except Exception:
            traceback.print_exc()

    def _atualizar_grafico(self):
        self.ax.clear()
        self._configurar_eixos()

        timestamps = self.trail_data['timestamps']
        p_s1 = self.trail_data['p_dc_s1']
        p_s2 = self.trail_data['p_dc_s2']
        p_ac = self.trail_data['p_ac']
        
        if timestamps:
            self.ax.plot(timestamps, p_s1, label="String 1 (DC)", color='blue', linewidth=1)
            self.ax.plot(timestamps, p_s2, label="String 2 (DC)", color='orange', linewidth=1)
            self.ax.plot(timestamps, self.trail_data['p_dc_total'], label="Total (DC)", color='purple', linewidth=1.5)
            self.ax.plot(timestamps, p_ac, label="Inversor (AC)", color='green', linewidth=1.5, linestyle='--')
            
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            self.fig.autofmt_xdate()
            self.ax.legend(loc='upper left')

        self.canvas.draw()

    def reset_history_ask(self):
        if messagebox.askyesno("Confirmar Reinicialização", "Deseja reiniciar o gráfico do inversor?"):
            self.reset_history(confirm=False)

    def reset_history(self, confirm=False):
        self.trail_data = {
            'timestamps': [],
            'p_dc_s1': [],
            'p_dc_s2': [],
            'p_dc_total': [],
            'p_ac': []
        }
        self._atualizar_grafico()
