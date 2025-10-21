import tkinter as tk
from tkinter import ttk, messagebox
import datetime

import irradiance_calculator as irr_calc
# <-- Importa o novo componente
from ui_components import EntradaGlobalFrame, IrradianceFrame

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates


class PaginaPainel(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.trail_data = {'timestamps': [],
                           'horizontal': [], 'ideal': [], 'fixo': []}

        self.saidas_irradiancia = {
            "kt": tk.StringVar(), "kd": tk.StringVar(),
            "GHI_global": tk.StringVar(), "GHI_direta": tk.StringVar(), "GHI_difusa": tk.StringVar(), "GHI_refletida": tk.StringVar(), "GHI_diff_perc": tk.StringVar(),
            "POA_ideal_global": tk.StringVar(), "POA_ideal_direta": tk.StringVar(), "POA_ideal_difusa": tk.StringVar(), "POA_ideal_refletida": tk.StringVar(), "POA_ideal_diff_perc": tk.StringVar(value="0.00%"),
            "POA_fixo_global": tk.StringVar(), "POA_fixo_direta": tk.StringVar(), "POA_fixo_difusa": tk.StringVar(), "POA_fixo_refletida": tk.StringVar(), "POA_fixo_diff_perc": tk.StringVar(),
        }
        self.entrada_widgets = {}

        self._criar_widgets()

        self.controller.editar_data_var.trace_add(
            "write", self._toggle_edit_state)
        self.controller.editar_hora_var.trace_add(
            "write", self._toggle_edit_state)
        self.controller.editar_painel_var.trace_add(
            "write", self._toggle_panel_edit_state)
        self._toggle_edit_state()
        self._toggle_panel_edit_state()

    def _criar_widgets(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True)

        coluna_esquerda = ttk.Frame(main_frame)
        coluna_esquerda.pack(side="left", fill="y",
                             padx=10, pady=5, anchor="n")

        self.frame_entrada = EntradaGlobalFrame(
            coluna_esquerda, self.controller)
        self.frame_entrada.pack(pady=(0, 3), fill="x")

        # --- MUDANÇA: Usa o novo componente de Irradiância ---
        self.frame_irradiancia = IrradianceFrame(
            coluna_esquerda, self.controller)
        self.frame_irradiancia.pack(pady=3, fill="x")

        frame_configs = ttk.LabelFrame(
            coluna_esquerda, text="Configurações do Painel Fixo", padding=5)
        frame_configs.pack(pady=3, fill="x")
        frame_configs.columnconfigure(1, weight=1)

        cb_painel = ttk.Checkbutton(frame_configs, text="Editar Painel/Albedo",
                                    variable=self.controller.editar_painel_var, style="Compact.TCheckbutton")
        cb_painel.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 3))

        panel_labels = {"albedo": "Albedo do Solo:",
                        "painel_inclinacao": "Inclinação (°):", "painel_azimute": "Azimute (°):"}
        for i, (key, text) in enumerate(panel_labels.items(), start=1):
            ttk.Label(frame_configs, text=text, style="Compact.TLabel").grid(
                row=i, column=0, sticky="w", pady=1)
            entry = ttk.Entry(
                frame_configs, textvariable=self.controller.dados_painel[key], font=('TkDefaultFont', 6))
            entry.grid(row=i, column=1, sticky="ew", padx=5, pady=1)
            entry.bind("<KeyRelease>",
                       lambda e: self.controller.atualizar_calculos_e_telas())
            self.entrada_widgets[key] = entry

        btn_limpar = ttk.Button(
            frame_configs, text="Reiniciar Gráfico", command=self._clear_and_restart_trail)
        btn_limpar.grid(row=len(panel_labels)+1, column=0,
                        columnspan=2, pady=(5, 0), sticky="ew")

        frame_tabela = ttk.LabelFrame(
            coluna_esquerda, text="Componentes da Irradiância (W/m²)", padding=5)
        frame_tabela.pack(pady=5, fill="x")

        headers = ["", "Global",
                   "Ganho/Perda (%)", "Direta", "Difusa", "Refletida"]
        for col, header in enumerate(headers):
            ttk.Label(frame_tabela, text=header, font=('TkDefaultFont', 6, 'bold')).grid(
                row=0, column=col, padx=5, pady=2, sticky="w")

        rows_data = [("Painel Ideal", "POA_ideal"), ("Painel Fixo",
                                                     "POA_fixo"), ("Painel Horizontal", "GHI")]
        for row, (label_text, prefix) in enumerate(rows_data, start=1):
            ttk.Label(frame_tabela, text=label_text).grid(
                row=row, column=0, padx=5, sticky="w")
            ttk.Entry(frame_tabela, textvariable=self.saidas_irradiancia[f"{prefix}_global"], state="readonly", width=10).grid(
                row=row, column=1, padx=2)
            ttk.Entry(frame_tabela, textvariable=self.saidas_irradiancia[f"{prefix}_diff_perc"], state="readonly", width=10).grid(
                row=row, column=2, padx=2)
            ttk.Entry(frame_tabela, textvariable=self.saidas_irradiancia[f"{prefix}_direta"], state="readonly", width=10).grid(
                row=row, column=3, padx=2)
            ttk.Entry(frame_tabela, textvariable=self.saidas_irradiancia[f"{prefix}_difusa"], state="readonly", width=10).grid(
                row=row, column=4, padx=2)
            ttk.Entry(frame_tabela, textvariable=self.saidas_irradiancia[f"{prefix}_refletida"], state="readonly", width=10).grid(
                row=row, column=5, padx=2)

        frame_indices = ttk.LabelFrame(
            coluna_esquerda, text="Índices Atmosféricos - Atual", padding=5)
        frame_indices.pack(pady=5, fill="x")
        frame_indices.columnconfigure(1, weight=1)
        ttk.Label(frame_indices, text="Índice de Claridade (Kτ):").grid(
            row=0, column=0, sticky="w", pady=2)
        ttk.Entry(frame_indices, textvariable=self.saidas_irradiancia["kt"], state="readonly").grid(
            row=0, column=1, sticky="ew", padx=5, pady=1)
        ttk.Label(frame_indices, text="Indíce de Fração Difusa (Kɗ):").grid(
            row=1, column=0, sticky="w", pady=2)
        ttk.Entry(frame_indices, textvariable=self.saidas_irradiancia["kd"], state="readonly").grid(
            row=1, column=1, sticky="ew", padx=5, pady=1)

        frame_grafico = ttk.LabelFrame(
            main_frame, text="Irradiância Global x Tempo", padding=10)
        frame_grafico.pack(side="left", fill="both",
                           expand=True, padx=(10, 20), pady=10)
        self.figura_irradiancia = Figure(figsize=(7, 5), dpi=100)
        self.ax_irradiancia = self.figura_irradiancia.add_subplot(111)
        self.canvas_irradiancia = FigureCanvasTkAgg(
            self.figura_irradiancia, master=frame_grafico)
        self.canvas_irradiancia.get_tk_widget().pack(fill="both", expand=True)

    def _toggle_edit_state(self, *args):
        self.frame_entrada._toggle_edit_state()

    def _toggle_panel_edit_state(self, *args):
        state = "normal" if self.controller.editar_painel_var.get() else "disabled"
        for key in ("albedo", "painel_inclinacao", "painel_azimute"):
            if key in self.entrada_widgets:
                self.entrada_widgets[key].config(state=state)

    def _clear_and_restart_trail(self):
        resposta = messagebox.askyesno(
            "Confirmar Reinicialização", "Você tem certeza que deseja reiniciar o gráfico?")
        if resposta:
            self.trail_data = {'timestamps': [],
                               'horizontal': [], 'ideal': [], 'fixo': []}
            self._atualizar_grafico_irradiancia()

    def calcular_e_atualizar_tabela(self):
        solar = self.controller.solar_object
        if not solar:
            return
        try:
            ghi_atual = float(
                self.controller.dados_painel["irradiancia_ghi"].get())
            albedo = float(self.controller.dados_painel["albedo"].get())
            inclinacao_fixa = float(
                self.controller.dados_painel["painel_inclinacao"].get())
            azimute_fixo = float(
                self.controller.dados_painel["painel_azimute"].get())
        except (ValueError, tk.TclError):
            return

        params = {'albedo': albedo, 'dia_do_ano': solar.n, 'solar_zenith_deg': 90 -
                  solar.elevacao, 'solar_azimuth_deg': solar.azimute}
        res_horiz = irr_calc.calcular_componentes_irradiancia(
            ghi=ghi_atual, **params, inclinacao_superficie=0, azimute_superficie=0)
        inclinacao_ideal = 90 - solar.elevacao if solar.elevacao > 0 else 90
        res_ideal = irr_calc.calcular_componentes_irradiancia(
            ghi=ghi_atual, **params, inclinacao_superficie=inclinacao_ideal, azimute_superficie=solar.azimute)
        res_fixo = irr_calc.calcular_componentes_irradiancia(
            ghi=ghi_atual, **params, inclinacao_superficie=inclinacao_fixa, azimute_superficie=azimute_fixo)

        ideal_global = res_ideal['global']
        horiz_global = res_horiz['global']
        diff_horiz = ((horiz_global - ideal_global) /
                      ideal_global * 100) if ideal_global > 0 else 0
        self.saidas_irradiancia["GHI_diff_perc"].set(f"{diff_horiz:.2f}%")
        fixo_global = res_fixo['global']
        diff_fixo = ((fixo_global - ideal_global) /
                     ideal_global * 100) if ideal_global > 0 else 0
        self.saidas_irradiancia["POA_fixo_diff_perc"].set(f"{diff_fixo:.2f}%")

        self.saidas_irradiancia["kt"].set(f"{res_horiz['kt']:.4f}")
        self.saidas_irradiancia["kd"].set(f"{res_horiz['kd']:.4f}")
        for k, v in res_horiz.items():
            if f"GHI_{k}" in self.saidas_irradiancia:
                self.saidas_irradiancia[f"GHI_{k}"].set(f"{v:.2f}")
        self.saidas_irradiancia["GHI_direta"].set(
            f"{res_horiz['global'] - res_horiz['dhi']:.2f}")

        for k, v in res_ideal.items():
            if f"POA_ideal_{k}" in self.saidas_irradiancia:
                self.saidas_irradiancia[f"POA_ideal_{k}"].set(f"{v:.2f}")

        for k, v in res_fixo.items():
            if f"POA_fixo_{k}" in self.saidas_irradiancia:
                self.saidas_irradiancia[f"POA_fixo_{k}"].set(f"{v:.2f}")

        self.trail_data['timestamps'].append(solar.data_hora)
        self.trail_data['horizontal'].append(res_horiz['global'])
        self.trail_data['ideal'].append(res_ideal['global'])
        self.trail_data['fixo'].append(res_fixo['global'])

        self._atualizar_grafico_irradiancia()

    def _atualizar_grafico_irradiancia(self):
        self.ax_irradiancia.clear()
        if self.trail_data['timestamps']:
            self.ax_irradiancia.plot(
                self.trail_data['timestamps'], self.trail_data['horizontal'], label="Painel Horizontal", color='blue', zorder=2)
            self.ax_irradiancia.plot(
                self.trail_data['timestamps'], self.trail_data['ideal'], label="Painel Ideal", color='red', zorder=2)
            self.ax_irradiancia.plot(
                self.trail_data['timestamps'], self.trail_data['fixo'], label="Painel Fixo", color='orange', zorder=2)

            last_ts = self.trail_data['timestamps'][-1]
            self.ax_irradiancia.plot(
                last_ts, self.trail_data['horizontal'][-1], 'o', color='mediumblue', markersize=8, zorder=4)
            self.ax_irradiancia.plot(
                last_ts, self.trail_data['ideal'][-1], 'o', color='darkred', markersize=8, zorder=4)
            self.ax_irradiancia.plot(
                last_ts, self.trail_data['fixo'][-1], 'o', color='darkorange', markersize=8, zorder=4)

        self.ax_irradiancia.set_title("Irradiância Global")
        self.ax_irradiancia.set_xlabel("Hora")
        self.ax_irradiancia.set_ylabel("Irradiância (W/m²)")
        if self.trail_data['timestamps']:
            self.ax_irradiancia.legend()
        self.ax_irradiancia.grid(
            True, which='both', linestyle='--', linewidth=0.5)

        if self.trail_data['timestamps']:
            self.ax_irradiancia.xaxis.set_major_formatter(
                mdates.DateFormatter('%H:%M:%S'))
            self.figura_irradiancia.autofmt_xdate()

        self.figura_irradiancia.tight_layout()
        self.canvas_irradiancia.draw()
