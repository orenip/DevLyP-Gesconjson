import customtkinter as ctk
import tkinter as tk  # <-- LÍNEA CORREGIDA/AÑADIDA
from tkinter import filedialog, messagebox
import os
import re
import json
import shutil
from pathlib import Path
import sys
import subprocess # <-- Import para lanzar el script de sync

# --- MODIFICACIÓN CLAVE PARA .EXE ---
if getattr(sys, 'frozen', False):
    SCRIPT_DIR = Path(sys.executable).parent
else:
    SCRIPT_DIR = Path(__file__).parent

CONFIG_PATH_FILE = SCRIPT_DIR / ".configpath.txt"
PROJECT_MAP_FILE = SCRIPT_DIR / "projectmap.json"

# --- Configuración Visual ---
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class ConfigSwitcherApp(ctk.CTk):
    """
    Aplicación visual (con CustomTkinter) para gestionar y aplicar 
    configuraciones (appsettings.json o .env).
    """
    
    def __init__(self):
        super().__init__()
        self.title("Gestor de Configuraciones")
        self.geometry("700x750")
        self.resizable(False, False)

        # Variables de estado
        self.base_config_path = ctk.StringVar()
        self.target_project_path = ctk.StringVar()
        self.selected_project = ctk.StringVar()
        self.selected_subfolder = ctk.StringVar()
        self.project_map = {}
        
        self.load_project_map()
        self.load_base_path()

        self.create_widgets()
        
        if self.base_config_path.get():
            self.refresh_project_list()

    def create_widgets(self):
        main_frame = ctk.CTkFrame(self, corner_radius=10)
        # La constante tk.BOTH ahora es reconocida
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- 1. Ruta Base ---
        base_path_frame = ctk.CTkFrame(main_frame)
        base_path_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ctk.CTkLabel(base_path_frame, text="1. Carpeta Base de Configs:", font=ctk.CTkFont(weight="bold")).pack(anchor=tk.W, padx=10, pady=(5,0))
        
        entry_frame = ctk.CTkFrame(base_path_frame, fg_color="transparent")
        entry_frame.pack(fill=tk.X, padx=10, pady=(5,10))
        
        self.entry_base_path = ctk.CTkEntry(entry_frame, textvariable=self.base_config_path, state="disabled", width=350)
        self.entry_base_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        ctk.CTkButton(entry_frame, text="Cambiar", width=100, command=self.select_base_path).pack(side=tk.RIGHT, padx=5)

        # Botón de Sincronizar
        ctk.CTkButton(
            entry_frame, 
            text="Sincronizar Repos 🔄", 
            width=150, 
            command=self.launch_sync_script,
            fg_color="#4a4a4a",
            hover_color="#333333"
        ).pack(side=tk.RIGHT)

        # --- 2. Selección ---
        selection_frame = ctk.CTkFrame(main_frame)
        selection_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ctk.CTkLabel(selection_frame, text="2. Seleccionar Configuración:", font=ctk.CTkFont(weight="bold")).pack(anchor=tk.W, padx=10, pady=(5,0))

        lists_frame = ctk.CTkFrame(selection_frame, fg_color="transparent")
        lists_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        project_col_frame = ctk.CTkFrame(lists_frame)
        project_col_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        ctk.CTkLabel(project_col_frame, text="Proyecto:").pack(pady=5)
        self.project_list_frame = ctk.CTkScrollableFrame(project_col_frame, height=200, border_width=1, border_color="gray50")
        self.project_list_frame.pack(fill=tk.X, expand=True, padx=5, pady=(0,5))
        self.project_buttons = {} 

        env_sub_col_frame = ctk.CTkFrame(lists_frame)
        env_sub_col_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        ctk.CTkLabel(env_sub_col_frame, text="Entorno:").pack(pady=5)
        self.env_combobox = ctk.CTkComboBox(env_sub_col_frame, values=["Preproduccion", "Produccion"], state="readonly", command=self.on_env_select)
        self.env_combobox.set("Preproduccion")
        self.env_combobox.pack(fill=tk.X, padx=5, pady=(0, 10))

        ctk.CTkLabel(env_sub_col_frame, text="Subcarpeta Específica:").pack(pady=5)
        self.subfolder_list_frame = ctk.CTkScrollableFrame(env_sub_col_frame, height=148, border_width=1, border_color="gray50")
        self.subfolder_list_frame.pack(fill=tk.X, expand=True, padx=5, pady=(0,5))
        self.subfolder_buttons = {}

        # --- 3. Destino ---
        target_frame = ctk.CTkFrame(main_frame)
        target_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ctk.CTkLabel(target_frame, text="3. Carpeta de Destino (Enlace):", font=ctk.CTkFont(weight="bold")).pack(anchor=tk.W, padx=10, pady=(5,0))
        
        entry_frame_target = ctk.CTkFrame(target_frame, fg_color="transparent")
        entry_frame_target.pack(fill=tk.X, padx=10, pady=(5,10))
        
        self.entry_target_path = ctk.CTkEntry(entry_frame_target, textvariable=self.target_project_path, state="disabled", width=450)
        self.entry_target_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        ctk.CTkButton(entry_frame_target, text="Asociar", width=100, command=self.select_target_project).pack(side=tk.RIGHT)

        # --- 4. Acción ---
        action_frame = ctk.CTkFrame(main_frame)
        action_frame.pack(fill=tk.X, padx=10, pady=10)

        self.status_label = ctk.CTkLabel(action_frame, text="Selecciona una configuración para aplicar.", text_color="gray", wraplength=500)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=5)
        
        self.btn_apply = ctk.CTkButton(action_frame, text="Aplicar Configuración", command=self.apply_config, height=40, font=ctk.CTkFont(weight="bold"))
        self.btn_apply.pack(side=tk.RIGHT, padx=10, pady=10)

    # --- Funciones de Carga y Guardado ---
    def load_base_path(self):
        try:
            if CONFIG_PATH_FILE.exists():
                path = CONFIG_PATH_FILE.read_text().strip()
                if Path(path).is_dir():
                    self.base_config_path.set(path)
                else:
                    self.status_label.configure(text="Ruta guardada no válida.", text_color="orange")
        except Exception as e:
            self.show_error(f"Error al leer {CONFIG_PATH_FILE.name}: {e}")

    def save_base_path(self):
        try:
            CONFIG_PATH_FILE.write_text(self.base_config_path.get())
        except Exception as e:
            self.show_error(f"Error al guardar {CONFIG_PATH_FILE.name}: {e}")

    def load_project_map(self):
        try:
            if PROJECT_MAP_FILE.exists():
                with open(PROJECT_MAP_FILE, 'r') as f:
                    content = f.read()
                    if content:
                        self.project_map = json.loads(content)
        except Exception as e:
            self.show_error(f"Error al leer {PROJECT_MAP_FILE.name}: {e}")
            self.project_map = {}

    def save_project_map(self):
        try:
            with open(PROJECT_MAP_FILE, 'w') as f:
                json.dump(self.project_map, f, indent=4)
        except Exception as e:
            self.show_error(f"Error al guardar {PROJECT_MAP_FILE.name}: {e}")

    # --- Funciones de Lógica de UI ---
    def select_base_path(self):
        path = filedialog.askdirectory(title="Selecciona la carpeta base de CONFIGURACIONES")
        if path:
            self.base_config_path.set(path)
            self.save_base_path()
            self.refresh_project_list()
            self.status_label.configure(text="Ruta base actualizada.", text_color="gray")

    def clear_scrollable_frame(self, frame):
        for widget in frame.winfo_children():
            widget.destroy()

    def refresh_project_list(self):
        self.clear_scrollable_frame(self.project_list_frame)
        self.project_buttons.clear()
        base_path = Path(self.base_config_path.get())
        if not base_path.is_dir():
            return

        projects = set()
        regex = re.compile(r"^(.*?)[-_]Config[-_]?(Preprod|Prod)$", re.IGNORECASE)
        
        try:
            for item in base_path.iterdir():
                if item.is_dir():
                    match = regex.match(item.name)
                    if match:
                        projects.add(match.group(1))
            
            if not projects:
                self.status_label.configure(text="No se encontraron proyectos en la ruta base.", text_color="orange")
                return

            for project in sorted(list(projects)):
                btn = ctk.CTkButton(
                    self.project_list_frame, 
                    text=project, 
                    fg_color="transparent", 
                    text_color=("gray10", "gray90"), 
                    hover_color=("gray85", "gray20"),
                    command=lambda p=project: self.on_project_select(p)
                )
                btn.pack(fill=tk.X, padx=2, pady=2)
                self.project_buttons[project] = btn
            
            self.status_label.configure(text="Proyectos cargados. Selecciona uno.", text_color="gray")
        except Exception as e:
            self.show_error(f"Error escaneando proyectos: {e}")

    def on_project_select(self, project_name):
        self.selected_project.set(project_name)
        
        for name, btn in self.project_buttons.items():
            if name == project_name:
                btn.configure(fg_color=("gray80", "gray30"))
            else:
                btn.configure(fg_color="transparent")

        if project_name in self.project_map:
            self.target_project_path.set(self.project_map[project_name])
        else:
            self.target_project_path.set("--- NINGUNA ASOCIACIÓN ---")
        
        self.refresh_subfolder_list()

    def on_env_select(self, event=None):
        self.refresh_subfolder_list()

    def refresh_subfolder_list(self):
        self.clear_scrollable_frame(self.subfolder_list_frame)
        self.subfolder_buttons.clear()
        self.selected_subfolder.set("") 
        
        selected_project = self.selected_project.get()
        selected_env = self.env_combobox.get()
        
        if not selected_project or not selected_env:
            return

        env_key = "Preprod" if selected_env == "Preproduccion" else "Prod"
        base_path = Path(self.base_config_path.get())
        
        patterns_to_try = [
            f"{selected_project}-Config-{env_key}",
            f"{selected_project}_Config_{env_key}",
            f"{selected_project}-Config{env_key}",
            f"{selected_project}_Config{env_key}"
        ]
        
        config_folder = None
        for pattern in patterns_to_try:
            folder = base_path / pattern
            if folder.is_dir():
                config_folder = folder
                break

        if not config_folder:
            self.status_label.configure(text=f"No se encuentra carpeta para {selected_project} y {env_key}", text_color="orange")
            return

        subfolders = [f.name for f in config_folder.iterdir() if f.is_dir() and not f.name.startswith('.')]
        
        if not subfolders:
            subfolders = [".(Raíz)"]

        for folder in sorted(subfolders):
            btn = ctk.CTkButton(
                self.subfolder_list_frame, 
                text=folder, 
                fg_color="transparent", 
                text_color=("gray10", "gray90"), 
                hover_color=("gray85", "gray20"),
                command=lambda f=folder: self.on_subfolder_select(f)
            )
            btn.pack(fill=tk.X, padx=2, pady=2)
            self.subfolder_buttons[folder] = btn

    def on_subfolder_select(self, folder_name):
        self.selected_subfolder.set(folder_name)
        for name, btn in self.subfolder_buttons.items():
            if name == folder_name:
                btn.configure(fg_color=("gray80", "gray30"))
            else:
                btn.configure(fg_color="transparent")

    def select_target_project(self):
        selected_project = self.selected_project.get()
        if not selected_project:
            self.show_error("Selecciona un proyecto de la lista primero.")
            return

        path = filedialog.askdirectory(title=f"Selecciona la carpeta RAÍZ de {selected_project} (donde buscar Program.cs o package.json)")
        if path:
            self.target_project_path.set(path)
            self.project_map[selected_project] = path
            self.save_project_map()
            self.status_label.configure(text=f"Asociación guardada para {selected_project}.", text_color="gray")

    # --- Nueva Función para lanzar el script de Sync ---
    def launch_sync_script(self):
        """
        Lanza el script sync_repos.py en una nueva ventana de terminal,
        pasándole la ruta base actual como argumento.
        """
        base_path = self.base_config_path.get()
        if not base_path or not Path(base_path).is_dir():
            self.show_error("Selecciona una Carpeta Base de Configs válida primero.")
            return

        sync_script_path = SCRIPT_DIR / "sync_repos.py"
        
        if not sync_script_path.exists():
            self.show_error(f"Error: No se encuentra el script 'sync_repos.py' en la carpeta:\n{SCRIPT_DIR}")
            return
            
        command = [sys.executable, str(sync_script_path), base_path]

        try:
            if sys.platform == "win32":
                subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_CONSOLE)
                self.status_label.configure(text="Iniciando sincronización en nueva ventana...", text_color="gray")
            else:
                subprocess.Popen(command) 
                
        except Exception as e:
            self.show_error(f"Error al lanzar el script de sincronización:\n{e}")

    # --- Función de Aplicar Config ---
    def apply_config(self):
        selected_project = self.selected_project.get()
        selected_env = self.env_combobox.get()
        selected_subfolder = self.selected_subfolder.get()

        if not all([selected_project, selected_env, selected_subfolder]):
            self.show_error("Selección incompleta. Debes elegir Proyecto, Entorno y Subcarpeta.")
            return

        target_project_root = Path(self.target_project_path.get())
        if not target_project_root.is_dir() or "NINGUNA" in str(target_project_root):
            self.show_error(f"No hay una carpeta de destino válida asociada para {selected_project}. Usa 'Asociar'.")
            return

        env_key = "Preprod" if selected_env == "Preproduccion" else "Prod"
        base_path = Path(self.base_config_path.get())
        
        patterns_to_try = [
            f"{selected_project}-Config-{env_key}",
            f"{selected_project}_Config_{env_key}",
            f"{selected_project}-Config{env_key}",
            f"{selected_project}_Config{env_key}"
        ]
        
        config_folder = None
        for pattern in patterns_to_try:
            folder = base_path / pattern
            if folder.is_dir():
                config_folder = folder
                break
        
        if not config_folder:
            self.show_error(f"No se encontró la carpeta de configuración para {selected_project} y {env_key}.")
            return

        source_folder = config_folder
        if selected_subfolder != ".(Raíz)":
            source_folder = config_folder / selected_subfolder

        if not source_folder.is_dir():
            self.show_error(f"La subcarpeta de origen '{source_folder}' no existe.")
            return

        source_file = None
        destination_filename = None
        anchor_file = None 
        try:
            source_file = next(source_folder.glob("appsettings*.json"))
            destination_filename = 'appsettings.json'
            anchor_file = 'Program.cs'
        except StopIteration:
            try:
                source_file = next(source_folder.glob(".env"))
                destination_filename = '.env'
                anchor_file = 'package.json' 
            except StopIteration:
                self.show_error(f"No se encontró 'appsettings*.json' ni '.env' en '{source_folder}'")
                return

        try:
            anchor_file_path = next(target_project_root.rglob(anchor_file))
            final_destination_dir = anchor_file_path.parent
        except StopIteration:
            self.show_error(f"No se encontró el archivo '{anchor_file}' dentro de '{target_project_root}'.")
            return
            
        destination_file = final_destination_dir / destination_filename

        try:
            shutil.copy2(source_file, destination_file)
            success_msg = f"Copiado: {source_file.name} -> {destination_file}"
            self.status_label.configure(text=success_msg, text_color="lightgreen")
            messagebox.showinfo("Éxito", f"Configuración aplicada correctamente.\n\nDesde: {source_file}\n\nHacia: {destination_file}")
        except Exception as e:
            self.show_error(f"Error al copiar el archivo: {e}")

    # --- Utilidades ---
    def show_error(self, message):
        messagebox.showerror("Error", message)
        self.status_label.configure(text=f"Error: {message}", text_color="red")

if __name__ == "__main__":
    if "PYINSTALLER_VER" in os.environ:
        ctk.set_appearance_mode(ctk.get_appearance_mode())

    app = ConfigSwitcherApp()
    app.mainloop()