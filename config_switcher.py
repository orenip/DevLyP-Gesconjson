import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import re
import json
import shutil
from pathlib import Path

# Constantes para los archivos de configuración
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH_FILE = SCRIPT_DIR / ".configpath.txt"
PROJECT_MAP_FILE = SCRIPT_DIR / "projectmap.json"

class ConfigSwitcherApp(tk.Tk):
    """
    Aplicación visual para gestionar y aplicar configuraciones de appsettings.json
    replicando la lógica del script de PowerShell.
    """
    
    def __init__(self):
        super().__init__()
        self.title("Gestor de Configuraciones")
        self.geometry("600x650")
        self.resizable(False, False)

        # Variables de estado
        self.base_config_path = tk.StringVar()
        self.target_project_path = tk.StringVar()
        self.project_map = {}
        
        # Cargar datos iniciales
        self.load_project_map()
        self.load_base_path()

        # Configurar la UI
        self.create_widgets()
        
        # Poblar la lista de proyectos si ya tenemos una ruta base
        if self.base_config_path.get():
            self.refresh_project_list()

    def create_widgets(self):
        """Crea y organiza todos los widgets de la interfaz."""
        
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- 1. Selección de Ruta Base ---
        base_path_frame = ttk.LabelFrame(main_frame, text="1. Carpeta Base de Configuraciones", padding="10")
        base_path_frame.pack(fill=tk.X, pady=5)
        
        entry_base_path = ttk.Entry(base_path_frame, textvariable=self.base_config_path, state="readonly", width=70)
        entry_base_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        btn_select_base = ttk.Button(base_path_frame, text="Cambiar", command=self.select_base_path)
        btn_select_base.pack(side=tk.RIGHT)

        # --- 2. Selección de Configuración ---
        selection_frame = ttk.LabelFrame(main_frame, text="2. Seleccionar Configuración", padding="10")
        selection_frame.pack(fill=tk.X, pady=5)

        # Proyectos
        ttk.Label(selection_frame, text="Proyecto:").pack(anchor=tk.W)
        self.project_listbox = tk.Listbox(selection_frame, height=8, exportselection=False)
        self.project_listbox.pack(fill=tk.X, expand=True, pady=(0, 10))
        self.project_listbox.bind("<<ListboxSelect>>", self.on_project_select)

        # Entorno y Subcarpeta (en un frame horizontal)
        env_sub_frame = ttk.Frame(selection_frame)
        env_sub_frame.pack(fill=tk.X, expand=True)

        # Entorno
        env_frame = ttk.Frame(env_sub_frame)
        env_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Label(env_frame, text="Entorno:").pack(anchor=tk.W)
        self.env_combobox = ttk.Combobox(env_frame, values=["Preproduccion", "Produccion"], state="readonly")
        self.env_combobox.pack(fill=tk.X)
        self.env_combobox.bind("<<ComboboxSelected>>", self.on_env_select)

        # Subcarpeta
        sub_frame = ttk.Frame(env_sub_frame)
        sub_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))
        ttk.Label(sub_frame, text="Subcarpeta Específica:").pack(anchor=tk.W)
        self.subfolder_listbox = tk.Listbox(sub_frame, height=5, exportselection=False)
        self.subfolder_listbox.pack(fill=tk.X)

        # --- 3. Destino ---
        target_frame = ttk.LabelFrame(main_frame, text="3. Carpeta de Destino del Proyecto (Enlace)", padding="10")
        target_frame.pack(fill=tk.X, pady=5)

        entry_target_path = ttk.Entry(target_frame, textvariable=self.target_project_path, state="readonly", width=70)
        entry_target_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        btn_select_target = ttk.Button(target_frame, text="Asociar", command=self.select_target_project)
        btn_select_target.pack(side=tk.RIGHT)

        # --- 4. Acción ---
        action_frame = ttk.Frame(main_frame, padding="10")
        action_frame.pack(fill=tk.X)

        self.status_label = ttk.Label(action_frame, text="Selecciona una configuración para aplicar.", anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        btn_apply = ttk.Button(action_frame, text="Aplicar Configuración", command=self.apply_config)
        btn_apply.pack(side=tk.RIGHT)

    # --- Funciones de Carga y Guardado ---

    def load_base_path(self):
        """Carga la ruta base desde .configpath.txt"""
        try:
            if CONFIG_PATH_FILE.exists():
                path = CONFIG_PATH_FILE.read_text().strip()
                if Path(path).is_dir():
                    self.base_config_path.set(path)
                else:
                    self.status_label.config(text="Ruta guardada no válida.")
        except Exception as e:
            self.show_error(f"Error al leer {CONFIG_PATH_FILE.name}: {e}")

    def save_base_path(self):
        """Guarda la ruta base en .configpath.txt"""
        try:
            CONFIG_PATH_FILE.write_text(self.base_config_path.get())
        except Exception as e:
            self.show_error(f"Error al guardar {CONFIG_PATH_FILE.name}: {e}")

    def load_project_map(self):
        """Carga el mapeo de proyectos desde projectmap.json"""
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
        """Guarda el mapeo de proyectos en projectmap.json"""
        try:
            with open(PROJECT_MAP_FILE, 'w') as f:
                json.dump(self.project_map, f, indent=4)
        except Exception as e:
            self.show_error(f"Error al guardar {PROJECT_MAP_FILE.name}: {e}")

    # --- Funciones de Lógica de UI ---

    def select_base_path(self):
        """Abre el diálogo para seleccionar la carpeta base."""
        path = filedialog.askdirectory(title="Selecciona la carpeta base de CONFIGURACIONES")
        if path:
            self.base_config_path.set(path)
            self.save_base_path()
            self.refresh_project_list()
            self.status_label.config(text="Ruta base actualizada.")

    def refresh_project_list(self):
        """Escanea la carpeta base y actualiza la lista de proyectos."""
        self.project_listbox.delete(0, tk.END)
        base_path = Path(self.base_config_path.get())
        if not base_path.is_dir():
            return

        projects = set()
        # Regex para encontrar carpetas como:
        # Project-Config-Preprod, Project_Config_Preprod, Project_ConfigPreprod
        regex = re.compile(r"^(.*?)[-_]Config[-_]?(Preprod|Prod)$", re.IGNORECASE)
        
        try:
            for item in base_path.iterdir():
                if item.is_dir():
                    match = regex.match(item.name)
                    if match:
                        projects.add(match.group(1))
            
            if not projects:
                self.status_label.config(text="No se encontraron proyectos en la ruta base.")
                return

            for project in sorted(list(projects)):
                self.project_listbox.insert(tk.END, project)
            self.status_label.config(text="Proyectos cargados. Selecciona uno.")
        except Exception as e:
            self.show_error(f"Error escaneando proyectos: {e}")

    def on_project_select(self, event=None):
        """Maneja la selección de un proyecto."""
        try:
            selected_project = self.project_listbox.get(self.project_listbox.curselection())
        except tk.TclError:
            return  # No hay selección

        # Actualizar la ruta de destino enlazada
        if selected_project in self.project_map:
            self.target_project_path.set(self.project_map[selected_project])
        else:
            self.target_project_path.set("--- NINGUNA ASOCIACIÓN ---")
        
        self.refresh_subfolder_list()

    def on_env_select(self, event=None):
        """Maneja la selección de un entorno."""
        self.refresh_subfolder_list()

    def refresh_subfolder_list(self):
        """Actualiza la lista de subcarpetas basado en proyecto y entorno."""
        self.subfolder_listbox.delete(0, tk.END)
        
        try:
            selected_project = self.project_listbox.get(self.project_listbox.curselection())
            selected_env = self.env_combobox.get()
        except tk.TclError:
            return # Aún no se ha seleccionado proyecto
        
        if not selected_project or not selected_env:
            return

        env_key = "Preprod" if selected_env == "Preproduccion" else "Prod"
        base_path = Path(self.base_config_path.get())
        
        # Encontrar la carpeta de config exacta (ej: ProjectA_Config_Prod)
        # Probamos varios patrones comunes
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
            self.status_label.config(text=f"No se encuentra carpeta para {selected_project} y {env_key}")
            return

        # Buscar subcarpetas (ignorando las que empiezan por '.')
        subfolders = [f.name for f in config_folder.iterdir() if f.is_dir() and not f.name.startswith('.')]
        
        if not subfolders:
            self.subfolder_listbox.insert(tk.END, ".(Raíz)") # Usar la raíz
        else:
            for folder in sorted(subfolders):
                self.subfolder_listbox.insert(tk.END, folder)

    def select_target_project(self):
        """Asocia un proyecto de la lista con una carpeta de destino."""
        try:
            selected_project = self.project_listbox.get(self.project_listbox.curselection())
        except tk.TclError:
            self.show_error("Selecciona un proyecto de la lista primero.")
            return

        path = filedialog.askdirectory(title=f"Selecciona la carpeta RAÍZ de {selected_project} (donde buscar Program.cs)")
        if path:
            self.target_project_path.set(path)
            self.project_map[selected_project] = path
            self.save_project_map()
            self.status_label.config(text=f"Asociación guardada para {selected_project}.")

    def apply_config(self):
        """Función principal: Valida y copia el archivo appsettings.json."""
        
        # --- 1. Validar selecciones ---
        try:
            selected_project = self.project_listbox.get(self.project_listbox.curselection())
            selected_env = self.env_combobox.get()
            selected_subfolder = self.subfolder_listbox.get(self.subfolder_listbox.curselection())
        except tk.TclError:
            self.show_error("Selección incompleta. Debes elegir Proyecto, Entorno y Subcarpeta.")
            return

        if not all([selected_project, selected_env, selected_subfolder]):
            self.show_error("Selección incompleta. Faltan datos.")
            return

        # --- 2. Obtener ruta de destino ---
        target_project_root = Path(self.target_project_path.get())
        if not target_project_root.is_dir() or "NINGUNA" in str(target_project_root):
            self.show_error(f"No hay una carpeta de destino válida asociada para {selected_project}. Usa 'Asociar'.")
            return

        # --- 3. Encontrar carpeta de origen ---
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

        # --- 4. Encontrar subcarpeta de origen ---
        source_folder = config_folder
        if selected_subfolder != ".(Raíz)":
            source_folder = config_folder / selected_subfolder

        if not source_folder.is_dir():
            self.show_error(f"La subcarpeta de origen '{source_folder}' no existe.")
            return

        # --- 5. Encontrar el appsettings.json de origen ---
        try:
            # Busca appsettings*.json y coge el primero
            source_file = next(source_folder.glob("appsettings*.json"))
        except StopIteration:
            self.show_error(f"No se encontró ningún archivo appsettings*.json en '{source_folder}'")
            return

        # --- 6. Encontrar la carpeta de destino (donde está Program.cs) ---
        try:
            # Busca recursivamente Program.cs
            program_cs_file = next(target_project_root.rglob("Program.cs"))
            final_destination_dir = program_cs_file.parent
        except StopIteration:
            self.show_error(f"No se encontró Program.cs dentro de '{target_project_root}'.")
            return
            
        destination_file = final_destination_dir / "appsettings.json"

        # --- 7. Copiar el archivo ---
        try:
            shutil.copy2(source_file, destination_file)
            success_msg = f"Copiado: {source_file.name} -> {destination_file}"
            self.status_label.config(text=success_msg)
            messagebox.showinfo("Éxito", f"Configuración aplicada correctamente.\n\nDesde: {source_file}\n\nHacia: {destination_file}")
        except Exception as e:
            self.show_error(f"Error al copiar el archivo: {e}")

    # --- Utilidades ---
    def show_error(self, message):
        """Muestra un mensaje de error en un popup y en la etiqueta de estado."""
        messagebox.showerror("Error", message)
        self.status_label.config(text=f"Error: {message}")


if __name__ == "__main__":
    app = ConfigSwitcherApp()
    app.mainloop()