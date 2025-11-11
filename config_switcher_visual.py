import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import re
import json
from pathlib import Path
import sys
import subprocess
import threading
import shutil

# ===================== Config UI =====================
APP_DATA_PATH = Path(os.environ['APPDATA']) / "ConfigSwitcher"
APP_DATA_PATH.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = APP_DATA_PATH / "config.json"

NEUTRAL_COLOR = ("gray10", "gray90")
SUCCESS_COLOR = ("#15803d", "#22c55e")
ERROR_COLOR   = ("#B00020", "#FF4C4C")
WARNING_COLOR = ("#E69B00", "#FFA500")
SELECTED_FG_COLOR = ("#3a7ebf", "#1f538d")
SELECTED_TEXT_COLOR = "#FFFFFF"

HIDE_BAR_ON_FINISH = False

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


# ---------- util para recursos (icono con/ sin PyInstaller) ----------
def resource_path(relative: str) -> str:
    try:
        base = sys._MEIPASS  # PyInstaller
    except Exception:
        base = os.path.abspath(".")
    return os.path.join(base, relative)


# ---------- ejecutar git con salida en streaming + cancelación ----------
def _kill_process_tree_windows(pid: int):
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def run_git_stream(cmd: list[str], cwd: Path, env: dict, startupinfo, on_line, stop_event: threading.Event | None = None):
    """
    Ejecuta git y llama on_line por cada línea (stdout y stderr).
    Si stop_event está seteado, intenta terminar el proceso.
    """
    proc = subprocess.Popen(
        cmd, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", bufsize=1,
        env=env, startupinfo=startupinfo
    )

    def pump(stream):
        if not stream:
            return
        for raw in stream:
            if stop_event is not None and stop_event.is_set():
                break
            if raw is None:
                continue
            # Normaliza CR y asegura saltos
            line = raw.replace("\r", "\n")
            for chunk in line.split("\n"):
                if chunk.strip():
                    on_line(chunk)

    try:
        pump(proc.stdout)
        pump(proc.stderr)
    finally:
        if stop_event is not None and stop_event.is_set():
            try:
                proc.terminate()
            except Exception:
                pass
            if sys.platform.startswith("win"):
                _kill_process_tree_windows(proc.pid)
    try:
        return proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        # si se canceló, devuelve código no-cero para abortar flujo
        return 1


# ===================== Ventana de progreso =====================
class ProgressDialog(ctk.CTkToplevel):
    def __init__(self, master, total_repos: int, stop_event: threading.Event,  on_close=None):
        super().__init__(master)
        self._on_close_cb = on_close  # <-- guarda callback
        self.title("Sincronizando repos...")
        self.geometry("820x520")
        self.resizable(True, True)
        self._can_close = False
        self._alive = True
        self._stop_event = stop_event

        try:
            ico = resource_path("app.ico")
            if os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

        self.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self.bind("<Escape>", lambda e: self._try_close())

        ctk.CTkLabel(
            self, text=f"Sincronizando {total_repos} repositorios...",
            font=ctk.CTkFont(weight="bold", size=14)
        ).pack(anchor="w", padx=12, pady=(12, 6))

        self.progress = ctk.CTkProgressBar(self, mode="determinate", progress_color="#3a7ebf")
        self.progress.pack(fill="x", padx=12)
        self.progress.set(0.0)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(2, 8))
        self.counter_var = tk.StringVar(value="0 / 0")
        ctk.CTkLabel(head, textvariable=self.counter_var).pack(side="right")

        self.log = ctk.CTkTextbox(self, wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=8)
        self.log.configure(state="disabled")

        bottom = ctk.CTkFrame(self)
        bottom.pack(fill="x", padx=12, pady=8)
        self.btn_cancel = ctk.CTkButton(
            bottom, text="Cancelar", command=self._on_cancel,
            fg_color="#B00020", hover_color="#8A0019"
        )
        self.btn_cancel.pack(side="right")

    # ---- helpers seguros ----
    def _is_alive(self) -> bool:
        try:
            return self._alive and self.winfo_exists()
        except Exception:
            return False

    def safe_after(self, ms: int, fn, *args, **kwargs):
        if self._is_alive():
            try:
                self.after(ms, fn, *args, **kwargs)
            except Exception:
                pass

    # ---- API de escritura ----
    def write(self, text: str):
        if not self._is_alive():
            return
        self.log.configure(state="normal")
        if not text.endswith("\n"):
            text += "\n"
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def write_section(self, title: str):
        sep = "─" * max(20, len(title) + 4)
        self.write(f"\n{sep}\n📦 {title}\n{sep}")

    def write_ok(self, text: str):   self.write(f"✅ {text}")
    def write_info(self, text: str): self.write(f"🔎 {text}")
    def write_push(self, text: str): self.write(f"📤 {text}")
    def write_pull(self, text: str): self.write(f"📥 {text}")
    def write_warn(self, text: str): self.write(f"⚠️ {text}")
    def write_err(self, text: str):  self.write(f"❌ {text}")

    def set_counter(self, done: int, total: int):
        if not self._is_alive():
            return
        self.counter_var.set(f"{done} / {total}")
        if total > 0:
            self.progress.set(min(1.0, max(0.0, done / total)))

    # ---- cancelar / cerrar ----
    def _on_cancel(self):
        # Señal global de parada
        self._stop_event.set()
        # Permite cerrar ya mismo
        self.allow_close()
        self.write_warn("Cancelación solicitada. Puedes cerrar esta ventana.")

    def allow_close(self):
        if not self._is_alive():
            return
        self._can_close = True
        try:
            self.btn_cancel.configure(
                text="Cerrar",
                state="normal",
                fg_color="#3f3f46",
                hover_color="#2d2d31",
                command=self._try_close
            )
        except Exception:
            pass

    def _try_close(self):
        if self._can_close and self._is_alive():
            self._alive = False
            # avisa al padre para que habilite botones
            try:
                if callable(self._on_close_cb):
                    self._on_close_cb()
            except Exception:
                pass
            # cierra ventana
            try:
                self.destroy()
            except Exception:
                pass

            if self._can_close and self._is_alive():
                self._alive = False
                try:
                    self.destroy()
                except Exception:
                    pass

    def _on_close_request(self):
        # Si aún no se puede cerrar, convierte el click en "cancelar"
        if not self._can_close:
            self._on_cancel()
        else:
            self._try_close()

    # ---- final de trabajo ----
    def finish_ok(self, text: str = "Sincronización completada."):
        if HIDE_BAR_ON_FINISH:
            self.progress.pack_forget()
        else:
            self.progress.set(1.0)
            self.progress.configure(progress_color="#22c55e")
        self.write_ok(text)
        self.allow_close()

    def finish_warn(self, text: str = "Finalizado con avisos/errores."):
        if HIDE_BAR_ON_FINISH:
            self.progress.pack_forget()
        else:
            self.progress.set(1.0)
            self.progress.configure(progress_color="#eab308")
        self.write_warn(text)
        self.allow_close()


# ===================== App principal =====================
class ConfigSwitcherApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Gestor de Configuraciones")
        self.geometry("700x750")
        self.resizable(False, False)
        try:
            ico = resource_path("app.ico")
            if os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

        self.base_config_path = ctk.StringVar()
        self.target_project_path = ctk.StringVar()
        self.selected_project = ctk.StringVar()
        self.selected_subfolder = ctk.StringVar()

        self.config = {}
        self.project_map = {}
        self.sync_stop = threading.Event()   # <-- evento de cancelación

        self.load_app_config()
        self.create_widgets()

        if self.base_config_path.get():
            self.refresh_project_list()

    # ---------- UI ----------
    def create_widgets(self):
        main_frame = ctk.CTkFrame(self, corner_radius=10)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        base_path_frame = ctk.CTkFrame(main_frame)
        base_path_frame.pack(fill=tk.X, padx=10, pady=10)
        ctk.CTkLabel(base_path_frame, text="1. Carpeta Base de Configs:",
                     font=ctk.CTkFont(weight="bold")).pack(anchor=tk.W, padx=10, pady=(5, 0))
        entry_frame = ctk.CTkFrame(base_path_frame, fg_color="transparent")
        entry_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

        self.entry_base_path = ctk.CTkEntry(entry_frame, textvariable=self.base_config_path,
                                            state="disabled", width=350)
        self.entry_base_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ctk.CTkButton(entry_frame, text="Cambiar", width=100,
                      command=self.select_base_path).pack(side=tk.RIGHT, padx=5)

        self.btn_sync = ctk.CTkButton(
            entry_frame, text="Sincronizar Repos 🔄", width=150,
            command=self.start_sync_thread, fg_color="#4a4a4a", hover_color="#333333"
        )
        self.btn_sync.pack(side=tk.RIGHT)

        selection_frame = ctk.CTkFrame(main_frame)
        selection_frame.pack(fill=tk.X, padx=10, pady=5)
        ctk.CTkLabel(selection_frame, text="2. Seleccionar Configuración:",
                     font=ctk.CTkFont(weight="bold")).pack(anchor=tk.W, padx=10, pady=(5, 0))

        lists_frame = ctk.CTkFrame(selection_frame, fg_color="transparent")
        lists_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        project_col_frame = ctk.CTkFrame(lists_frame)
        project_col_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        ctk.CTkLabel(project_col_frame, text="Proyecto:").pack(pady=5)
        self.project_list_frame = ctk.CTkScrollableFrame(project_col_frame, height=200,
                                                         border_width=1, border_color="gray50")
        self.project_list_frame.pack(fill=tk.X, expand=True, padx=5, pady=(0, 5))
        self.project_buttons = {}

        env_sub_col_frame = ctk.CTkFrame(lists_frame)
        env_sub_col_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        ctk.CTkLabel(env_sub_col_frame, text="Entorno:").pack(pady=5)
        self.env_combobox = ctk.CTkComboBox(env_sub_col_frame,
                                            values=["Preproduccion", "Produccion"],
                                            state="readonly", command=self.on_env_select)
        self.env_combobox.set("Preproduccion")
        self.env_combobox.pack(fill=tk.X, padx=5, pady=(0, 10))

        ctk.CTkLabel(env_sub_col_frame, text="Subcarpeta Específica:").pack(pady=5)
        self.subfolder_list_frame = ctk.CTkScrollableFrame(env_sub_col_frame, height=148,
                                                           border_width=1, border_color="gray50")
        self.subfolder_list_frame.pack(fill=tk.X, expand=True, padx=5, pady=(0, 5))
        self.subfolder_buttons = {}

        target_frame = ctk.CTkFrame(main_frame)
        target_frame.pack(fill=tk.X, padx=10, pady=5)
        ctk.CTkLabel(target_frame, text="3. Carpeta de Destino (Enlace):",
                     font=ctk.CTkFont(weight="bold")).pack(anchor=tk.W, padx=10, pady=(5, 0))
        entry_frame_target = ctk.CTkFrame(target_frame, fg_color="transparent")
        entry_frame_target.pack(fill=tk.X, padx=10, pady=(5, 10))
        self.entry_target_path = ctk.CTkEntry(entry_frame_target, textvariable=self.target_project_path,
                                              state="disabled", width=450)
        self.entry_target_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ctk.CTkButton(entry_frame_target, text="Asociar", width=100,
                      command=self.select_target_project).pack(side=tk.RIGHT)

        action_frame = ctk.CTkFrame(main_frame)
        action_frame.pack(fill=tk.X, padx=10, pady=10)
        self.status_label = ctk.CTkLabel(action_frame,
                                         text="Selecciona una configuración para aplicar.",
                                         text_color=NEUTRAL_COLOR, wraplength=500)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=5)
        self.btn_apply = ctk.CTkButton(action_frame, text="Aplicar Configuración",
                                       command=self.apply_config, height=40,
                                       font=ctk.CTkFont(weight="bold"))
        self.btn_apply.pack(side=tk.RIGHT, padx=10, pady=10)

    # ---------- Habilitar / deshabilitar UI ----------
    def enable_main_buttons(self):
        # Rehabilita botones de la ventana principal
        self.btn_sync.configure(state="normal")
        self.btn_apply.configure(state="normal")

    # ---------- Persistencia ----------
    def load_app_config(self):
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r') as f:
                    self.config = json.load(f)
            self.config.setdefault("base_config_path", "")
            self.config.setdefault("project_map", {})
            self.base_config_path.set(self.config["base_config_path"])
            self.project_map = self.config["project_map"]
        except Exception as e:
            self.show_error(f"Error al leer {CONFIG_FILE.name}: {e}")
            self.config = {"base_config_path": "", "project_map": {}}
            self.project_map = self.config["project_map"]

    def save_app_config(self):
        try:
            self.config["base_config_path"] = self.base_config_path.get()
            self.config["project_map"] = self.project_map
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            self.show_error(f"Error al guardar {CONFIG_FILE.name}: {e}")

    # ---------- Lógica UI ----------
    def select_base_path(self):
        path = filedialog.askdirectory(title="Selecciona la carpeta base de CONFIGURACIONES")
        if path:
            self.base_config_path.set(path)
            self.save_app_config()
            self.refresh_project_list()
            self.status_label.configure(text="Ruta base actualizada.", text_color=NEUTRAL_COLOR)

    def select_target_project(self):
        selected_project = self.selected_project.get()
        if not selected_project:
            self.show_error("Selecciona un proyecto de la lista primero.")
            return
        path = filedialog.askdirectory(
            title=f"Selecciona la carpeta RAÍZ de {selected_project} (donde buscar Program.cs o package.json)"
        )
        if path:
            self.target_project_path.set(path)
            self.project_map[selected_project] = path
            self.save_app_config()
            self.status_label.configure(text=f"Asociación guardada para {selected_project}.",
                                        text_color=NEUTRAL_COLOR)

    def clear_scrollable_frame(self, frame):
        for widget in frame.winfo_children():
            widget.destroy()

    def refresh_project_list(self):
        self.clear_scrollable_frame(self.project_list_frame)
        self.project_buttons.clear()
        base_path = Path(self.base_config_path.get())
        if not base_path.is_dir():
            if self.base_config_path.get() != "":
                self.status_label.configure(text="La ruta base no es válida.", text_color=WARNING_COLOR)
            return

        projects = set()
        regex = re.compile(r"^(.*?)[-_]Config[-_]?(Preprod|Prod)$", re.IGNORECASE)
        try:
            for item in base_path.iterdir():
                if item.is_dir():
                    m = regex.match(item.name)
                    if m:
                        projects.add(m.group(1))
            if not projects:
                self.status_label.configure(text="No se encontraron proyectos en la ruta base.",
                                            text_color=WARNING_COLOR)
                return
            for project in sorted(projects):
                btn = ctk.CTkButton(
                    self.project_list_frame, text=project,
                    fg_color="transparent", text_color=NEUTRAL_COLOR,
                    hover_color=("gray85", "gray20"),
                    command=lambda p=project: self.on_project_select(p)
                )
                btn.pack(fill=tk.X, padx=2, pady=2)
                self.project_buttons[project] = btn
            self.status_label.configure(text="Proyectos cargados. Selecciona uno.",
                                        text_color=NEUTRAL_COLOR)
        except Exception as e:
            self.show_error(f"Error escaneando proyectos: {e}")

    def on_project_select(self, project_name):
        self.selected_project.set(project_name)
        for name, btn in self.project_buttons.items():
            if name == project_name:
                btn.configure(fg_color=SELECTED_FG_COLOR, text_color=SELECTED_TEXT_COLOR)
            else:
                btn.configure(fg_color="transparent", text_color=NEUTRAL_COLOR)
        self.target_project_path.set(self.project_map.get(project_name, "--- NINGUNA ASOCIACIÓN ---"))
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
        patterns = [
            f"{selected_project}-Config-{env_key}", f"{selected_project}_Config_{env_key}",
            f"{selected_project}-Config{env_key}", f"{selected_project}_Config{env_key}"
        ]
        config_folder = next((base_path / p for p in patterns if (base_path / p).is_dir()), None)
        if not config_folder:
            self.status_label.configure(text=f"No se encuentra carpeta para {selected_project} y {env_key}",
                                        text_color=WARNING_COLOR)
            return

        subfolders = [f.name for f in config_folder.iterdir() if f.is_dir() and not f.name.startswith('.')]
        if not subfolders:
            subfolders = [".(Raíz)"]
        for folder in sorted(subfolders):
            btn = ctk.CTkButton(
                self.subfolder_list_frame, text=folder, fg_color="transparent",
                text_color=NEUTRAL_COLOR, hover_color=("gray85", "gray20"),
                command=lambda f=folder: self.on_subfolder_select(f)
            )
            btn.pack(fill=tk.X, padx=2, pady=2)
            self.subfolder_buttons[folder] = btn

    def on_subfolder_select(self, folder_name):
        self.selected_subfolder.set(folder_name)
        for name, btn in self.subfolder_buttons.items():
            if name == folder_name:
                btn.configure(fg_color=SELECTED_FG_COLOR, text_color=SELECTED_TEXT_COLOR)
            else:
                btn.configure(fg_color="transparent", text_color=NEUTRAL_COLOR)

    # ---------- helpers ----------
    def update_status_from_thread(self, message, color):
        self.after(0, self.status_label.configure, {"text": message, "text_color": color})

    # ---------- Sync ----------
    def start_sync_thread(self):
        if not shutil.which("git"):
            self.show_error("Error: 'git.exe' no se encuentra.\n\nInstala Git y añade al PATH.")
            return
        base_path = self.base_config_path.get()
        if not base_path or not Path(base_path).is_dir():
            self.show_error("Selecciona una Carpeta Base de Configs válida primero.")
            return

        self.btn_sync.configure(state="disabled")
        self.btn_apply.configure(state="disabled")
        self.update_status_from_thread("Iniciando sincronización...", NEUTRAL_COLOR)

        git_dirs = []
        try:
            for root, dirs, files in os.walk(base_path):
                if ".git" in dirs:
                    git_dirs.append(Path(root) / ".git")
                    dirs[:] = [d for d in dirs if d != ".git"]
        except Exception as e:
            self.show_error(f"Error escaneando repos: {e}")
            self.btn_sync.configure(state="normal")
            self.btn_apply.configure(state="normal")
            return

        if not git_dirs:
            self.status_label.configure(text="No se encontraron repositorios Git.", text_color=WARNING_COLOR)
            self.btn_sync.configure(state="normal")
            self.btn_apply.configure(state="normal")
            return

        # reset evento de cancelación y abre ventana
        self.sync_stop.clear()
        self.progress_win = ProgressDialog(
            self,
            total_repos=len(git_dirs),
            stop_event=self.sync_stop,
            on_close=self.enable_main_buttons
        )

        threading.Thread(target=self._sync_streaming, args=(git_dirs,), daemon=True).start()

    def _sync_streaming(self, git_dirs: list[Path]):
        had_error = False
        try:
            total = len(git_dirs)
            done = 0

            git_env = os.environ.copy()
            git_env["GIT_TERMINAL_PROMPT"] = "0"
            git_env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"

            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            for i, git_dir in enumerate(git_dirs, start=1):
                if self.sync_stop.is_set():
                    break

                repo_dir = git_dir.parent
                name = repo_dir.name
                self.progress_win.safe_after(0, self.progress_win.write_section, name)
                self.update_status_from_thread(f"({i}/{total}) {name}: comprobando estado...", NEUTRAL_COLOR)
                self.progress_win.safe_after(0, self.progress_win.set_counter, i - 1, total)

                # status breve (sin volcar toda la salida)
                rc = run_git_stream(["git", "status", "--porcelain", "--untracked-files=normal"],
                                    repo_dir, git_env, startupinfo, lambda _: None, self.sync_stop)
                dirty = False
                if rc == 0 and not self.sync_stop.is_set():
                    status_out = subprocess.run(
                        ["git", "status", "--porcelain", "--untracked-files=normal"],
                        cwd=repo_dir, env=git_env, text=True, encoding="utf-8",
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo
                    )
                    dirty = bool(status_out.stdout.strip())

                try:
                    if self.sync_stop.is_set():
                        break

                    if dirty:
                        self.progress_win.safe_after(0, self.progress_win.write_info, "Cambios locales detectados → add/commit/push")
                        run_git_stream(["git", "add", "."], repo_dir, git_env, startupinfo,
                                       lambda l: self.progress_win.safe_after(0, self.progress_win.write, f"📝 {l}"),
                                       self.sync_stop)
                        has_staged = subprocess.run(
                            ["git", "diff", "--cached", "--quiet"],
                            cwd=repo_dir, env=git_env, startupinfo=startupinfo
                        ).returncode != 0
                        if has_staged and not self.sync_stop.is_set():
                            run_git_stream(["git", "commit", "-m", "update (auto-sync)"], repo_dir, git_env,
                                           startupinfo, lambda l: self.progress_win.safe_after(0, self.progress_win.write, f"🧷 {l}"),
                                           self.sync_stop)
                        if not self.sync_stop.is_set():
                            run_git_stream(["git", "push", "--progress"], repo_dir, git_env, startupinfo,
                                           lambda l: self.progress_win.safe_after(0, self.progress_win.write_push, l),
                                           self.sync_stop)
                        self.update_status_from_thread(f"({i}/{total}) {name}: push completado.", NEUTRAL_COLOR)
                        self.progress_win.safe_after(0, self.progress_win.write_ok, "Estado: push completado")
                    else:
                        self.progress_win.safe_after(0, self.progress_win.write_info, "Sin cambios locales → pull")
                        run_git_stream(["git", "pull", "--progress"], repo_dir, git_env, startupinfo,
                                       lambda l: self.progress_win.safe_after(0, self.progress_win.write_pull, l),
                                       self.sync_stop)
                        self.update_status_from_thread(f"({i}/{total}) {name}: up to date.", NEUTRAL_COLOR)
                        self.progress_win.safe_after(0, self.progress_win.write_ok, "Estado: up to date")

                except subprocess.CalledProcessError as e:
                    had_error = True
                    last = (e.stderr or "").strip().splitlines()[-1] if getattr(e, "stderr", None) else str(e)
                    self.progress_win.safe_after(0, self.progress_win.write_err, last)
                except Exception as ex:
                    had_error = True
                    self.progress_win.safe_after(0, self.progress_win.write_err, f"{type(ex).__name__}: {ex}")

                done += 1
                self.progress_win.safe_after(0, self.progress_win.set_counter, done, total)

            # finalización
            if self.sync_stop.is_set():
                self.progress_win.safe_after(0, self.progress_win.finish_warn, "Sincronización cancelada.")
            else:
                if had_error:
                    self.progress_win.safe_after(0, self.progress_win.finish_warn, "Finalizado con avisos/errores.")
                else:
                    self.progress_win.safe_after(0, self.progress_win.finish_ok, "Sincronización completada.")

        finally:
            self.after(0, self.btn_sync.configure, {"state": "normal"})
            self.after(0, self.btn_apply.configure, {"state": "normal"})
            if hasattr(self, "progress_win"):
                # por si hubo cualquier return temprano
                self.progress_win.safe_after(0, self.progress_win.allow_close)

    # ---------- Aplicar config ----------
    def apply_config(self):
        selected_project = self.selected_project.get()
        selected_env = self.env_combobox.get()
        selected_subfolder = self.selected_subfolder.get()

        if not all([selected_project, selected_env, selected_subfolder]):
            self.show_error("Selección incompleta. Debes elegir Proyecto, Entorno y Subcarpeta.")
            return

        target_root = Path(self.target_project_path.get())
        if not target_root.is_dir() or "NINGUNA" in str(target_root):
            self.show_error(f"No hay una carpeta de destino válida asociada para {selected_project}. Usa 'Asociar'.")
            return

        env_key = "Preprod" if selected_env == "Preproduccion" else "Prod"
        base_path = Path(self.base_config_path.get())
        patterns = [
            f"{selected_project}-Config-{env_key}", f"{selected_project}_Config_{env_key}",
            f"{selected_project}-Config{env_key}", f"{selected_project}_Config{env_key}"
        ]
        config_folder = next((base_path / p for p in patterns if (base_path / p).is_dir()), None)
        if not config_folder:
            self.show_error(f"No se encontró la carpeta de configuración para {selected_project} y {env_key}.")
            return

        source_folder = config_folder if selected_subfolder == ".(Raíz)" else config_folder / selected_subfolder
        if not source_folder.is_dir():
            self.show_error(f"La subcarpeta de origen '{source_folder}' no existe.")
            return

        try:
            source_file = next(source_folder.glob("appsettings*.json"))
            dest_name = "appsettings.json"
            anchor = "Program.cs"
        except StopIteration:
            try:
                source_file = next(source_folder.glob(".env"))
                dest_name = ".env"
                anchor = "package.json"
            except StopIteration:
                self.show_error(f"No se encontró 'appsettings*.json' ni '.env' en '{source_folder}'")
                return

        try:
            anchor_path = next(target_root.rglob(anchor))
            final_dir = anchor_path.parent
        except StopIteration:
            self.show_error(f"No se encontró '{anchor}' dentro de '{target_root}'.")
            return

        dest = final_dir / dest_name
        try:
            shutil.copy2(source_file, dest)
            self.status_label.configure(text=f"Copiado: {source_file.name} → {dest}", text_color=SUCCESS_COLOR)
            messagebox.showinfo("Éxito", f"Configuración aplicada.\n\nDesde: {source_file}\nHacia: {dest}")
        except Exception as e:
            self.show_error(f"Error al copiar el archivo: {e}")

    # ---------- Utilidades ----------
    def show_error(self, message):
        messagebox.showerror("Error", message)
        self.status_label.configure(text=f"Error: {message}", text_color=ERROR_COLOR)


if __name__ == "__main__":
    if "PYINSTALLER_VER" in os.environ:
        ctk.set_appearance_mode(ctk.get_appearance_mode())

    app = ConfigSwitcherApp()
    app.mainloop()
