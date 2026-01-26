import tkinter as tk
from tkinter import ttk, messagebox
import datetime

class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        
        # Canvas para scroll
        self.canvas = tk.Canvas(self)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        
        # Frame interno que conterá os logs
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )
        
        # Cria a janela do frame dentro do canvas
        self.canvas_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # Configura resize do canvas para ajustar largura do frame interno
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Mousewheel
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_canvas_configure(self, event):
        # Ajusta a largura do frame interno para a largura do canvas
        self.canvas.itemconfig(self.canvas_frame, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

class PaginaAnalise(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        
        self._criar_widgets()

    def _criar_widgets(self):
        # Layout Principal
        self.pack_propagate(False) # Força obedecer tamanho
        
        # Header (simulando colunas)
        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", padx=10, pady=(10,0))
        
        lbl_h1 = ttk.Label(header_frame, text="Horário (Gêmeo)", font=('TkDefaultFont', 9, 'bold'), width=20, anchor="center")
        lbl_h1.pack(side="left")
        
        lbl_h2 = ttk.Label(header_frame, text="Análise do Especialista", font=('TkDefaultFont', 9, 'bold'), anchor="w")
        lbl_h2.pack(side="left", fill="x", expand=True, padx=(10,0))
        
        # Divisor
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=5)
        
        # Container Scrollavel
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=10, pady=(0,10))
        
        self.scroll_area = ScrollableFrame(container)
        self.scroll_area.pack(fill="both", expand=True)
        
        # Botões
        frame_botoes = ttk.Frame(self)
        frame_botoes.pack(fill="x", padx=10, pady=5)
        
        btn_limpar = ttk.Button(frame_botoes, text="Limpar Histórico", command=self.limpar_historico)
        btn_limpar.pack(side="right")

    def add_log(self, timestamp, text):
        """
        Adiciona uma nova linha de log na tabela.
        """
        if isinstance(timestamp, datetime.datetime):
            ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts_str = str(timestamp)
            
        # Frame da Linha
        row_frame = ttk.Frame(self.scroll_area.scrollable_frame, style="Card.TFrame")
        
        # Lógica para inserir no topo:
        # Pega a lista de widgets PACOTADOS anteriormente.
        slaves = self.scroll_area.scrollable_frame.pack_slaves()
        
        if slaves:
            # Insere ANTES do primeiro widget (que está no topo visual)
            row_frame.pack(side="top", fill="x", expand=True, pady=2, before=slaves[0]) 
        else:
            # Se não tem ninguém, é o primeiro
            row_frame.pack(side="top", fill="x", expand=True, pady=2)

        # Coluna 1: Timestamp (Fundo levemente diferente ou borda?)
        lbl_ts = ttk.Label(row_frame, text=ts_str, width=20, anchor="n", font=('Consolas', 9))
        lbl_ts.pack(side="left", anchor="n", padx=(0,10))
        
        # Coluna 2: Texto
        # Usaremos Label com wraplength dinâmico
        lbl_text = ttk.Label(row_frame, text=text, justify="left", anchor="nw")
        lbl_text.pack(side="left", fill="x", expand=True)
        
        # Bind resize para ajustar wraplength
        def on_resize(event):
            # width do label = event.width. Wraplength = width
            lbl_text.config(wraplength=event.width - 5) # -5 padding
            
        lbl_text.bind("<Configure>", on_resize)
        
        # Separator visual entre linhas
        # sep = ttk.Separator(self.scroll_area.scrollable_frame, orient="horizontal")
        # if children: sep.pack(side="top", fill="x", pady=2, before=children[0])
        # else: sep.pack(side="top", fill="x", pady=2)

    def limpar_historico(self):
        for widget in self.scroll_area.scrollable_frame.winfo_children():
            widget.destroy()

    def reset_history(self, confirm=True):
        if confirm:
             if not messagebox.askyesno("Limpar Histórico", "Deseja limpar o histórico de análises?"):
                 return
        self.limpar_historico()
