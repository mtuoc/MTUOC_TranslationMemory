import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import sys
import os

# Importació del motor backend
from MTUOC_TranslationMemory import MTUOC_TranslationMemory

class MTUOC_GUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MTUOC Translation Memory Management")
        self.root.minsize(1000, 650)
        
        # Truc universal per maximitzar la finestra sense errors a Linux/Mac/Windows
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"{screen_width}x{screen_height}+0+0")
        
        # Estil general de la interfície
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.db_instance = None
        self._create_layout()

    def _create_layout(self):
        # -----------------------------------------------------------------
        # 1. BARRA SUPERIOR: Connexió Permanent a la BD (Obertura o Creació)
        # -----------------------------------------------------------------
        db_frame = ttk.LabelFrame(self.root, text=" Global Database Connection ", padding=10)
        db_frame.pack(fill="x", padx=10, pady=5, side="top")
        
        ttk.Label(db_frame, text="Database Path:").pack(side="left", padx=5)
        self.db_path_var = tk.StringVar()
        self.db_entry = ttk.Entry(db_frame, textvariable=self.db_path_var, width=60)
        self.db_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        ttk.Button(db_frame, text="Browse...", command=self._browse_db).pack(side="left", padx=5)
        self.btn_connect = ttk.Button(db_frame, text="Connect", command=self._toggle_connect)
        self.btn_connect.pack(side="left", padx=5)

        # Status de la connexió
        self.lbl_status = ttk.Label(db_frame, text="Disconnected", foreground="red", font=("Arial", 10, "bold"))
        self.lbl_status.pack(side="left", padx=10)

        # -----------------------------------------------------------------
        # 2. PANELL CENTRAL: Pestanyes de les Accions (Notebook)
        # -----------------------------------------------------------------
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.tab_search = ttk.Frame(self.notebook, padding=10)
        self.tab_submemory = ttk.Frame(self.notebook, padding=10)
        self.tab_moses = ttk.Frame(self.notebook, padding=10)
        self.tab_tmx = ttk.Frame(self.notebook, padding=10)
        self.tab_tabtxt = ttk.Frame(self.notebook, padding=10)
        
        self.notebook.add(self.tab_search, text="Search")
        self.notebook.add(self.tab_submemory, text="Create SubMemory")
        self.notebook.add(self.tab_moses, text="Index Moses")
        self.notebook.add(self.tab_tmx, text="Index TMX")
        self.notebook.add(self.tab_tabtxt, text="Index TabTxt")
        
        # Inicialitzem el contingut de cada pestanya
        self._setup_tab_search()
        self._setup_tab_submemory()
        self._setup_tab_moses()
        self._setup_tab_tmx()
        self._setup_tab_tabtxt()

        # -----------------------------------------------------------------
        # 3. CONSOLA INFERIOR: Correcció d'empaquetat i expansió de text
        # -----------------------------------------------------------------
        log_frame = ttk.LabelFrame(self.root, text=" System Logs & Progress ", padding=5, height=420)
        log_frame.pack(fill="x", expand=False, padx=10, pady=10, side="bottom")
        log_frame.pack_propagate(False) # Manté ferms els 420px d'alçada
        
        # Definim height=22 per llegir unes 22-25 línies reals depenent de la font
        self.txt_log = tk.Text(log_frame, height=22, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 10), wrap="none")
        self.txt_log.pack(fill="both", expand=True, side="left")
        
        # Barra de desplaçament vertical
        scrollbar_y = ttk.Scrollbar(log_frame, command=self.txt_log.yview)
        scrollbar_y.pack(side="right", fill="y")
        
        # Barra de desplaçament horitzontal
        scrollbar_x = ttk.Scrollbar(log_frame, orient="horizontal", command=self.txt_log.xview)
        scrollbar_x.pack(side="bottom", fill="x")
        
        self.txt_log.config(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        
        # Redirigir el stdout clàssic de Python a la nostra caixa de text gràfica
        sys.stdout = RedirectText(self.txt_log)

    # -----------------------------------------------------------------
    # MÈTODES DE CONTROL GENERAL DE LA BASE DE DADES
    # -----------------------------------------------------------------
    def _browse_db(self):
        # SOLUCIÓ TOTAL: Permet triar fitxers existents, escriure'n de nous
        # i ELIMINA per complet el cartell d'avís de confirmació d'esborrat.
        file_path = filedialog.asksaveasfilename(
            defaultextension=".db",
            confirmoverwrite=False, # <--- AQUESTA ÉS LA LÍNIA MÀGICA
            filetypes=[
                ("Database Files (*.db)", "*.db"),
                ("SQLite Files (*.sqlite)", "*.sqlite"),
                ("All Files (*.*)", "*.*")
            ]
        )
        if file_path:
            self.db_path_var.set(file_path)

    def _toggle_connect(self):
        if self.db_instance is None:
            path = self.db_path_var.get().strip()
            if not path:
                messagebox.showerror("Error", "Please provide a valid database file path.")
                return
            try:
                # El motor SQLite crea el fitxer automàticament si no existeix
                self.db_instance = MTUOC_TranslationMemory(path)
                stats = self.db_instance.get_stats()
                self.lbl_status.config(text=f"Connected ({stats['segments']:,} segments)", foreground="green")
                self.btn_connect.config(text="Disconnect")
                self.db_entry.config(state="disabled")
                print(f"[System]: Connected to DB. Segments: {stats['segments']:,}, Blacklisted: {stats['blacklisted_ngrams']:,}")
            except Exception as e:
                messagebox.showerror("Connection Error", f"Could not open database:\n{e}")
        else:
            self.db_instance.close()
            self.db_instance = None
            self.lbl_status.config(text="Disconnected", foreground="red")
            self.btn_connect.config(text="Connect")
            self.db_entry.config(state="normal")
            print("[System]: Disconnected from database.")

    def _is_db_ready(self):
        if self.db_instance is None:
            messagebox.showwarning("Warning", "You must click 'Connect' to open the database before running this action.")
            return False
        return True

    # -----------------------------------------------------------------
    # DETALL DE PESTANYES
    # -----------------------------------------------------------------
    def _setup_tab_search(self):
        # Panell superior: Text de cerca i paràmetres (un costat de l'altre per estalviar espai vertical)
        top_f = ttk.Frame(self.tab_search)
        top_f.pack(side="top", fill="x", padx=5, pady=5)
        
        # Caixa de text per introduir la query (ara més ampla a dalt)
        query_frame = ttk.Frame(top_f)
        query_frame.pack(side="left", fill="both", expand=True, padx=5)
        ttk.Label(query_frame, text="Search Query:").pack(anchor="w")
        self.txt_query = tk.Text(query_frame, height=4, bg="white", fg="black")
        self.txt_query.pack(fill="both", expand=True, pady=2)
        
        # Paràmetres i botó de cerca (a la dreta de la query)
        p_frame = ttk.Frame(top_f, padding=10)
        p_frame.pack(side="right", fill="y", padx=5)
        
        ttk.Label(p_frame, text="Min Similarity %:").grid(row=0, column=0, sticky="w", pady=2)
        self.spin_sim = ttk.Spinbox(p_frame, from_=0.0, to=100.0, increment=5, width=8)
        self.spin_sim.set(70.0)
        self.spin_sim.grid(row=0, column=1, padx=5, sticky="w")
        
        ttk.Label(p_frame, text="Max Candidates:").grid(row=1, column=0, sticky="w", pady=2)
        self.spin_cand = ttk.Spinbox(p_frame, from_=1, to=500, width=8)
        self.spin_cand.set(100)
        self.spin_cand.grid(row=1, column=1, padx=5, sticky="w")
        
        # COM HA DE QUEDAR (Corregit):
        ttk.Button(p_frame, text="Perform Search", command=self._run_search).grid(row=2, column=0, columnspan=2, sticky="ew", pady=10)

        # Panell inferior (DINS DE LA PESTANYA): Resultats en horitzontal a sota de tot
        bottom_f = ttk.Frame(self.tab_search)
        bottom_f.pack(side="top", fill="both", expand=True, padx=5, pady=5)
        
        ttk.Label(bottom_f, text="Found Candidates:").pack(anchor="w")
        
        # Afegim scrollbars a la llista de resultats perquè sigui còmoda
        res_scroll_y = ttk.Scrollbar(bottom_f)
        res_scroll_y.pack(side="right", fill="y")
        
        res_scroll_x = ttk.Scrollbar(bottom_f, orient="horizontal")
        res_scroll_x.pack(side="bottom", fill="x")
        
        self.lst_results = tk.Listbox(
            bottom_f, 
            font=("Arial", 11), 
            yscrollcommand=res_scroll_y.set,
            xscrollcommand=res_scroll_x.set
        )
        self.lst_results.pack(fill="both", expand=True)
        
        res_scroll_y.config(command=self.lst_results.yview)
        res_scroll_x.config(command=self.lst_results.xview)

    def _run_search(self):
        if not self._is_db_ready(): return
        query = self.txt_query.get("1.0", tk.END).strip()
        sim = float(self.spin_sim.get())
        max_c = int(self.spin_cand.get())
        
        self.lst_results.delete(0, tk.END)
        results = self.db_instance.search(query, min_similarity=sim, max_candidates=max_c)
        
        if not results:
            self.lst_results.insert(tk.END, "No matching translation units found.")
        for tgt, score in results:
            self.lst_results.insert(tk.END, f"[{score:.1f}%] {tgt}")

    def _setup_tab_submemory(self):
        ttk.Label(self.tab_submemory, text="Input File (.xliff, .xlf or .txt containing reference phrases):").pack(anchor="w", pady=2)
        f_in = ttk.Frame(self.tab_submemory)
        f_in.pack(fill="x", pady=2)
        self.sub_in_var = tk.StringVar()
        ttk.Entry(f_in, textvariable=self.sub_in_var).pack(side="left", fill="x", expand=True)
        ttk.Button(f_in, text="Select", command=lambda: self.sub_in_var.set(filedialog.askopenfilename(filetypes=[("Supported formats", "*.xliff *.xlf *.txt")]))).pack(side="right", padx=5)

        ttk.Label(self.tab_submemory, text="Output TMX Save Path:").pack(anchor="w", pady=2)
        f_out = ttk.Frame(self.tab_submemory)
        f_out.pack(fill="x", pady=2)
        self.sub_out_var = tk.StringVar()
        ttk.Entry(f_out, textvariable=self.sub_out_var).pack(side="left", fill="x", expand=True)
        ttk.Button(f_out, text="Select", command=lambda: self.sub_out_var.set(filedialog.asksaveasfilename(defaultextension=".tmx", filetypes=[("TMX file", "*.tmx")]))).pack(side="right", padx=5)

        cfg = ttk.Frame(self.tab_submemory)
        cfg.pack(fill="x", pady=5)
        
        ttk.Label(cfg, text="Min Sim %:").grid(row=0, column=0, sticky="w")
        self.sub_sim = ttk.Spinbox(cfg, from_=0, to=100, width=8); self.sub_sim.set(70.0); self.sub_sim.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(cfg, text="Source Lang (SL):").grid(row=1, column=0, sticky="w")
        self.sub_sl = ttk.Entry(cfg, width=10); self.sub_sl.insert(0, "en"); self.sub_sl.grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(cfg, text="Target Lang (TL):").grid(row=2, column=0, sticky="w")
        self.sub_tl = ttk.Entry(cfg, width=10); self.sub_tl.insert(0, "ca"); self.sub_tl.grid(row=2, column=1, padx=5, pady=2)

        ttk.Button(self.tab_submemory, text="Generate TMX SubMemory", command=lambda: self._run_in_thread(self._proc_submemory)).pack(fill="x", pady=15)

    def _proc_submemory(self):
        src_input = self.sub_in_var.get()
        if os.path.exists(src_input) and src_input.lower().endswith('.txt'):
            with open(src_input, 'r', encoding='utf-8') as f:
                src_input = [line.strip() for line in f if line.strip()]
        
        self.db_instance.create_submemory(
            source_input=src_input, output_tmx_path=self.sub_out_var.get(),
            min_similarity=float(self.sub_sim.get()), sl=self.sub_sl.get().strip(), tl=self.sub_tl.get().strip()
        )
        self._refresh_stats()

    def _setup_tab_moses(self):
        ttk.Label(self.tab_moses, text="Source Language File (e.g., .en):").pack(anchor="w", pady=2)
        f1 = ttk.Frame(self.tab_moses); f1.pack(fill="x")
        self.moses_src = tk.StringVar(); ttk.Entry(f1, textvariable=self.moses_src).pack(side="left", fill="x", expand=True)
        ttk.Button(f1, text="Browse", command=lambda: self.moses_src.set(filedialog.askopenfilename())).pack(side="right", padx=5)

        ttk.Label(self.tab_moses, text="Target Language File (e.g., .ca):").pack(anchor="w", pady=2)
        f2 = ttk.Frame(self.tab_moses); f2.pack(fill="x")
        self.moses_tgt = tk.StringVar(); ttk.Entry(f2, textvariable=self.moses_tgt).pack(side="left", fill="x", expand=True)
        ttk.Button(f2, text="Browse", command=lambda: self.moses_tgt.set(filedialog.askopenfilename())).pack(side="right", padx=5)

        ttk.Button(self.tab_moses, text="Start Moses Indexation", command=lambda: self._run_in_thread(self._proc_moses)).pack(fill="x", pady=20)

    def _proc_moses(self):
        self.db_instance.index_moses(self.moses_src.get(), self.moses_tgt.get())
        self._refresh_stats()

    def _setup_tab_tmx(self):
        ttk.Label(self.tab_tmx, text="Select TMX Translation Memory File:").pack(anchor="w", pady=2)
        f1 = ttk.Frame(self.tab_tmx); f1.pack(fill="x", pady=5)
        self.tmx_path = tk.StringVar(); ttk.Entry(f1, textvariable=self.tmx_path).pack(side="left", fill="x", expand=True)
        ttk.Button(f1, text="Browse", command=lambda: self.tmx_path.set(filedialog.askopenfilename(filetypes=[("TMX file", "*.tmx")]))).pack(side="right", padx=5)

        ttk.Label(self.tab_tmx, text="Source Language Codes (space-separated, e.g.: en en-US ENG):").pack(anchor="w")
        self.tmx_sl = ttk.Entry(self.tab_tmx); self.tmx_sl.insert(0, "en en-US"); self.tmx_sl.pack(fill="x", pady=2)

        ttk.Label(self.tab_tmx, text="Target Language Codes (space-separated, e.g.: ca ca-ES CAT):").pack(anchor="w")
        self.tmx_tl = ttk.Entry(self.tab_tmx); self.tmx_tl.insert(0, "ca ca-ES"); self.tmx_tl.pack(fill="x", pady=2)

        ttk.Button(self.tab_tmx, text="Start TMX Indexation", command=lambda: self._run_in_thread(self._proc_tmx)).pack(fill="x", pady=20)

    def _proc_tmx(self):
        s_langs = self.tmx_sl.get().strip().split()
        t_langs = self.tmx_tl.get().strip().split()
        self.db_instance.index_tmx(self.tmx_path.get(), s_langs, t_langs)
        self._refresh_stats()

    def _setup_tab_tabtxt(self):
        ttk.Label(self.tab_tabtxt, text="Select Tabulated Text File (.txt or .txt.gz):").pack(anchor="w", pady=2)
        f1 = ttk.Frame(self.tab_tabtxt); f1.pack(fill="x", pady=5)
        self.tabtxt_path = tk.StringVar(); ttk.Entry(f1, textvariable=self.tabtxt_path).pack(side="left", fill="x", expand=True)
        ttk.Button(f1, text="Browse", command=lambda: self.tabtxt_path.set(filedialog.askopenfilename(filetypes=[("Tabulated text", "*.txt *.txt.gz *.tsv")]))).pack(side="right", padx=5)

        self.tabtxt_rev = tk.BooleanVar()
        ttk.Checkbutton(self.tab_tabtxt, text="Reverse Columns (Treat 2nd column as Source Language)", variable=self.tabtxt_rev).pack(anchor="w", pady=5)

        ttk.Button(self.tab_tabtxt, text="Start TabTxt Indexation", command=lambda: self._run_in_thread(self._proc_tabtxt)).pack(fill="x", pady=20)

    def _proc_tabtxt(self):
        self.db_instance.index_tabtxt(self.tabtxt_path.get(), reverse=self.tabtxt_rev.get())
        self._refresh_stats()

    # -----------------------------------------------------------------
    # GESTIÓ ASÍNCRONA (Threading)
    # -----------------------------------------------------------------
    def _run_in_thread(self, target_function):
        if not self._is_db_ready(): return
        thread = threading.Thread(target=target_function, daemon=True)
        thread.start()

    def _refresh_stats(self):
        if self.db_instance:
            stats = self.db_instance.get_stats()
            self.root.after(0, lambda: self.lbl_status.config(text=f"Connected ({stats['segments']:,} segments)", foreground="green"))


# CLASSE AUXILIAR: Redirecció de la consola de text
class RedirectText:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, string):
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)

    def flush(self):
        pass


if __name__ == "__main__":
    root = tk.Tk()
    app = MTUOC_GUI(root)
    root.mainloop()
