import os
import argparse
from typing import Any, Dict, List, Tuple

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
)

# ========= 1) Leer SOLO columnas bajo "BD" =========
def read_bd_df(xlsx_path: str, sheet_name: str) -> pd.DataFrame:
    raw = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None, engine="openpyxl")

    groups = raw.iloc[0].replace({np.nan: None}).ffill().astype(str).str.strip().str.upper()
    bd_mask = groups.eq("BD").to_numpy()

    if bd_mask.sum() == 0:
        return pd.DataFrame()

    cols = raw.iloc[1, bd_mask].astype(str).str.strip().tolist()

    df = raw.iloc[2:, bd_mask].copy()
    df.columns = cols
    df = df.replace({np.nan: None})

    # quitar filas vacías
    df = df.loc[df.apply(lambda r: any(v is not None and str(v).strip() != "" for v in r), axis=1)]

    for c in df.columns:
        df[c] = df[c].apply(lambda v: v.strip() if isinstance(v, str) else v)

    return df


def to_int(v):
    if v in (None, "", " "):
        return None
    try:
        return int(v)
    except Exception:
        return None

def to_float(v):
    if v in (None, "", " "):
        return None
    try:
        return float(v)
    except Exception:
        return None


# ========= 2) Config global =========
# NombreTabla -> cómo leerla + modelo + PK + columnas
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
        "pk": ["metodologia_base_id", "orden"],  # PK compuesta
        "fields": ["metodologia_base_id", "orden", "instruccion"],
        "casters": {"orden": to_int},
    },
    "Metodologia": {
        "file": "Metodologia.xlsx", "sheet": "Metodologia", "model": Metodologia,
        "pk": ["fraccion_id", "nivel_limpieza_id"],  # PK compuesta
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
        "fields": ["kit_id", "nombre"],
        "casters": {},
    },
    "KitDetalle": {
        "file": "Herramienta.xlsx", "sheet": "KitDetalle", "model": KitDetalle,
        "pk": ["kit_id", "herramienta_id"],  # PK compuesta
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
        "pk": ["receta_id", "quimico_id"],  # PK compuesta
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
        "pk": ["elemento_set_id", "elemento_id"],  # PK compuesta
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

# Orden correcto (padres -> hijos)
IMPORT_ORDER = [
    "NivelLimpieza",
    "Personal",
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

    # nos quedamos solo con campos que importamos
    df = df[[c for c in fields if c in df.columns]].copy()
    df = df.replace({np.nan: None})

    for row in df.to_dict(orient="records"):
        row = cast_row(row, casters)
        pk_val = get_pk_value(pk_cols, row)
        if pk_val is None or (isinstance(pk_val, tuple) and any(v is None for v in pk_val)):
            continue

        obj = db.session.get(Model, pk_val)
        is_new = obj is None
        if is_new:
            # construir con PK
            init_kwargs = {c: row.get(c) for c in pk_cols}
            obj = Model(**init_kwargs)

        # set fields (except PK)
        for f in fields:
            if f in pk_cols:
                continue
            if f in row:
                setattr(obj, f, row.get(f))

        db.session.add(obj)
        if is_new:
            inserted += 1
        else:
            updated += 1

    return inserted, updated


def reset_db():
    # Borrar en orden seguro (hijas -> padres)
    db.session.query(SopFraccionDetalle).delete()
    db.session.query(SopFraccion).delete()

    db.session.query(ElementoDetalle).delete()
    db.session.query(ElementoSet).delete()
    db.session.query(Elemento).delete()

    db.session.query(RecetaDetalle).delete()
    db.session.query(Receta).delete()
    db.session.query(Quimico).delete()

    db.session.query(KitDetalle).delete()
    db.session.query(Kit).delete()
    db.session.query(Herramienta).delete()

    db.session.query(MetodologiaBasePaso).delete()
    db.session.query(Metodologia).delete()
    db.session.query(MetodologiaBase).delete()

    db.session.query(Consumo).delete()
    db.session.query(Fraccion).delete()

    db.session.query(SOP).delete()
    db.session.query(SubArea).delete()
    db.session.query(Area).delete()

    db.session.query(Personal).delete()
    db.session.query(NivelLimpieza).delete()


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

        stats = {}
        for t in IMPORT_ORDER:
            df = load_df(args.dir, t)
            ins, upd = upsert_table(df, t)
            stats[t] = {"inserted": ins, "updated": upd}
            print(f"{t}: +{ins} insert / ~{upd} update")

        db.session.commit()
        print("🎉 Import terminado.")

if __name__ == "__main__":
    main()
