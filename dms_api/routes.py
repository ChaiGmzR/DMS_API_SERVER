from __future__ import annotations

import secrets
import time
from functools import wraps
from typing import Any, Callable

import bcrypt
from flask import Flask, current_app, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .db import Database, serialize_row


ROLES_CALIDAD = ["Inspector_LQC", "Inspector_OQC"]
ROLES_PRODUCCION = ["Reparador"]
AREAS_CALIDAD_USUARIOS = ["Calidad", "LQC", "OQC"]
AREAS_PRODUCCION_USUARIOS = ["Produccion", "Reparador"]
TODOS_LOS_ROLES = [
    *ROLES_CALIDAD,
    *ROLES_PRODUCCION,
    "Supervisor_Calidad",
    "Supervisor_Produccion",
    "Admin",
]
TIPOS_INSPECCION = {"ICT", "FCT", "Packing", "Visual"}
ETAPAS_DETECCION = {"LQC", "OQC"}
DEFECTO_STATUS = {
    "Pendiente_Reparacion",
    "En_Reparacion",
    "Reparado",
    "Rechazado",
    "Aprobado",
}
DEFAULT_DEFECTOS_LIMIT = 1000
MAX_DEFECTOS_LIMIT = 50000
DEFAULT_DEFECTOS_PAGE_SIZE = 100
MAX_DEFECTOS_PAGE_SIZE = 500
DEFECT_PART_NO_SQL = """
CASE
  WHEN d.codigo LIKE '%%;%%;%%'
   AND SUBSTRING_INDEX(SUBSTRING_INDEX(d.codigo, ';', 3), ';', -1) LIKE 'EBR%%'
  THEN SUBSTRING_INDEX(SUBSTRING_INDEX(d.codigo, ';', 3), ';', -1)
  ELSE SUBSTRING(d.codigo, 1, 11)
END
"""
DEFECT_TABLES_BY_AREA = {
    "SMD": "defect_data_smd",
}
DEFAULT_DEFECT_TABLE = "defect_data"
AREAS_USUARIO = [
    {"value": "LQC", "label": "LQC", "description": "Para inspectores de LQC"},
    {"value": "OQC", "label": "OQC", "description": "Para inspectores de OQC"},
    {"value": "SMD", "label": "SMD", "description": "Usuarios y supervisores del area SMD"},
    {"value": "Reparador", "label": "Reparador", "description": "Para reparadores"},
    {"value": "Calidad", "label": "Calidad", "description": "Para Supervisor de Calidad"},
    {"value": "Produccion", "label": "Produccion", "description": "Para Supervisor de Produccion"},
    {"value": "Administracion", "label": "Administracion", "description": "Para Administrador"},
]


def db() -> Database:
    return current_app.config["DMS_DB"]


def serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        current_app.config["DMS_SETTINGS"].token_secret,
        salt="dms-api",
    )


def json_error(message: str, status: int = 500, details: Any | None = None):
    payload: dict[str, Any] = {"error": message}
    if details is not None:
        payload["details"] = str(details)
    return jsonify(payload), status


def body() -> dict[str, Any]:
    return request.get_json(silent=True) or {}


def parse_limit(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return DEFAULT_DEFECTOS_LIMIT

    normalized = value.strip().lower()
    if normalized in {"0", "all", "none", "unlimited"}:
        return None

    try:
        limit = int(normalized)
    except ValueError:
        raise ValueError("limit debe ser numerico, 0 o all") from None

    if limit < 1:
        raise ValueError("limit debe ser mayor a 0")
    return min(limit, MAX_DEFECTOS_LIMIT)


def parse_positive_int(
    value: str | None,
    *,
    default: int,
    max_value: int | None = None,
    name: str,
) -> int:
    if value is None or value.strip() == "":
        return default

    try:
        parsed = int(value.strip())
    except ValueError:
        raise ValueError(f"{name} debe ser numerico") from None

    if parsed < 1:
        raise ValueError(f"{name} debe ser mayor a 0")
    return min(parsed, max_value) if max_value is not None else parsed


def part_code_for_lookup(codigo: str) -> str:
    normalized = codigo.upper().strip()
    parts = [part.strip().upper() for part in normalized.split(";")]
    if len(parts) >= 3 and parts[2].startswith("EBR"):
        return parts[2]
    return normalized


def defect_table_for_user(user: dict[str, Any]) -> str:
    area = str(user.get("area") or "").strip()
    return DEFECT_TABLES_BY_AREA.get(area, DEFAULT_DEFECT_TABLE)


def validate_table_name(table: str) -> str:
    allowed = {DEFAULT_DEFECT_TABLE, *DEFECT_TABLES_BY_AREA.values()}
    if table not in allowed:
        raise ValueError(f"Tabla de defectos no permitida: {table}")
    return table


def manageable_user_areas(user: dict[str, Any]) -> list[str]:
    user_role = user.get("rol") or ""
    user_area = user.get("area")
    if user_role == "Admin":
        return [area["value"] for area in AREAS_USUARIO]
    if user_role == "Supervisor_Calidad":
        if user_area == "SMD":
            return ["SMD"]
        return AREAS_CALIDAD_USUARIOS
    if user_role == "Supervisor_Produccion":
        if user_area and user_area not in {"Administracion", "Produccion"}:
            return [user_area]
        return AREAS_PRODUCCION_USUARIOS
    return []


def user_area_options(user: dict[str, Any]) -> list[dict[str, str]]:
    allowed = set(manageable_user_areas(user))
    return [area for area in AREAS_USUARIO if area["value"] in allowed]


def is_known_user_area(area: str | None) -> bool:
    if area is None:
        return True
    return any(option["value"] == area for option in AREAS_USUARIO)


def scoped_user_area(user: dict[str, Any], requested_area: Any) -> str | None:
    area = None if requested_area in (None, "") else str(requested_area)
    if user.get("rol") == "Admin":
        return area

    allowed_areas = manageable_user_areas(user)
    if not allowed_areas:
        raise ValueError("No tienes areas asignadas para administrar usuarios")
    if area is None:
        return allowed_areas[0]
    if area not in allowed_areas:
        raise ValueError("Solo puedes administrar usuarios de tus areas permitidas")
    return area


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(user["id"]),
        "username": user.get("username") or "",
        "nombre_completo": user.get("nombre_completo") or user.get("username") or "",
        "rol": user.get("rol") or "",
        "area": user.get("area"),
    }


def generate_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}_{secrets.token_hex(4)}"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    return header.split(" ", 1)[1].strip() or None


def load_user_from_token():
    token = bearer_token()
    if not token:
        return None, json_error("Token no proporcionado", 401)
    try:
        payload = serializer().loads(
            token,
            max_age=current_app.config["DMS_SETTINGS"].token_max_age_seconds,
        )
    except SignatureExpired:
        return None, json_error("Token expirado", 401)
    except BadSignature:
        return None, json_error("Token invalido", 401)

    user_id = payload.get("id") if isinstance(payload, dict) else None
    if not user_id:
        return None, json_error("Token invalido", 401)

    user = db().fetch_one(
        """
        SELECT id, username, nombre_completo, rol, area
        FROM usuarios_dms
        WHERE id = %s AND activo = TRUE
        """,
        (user_id,),
    )
    if user is None:
        return None, json_error("Usuario no valido", 401)
    return public_user(user), None


def require_auth(view: Callable):
    @wraps(view)
    def wrapper(*args, **kwargs):
        try:
            user, error_response = load_user_from_token()
        except Exception as exc:
            return json_error("Error al verificar token", 500, exc)
        if error_response is not None:
            return error_response
        request.dms_user = user
        return view(*args, **kwargs)

    return wrapper


def current_user() -> dict[str, Any]:
    return getattr(request, "dms_user", {}) or {}


def require_role(allowed_roles: set[str], message: str):
    def decorator(view: Callable):
        @wraps(view)
        @require_auth
        def wrapper(*args, **kwargs):
            user = current_user()
            if user.get("rol") not in allowed_roles:
                return json_error(message, 403, f"Rol actual: {user.get('rol')}")
            return view(*args, **kwargs)

        return wrapper

    return decorator


require_repair_role = require_role(
    {"Reparador", "Supervisor_Produccion", "Admin"},
    "Acceso denegado. Se requiere rol de Reparador o Supervisor",
)
require_qa_role = require_role(
    {"Supervisor_Calidad", "Admin"},
    "Acceso denegado. Se requiere rol de Supervisor Calidad o Admin",
)
require_admin_role = require_role(
    {"Admin", "Supervisor_Calidad", "Supervisor_Produccion"},
    "Acceso denegado. Se requiere rol de Administrador o Supervisor",
)


def roles_gestionables(user_role: str) -> list[str]:
    if user_role == "Admin":
        return TODOS_LOS_ROLES
    if user_role == "Supervisor_Calidad":
        return ROLES_CALIDAD
    if user_role == "Supervisor_Produccion":
        return ROLES_PRODUCCION
    return []


def positive_int(value: Any, default: int = 30, minimum: int = 1, maximum: int = 365) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def coerce_bool(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    return 1 if str(value).strip().lower() in {"1", "true", "yes", "si", "on"} else 0


def user_scope_clause(user: dict[str, Any], prefix: str = "WHERE") -> tuple[str, list[Any]]:
    user_role = user.get("rol") or ""
    if user_role == "Admin":
        return "", []
    roles = roles_gestionables(user_role)
    if not roles:
        return (" AND 1=0" if prefix == "AND" else " WHERE 1=0"), []
    clause = f" {prefix} rol IN ({', '.join(['%s'] * len(roles))})"
    params: list[Any] = list(roles)
    areas = manageable_user_areas(user)
    if not areas:
        clause += " AND 1=0"
    else:
        clause += f" AND area IN ({', '.join(['%s'] * len(areas))})"
        params.extend(areas)
    return clause, params


def audit_status_change(cursor, defect_id: str, old_value: str, new_value: str, username: str):
    try:
        cursor.execute(
            """
            INSERT INTO audit_log_dms
              (tabla, registro_id, accion, campo_modificado, valor_anterior, valor_nuevo, usuario)
            VALUES ('defect_data', %s, 'UPDATE', 'status', %s, %s, %s)
            """,
            (defect_id, old_value, new_value, username),
        )
    except Exception as exc:
        current_app.logger.warning("No se pudo registrar audit_log_dms: %s", exc)


def register_routes(app: Flask):
    @app.get("/api/dms/health")
    def health():
        try:
            rows = db().fetch_all(
                """
                SELECT table_name AS table_name
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name IN (
                    'defect_data',
                    'defect_data_smd',
                    'repair_data',
                    'usuarios_dms',
                    'audit_log_dms',
                    'vw_pendientes_reparacion_dms',
                    'vw_en_reparacion_dms',
                    'vw_pendientes_validacion_qa_dms'
                  )
                ORDER BY table_name
                """
            )
            settings = current_app.config["DMS_SETTINGS"]
            return jsonify(
                {
                    "success": True,
                    "service": "DMS API Server",
                    "database": settings.mysql_database,
                    "objects": [row.get("table_name") or row.get("TABLE_NAME") for row in rows],
                }
            )
        except Exception as exc:
            return json_error("Error al consultar salud de DMS", 500, exc)

    @app.post("/api/auth/login")
    def login():
        try:
            data = body()
            username = str(data.get("username") or "").strip()
            password = str(data.get("password") or "")
            if not username or not password:
                return json_error("Usuario y contrasena son requeridos", 400)

            user = db().fetch_one(
                "SELECT * FROM usuarios_dms WHERE username = %s AND activo = TRUE",
                (username,),
            )
            if user is None or not check_password(password, user.get("password_hash") or ""):
                return json_error("Usuario o contrasena incorrectos", 401)

            db().execute("UPDATE usuarios_dms SET ultimo_acceso = NOW() WHERE id = %s", (user["id"],))
            clean_user = public_user(user)
            token = serializer().dumps(
                {
                    "id": clean_user["id"],
                    "username": clean_user["username"],
                    "rol": clean_user["rol"],
                    "area": clean_user["area"],
                }
            )
            return jsonify({"success": True, "token": token, "user": clean_user})
        except Exception as exc:
            current_app.logger.exception("Error en login")
            return json_error("Error al iniciar sesion", 500, exc)

    @app.get("/api/auth/verify")
    @require_auth
    def verify_token():
        return jsonify({"success": True, "user": current_user()})

    @app.get("/api/auth/profile")
    @require_auth
    def profile():
        user = db().fetch_one(
            """
            SELECT id, username, nombre_completo, rol, area, fecha_creacion, ultimo_acceso
            FROM usuarios_dms
            WHERE id = %s AND activo = TRUE
            """,
            (current_user()["id"],),
        )
        if user is None:
            return json_error("Usuario no encontrado", 404)
        return jsonify(user)

    @app.post("/api/auth/change-password")
    @require_auth
    def change_password():
        data = body()
        current_password = str(data.get("currentPassword") or "")
        new_password = str(data.get("newPassword") or "")
        if not current_password or not new_password:
            return json_error("Contrasena actual y nueva son requeridas", 400)
        if len(new_password) < 4:
            return json_error("La nueva contrasena debe tener al menos 4 caracteres", 400)

        row = db().fetch_one("SELECT password_hash FROM usuarios_dms WHERE id = %s", (current_user()["id"],))
        if row is None:
            return json_error("Usuario no encontrado", 404)
        if not check_password(current_password, row.get("password_hash") or ""):
            return json_error("Contrasena actual incorrecta", 401)

        db().execute(
            "UPDATE usuarios_dms SET password_hash = %s WHERE id = %s",
            (hash_password(new_password), current_user()["id"]),
        )
        return jsonify({"success": True, "message": "Contrasena actualizada correctamente"})

    @app.get("/api/modelo")
    def get_modelo():
        try:
            codigo = part_code_for_lookup(str(request.args.get("codigo") or ""))
            if len(codigo) < 3:
                return jsonify({"modelo": ""})
            row = db().fetch_one(
                """
                SELECT model
                FROM part_numbers
                WHERE %s LIKE CONCAT(part_number, '%%')
                  AND model IS NOT NULL
                  AND model != ''
                  AND active = 1
                ORDER BY LENGTH(part_number) DESC
                LIMIT 1
                """,
                (codigo,),
            )
            return jsonify({"modelo": (row or {}).get("model") or ""})
        except Exception as exc:
            return json_error("Error al buscar modelo", 500, exc)

    @app.post("/api/modelo")
    def post_modelo():
        data = body()
        if not data.get("codigo") or not data.get("modelo"):
            return json_error("Codigo y modelo son requeridos", 400)
        return jsonify({"success": True, "message": "Modelo registrado"})

    @app.post("/api/defectos")
    @require_auth
    def create_defecto():
        try:
            data = body()
            required = [
                "linea",
                "codigo",
                "defecto",
                "ubicacion",
                "area",
                "tipo_inspeccion",
                "etapa_deteccion",
                "registrado_por",
            ]
            if any(not data.get(field) for field in required):
                return json_error("Faltan campos requeridos", 400, "Se requieren: " + ", ".join(required))
            if data["tipo_inspeccion"] not in TIPOS_INSPECCION:
                return json_error("tipo_inspeccion invalido", 400, "Valores validos: " + ", ".join(sorted(TIPOS_INSPECCION)))
            if data["etapa_deteccion"] not in ETAPAS_DETECCION:
                return json_error("etapa_deteccion invalida", 400, "Valores validos: " + ", ".join(sorted(ETAPAS_DETECCION)))

            table = validate_table_name(defect_table_for_user(current_user()))
            defect_id = generate_id("DEF")
            db().execute(
                f"""
                INSERT INTO {table}
                  (id, fecha, linea, codigo, defecto, ubicacion, area, modelo,
                   tipo_inspeccion, etapa_deteccion, registrado_por)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    defect_id,
                    data.get("fecha") or time.strftime("%Y-%m-%d %H:%M:%S"),
                    data["linea"],
                    str(data["codigo"]).upper().strip(),
                    data["defecto"],
                    str(data["ubicacion"]).upper().strip(),
                    data["area"],
                    data.get("modelo") or "",
                    data["tipo_inspeccion"],
                    data["etapa_deteccion"],
                    data["registrado_por"],
                ),
            )
            return jsonify({"success": True, "id": defect_id, "message": "Defecto registrado exitosamente"}), 201
        except Exception as exc:
            current_app.logger.exception("Error al guardar defecto")
            return json_error("Error al guardar el defecto", 500, exc)

    @app.get("/api/defectos")
    @require_auth
    def list_defectos():
        try:
            table = validate_table_name(defect_table_for_user(current_user()))
            select_clause = """
                SELECT
                  d.id,
                  d.fecha,
                  d.linea,
                  d.codigo,
                  d.defecto,
                  d.ubicacion,
                  d.area,
                  COALESCE(r.project, d.modelo, 'N/A') AS modelo,
                  d.tipo_inspeccion,
                  d.etapa_deteccion,
                  d.status,
                  COALESCE(u.nombre_completo, d.registrado_por) AS registrado_por,
                  d.fecha_envio_reparacion
            """
            from_clause = f"""
                FROM {table} d
                LEFT JOIN raw r
                  ON r.part_no COLLATE utf8mb4_unicode_ci =
                     ({DEFECT_PART_NO_SQL}) COLLATE utf8mb4_unicode_ci
                LEFT JOIN usuarios_dms u
                  ON u.username COLLATE utf8mb4_unicode_ci =
                     d.registrado_por COLLATE utf8mb4_unicode_ci
                WHERE 1=1
            """
            params: list[Any] = []
            filters = request.args
            if filters.get("fecha"):
                from_clause += " AND DATE(d.fecha) = %s"
                params.append(filters["fecha"])
            if filters.get("fechaInicio") and filters.get("fechaFin"):
                from_clause += " AND DATE(d.fecha) BETWEEN %s AND %s"
                params.extend([filters["fechaInicio"], filters["fechaFin"]])
            for key, column in [("linea", "d.linea"), ("area", "d.area"), ("status", "d.status"), ("tipo_inspeccion", "d.tipo_inspeccion"), ("etapa_deteccion", "d.etapa_deteccion")]:
                if filters.get(key):
                    from_clause += f" AND {column} = %s"
                    params.append(filters[key])
            for key, column in [("codigo", "d.codigo"), ("defecto", "d.defecto"), ("ubicacion", "d.ubicacion")]:
                if filters.get(key):
                    from_clause += f" AND {column} LIKE %s"
                    params.append(f"%{filters[key]}%")

            paginated = filters.get("page") is not None or filters.get("pageSize") is not None
            if paginated:
                try:
                    page = parse_positive_int(filters.get("page"), default=1, name="page")
                    page_size = parse_positive_int(
                        filters.get("pageSize"),
                        default=DEFAULT_DEFECTOS_PAGE_SIZE,
                        max_value=MAX_DEFECTOS_PAGE_SIZE,
                        name="pageSize",
                    )
                except ValueError as exc:
                    return json_error("Parametros de paginacion invalidos", 400, exc)

                count_query = f"SELECT COUNT(*) AS total {from_clause}"
                total_row = db().fetch_one(count_query, params) or {}
                total = int(total_row.get("total") or 0)
                offset = (page - 1) * page_size
                query = f"{select_clause} {from_clause} ORDER BY d.fecha DESC LIMIT %s OFFSET %s"
                rows = db().fetch_all(query, [*params, page_size, offset])
                return jsonify({
                    "data": rows,
                    "total": total,
                    "page": page,
                    "pageSize": page_size,
                })

            try:
                limit = parse_limit(filters.get("limit"))
            except ValueError as exc:
                return json_error("Parametro limit invalido", 400, exc)

            query = f"{select_clause} {from_clause} ORDER BY d.fecha DESC"
            if limit is not None:
                query += " LIMIT %s"
                params.append(limit)
            return jsonify(db().fetch_all(query, params))
        except Exception as exc:
            return json_error("Error al consultar defectos", 500, exc)

    @app.get("/api/defectos/<defect_id>")
    @require_auth
    def get_defecto(defect_id: str):
        table = validate_table_name(defect_table_for_user(current_user()))
        row = db().fetch_one(f"SELECT * FROM {table} WHERE id = %s", (defect_id,))
        if row is None:
            return json_error("Defecto no encontrado", 404)
        return jsonify(row)

    @app.put("/api/defectos/<defect_id>/status")
    @require_auth
    def update_defecto_status(defect_id: str):
        status = body().get("status")
        if status not in DEFECTO_STATUS:
            return json_error("Status invalido", 400, "Valores validos: " + ", ".join(sorted(DEFECTO_STATUS)))
        table = validate_table_name(defect_table_for_user(current_user()))
        result = db().execute(f"UPDATE {table} SET status = %s WHERE id = %s", (status, defect_id))
        if result["affected"] == 0:
            return json_error("Defecto no encontrado", 404)
        return jsonify({"success": True, "message": "Status actualizado correctamente"})

    @app.get("/api/repairs/pendientes")
    @require_auth
    def get_repair_pending():
        return jsonify(db().fetch_all("SELECT * FROM vw_pendientes_reparacion_dms"))

    @app.get("/api/repairs/en-proceso")
    @require_auth
    def get_repair_in_process():
        return jsonify(db().fetch_all("SELECT * FROM vw_en_reparacion_dms"))

    @app.post("/api/repairs/iniciar")
    @require_repair_role
    def start_repair():
        data = body()
        defect_id = data.get("defect_id")
        if not defect_id:
            return json_error("defect_id es requerido", 400)
        user = current_user()
        tecnico = user.get("nombre_completo") or user.get("username") or "Unknown"
        repair_id = generate_id("REP")

        with db().transaction() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM defect_data WHERE id = %s FOR UPDATE", (defect_id,))
                defect = serialize_row(cursor.fetchone())
                if defect is None:
                    return json_error("Defecto no encontrado", 404)
                if defect.get("status") != "Pendiente_Reparacion":
                    return json_error("El defecto no esta en estado Pendiente_Reparacion", 400, f"Estado actual: {defect.get('status')}")
                cursor.execute(
                    "UPDATE defect_data SET status = 'En_Reparacion', fecha_envio_reparacion = NOW() WHERE id = %s",
                    (defect_id,),
                )
                cursor.execute(
                    """
                    INSERT INTO repair_data
                      (id, defect_id, tecnico, status_antes, status_despues, fecha_inicio, accion_correctiva)
                    VALUES (%s, %s, %s, 'Pendiente_Reparacion', 'En_Reparacion', NOW(), 'En proceso')
                    """,
                    (repair_id, defect_id, tecnico),
                )
        return jsonify({"success": True, "message": "Reparacion iniciada correctamente", "repair_id": repair_id})

    @app.put("/api/repairs/<repair_id>/progreso")
    @require_repair_role
    def update_repair_progress(repair_id: str):
        data = body()
        fields = []
        params: list[Any] = []
        for key in ("accion_correctiva", "materiales_usados", "observaciones"):
            if key in data:
                fields.append(f"{key} = %s")
                params.append(data.get(key))
        if not fields:
            return json_error("No hay campos para actualizar", 400)
        params.append(repair_id)
        result = db().execute(f"UPDATE repair_data SET {', '.join(fields)} WHERE id = %s", params)
        if result["affected"] == 0:
            return json_error("Reparacion no encontrada", 404)
        return jsonify({"success": True, "message": "Progreso actualizado correctamente"})

    @app.post("/api/repairs/<repair_id>/finalizar")
    @require_repair_role
    def finish_repair(repair_id: str):
        data = body()
        accion_correctiva = data.get("accion_correctiva")
        if not accion_correctiva:
            return json_error("accion_correctiva es requerida", 400)

        with db().transaction() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT r.*, d.status AS defect_status, d.id AS defect_id
                    FROM repair_data r
                    JOIN defect_data d ON r.defect_id = d.id
                    WHERE r.id = %s
                    FOR UPDATE
                    """,
                    (repair_id,),
                )
                repair = serialize_row(cursor.fetchone())
                if repair is None:
                    return json_error("Reparacion no encontrada", 404)
                if repair.get("defect_status") != "En_Reparacion":
                    return json_error("El defecto no esta en reparacion", 400, f"Estado actual: {repair.get('defect_status')}")
                cursor.execute(
                    """
                    UPDATE repair_data
                    SET fecha_fin = NOW(),
                        accion_correctiva = %s,
                        materiales_usados = %s,
                        observaciones = %s,
                        status_despues = 'Reparado',
                        fecha_retorno_qa = NOW()
                    WHERE id = %s
                    """,
                    (accion_correctiva, data.get("materiales_usados"), data.get("observaciones"), repair_id),
                )
                cursor.execute("UPDATE defect_data SET status = 'Reparado' WHERE id = %s", (repair["defect_id"],))
        return jsonify({"success": True, "message": "Reparacion finalizada correctamente"})

    @app.get("/api/repairs/defecto/<defect_id>")
    @require_auth
    def get_repair_history(defect_id: str):
        return jsonify(
            db().fetch_all(
                """
                SELECT r.*, u.nombre_completo AS tecnico_nombre
                FROM repair_data r
                LEFT JOIN usuarios_dms u
                  ON r.tecnico = u.username OR r.tecnico = u.nombre_completo
                WHERE r.defect_id = %s
                ORDER BY r.fecha_recepcion DESC
                """,
                (defect_id,),
            )
        )

    @app.get("/api/repairs/estadisticas/tecnicos")
    @require_auth
    def get_repair_stats():
        dias = positive_int(request.args.get("dias"), default=30)
        return jsonify(
            db().fetch_all(
                """
                SELECT
                  tecnico,
                  COUNT(*) AS reparaciones_realizadas,
                  AVG(TIMESTAMPDIFF(HOUR, fecha_inicio, fecha_fin)) AS promedio_horas_reparacion,
                  SUM(CASE WHEN resultado_inspeccion_qa = 'Aprobado' THEN 1 ELSE 0 END) AS aprobadas,
                  SUM(CASE WHEN resultado_inspeccion_qa = 'Rechazado' THEN 1 ELSE 0 END) AS rechazadas,
                  SUM(CASE WHEN resultado_inspeccion_qa IS NULL THEN 1 ELSE 0 END) AS pendientes_qa
                FROM repair_data
                WHERE fecha_recepcion >= DATE_SUB(NOW(), INTERVAL %s DAY)
                GROUP BY tecnico
                ORDER BY reparaciones_realizadas DESC
                """,
                (dias,),
            )
        )

    @app.get("/api/qa/pendientes")
    @require_qa_role
    def get_qa_pending():
        return jsonify(db().fetch_all("SELECT * FROM vw_pendientes_validacion_qa_dms"))

    def qa_decision(repair_id: str, result: str, observations: str | None):
        if result == "Rechazado" and not observations:
            return json_error("Las observaciones son requeridas al rechazar una reparacion", 400)
        inspector = current_user().get("nombre_completo") or current_user().get("username") or "Unknown"
        new_status = "Aprobado" if result == "Aprobado" else "Rechazado"
        with db().transaction() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT r.*, d.status AS defect_status, d.id AS defect_id
                    FROM repair_data r
                    JOIN defect_data d ON r.defect_id = d.id
                    WHERE r.id = %s
                    FOR UPDATE
                    """,
                    (repair_id,),
                )
                repair = serialize_row(cursor.fetchone())
                if repair is None:
                    return json_error("Reparacion no encontrada", 404)
                if repair.get("defect_status") != "Reparado":
                    return json_error("El defecto no esta en estado Reparado", 400, f"Estado actual: {repair.get('defect_status')}")
                if repair.get("inspeccionado_por_qa"):
                    return json_error("Esta reparacion ya fue inspeccionada", 400, f"Resultado: {repair.get('resultado_inspeccion_qa')}")
                cursor.execute(
                    """
                    UPDATE repair_data
                    SET inspeccionado_por_qa = TRUE,
                        inspector_qa = %s,
                        fecha_inspeccion_qa = NOW(),
                        resultado_inspeccion_qa = %s,
                        observaciones_qa = %s
                    WHERE id = %s
                    """,
                    (inspector, result, observations or "", repair_id),
                )
                cursor.execute("UPDATE defect_data SET status = %s WHERE id = %s", (new_status, repair["defect_id"]))
                audit_status_change(cursor, repair["defect_id"], "Reparado", new_status, inspector)
        message = "Reparacion aprobada correctamente" if result == "Aprobado" else "Reparacion rechazada. El producto regresa a reparacion."
        return jsonify({"success": True, "message": message})

    @app.post("/api/qa/<repair_id>/aprobar")
    @require_qa_role
    def approve_qa(repair_id: str):
        return qa_decision(repair_id, "Aprobado", body().get("observaciones_qa"))

    @app.post("/api/qa/<repair_id>/rechazar")
    @require_qa_role
    def reject_qa(repair_id: str):
        return qa_decision(repair_id, "Rechazado", body().get("observaciones_qa"))

    @app.get("/api/qa/historial")
    @require_auth
    def get_qa_history():
        dias = positive_int(request.args.get("dias"), default=30)
        inspector = request.args.get("inspector")
        query = """
            SELECT
              r.*,
              d.codigo,
              d.defecto,
              d.modelo,
              d.linea,
              u.nombre_completo AS inspector_nombre
            FROM repair_data r
            JOIN defect_data d ON r.defect_id = d.id
            LEFT JOIN usuarios_dms u
              ON r.inspector_qa = u.username OR r.inspector_qa = u.nombre_completo
            WHERE r.inspeccionado_por_qa = TRUE
              AND r.fecha_inspeccion_qa >= DATE_SUB(NOW(), INTERVAL %s DAY)
        """
        params: list[Any] = [dias]
        if inspector:
            query += " AND r.inspector_qa = %s"
            params.append(inspector)
        query += " ORDER BY r.fecha_inspeccion_qa DESC"
        return jsonify(db().fetch_all(query, params))

    @app.get("/api/qa/estadisticas")
    @require_auth
    def get_qa_stats():
        dias = positive_int(request.args.get("dias"), default=30)
        return jsonify(
            db().fetch_all(
                """
                SELECT
                  inspector_qa,
                  COUNT(*) AS total_inspecciones,
                  SUM(CASE WHEN resultado_inspeccion_qa = 'Aprobado' THEN 1 ELSE 0 END) AS aprobadas,
                  SUM(CASE WHEN resultado_inspeccion_qa = 'Rechazado' THEN 1 ELSE 0 END) AS rechazadas,
                  ROUND(SUM(CASE WHEN resultado_inspeccion_qa = 'Aprobado' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS tasa_aprobacion
                FROM repair_data
                WHERE inspeccionado_por_qa = TRUE
                  AND fecha_inspeccion_qa >= DATE_SUB(NOW(), INTERVAL %s DAY)
                GROUP BY inspector_qa
                ORDER BY total_inspecciones DESC
                """,
                (dias,),
            )
        )

    @app.get("/api/usuarios/roles/list")
    @require_admin_role
    def get_roles():
        user_role = current_user().get("rol") or ""
        allowed = set(roles_gestionables(user_role))
        roles = [
            {"value": "Inspector_LQC", "label": "Inspector LQC", "description": "Inspeccion en linea de produccion (LQC)"},
            {"value": "Inspector_OQC", "label": "Inspector OQC", "description": "Inspeccion de calidad final (OQC)"},
            {"value": "Reparador", "label": "Reparador", "description": "Reparacion de defectos"},
            {"value": "Supervisor_Calidad", "label": "Supervisor Calidad", "description": "Administra inspectores LQC y OQC"},
            {"value": "Supervisor_Produccion", "label": "Supervisor Produccion", "description": "Administra reparadores"},
            {"value": "Admin", "label": "Administrador", "description": "Acceso completo al sistema"},
        ]
        return jsonify({"success": True, "data": [role for role in roles if role["value"] in allowed]})

    @app.get("/api/usuarios/areas/list")
    @require_admin_role
    def get_areas():
        return jsonify({"success": True, "data": user_area_options(current_user())})

    @app.get("/api/usuarios")
    @require_admin_role
    def list_users():
        query = """
            SELECT id, username, nombre_completo, rol, area, activo, fecha_creacion, ultimo_acceso
            FROM usuarios_dms
        """
        clause, params = user_scope_clause(current_user(), "WHERE")
        query += clause + " ORDER BY fecha_creacion DESC"
        return jsonify({"success": True, "data": db().fetch_all(query, params)})

    @app.get("/api/usuarios/<int:user_id>")
    @require_admin_role
    def get_user(user_id: int):
        query = """
            SELECT id, username, nombre_completo, rol, area, activo, fecha_creacion, ultimo_acceso
            FROM usuarios_dms
            WHERE id = %s
        """
        params: list[Any] = [user_id]
        clause, scope_params = user_scope_clause(current_user(), "AND")
        query += clause
        params.extend(scope_params)
        row = db().fetch_one(query, params)
        if row is None:
            return json_error("Usuario no encontrado o sin permisos para verlo", 404)
        return jsonify({"success": True, "data": row})

    @app.post("/api/usuarios")
    @require_admin_role
    def create_user():
        data = body()
        username = str(data.get("username") or "").strip()
        password = str(data.get("password") or "")
        nombre_completo = str(data.get("nombre_completo") or "").strip()
        rol = data.get("rol")
        try:
            area = scoped_user_area(current_user(), data.get("area"))
        except ValueError as exc:
            return json_error("Area no permitida", 403, exc)
        if not is_known_user_area(area):
            return json_error("Area invalida", 400, f"Area recibida: {area}")
        if not username or not password or not nombre_completo or not rol:
            return json_error("Campos requeridos: username, password, nombre_completo, rol", 400)
        allowed = roles_gestionables(current_user().get("rol") or "")
        if rol not in allowed:
            return json_error(f"No tienes permisos para crear usuarios con el rol: {rol}", 403, "Roles permitidos: " + ", ".join(allowed))
        if db().fetch_one("SELECT id FROM usuarios_dms WHERE username = %s", (username,)):
            return json_error("El nombre de usuario ya existe", 409)
        result = db().execute(
            """
            INSERT INTO usuarios_dms
              (username, password_hash, nombre_completo, rol, area, activo, fecha_creacion)
            VALUES (%s, %s, %s, %s, %s, TRUE, NOW())
            """,
            (username, hash_password(password), nombre_completo, rol, area),
        )
        return jsonify(
            {
                "success": True,
                "message": "Usuario creado exitosamente",
                "data": {
                    "id": result["lastrowid"],
                    "username": username,
                    "nombre_completo": nombre_completo,
                    "rol": rol,
                    "area": area,
                },
            }
        ), 201

    @app.put("/api/usuarios/<int:user_id>")
    @require_admin_role
    def update_user(user_id: int):
        data = body()
        check_query = "SELECT id FROM usuarios_dms WHERE id = %s"
        check_params: list[Any] = [user_id]
        clause, scope_params = user_scope_clause(current_user(), "AND")
        check_query += clause
        check_params.extend(scope_params)
        if db().fetch_one(check_query, check_params) is None:
            return json_error("Usuario no encontrado o sin permisos para editarlo", 404)
        allowed = roles_gestionables(current_user().get("rol") or "")
        if data.get("rol") is not None and data.get("rol") not in allowed:
            return json_error(f"No tienes permisos para asignar el rol: {data.get('rol')}", 403, "Roles permitidos: " + ", ".join(allowed))
        fields = []
        values: list[Any] = []
        for key in ("nombre_completo", "rol"):
            if key in data:
                fields.append(f"{key} = %s")
                values.append(data.get(key))
        if "area" in data:
            try:
                area = scoped_user_area(current_user(), data.get("area"))
            except ValueError as exc:
                return json_error("Area no permitida", 403, exc)
            if not is_known_user_area(area):
                return json_error("Area invalida", 400, f"Area recibida: {area}")
            fields.append("area = %s")
            values.append(area)
        if "activo" in data:
            fields.append("activo = %s")
            values.append(coerce_bool(data.get("activo")))
        if not fields:
            return json_error("No se proporcionaron campos para actualizar", 400)
        values.append(user_id)
        db().execute(f"UPDATE usuarios_dms SET {', '.join(fields)} WHERE id = %s", values)
        return jsonify({"success": True, "message": "Usuario actualizado exitosamente"})

    @app.put("/api/usuarios/<int:user_id>/password")
    @require_admin_role
    def update_user_password(user_id: int):
        new_password = str(body().get("new_password") or "")
        if len(new_password) < 4:
            return json_error("La contrasena debe tener al menos 4 caracteres", 400)
        check_query = "SELECT id FROM usuarios_dms WHERE id = %s"
        check_params: list[Any] = [user_id]
        clause, scope_params = user_scope_clause(current_user(), "AND")
        check_query += clause
        check_params.extend(scope_params)
        if db().fetch_one(check_query, check_params) is None:
            return json_error("Usuario no encontrado o sin permisos", 404)
        db().execute("UPDATE usuarios_dms SET password_hash = %s WHERE id = %s", (hash_password(new_password), user_id))
        return jsonify({"success": True, "message": "Contrasena actualizada exitosamente"})

    @app.delete("/api/usuarios/<int:user_id>")
    @require_admin_role
    def deactivate_user(user_id: int):
        if current_user().get("id") == user_id:
            return json_error("No puedes desactivar tu propia cuenta", 400)
        check_query = "SELECT id, username FROM usuarios_dms WHERE id = %s"
        check_params: list[Any] = [user_id]
        clause, scope_params = user_scope_clause(current_user(), "AND")
        check_query += clause
        check_params.extend(scope_params)
        row = db().fetch_one(check_query, check_params)
        if row is None:
            return json_error("Usuario no encontrado o sin permisos", 404)
        db().execute("UPDATE usuarios_dms SET activo = FALSE WHERE id = %s", (user_id,))
        return jsonify({"success": True, "message": f"Usuario {row.get('username')} desactivado exitosamente"})

    @app.delete("/api/usuarios/<int:user_id>/permanent")
    @require_admin_role
    def delete_user_permanent(user_id: int):
        if current_user().get("rol") != "Admin":
            return json_error("Solo el Super Administrador puede eliminar usuarios permanentemente", 403)
        if current_user().get("id") == user_id:
            return json_error("No puedes eliminar tu propia cuenta", 400)
        row = db().fetch_one("SELECT id, username FROM usuarios_dms WHERE id = %s", (user_id,))
        if row is None:
            return json_error("Usuario no encontrado", 404)
        db().execute("DELETE FROM usuarios_dms WHERE id = %s", (user_id,))
        return jsonify({"success": True, "message": f"Usuario {row.get('username')} eliminado permanentemente"})
