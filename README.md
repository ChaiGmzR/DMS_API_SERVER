# DMS API Server

Backend independiente para las aplicaciones DMS Flutter/Web.

## Rutas principales

- `POST /api/auth/login`
- `GET /api/auth/verify`
- `GET /api/modelo?codigo=...`
- `GET /api/defectos`
- `POST /api/defectos`
- `GET /api/repairs/pendientes`
- `GET /api/repairs/en-proceso`
- `POST /api/repairs/iniciar`
- `POST /api/repairs/<repair_id>/finalizar`
- `GET /api/qa/pendientes`
- `POST /api/qa/<repair_id>/aprobar`
- `POST /api/qa/<repair_id>/rechazar`
- `GET /api/usuarios`

## Arranque en Windows

Requisito en el servidor: Python 3.11 o superior instalado.
Si el servidor no tiene Python:

```powershell
winget install -e --id Python.Python.3.13
```

Crear el archivo `.env` en la raiz del proyecto. Este archivo no se sube a git:

```powershell
cd C:\Users\Administrator\Documents\ILSANMES\DMS_API_SERVER
Copy-Item .env.example .env
notepad .env
```

Verifica que `.env` tenga los valores reales:

```text
MYSQL_HOST=192.168.1.10
MYSQL_PORT=3306
MYSQL_DATABASE=mes_production
MYSQL_USER=mes_admin
MYSQL_PASSWORD=<password real>
DMS_TOKEN_SECRET=<cadena larga privada>
DMS_TOKEN_MAX_AGE_SECONDS=86400
PORT=5000
```

```powershell
cd C:\Users\jesus\OneDrive\Documents\Desarrollo\DMS_API_SERVER
.\scripts\start.ps1
```

`scripts\start.ps1` crea `.venv`, instala dependencias y arranca el servicio.
Si Python esta instalado en una ruta no estandar, define `PYTHON_EXE` antes de
ejecutarlo:

```powershell
$env:PYTHON_EXE="C:\Path\To\python.exe"
.\scripts\start.ps1
```

El servicio escucha en `0.0.0.0:5000`. Desde las apps usa:

```text
http://192.168.1.10:5000/api
```

Si Windows Firewall bloquea el puerto en el servidor, abrirlo con PowerShell
como administrador:

```powershell
New-NetFirewallRule -DisplayName "DMS API 5000" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
```

## Diagnostico

```powershell
Invoke-RestMethod http://localhost:5000/api/dms/health
Invoke-RestMethod "http://localhost:5000/api/modelo?codigo=EBR80757421922407030048"
```

El archivo `.env` queda fuera de git y contiene la configuracion de base de datos.
