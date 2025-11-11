Add-Type -AssemblyName System.Windows.Forms

# Archivos de configuración
$configFile = "$PSScriptRoot\.configpath.txt"
$projectMapFile = "$PSScriptRoot\projectmap.json"

function DetenerConMensaje($mensaje) {
    Write-Host "`nERROR: $mensaje"
    Read-Host "`nPresiona Enter para salir..."
    exit
}

function ObtenerRutaBase {
    if (Test-Path $configFile) {
        $rutaGuardada = (Get-Content $configFile -Raw).Trim()
        Write-Host "`nRuta guardada actual: $rutaGuardada"

        if (-not (Test-Path $rutaGuardada)) {
            Write-Host "`nLa ruta guardada no existe. Se solicitará una nueva."
            return PedirRutaBase
        }

        $cambiar = Read-Host "¿Quieres cambiar la ruta base? (s/n)"
        if ($cambiar -eq "s") {
            return PedirRutaBase
        } else {
            return $rutaGuardada
        }
    } else {
        return PedirRutaBase
    }
}

function PedirRutaBase {
    $folder = New-Object System.Windows.Forms.FolderBrowserDialog
    $folder.Description = "Selecciona la carpeta base donde están las CONFIGURACIONES *_Config_Preprod o *_Config_Prod"
    if ($folder.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        Set-Content -Path $configFile -Value $folder.SelectedPath
        return $folder.SelectedPath
    } else {
        DetenerConMensaje "Operación cancelada por el usuario."
    }
}

function ObtenerProyectos($rutaBase) {
    Get-ChildItem -Path $rutaBase -Directory |
        Where-Object { $_.Name -match '[-_]Config[-_]?(Preprod|Prod)$' } |
        ForEach-Object { $_.Name -replace '[-_]Config[-_]?(Preprod|Prod)$', '' } |
        Sort-Object -Unique
}

function ElegirElemento($titulo, $lista) {
    $lista = [string[]]$lista

    Write-Host "`n$titulo"
    for ($i = 0; $i -lt $lista.Count; $i++) {
        Write-Host " [$($i+1)] $($lista[$i])"
    }

    do {
        $indice = Read-Host "Elige una opción (1-$($lista.Count))"
    } while (-not ($indice -as [int]) -or $indice -lt 1 -or $indice -gt $lista.Count)

    return $lista[$indice - 1]
}

# === MAIN LOOP ===
do {
    $rutaBase = ObtenerRutaBase
    if (-not $rutaBase) { DetenerConMensaje "No se pudo obtener la ruta base." }

    $proyectos = ObtenerProyectos $rutaBase
    if ($proyectos.Count -eq 0) {
        DetenerConMensaje "No se encontraron carpetas *_Config_Preprod o *_Config_Prod en: $rutaBase"
    }

    $proyecto = ElegirElemento "Selecciona un proyecto:" $proyectos
    $entornoElegido = ElegirElemento "Selecciona entorno:" @("Preproduccion", "Produccion")
    $entornoClave = if ($entornoElegido -eq "Preproduccion") { "Preprod" } else { "Prod" }

    $carpetaConfig = Get-ChildItem -Path $rutaBase -Directory |
        Where-Object {
            $_.Name -match "^$proyecto[-_]Config[-_]?$entornoClave$"
        } |
        Select-Object -First 1

    if (-not $carpetaConfig) {
        DetenerConMensaje "No se encontró carpeta para $proyecto con entorno $entornoElegido."
    }

    $subcarpetas = Get-ChildItem -Path $carpetaConfig.FullName -Directory |
        Where-Object { -not ($_.Name.StartsWith(".")) }

    if (-not $subcarpetas -or $subcarpetas.Count -eq 0) {
        Write-Host "`nNo hay subcarpetas. Se usará la raíz de '$($carpetaConfig.Name)'."
        $carpetaFinal = $carpetaConfig.FullName
    } else {
        $subcarpeta = ElegirElemento "Selecciona el entorno específico dentro de '$($carpetaConfig.Name)':" ($subcarpetas | Select-Object -ExpandProperty Name)
        $carpetaFinal = Join-Path $carpetaConfig.FullName $subcarpeta
    }

    $json = Get-ChildItem -Path $carpetaFinal -Filter "appsettings*.json" | Select-Object -First 1
    if (-not $json) {
        DetenerConMensaje "No se encontró ningún archivo appsettings*.json en $carpetaFinal."
    }

    $projectMap = @{}
    if (Test-Path $projectMapFile) {
        try {
            $jsonContent = Get-Content $projectMapFile -Raw
            if ($jsonContent.Trim() -ne "") {
                $tempMap = $jsonContent | ConvertFrom-Json
                foreach ($key in $tempMap.PSObject.Properties.Name) {
                    $projectMap[$key] = $tempMap.$key
                }
            }
        } catch {
            Write-Host "Error leyendo 'projectmap.json'. Se ignorará."
        }
    }

    if ($projectMap.ContainsKey($proyecto)) {
        $carpetaProyectoUsuario = $projectMap[$proyecto]
        Write-Host "`nUsando carpeta previamente asociada: $carpetaProyectoUsuario"
    } else {
        Write-Host "`nNo hay asociación previa para $proyecto."
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $dialog.Description = "Selecciona la carpeta RAÍZ DEL PROYECTO $proyecto (en el que quieres copiar el appsettings.json)"
        if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
            DetenerConMensaje "Operación cancelada por el usuario."
        }
        $carpetaProyectoUsuario = $dialog.SelectedPath
        $projectMap[$proyecto] = $carpetaProyectoUsuario
        $projectMap | ConvertTo-Json -Depth 10 | Set-Content -Path $projectMapFile
        Write-Host "`nAsociación guardada: $proyecto -> $carpetaProyectoUsuario"
    }

    $programPath = Get-ChildItem -Path $carpetaProyectoUsuario -Recurse -Filter "Program.cs" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $programPath) {
        DetenerConMensaje "No se encontró Program.cs dentro de $carpetaProyectoUsuario."
    }

    $destinoFinal = Join-Path $programPath.Directory.FullName "appsettings.json"
    Copy-Item -Path $json.FullName -Destination $destinoFinal -Force

    Write-Host "`nArchivo copiado correctamente:"
    Write-Host "   Desde: $($json.FullName)"
    Write-Host "   Hacia: $destinoFinal"

    $repetir = Read-Host "`n¿Deseas aplicar otra configuración? (s/n)"
} while ($repetir -eq "s")

Read-Host "`nPresiona Enter para finalizar..."
