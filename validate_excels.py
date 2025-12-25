import os
import json
import argparse
from datetime import datetime, timezone

import pandas as pd
import numpy as np


# ========= 1) Leer SOLO columnas bajo "BD" =========
def read_bd_df(xlsx_path: str, sheet_name: str) -> pd.DataFrame:
    raw = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None, engine="openpyxl")

    # fila 0 = grupos (BD/AGRUPAMIENTO/GLOSARIO) con celdas combinadas => ffill
    groups = raw.iloc[0].replace({np.nan: None}).ffill().astype(str).str.strip().str.upper()

    # máscara BD como numpy array (para evitar el error de iloc)
    bd_mask = groups.eq("BD").to_numpy()

    if bd_mask.sum() == 0:
        return pd.DataFrame()

    # fila 1 = headers reales
    cols = raw.iloc[1, bd_mask].astype(str).str.strip().tolist()

    # fila 2+ = datos
    df = raw.iloc[2:, bd_mask].copy()
    df.columns = cols

    df = df.replace({np.nan: None})
    # quitar filas vacías
    df = df.loc[df.apply(lambda r: any(v is not None and str(v).strip() != "" for v in r), axis=1)]

    # strip strings
    for c in df.columns:
        df[c] = df[c].apply(lambda v: v.strip() if isinstance(v, str) else v)

    return df


# ========= 2) Config por tabla (sheet -> pk -> columnas mínimas) =========
CFG = {
    "NivelLimpieza": {"sheet": "NivelLimpieza", "pk": "nivel_limpieza_id",
                     "required": ["nivel_limpieza_id", "nombre"]},

    "Personal": {"sheet": "Personal", "pk": "personal_id",
                 "required": ["personal_id", "nombre"]},

    "Area": {"sheet": "Area", "pk": "area_id",
             "required": ["area_id", "area_nombre", "tipo_area", "cantidad_subareas", "orden_area"]},

    "SubArea": {"sheet": "SubArea", "pk": "subarea_id",
                "required": ["subarea_id", "area_id", "subarea_nombre", "superficie_subarea", "frecuencia", "orden_subarea"]},

    "SOP": {"sheet": "SOP", "pk": "sop_id",
            "required": ["sop_id", "subarea_id"]},

    "Fraccion": {"sheet": "Fraccion", "pk": "fraccion_id",
                 "required": ["fraccion_id", "fraccion_nombre"]},

    "MetodologiaBase": {"sheet": "MetodologiaBase", "pk": "metodologia_base_id",
                        "required": ["metodologia_base_id"]},

    "MetodologiaBasePaso": {"sheet": "MetodologiaBasePaso", "pk": None,
                            "required": ["metodologia_base_id", "orden", "instruccion"]},

    "Metodologia": {"sheet": "Metodologia", "pk": None,
                    "required": ["fraccion_id", "nivel_limpieza_id", "metodologia_base_id"]},

    "Herramienta": {"sheet": "Herramienta", "pk": "herramienta_id",
                    "required": ["herramienta_id", "nombre"]},

    "Kit": {"sheet": "Kit", "pk": "kit_id",
            "required": ["kit_id", "nombre"]},

    "KitDetalle": {"sheet": "KitDetalle", "pk": None,
                   "required": ["kit_id", "herramienta_id"]},

    "Quimico": {"sheet": "Quimico", "pk": "quimico_id",
                "required": ["quimico_id", "nombre"]},

    "Receta": {"sheet": "Receta", "pk": "receta_id",
               "required": ["receta_id", "nombre"]},

    "RecetaDetalle": {"sheet": "RecetaDetalle", "pk": None,
                      "required": ["receta_id", "quimico_id"]},

    "Consumo": {"sheet": "Consumo", "pk": "consumo_id",
                "required": ["consumo_id", "valor", "unidad", "regla"]},

    "Elemento": {"sheet": "Elemento", "pk": "elemento_id",
                 "required": ["elemento_id", "subarea_id", "nombre"]},

    "ElementoSet": {"sheet": "ElementoSet", "pk": "elemento_set_id",
                    "required": ["elemento_set_id", "subarea_id", "fraccion_id", "nivel_limpieza_id", "nombre"]},

    "ElementoDetalle": {"sheet": "ElementoDetalle", "pk": None,
                        "required": ["elemento_set_id", "elemento_id"]},

    "SOPFraccion": {"sheet": "SOPFraccion", "pk": "sop_fraccion_id",
                    "required": ["sop_fraccion_id", "sop_id", "fraccion_id", "orden"]},

    "SOPFraccionDetalle": {"sheet": "SOPFraccionDetalle", "pk": "sop_fraccion_detalle_id",
                           "required": ["sop_fraccion_detalle_id", "sop_fraccion_id", "nivel_limpieza_id"]},
}

# Qué excel trae qué hojas (si una hoja no existe, no falla, solo la ignora)
FILES_HINT = {
    "Area-SubArea.xlsx": ["Area", "SubArea"],
    "SOP.xlsx": ["SOP", "SOPFraccion", "SOPFraccionDetalle"],
    "Fraccion.xlsx": ["Fraccion"],
    "Metodologia.xlsx": ["MetodologiaBase", "MetodologiaBasePaso", "Metodologia"],
    "Herramienta.xlsx": ["Herramienta", "Kit", "KitDetalle"],
    "Quimico.xlsx": ["Quimico", "Receta", "RecetaDetalle"],
    "Consumo.xlsx": ["Consumo"],
    "Elemento.xlsx": ["Elemento", "ElementoSet", "ElementoDetalle"],
    "Personal.xlsx": ["Personal"],
    "NivelLimpieza.xlsx": ["NivelLimpieza"],
}


def load_tables_from_excels(excel_paths):
    data = {}   # table_name -> df
    notes = []

    for path in excel_paths:
        if not os.path.exists(path):
            notes.append(f"No existe: {path}")
            continue

        try:
            xl = pd.ExcelFile(path, engine="openpyxl")
            sheets = set(xl.sheet_names)
        except Exception as e:
            notes.append(f"No pude abrir {path}: {e}")
            continue

        filename = os.path.basename(path)
        target_sheets = FILES_HINT.get(filename, list(sheets))

        for table_name, cfg in CFG.items():
            sheet = cfg["sheet"]
            if sheet not in target_sheets:
                continue
            if sheet not in sheets:
                continue

            df = read_bd_df(path, sheet)
            if df.empty:
                continue

            data[table_name] = df

    return data, notes


def unique_check(df, pk_col):
    if pk_col is None or pk_col not in df.columns:
        return []
    s = df[pk_col].dropna().astype(str)
    dup = s[s.duplicated()].unique().tolist()
    return dup


def fk_check(child_df, child_col, parent_df, parent_pk):
    if child_col not in child_df.columns or parent_pk not in parent_df.columns:
        return []
    child_vals = child_df[child_col].dropna().astype(str)
    parent_vals = set(parent_df[parent_pk].dropna().astype(str))
    bad = sorted(set(v for v in child_vals.unique() if v not in parent_vals))
    return bad


def validate(data):
    report = {"ok": True, "errors": [], "warnings": [], "stats": {}}

    # 1) columnas requeridas + PK duplicadas
    for tname, df in data.items():
        cfg = CFG[tname]
        req = cfg["required"]
        missing = [c for c in req if c not in df.columns]
        if missing:
            report["ok"] = False
            report["errors"].append(f"[{tname}] Faltan columnas BD requeridas: {missing}")

        pk = cfg["pk"]
        dups = unique_check(df, pk)
        if dups:
            report["ok"] = False
            report["errors"].append(f"[{tname}] PK duplicadas en {pk}: ejemplos {dups[:10]}")

        report["stats"][tname] = {"rows": int(len(df))}

    def get(t): return data.get(t)

    # 2) Validar FKs importantes (si existen ambas tablas)
    if get("SubArea") is not None and get("Area") is not None:
        bad = fk_check(get("SubArea"), "area_id", get("Area"), "area_id")
        if bad:
            report["ok"] = False
            report["errors"].append(f"[SubArea] area_id no existe en Area: ejemplos {bad[:10]}")

    if get("SOP") is not None and get("SubArea") is not None:
        bad = fk_check(get("SOP"), "subarea_id", get("SubArea"), "subarea_id")
        if bad:
            report["ok"] = False
            report["errors"].append(f"[SOP] subarea_id no existe en SubArea: ejemplos {bad[:10]}")

        # 1 SOP por subarea (tu constraint)
        if "subarea_id" in get("SOP").columns:
            dup_sub = get("SOP")["subarea_id"].dropna().astype(str)
            dup_vals = dup_sub[dup_sub.duplicated()].unique().tolist()
            if dup_vals:
                report["ok"] = False
                report["errors"].append(f"[SOP] Hay más de 1 SOP por subarea_id: ejemplos {dup_vals[:10]}")

    if get("SOPFraccion") is not None and get("SOP") is not None:
        bad = fk_check(get("SOPFraccion"), "sop_id", get("SOP"), "sop_id")
        if bad:
            report["ok"] = False
            report["errors"].append(f"[SOPFraccion] sop_id no existe en SOP: ejemplos {bad[:10]}")

    if get("SOPFraccion") is not None and get("Fraccion") is not None:
        bad = fk_check(get("SOPFraccion"), "fraccion_id", get("Fraccion"), "fraccion_id")
        if bad:
            report["ok"] = False
            report["errors"].append(f"[SOPFraccion] fraccion_id no existe en Fraccion: ejemplos {bad[:10]}")

    if get("SOPFraccionDetalle") is not None and get("SOPFraccion") is not None:
        bad = fk_check(get("SOPFraccionDetalle"), "sop_fraccion_id", get("SOPFraccion"), "sop_fraccion_id")
        if bad:
            report["ok"] = False
            report["errors"].append(f"[SOPFraccionDetalle] sop_fraccion_id no existe en SOPFraccion: ejemplos {bad[:10]}")

    if get("Elemento") is not None and get("SubArea") is not None:
        bad = fk_check(get("Elemento"), "subarea_id", get("SubArea"), "subarea_id")
        if bad:
            report["ok"] = False
            report["errors"].append(f"[Elemento] subarea_id no existe en SubArea: ejemplos {bad[:10]}")

    if get("ElementoSet") is not None and get("SubArea") is not None:
        bad = fk_check(get("ElementoSet"), "subarea_id", get("SubArea"), "subarea_id")
        if bad:
            report["ok"] = False
            report["errors"].append(f"[ElementoSet] subarea_id no existe en SubArea: ejemplos {bad[:10]}")

    if get("ElementoSet") is not None and get("Fraccion") is not None:
        bad = fk_check(get("ElementoSet"), "fraccion_id", get("Fraccion"), "fraccion_id")
        if bad:
            report["ok"] = False
            report["errors"].append(f"[ElementoSet] fraccion_id no existe en Fraccion: ejemplos {bad[:10]}")

    if get("ElementoDetalle") is not None and get("ElementoSet") is not None:
        bad = fk_check(get("ElementoDetalle"), "elemento_set_id", get("ElementoSet"), "elemento_set_id")
        if bad:
            report["ok"] = False
            report["errors"].append(f"[ElementoDetalle] elemento_set_id no existe en ElementoSet: ejemplos {bad[:10]}")

    if get("ElementoDetalle") is not None and get("Elemento") is not None:
        bad = fk_check(get("ElementoDetalle"), "elemento_id", get("Elemento"), "elemento_id")
        if bad:
            report["ok"] = False
            report["errors"].append(f"[ElementoDetalle] elemento_id no existe en Elemento: ejemplos {bad[:10]}")

    # Consumo usado en SOPFraccionDetalle y ElementoDetalle
    if get("Consumo") is not None:
        if get("SOPFraccionDetalle") is not None and "consumo_id" in get("SOPFraccionDetalle").columns:
            bad = fk_check(get("SOPFraccionDetalle"), "consumo_id", get("Consumo"), "consumo_id")
            if bad:
                report["ok"] = False
                report["errors"].append(f"[SOPFraccionDetalle] consumo_id no existe en Consumo: ejemplos {bad[:10]}")
        if get("ElementoDetalle") is not None and "consumo_id" in get("ElementoDetalle").columns:
            bad = fk_check(get("ElementoDetalle"), "consumo_id", get("Consumo"), "consumo_id")
            if bad:
                report["ok"] = False
                report["errors"].append(f"[ElementoDetalle] consumo_id no existe en Consumo: ejemplos {bad[:10]}")

    # 3) Regla clave: si hay elemento_set_id => NO puede haber kit/receta en SOPFraccionDetalle
    if get("SOPFraccionDetalle") is not None:
        df = get("SOPFraccionDetalle")
        cols = df.columns
        if "elemento_set_id" in cols and ("kit_id" in cols or "receta_id" in cols):
            bad_rows = df[
                df["elemento_set_id"].notna()
                & (
                    (df["kit_id"].notna() if "kit_id" in cols else False)
                    | (df["receta_id"].notna() if "receta_id" in cols else False)
                )
            ]
            if len(bad_rows):
                report["ok"] = False
                ids = bad_rows["sop_fraccion_detalle_id"].head(10).tolist() if "sop_fraccion_detalle_id" in cols else []
                report["errors"].append(
                    f"[SOPFraccionDetalle] Regla rota: elemento_set_id tiene valor pero kit_id/receta_id también. Ejemplos: {ids}"
                )

    # warning suave: superficie_subarea vacía
    if get("SubArea") is not None and "superficie_subarea" in get("SubArea").columns:
        empty = int(get("SubArea")["superficie_subarea"].isna().sum())
        if empty:
            report["warnings"].append(f"[SubArea] {empty} filas con superficie_subarea vacía (permitido, pero puede afectar cálculos).")

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="Carpeta donde están los Excel")
    parser.add_argument("--out", default="report_validate.json", help="Archivo salida JSON del reporte")
    args = parser.parse_args()

    excel_paths = []
    for fname in FILES_HINT.keys():
        p = os.path.join(args.dir, fname)
        if os.path.exists(p):
            excel_paths.append(p)

    data, notes = load_tables_from_excels(excel_paths)
    report = validate(data)

    report["meta"] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files_used": [os.path.basename(p) for p in excel_paths],
        "notes": notes,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("OK" if report["ok"] else "HAY ERRORES")
    print(f"Reporte: {args.out}")
    if report["errors"]:
        print("Errores (primeros 10):")
        for e in report["errors"][:10]:
            print("-", e)
    if report["warnings"]:
        print("Warnings (primeros 10):")
        for w in report["warnings"][:10]:
            print("-", w)


if __name__ == "__main__":
    main()
