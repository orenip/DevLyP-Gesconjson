# Archivo: sync_repos.py
# (Debe estar en la misma carpeta que el .exe o .py principal)

import sys
import os
from pathlib import Path

try:
    import git
except ImportError:
    print("Error: La librería 'GitPython' no está instalada.")
    print("Por favor, instala con: pip install GitPython")
    input("Pulsa Enter para salir...")
    sys.exit(1)

def sync_repositories(base_path_str):
    """
    Busca y sincroniza todos los repositorios Git bajo la ruta base.
    """
    base_path = Path(base_path_str)
    if not base_path.is_dir():
        print(f"Error: La ruta base '{base_path_str}' no es un directorio válido.")
        return

    print(f"🔍 Buscando repositorios Git desde: {base_path}")
    print("-" * 40)

    git_dirs = list(base_path.rglob(".git"))

    if not git_dirs:
        print("No se encontraron repositorios Git en esta carpeta.")
        return

    for git_dir in git_dirs:
        repo_dir = git_dir.parent
        print(f"📁 Repositorio encontrado: {repo_dir}")
        
        try:
            repo = git.Repo(repo_dir)
            
            if repo.is_dirty(untracked_files=True):
                print("🔧 Cambios detectados, subiendo...")
                repo.git.add(all=True)
                
                if repo.index.diff("HEAD"):
                    repo.index.commit("update (auto-sync)")
                    print("... Commit 'update' creado.")
                else:
                    print("... No hay cambios para 'comitear'.")

                print("... Subiendo cambios (push)...")
                repo.remotes.origin.push()
                print("📤 Push completado.")
                
            else:
                print("✅ Sin cambios locales. Verificando cambios remotos (pull)...")
                repo.remotes.origin.pull()
                print("📥 Pull completado.")

        except git.GitCommandError as e:
            print(f"❌ ERROR en el repositorio {repo_dir}:")
            print(f"   {e}")
        except Exception as e:
            print(f"❌ ERROR INESPERADO en {repo_dir}: {e}")
        
        print("-" * 40)

    print("✅ Proceso completado.")
    print("🔄 Todos los repositorios han sido sincronizados.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Error: No se proporcionó la ruta base de configuración.")
    else:
        sync_repositories(sys.argv[1])
    
    input("⏸️ Pulsa Enter para cerrar esta ventana...")