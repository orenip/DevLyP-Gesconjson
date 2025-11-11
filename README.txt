1º Copiar la carpeta ConfiguradorJSON en la raíz del disco C:
2º Sacar el acceso directo .exe donde se quiera (escritorio etc)
3º Disfrutar y ante cualquier duda consultar el video.


Remove-Item -Recurse -Force build, dist, ConfigSwitcher.spec -ErrorAction SilentlyContinue


$icon = (Resolve-Path -LiteralPath .\icono.ico).Path
pyinstaller --onefile --windowed --name "ConfigSwitcher" --icon "$icon" .\config_switcher_visual.py


