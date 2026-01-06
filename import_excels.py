import os
import argparse
from typing import Any, Dict, List, Tuple, Optional

import pandas as pd
import numpy as np

from app import create_app
from app.extensions import db
from app.models import (
    NivelLimpieza, Personal,
    Area, SubArea, SOP,
    Fraccion, MetodologiaBase, MetodologiaBasePaso, Metodologia,
    Herramienta, Kit, KitDetalle,
    Quimico, Receta, RecetaDetalle,
    Consumo,
    Elemento, ElementoSet, ElementoDetalle,
    SopFraccion, SopFraccionDetalle,
    User,  # ✅ NUEVO
)

# ======================================================
# 1) Leer SOLO columnas bajo "BD"
# Soporta: fila 1 (index 0) con celdas combinadas "BD"
#          fila 2 (index 1) headers
#          data desde fila 3 (index 2)
# ======================================================
def read_bd_df(xlsx_path: str, sheet_name: str) -> pd.DataFrame:
    raw = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None, engine="openpyxl")

    # fila 0: grupos (BD, UI, etc). Al estar combinadas, ffill funciona.
    groups = raw.iloc[0].replace({np.nan: None}).ffill().astype(str).str.strip().str.upper()
    bd_mask = groups.eq("BD").to_numpy()

    if bd_mask.sum() == 0:
        return pd.DataFrame()

    # fila 1: nombres de columnas
    cols = raw.iloc[1, bd_mask].astype(str).str.strip().tolist()

    # datos desde fila 2
    df = raw.iloc[2:, bd_mask].copy()
    df.columns = cols
    df = df.replace({np.nan: None})

    # quitar filas completamente vacías
    df = df.loc[df.apply(lambda r: any(v is not None and str(v).strip() != "" for v in r), axis=1)]

    # strip strings
    for c in df.columns:
        df[c] = df[c].apply(lambda v: v.strip() if isinstance(v, str) else v)

    return df


# ======================================================
# Casters robustos
# ======================================================
def to_int(v):
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return None
        if s.endswith(".0") and s[:-2].isdigit():
            return int(s[:-2])
        if s.isdigit():
            return int(s)
        try:
            f = float(s)
            return int(f) if float(f).is_integer() else None
        except Exception:
            return None
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, float):
        return int(v) if float(v).is_integer() else None
    try:
        return int(v)
    except Exception:
        return None


def to_float(v):
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return None
        s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return None
    try:
        return float(v)
    except Exception:
        return None


# ======================================================
# Helpers de User
# ======================================================
def _norm_str(x: Any) -> str:
    return ("" if x is None else str(x)).strip()

def _canon_role(x: Any) -> str:
    r = _norm_str(x).lower()
    if r in ("admin",):
        return "admin"
    if r in ("operativo", "operador", "op", "oper"):
        return "operativo"
    return r


# ======================================================
# 2) Config global
# ======================================================
CFG: Dict[str, Dict[str, Any]] = {
    "NivelLimpieza": {
        "file": "NivelLimpieza.xlsx", "sheet": "NivelLimpieza", "model": NivelLimpieza,
        "pk": ["nivel_limpieza_id"],
        "fields": ["nivel_limpieza_id", "nombre"],
        "casters": {"nivel_limpieza_id": to_int},
    },
    "Personal": {
        "file": "Personal.xlsx", "sheet": "Personal", "model": Personal,
        "pk": ["personal_id"],
        "fields": ["personal_id", "nombre"],
        "casters": {},
    },

    # ✅ NUEVO: User
    # Archivo: User.xlsx
    # Hoja: User
    # Columnas BD: username | password | role | personal_id
    "User": {
        "file": "User.xlsx", "sheet": "User", "model": User,
        # pk "virtual" para el import (NO es el PK real), lo usamos para upsert por username
        "pk": ["username"],
        "fields": ["username", "password", "role", "personal_id"],
        "casters": {},
    },

    "Area": {
        "file": "Area-SubArea.xlsx", "sheet": "Area", "model": Area,
        "pk": ["area_id"],
        "fields": ["area_id", "area_nombre", "tipo_area", "cantidad_subareas", "orden_area"],
        "casters": {"cantidad_subareas": to_int, "orden_area": to_int},
    },
    "SubArea": {
        "file": "Area-SubArea.xlsx", "sheet": "SubArea", "model": SubArea,
        "pk": ["subarea_id"],
        "fields": ["subarea_id", "area_id", "subarea_nombre", "superficie_subarea", "frecuencia", "orden_subarea"],
        "casters": {"superficie_subarea": to_float, "frecuencia": to_float, "orden_subarea": to_int},
    },
    "SOP": {
        "file": "SOP.xlsx", "sheet": "SOP", "model": SOP,
        "pk": ["sop_id"],
        "fields": ["sop_id", "subarea_id", "observacion_critica_sop"],
        "casters": {},
    },
    "Fraccion": {
        "file": "Fraccion.xlsx", "sheet": "Fraccion", "model": Fraccion,
        "pk": ["fraccion_id"],
        "fields": ["fraccion_id", "fraccion_nombre", "nota_tecnica"],
        "casters": {},
    },
    "MetodologiaBase": {
        "file": "Metodologia.xlsx", "sheet": "MetodologiaBase", "model": MetodologiaBase,
        "pk": ["metodologia_base_id"],
        "fields": ["metodologia_base_id", "nombre", "descripcion"],
        "casters": {},
    },
    "MetodologiaBasePaso": {
        "file": "Metodologia.xlsx", "sheet": "MetodologiaBasePaso", "model": MetodologiaBasePaso,
        "pk": ["metodologia_base_id", "orden"],
        "fields": ["metodologia_base_id", "orden", "instruccion"],
        "casters": {"orden": to_int},
    },
    "Metodologia": {
        "file": "Metodologia.xlsx", "sheet": "Metodologia", "model": Metodologia,
        "pk": ["fraccion_id", "nivel_limpieza_id"],
        "fields": ["fraccion_id", "nivel_limpieza_id", "metodologia_base_id"],
        "casters": {"nivel_limpieza_id": to_int},
    },
    "Herramienta": {
        "file": "Herramienta.xlsx", "sheet": "Herramienta", "model": Herramienta,
        "pk": ["herramienta_id"],
        "fields": ["herramienta_id", "nombre", "descripcion", "estatus"],
        "casters": {},
    },
    "Kit": {
        "file": "Herramienta.xlsx", "sheet": "Kit", "model": Kit,
        "pk": ["kit_id"],
        "fields": ["kit_id", "fraccion_id", "nivel_limpieza_id", "nombre"],
        "casters": {"nivel_limpieza_id": to_int},
    },
    "KitDetalle": {
        "file": "Herramienta.xlsx", "sheet": "KitDetalle", "model": KitDetalle,
        "pk": ["kit_id", "herramienta_id"],
        "fields": ["kit_id", "herramienta_id", "nota"],
        "casters": {},
    },
    "Quimico": {
        "file": "Quimico.xlsx", "sheet": "Quimico", "model": Quimico,
        "pk": ["quimico_id"],
        "fields": ["quimico_id", "nombre", "categoria", "presentacion", "unidad_base"],
        "casters": {},
    },
    "Receta": {
        "file": "Quimico.xlsx", "sheet": "Receta", "model": Receta,
        "pk": ["receta_id"],
        "fields": ["receta_id", "nombre"],
        "casters": {},
    },
    "RecetaDetalle": {
        "file": "Quimico.xlsx", "sheet": "RecetaDetalle", "model": RecetaDetalle,
        "pk": ["receta_id", "quimico_id"],
        "fields": ["receta_id", "quimico_id", "dosis", "unidad_dosis", "volumen_base", "unidad_volumen", "nota"],
        "casters": {"dosis": to_float, "volumen_base": to_float},
    },
    "Consumo": {
        "file": "Consumo.xlsx", "sheet": "Consumo", "model": Consumo,
        "pk": ["consumo_id"],
        "fields": ["consumo_id", "valor", "unidad", "regla"],
        "casters": {"valor": to_float},
    },
    "Elemento": {
        "file": "Elemento.xlsx", "sheet": "Elemento", "model": Elemento,
        "pk": ["elemento_id"],
        "fields": ["elemento_id", "subarea_id", "nombre", "cantidad", "estatus", "descripcion"],
        "casters": {"cantidad": to_float},
    },
    "ElementoSet": {
        "file": "Elemento.xlsx", "sheet": "ElementoSet", "model": ElementoSet,
        "pk": ["elemento_set_id"],
        "fields": ["elemento_set_id", "subarea_id", "fraccion_id", "nivel_limpieza_id", "nombre"],
        "casters": {"nivel_limpieza_id": to_int},
    },
    "ElementoDetalle": {
        "file": "Elemento.xlsx", "sheet": "ElementoDetalle", "model": ElementoDetalle,
        "pk": ["elemento_set_id", "elemento_id"],
        "fields": ["elemento_set_id", "elemento_id", "receta_id", "kit_id", "consumo_id", "orden"],
        "casters": {"orden": to_int},
    },
    "SOPFraccion": {
        "file": "SOP.xlsx", "sheet": "SOPFraccion", "model": SopFraccion,
        "pk": ["sop_fraccion_id"],
        "fields": ["sop_fraccion_id", "sop_id", "fraccion_id", "orden"],
        "casters": {"orden": to_int},
    },
    "SOPFraccionDetalle": {
        "file": "SOP.xlsx", "sheet": "SOPFraccionDetalle", "model": SopFraccionDetalle,
        "pk": ["sop_fraccion_detalle_id"],
        "fields": ["sop_fraccion_detalle_id", "sop_fraccion_id", "nivel_limpieza_id",
                   "kit_id", "receta_id", "elemento_set_id", "consumo_id", "tiempo_unitario_min"],
        "casters": {"nivel_limpieza_id": to_int, "tiempo_unitario_min": to_float},
    },
}

IMPORT_ORDER = [
    "NivelLimpieza",
    "Personal",
    "User",  # ✅ Users después de Personal (porque valida personal_id)

    "Area",
    "SubArea",
    "SOP",
    "Fraccion",
    "MetodologiaBase",
    "MetodologiaBasePaso",
    "Metodologia",
    "Herramienta",
    "Kit",
    "KitDetalle",
    "Quimico",
    "Receta",
    "RecetaDetalle",
    "Consumo",
    "Elemento",
    "ElementoSet",
    "ElementoDetalle",
    "SOPFraccion",
    "SOPFraccionDetalle",
]


def load_df(import_dir: str, table_name: str) -> pd.DataFrame:
    cfg = CFG[table_name]
    path = os.path.join(import_dir, cfg["file"])
    if not os.path.exists(path):
        return pd.DataFrame()
    # si la hoja no existe, pandas lanza; lo dejamos “visible” para que te diga el nombre exacto
    return read_bd_df(path, cfg["sheet"])


def cast_row(row: Dict[str, Any], casters: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    for k, fn in casters.items():
        if k in out:
            out[k] = fn(out[k])
    return out


def get_pk_value(pk_cols: List[str], row: Dict[str, Any]):
    if len(pk_cols) == 1:
        return row.get(pk_cols[0])
    return tuple(row.get(c) for c in pk_cols)


def upsert_table(df: pd.DataFrame, table_name: str) -> Tuple[int, int]:
    cfg = CFG[table_name]
    Model = cfg["model"]
    pk_cols = cfg["pk"]
    fields = cfg["fields"]
    casters = cfg["casters"]

    inserted = 0
    updated = 0

    if df.empty:
        return inserted, updated

    # solo columnas declaradas
    df = df[[c for c in fields if c in df.columns]].copy()
    df = df.replace({np.nan: None})

    # ======================================================
    # CASO ESPECIAL: USER (upsert por username, hash password)
    # ======================================================
    if table_name == "User":
        for row in df.to_dict(orient="records"):
            username = _norm_str(row.get("username"))
            password = _norm_str(row.get("password"))
            role = _canon_role(row.get("role"))
            personal_id = _norm_str(row.get("personal_id")) or None

            if not username:
                continue

            if role not in ("admin", "operativo"):
                raise ValueError(f"User '{username}': role inválido '{role}' (usa admin u operativo)")

            if role == "admin":
                personal_id = None

            if role == "operativo":
                if not personal_id:
                    raise ValueError(f"User '{username}': operativo requiere personal_id")

                p = Personal.query.filter_by(personal_id=personal_id).first()
                if not p:
                    raise ValueError(f"User '{username}': no existe Personal '{personal_id}'")

                existing_link = User.query.filter(User.personal_id == personal_id, User.username != username).first()
                if existing_link:
                    raise ValueError(
                        f"User '{username}': personal_id '{personal_id}' ya ligado a '{existing_link.username}'"
                    )

            with db.session.no_autoflush:
                u = User.query.filter_by(username=username).first()

            is_new = u is None
            if is_new:
                if not password:
                    raise ValueError(f"User nuevo '{username}': password requerido (password_hash NOT NULL)")
                u = User(username=username)

            u.role = role
            u.personal_id = personal_id

            # si viene password, actualiza hash
            if password:
                u.set_password(password)

            db.session.add(u)
            if is_new:
                inserted += 1
            else:
                updated += 1

        return inserted, updated

    # ======================================================
    # RESTO: genérico por PK real
    # ======================================================
    for row in df.to_dict(orient="records"):
        row = cast_row(row, casters)

        pk_val = get_pk_value(pk_cols, row)
        if pk_val is None or (isinstance(pk_val, tuple) and any(v is None for v in pk_val)):
            continue

        with db.session.no_autoflush:
            obj = db.session.get(Model, pk_val)

        is_new = obj is None
        if is_new:
            init_kwargs = {c: row.get(c) for c in pk_cols}
            obj = Model(**init_kwargs)

        for f in fields:
            if f in pk_cols:
                continue
            if f in row:
                setattr(obj, f, row.get(f))

        # guard: Kit debe traer fraccion_id sí o sí
        if table_name == "Kit" and getattr(obj, "fraccion_id", None) in (None, "", " "):
            raise ValueError(f"Kit {getattr(obj,'kit_id',None)} quedó sin fraccion_id (NOT NULL).")

        db.session.add(obj)
        if is_new:
            inserted += 1
        else:
            updated += 1

    return inserted, updated


def reset_db():
    # Importar TODOS los modelos
    from app.models import (
        # Lanzamiento y Plantillas
        LanzamientoTarea, LanzamientoDia, LanzamientoSemana,
        PlantillaSemanaAplicada, PlantillaItem, PlantillaSemanal,
        AsignacionPersonal,
        # Resto de modelos
        SopFraccionDetalle, SopFraccion,
        ElementoDetalle, ElementoSet, Elemento,
        RecetaDetalle, Receta, Quimico,
        KitDetalle, Kit, Herramienta,
        MetodologiaBasePaso, Metodologia, MetodologiaBase,
        Consumo, Fraccion,
        SOP, SubArea, Area,
        User, Personal, NivelLimpieza
    )
    
    # Borrar en orden seguro (hijas → padres, respetando foreign keys)
    
    # 1. Tablas de lanzamiento (lo más dependiente)
    db.session.query(LanzamientoTarea).delete(synchronize_session=False)
    db.session.query(LanzamientoDia).delete(synchronize_session=False)
    db.session.query(LanzamientoSemana).delete(synchronize_session=False)
    
    # 2. Plantillas
    db.session.query(PlantillaSemanaAplicada).delete(synchronize_session=False)
    db.session.query(PlantillaItem).delete(synchronize_session=False)
    db.session.query(PlantillaSemanal).delete(synchronize_session=False)
    
    # 3. Asignaciones
    db.session.query(AsignacionPersonal).delete(synchronize_session=False)
    
    # 4. SOP y sus detalles
    db.session.query(SopFraccionDetalle).delete(synchronize_session=False)
    db.session.query(SopFraccion).delete(synchronize_session=False)

    # 5. Elementos
    db.session.query(ElementoDetalle).delete(synchronize_session=False)
    db.session.query(ElementoSet).delete(synchronize_session=False)
    db.session.query(Elemento).delete(synchronize_session=False)

    # 6. Recetas y químicos
    db.session.query(RecetaDetalle).delete(synchronize_session=False)
    db.session.query(Receta).delete(synchronize_session=False)
    db.session.query(Quimico).delete(synchronize_session=False)

    # 7. Kits y herramientas
    db.session.query(KitDetalle).delete(synchronize_session=False)
    db.session.query(Kit).delete(synchronize_session=False)
    db.session.query(Herramienta).delete(synchronize_session=False)

    # 8. Metodologías
    db.session.query(MetodologiaBasePaso).delete(synchronize_session=False)
    db.session.query(Metodologia).delete(synchronize_session=False)
    db.session.query(MetodologiaBase).delete(synchronize_session=False)

    # 9. Consumos y fracciones
    db.session.query(Consumo).delete(synchronize_session=False)
    db.session.query(Fraccion).delete(synchronize_session=False)

    # 10. SOP, SubAreas, Areas
    db.session.query(SOP).delete(synchronize_session=False)
    db.session.query(SubArea).delete(synchronize_session=False)
    db.session.query(Area).delete(synchronize_session=False)

    # 11. Users y Personal
    db.session.query(User).delete(synchronize_session=False)
    db.session.query(Personal).delete(synchronize_session=False)

    # 12. Niveles de limpieza
    db.session.query(NivelLimpieza).delete(synchronize_session=False)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="Carpeta donde están los Excel (imports)")
    parser.add_argument("--reset", action="store_true", help="Borra todo antes de importar (como seed)")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if args.reset:
            reset_db()
            db.session.commit()
            print("✅ BD limpiada (reset).")

        for t in IMPORT_ORDER:
            try:
                df = load_df(args.dir, t)
                ins, upd = upsert_table(df, t)
                db.session.commit()
                print(f"{t}: +{ins} insert / ~{upd} update")
            except Exception as e:
                db.session.rollback()
                raise RuntimeError(f"Fallo importando tabla {t}: {e}") from e

        print("🎉 Import terminado.")


if __name__ == "__main__":
    main()
