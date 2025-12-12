import tkinter as tk
from tkinter import ttk
import datetime


class EntradaGlobalFrame(ttk.LabelFrame):
    """Um componente de UI reutilizável para as entradas de data, hora e local."""

    def __init__(self, parent, controller, **kwargs):
        super().__init__(parent, text="Dados de Entrada", padding=5, **kwargs)
        self.controller = controller

        self.entrada_widgets = {}
        self.time_slider_label_var = tk.StringVar()
        self.day_slider_label_var = tk.StringVar()

        self._criar_widgets_internos()
        # Chama as funções de sincronização para garantir o estado inicial correto
        self._sync_slider_from_entries()
        self._sync_day_slider_from_entries()

    def _on_time_slider_move(self, value_str):
        minute_of_day = int(float(value_str))
        hour, minute = divmod(minute_of_day, 60)
        self.controller.entradas_globais["hora"].set(f"{hour:02d}")
        self.controller.entradas_globais["minuto"].set(f"{minute:02d}")
        self.time_slider_label_var.set(f"{hour:02d}:{minute:02d}")
        self.controller.atualizar_calculos_e_telas()

    def _sync_slider_from_entries(self, event=None):
        try:
            hour = int(self.controller.entradas_globais["hora"].get() or 0)
            minute = int(self.controller.entradas_globais["minuto"].get() or 0)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                total_minutes = hour * 60 + minute
                self.controller.time_slider_var.set(total_minutes)
                self.time_slider_label_var.set(f"{hour:02d}:{minute:02d}")
                self.controller.atualizar_calculos_e_telas()
        except (ValueError, tk.TclError):
            pass

    def _update_day_slider_range(self, *args):
        try:
            year = int(self.controller.entradas_globais["ano"].get())
            is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
            days_in_year = 366 if is_leap else 365
            if "day_of_year_slider" in self.entrada_widgets:
                self.entrada_widgets["day_of_year_slider"].config(
                    to=days_in_year)
                current_day = self.controller.day_of_year_slider_var.get()
                self.day_slider_label_var.set(f"{current_day}/{days_in_year}")
        except (ValueError, tk.TclError, KeyError):
            pass

    def _on_day_slider_move(self, value_str):
        try:
            doy = int(float(value_str))
            year = int(self.controller.entradas_globais["ano"].get())
            date = datetime.datetime(year, 1, 1) + datetime.timedelta(doy - 1)
            self.controller.entradas_globais["dia"].set(str(date.day))
            self.controller.entradas_globais["mes"].set(str(date.month))
            self._update_day_slider_range()
            self.controller.atualizar_calculos_e_telas()
        except (ValueError, tk.TclError):
            pass

    def _sync_day_slider_from_entries(self, event=None):
        try:
            year = int(self.controller.entradas_globais["ano"].get())
            month = int(self.controller.entradas_globais["mes"].get())
            day = int(self.controller.entradas_globais["dia"].get())
            doy = datetime.date(year, month, day).timetuple().tm_yday
            self.controller.day_of_year_slider_var.set(doy)
            self._update_day_slider_range()
            self.controller.atualizar_calculos_e_telas()
        except (ValueError, tk.TclError):
            pass

    def _handle_arrow_key(self, variable, step, from_val, to_val, event):
        """Função genérica para controlar sliders com as setas."""
        is_data_editing = self.controller.editar_data_var.get(
        ) and variable == self.controller.day_of_year_slider_var
        is_hora_editing = self.controller.editar_hora_var.get(
        ) and variable == self.controller.time_slider_var

        if is_data_editing or is_hora_editing:
            current_value = variable.get()
            new_value = current_value + step

            new_value = max(from_val, min(to_val, new_value))

            variable.set(new_value)

            if variable == self.controller.day_of_year_slider_var:
                self._on_day_slider_move(new_value)
            elif variable == self.controller.time_slider_var:
                self._on_time_slider_move(new_value)

    def _criar_widgets_internos(self):
        self.columnconfigure(1, weight=1)

        style = ttk.Style()
        style.configure("Compact.TLabel", font=('TkDefaultFont', 6))
        style.configure("Compact.TCheckbutton", font=('TkDefaultFont', 6))

        # --- LOCAL ---
        cb_local = ttk.Checkbutton(
            self, text="Editar Local", variable=self.controller.editar_local_var, style="Compact.TCheckbutton")
        cb_local.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 2))

        entradas_loc = {
            "latitude": "Latitude (°):", "longitude": "Longitude (°):", "utc": "UTC (h):"}
        row_idx = 1
        for key, label in entradas_loc.items():
            ttk.Label(self, text=label, style="Compact.TLabel").grid(
                row=row_idx, column=0, sticky="w", pady=1)
            variable = self.controller.entradas_globais.get(key)
            entry = ttk.Entry(self, textvariable=variable,
                              font=('TkDefaultFont', 6))
            entry.grid(row=row_idx, column=1, columnspan=2,
                       sticky="ew", padx=5, pady=1)
            self.entrada_widgets[key] = entry
            entry.bind(
                "<KeyRelease>", lambda e: self.controller.atualizar_calculos_e_telas())
            row_idx += 1

        # --- DATA ---
        cb_data = ttk.Checkbutton(
            self, text="Editar Data", variable=self.controller.editar_data_var, style="Compact.TCheckbutton")
        cb_data.grid(row=row_idx, column=0, columnspan=3, sticky="w", pady=(5, 2))
        row_idx += 1

        # Ano (separado do loop anterior)
        ttk.Label(self, text="Ano:", style="Compact.TLabel").grid(row=row_idx, column=0, sticky="w", pady=1)
        entry_ano = ttk.Entry(self, textvariable=self.controller.entradas_globais["ano"], font=('TkDefaultFont', 6))
        entry_ano.grid(row=row_idx, column=1, columnspan=2, sticky="ew", padx=5, pady=1)
        self.entrada_widgets["ano"] = entry_ano
        
        # Como o Ano influencia o slider de dias, precisamos rastreá-lo
        try:
             self.controller.entradas_globais["ano"].trace_add("write", self._update_day_slider_range)
        except tk.TclError:
             pass 
        entry_ano.bind("<KeyRelease>", self._sync_day_slider_from_entries)
        row_idx += 1

        dm_frame = ttk.Frame(self)
        dm_frame.grid(row=row_idx, column=0, columnspan=3, sticky="ew", pady=1)
        ttk.Label(dm_frame, text="Dia:", style="Compact.TLabel").pack(
            side="left", padx=(0, 2))
        entry_d = ttk.Entry(
            dm_frame, textvariable=self.controller.entradas_globais["dia"], width=4, font=('TkDefaultFont', 6))
        entry_d.pack(side="left")
        self.entrada_widgets["dia"] = entry_d
        ttk.Label(dm_frame, text="Mês:", style="Compact.TLabel").pack(
            side="left", padx=(10, 2))
        entry_m = ttk.Entry(
            dm_frame, textvariable=self.controller.entradas_globais["mes"], width=4, font=('TkDefaultFont', 6))
        entry_m.pack(side="left")
        self.entrada_widgets["mes"] = entry_m

        entry_d.bind("<KeyRelease>", self._sync_day_slider_from_entries)
        entry_m.bind("<KeyRelease>", self._sync_day_slider_from_entries)
        row_idx += 1

        ttk.Label(self, text="Dia do Ano:", style="Compact.TLabel").grid(
            row=row_idx, column=0, sticky="w", pady=(3, 1))
        day_slider = ttk.Scale(self, from_=1, to=365, orient='horizontal',
                               variable=self.controller.day_of_year_slider_var, command=self._on_day_slider_move, takefocus=True)
        day_slider.grid(row=row_idx, column=1,
                        sticky="ew", padx=5, pady=(3, 1))
        self.entrada_widgets["day_of_year_slider"] = day_slider
        ttk.Label(self, textvariable=self.day_slider_label_var, width=8, style="Compact.TLabel").grid(
            row=row_idx, column=2, sticky="w", pady=(3, 1))
        row_idx += 1

        day_slider.bind("<Button-1>", lambda e: day_slider.focus_set())
        day_slider.bind("<KeyPress-Left>", lambda event: self._handle_arrow_key(
            self.controller.day_of_year_slider_var, -1, 1, 366, event))
        day_slider.bind("<KeyPress-Right>", lambda event: self._handle_arrow_key(
            self.controller.day_of_year_slider_var, 1, 1, 366, event))

        cb_hora = ttk.Checkbutton(
            self, text="Editar Hora (HH:MM:SS)", variable=self.controller.editar_hora_var, style="Compact.TCheckbutton")
        cb_hora.grid(row=row_idx, column=0, columnspan=3,
                     sticky="w", pady=(3, 2))
        row_idx += 1

        time_frame = ttk.Frame(self)
        time_frame.grid(row=row_idx, column=0, columnspan=3, sticky="ew")
        ttk.Label(time_frame, text="Hora:",
                  style="Compact.TLabel").pack(side="left")
        entry_h = ttk.Entry(
            time_frame, textvariable=self.controller.entradas_globais["hora"], width=3, font=('TkDefaultFont', 6))
        entry_h.pack(side="left")
        self.entrada_widgets["hora"] = entry_h
        ttk.Label(time_frame, text=":",
                  style="Compact.TLabel").pack(side="left")
        entry_m_time = ttk.Entry(
            time_frame, textvariable=self.controller.entradas_globais["minuto"], width=3, font=('TkDefaultFont', 6))
        entry_m_time.pack(side="left")
        self.entrada_widgets["minuto"] = entry_m_time
        ttk.Label(time_frame, text=":",
                  style="Compact.TLabel").pack(side="left")
        entry_s = ttk.Entry(
            time_frame, textvariable=self.controller.entradas_globais["segundo"], width=3, font=('TkDefaultFont', 6))
        entry_s.pack(side="left")
        self.entrada_widgets["segundo"] = entry_s
        entry_h.bind("<KeyRelease>", self._sync_slider_from_entries)
        entry_m_time.bind("<KeyRelease>", self._sync_slider_from_entries)
        entry_s.bind("<KeyRelease>",
                     lambda e: self.controller.atualizar_calculos_e_telas())
        row_idx += 1

        ttk.Label(self, text="Hora do Dia:", style="Compact.TLabel").grid(
            row=row_idx, column=0, sticky="w", pady=(3, 1))
        time_slider = ttk.Scale(self, from_=0, to=1439, orient='horizontal',
                                variable=self.controller.time_slider_var, command=self._on_time_slider_move, takefocus=True)
        time_slider.grid(row=row_idx, column=1,
                         sticky="ew", padx=5, pady=(3, 1))
        self.entrada_widgets["time_slider"] = time_slider
        ttk.Label(self, textvariable=self.time_slider_label_var, width=5, style="Compact.TLabel").grid(
            row=row_idx, column=2, sticky="w", pady=(3, 1))

        time_slider.bind("<Button-1>", lambda e: time_slider.focus_set())
        time_slider.bind("<KeyPress-Left>", lambda event: self._handle_arrow_key(
            self.controller.time_slider_var, -1, 0, 1439, event))
        time_slider.bind("<KeyPress-Right>", lambda event: self._handle_arrow_key(
            self.controller.time_slider_var, 1, 0, 1439, event))

    def _toggle_edit_state(self):
        # Controle de Local
        state_local = "normal" if self.controller.editar_local_var.get() else "disabled"
        for key in ("latitude", "longitude", "utc"):
            if key in self.entrada_widgets:
                self.entrada_widgets[key].config(state=state_local)

        # Controle de Data
        state_data = "normal" if self.controller.editar_data_var.get() else "disabled"
        for key in ("ano", "dia", "mes", "day_of_year_slider"):
            if key in self.entrada_widgets:
                self.entrada_widgets[key].config(state=state_data)

        # Controle de Hora
        state_hora = "normal" if self.controller.editar_hora_var.get() else "disabled"
        for key in ("hora", "minuto", "segundo", "time_slider"):
            if key in self.entrada_widgets:
                self.entrada_widgets[key].config(state=state_hora)


class IrradianceFrame(ttk.LabelFrame):
    """Componente de UI reutilizável para os controles de irradiância."""

    def __init__(self, parent, controller, **kwargs):
        super().__init__(parent, text="Configurações de Irradiância", padding=5, **kwargs)
        self.controller = controller

        self.entrada_widgets = {}
        self._criar_widgets_internos()

        # Vincula o callback para o checkbox
        self.controller.editar_irradiancia_var.trace_add(
            "write", self._toggle_edit_state)
        self._toggle_edit_state()  # Define estado inicial

    def _on_slider_move(self, value_str):
        stepped_value = round(float(value_str) / 10) * 10
        self.controller.dados_painel["irradiancia_ghi"].set(str(stepped_value))
        self.controller.atualizar_calculos_e_telas()

    def _handle_arrow_key(self, step):
        if self.controller.editar_irradiancia_var.get():
            current_value = self.controller.irradiance_slider_var.get()
            new_value = current_value + step
            new_value = max(0, min(1400, new_value))
            stepped_value = round(new_value / 10) * 10
            self.controller.irradiance_slider_var.set(stepped_value)
            self.controller.dados_painel["irradiancia_ghi"].set(
                str(stepped_value))
            self.controller.atualizar_calculos_e_telas()

    def _toggle_edit_state(self, *args):
        state = "normal" if self.controller.editar_irradiancia_var.get() else "disabled"
        self.entrada_widgets["irradiance_slider"].config(state=state)

    def _criar_widgets_internos(self):
        self.columnconfigure(1, weight=1)

        style = ttk.Style()
        style.configure("Compact.TLabel", font=('TkDefaultFont', 6))
        style.configure("Compact.TCheckbutton", font=('TkDefaultFont', 6))

        cb_irradiancia = ttk.Checkbutton(
            self, text="Editar Irradiância", variable=self.controller.editar_irradiancia_var, style="Compact.TCheckbutton")
        cb_irradiancia.grid(row=0, column=0, columnspan=3,
                            sticky="w", pady=(0, 2))

        ttk.Label(self, text="GHI (W/m²):",
                  style="Compact.TLabel").grid(row=1, column=0, sticky="w", pady=2)

        # Inicializa o valor do slider a partir da variável global
        self.controller.irradiance_slider_var.set(
            float(self.controller.dados_painel["irradiancia_ghi"].get()))

        irradiance_slider = ttk.Scale(self, from_=0, to=1400, orient='horizontal',
                                      variable=self.controller.irradiance_slider_var, command=self._on_slider_move, takefocus=True)
        irradiance_slider.grid(row=1, column=1, sticky="ew", padx=5)
        self.entrada_widgets["irradiance_slider"] = irradiance_slider

        irradiance_slider.bind(
            "<Button-1>", lambda e: irradiance_slider.focus_set())
        irradiance_slider.bind(
            "<KeyPress-Left>", lambda event: self._handle_arrow_key(-10))
        irradiance_slider.bind(
            "<KeyPress-Right>", lambda event: self._handle_arrow_key(10))

        lbl_irradiance_val = ttk.Label(
            self, textvariable=self.controller.dados_painel["irradiancia_ghi"], width=5, style="Compact.TLabel")
        lbl_irradiance_val.grid(row=1, column=2, sticky="w")
