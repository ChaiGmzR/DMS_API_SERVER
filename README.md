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

```powershell
cd C:\Users\jesus\OneDrive\Documents\Desarrollo\DMS_API_SERVER
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
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
