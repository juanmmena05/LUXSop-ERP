import os
import json
import argparse
from datetime import datetime, timezone

import pandas as pd
import numpy as np


# ========= Helpers =========
def is_blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and np.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def _norm_id(v):
    """
    Normaliza IDs que vienen de Excel:
      - None/NaN/"" -> None
      - 3.0 -> "3"
      - "3.0" -> "3"
      - int -> "3"
      - str -> stripped
    """
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, float) and float(v).is_integer():
        return str(int(v))
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    s = str(v).strip()
    if s == "":
        return None
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def sample_ids(df: pd.DataFrame, cols, limit=10):
    cols = [c for c in cols if c in df.columns]
    if not cols:
        return []
    out = []
    for _, r in df[cols].head(limit).iterrows():
        out.append({c: (None if is_blank(r[c]) else r[c]) for c in cols})
    return out


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

    # quitar filas completamente vacías
    df = df.loc[df.apply(lambda r: any(not is_blank(v) for v in r), axis=1)].copy()

    # strip strings
    for c in df.columns:
        df[c] = df[c].apply(lambda v: v.strip() if isinstance(v, str) else v)

    return df


# ========= 2) Config por tabla =========
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
                            "required": ["metodologia_base_id", "orden", "instruccion"],
                            "uniq": ["metodologia_base_id", "orden"]},

    "Metodologia": {"sheet": "Metodologia", "pk": None,
                    "required": ["fraccion_id", "nivel_limpieza_id", "metodologia_base_id"],
                    "uniq": ["fraccion_id", "nivel_limpieza_id"]},

    "Herramienta": {"sheet": "Herramienta", "pk": "herramienta_id",
                    "required": ["herramienta_id", "nombre"]},

    # ✅ IMPORT-LIKE: Kit requiere fraccion_id (NOT NULL). nivel_limpieza_id puede ser NULL (kit general).
    "Kit": {"sheet": "Kit", "pk": "kit_id",
            "required": ["kit_id", "fraccion_id", "nombre"]},

    "KitDetalle": {"sheet": "KitDetalle", "pk": None,
                   "required": ["kit_id", "herramienta_id"],
                   "uniq": ["kit_id", "herramienta_id"]},

    "Quimico": {"sheet": "Quimico", "pk": "quimico_id",
                "required": ["quimico_id", "nombre"]},

    "Receta": {"sheet": "Receta", "pk": "receta_id",
               "required": ["receta_id", "nombre"]},

    "RecetaDetalle": {"sheet": "RecetaDetalle", "pk": None,
                      "required": ["receta_id", "quimico_id"],
                      "uniq": ["receta_id", "quimico_id"]},

    # ✅ regla opcional (tu modelo lo permite), valor/unidad pueden ser requeridos por negocio.
    "Consumo": {"sheet": "Consumo", "pk": "consumo_id",
                "required": ["consumo_id", "valor", "unidad"]},

    "Elemento": {"sheet": "Elemento", "pk": "elemento_id",
                 "required": ["elemento_id", "subarea_id", "nombre"]},

    "ElementoSet": {"sheet": "ElementoSet", "pk": "elemento_set_id",
                    "required": ["elemento_set_id", "subarea_id", "fraccion_id", "nivel_limpieza_id", "nombre"]},

    "ElementoDetalle": {"sheet": "ElementoDetalle", "pk": None,
                        "required": ["elemento_set_id", "elemento_id"],
                        "uniq": ["elemento_set_id", "elemento_id"]},

    "SOPFraccion": {"sheet": "SOPFraccion", "pk": "sop_fraccion_id",
                    "required": ["sop_fraccion_id", "sop_id", "fraccion_id", "orden"]},

    "SOPFraccionDetalle": {"sheet": "SOPFraccionDetalle", "pk": "sop_fraccion_detalle_id",
                           "required": ["sop_fraccion_detalle_id", "sop_fraccion_id", "nivel_limpieza_id"],
                           "uniq": ["sop_fraccion_id", "nivel_limpieza_id"]},
}


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
    data = {}
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


def unique_check_pk(df, pk_col):
    if pk_col is None or pk_col not in df.columns:
        return []
    s = df[pk_col].apply(_norm_id).dropna()
    dup = s[s.duplicated()].unique().tolist()
    return dup


def unique_check_composite(df, cols):
    cols = [c for c in cols if c in df.columns]
    if len(cols) < 2:
        return []

    tmp = df[cols].copy()
    # normaliza cada columna
    for c in cols:
        tmp[c] = tmp[c].apply(_norm_id)

    tmp = tmp.dropna(how="any")  # solo tuples completos
    if tmp.empty:
        return []

    dup_mask = tmp.duplicated(keep=False)
    if not dup_mask.any():
        return []

    return tmp[dup_mask].head(10).to_dict(orient="records")


def fk_check(child_df, child_col, parent_df, parent_pk, allow_null=True):
    if child_df is None or parent_df is None:
        return []
    if child_col not in child_df.columns or parent_pk not in parent_df.columns:
        return []

    child_vals_raw = [child_df[child_col].iloc[i] for i in range(len(child_df))]
    child_vals = [_norm_id(v) for v in child_vals_raw]

    if allow_null:
        child_vals = [v for v in child_vals if v is not None]
    else:
        # dejamos los None para reportarlos como <NULL>
        pass

    parent_vals = set(_norm_id(v) for v in parent_df[parent_pk].tolist())
    parent_vals.discard(None)

    bad = sorted(set(v for v in set(child_vals) if v is not None and v not in parent_vals))

    if not allow_null and any(v is None for v in [_norm_id(x) for x in child_vals_raw]):
        bad = ["<NULL>"] + bad

    return bad


def validate_required_values(df, required_cols):
    bad = {}
    for c in required_cols:
        if c not in df.columns:
            continue
        mask = df[c].apply(is_blank)
        if mask.any():
            bad[c] = int(mask.sum())
    return bad


def validate(data):
    report = {"ok": True, "errors": [], "warnings": [], "stats": {}}

    # 1) required cols + empty required values + duplicates
    for tname, df in data.items():
        cfg = CFG[tname]
        req = cfg["required"]

        missing_cols = [c for c in req if c not in df.columns]
        if missing_cols:
            report["ok"] = False
            report["errors"].append(f"[{tname}] Faltan columnas BD requeridas: {missing_cols}")

        bad_vals = validate_required_values(df, req)
        if bad_vals:
            report["ok"] = False
            report["errors"].append(f"[{tname}] Hay valores vacíos en columnas requeridas: {bad_vals}")

        pk = cfg["pk"]
        dups = unique_check_pk(df, pk)
        if dups:
            report["ok"] = False
            report["errors"].append(f"[{tname}] PK duplicadas en {pk}: ejemplos {dups[:10]}")

        if "uniq" in cfg:
            dup_rows = unique_check_composite(df, cfg["uniq"])
            if dup_rows:
                report["ok"] = False
                report["errors"].append(
                    f"[{tname}] Duplicados por clave compuesta {cfg['uniq']}: ejemplos {dup_rows[:5]}"
                )

        report["stats"][tname] = {"rows": int(len(df))}

    def get(t): return data.get(t)

    # 2) FKs
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

        # 1 SOP por subarea
        if "subarea_id" in get("SOP").columns:
            s = get("SOP")["subarea_id"].apply(_norm_id).dropna()
            dup_vals = s[s.duplicated()].unique().tolist()
            if dup_vals:
                report["ok"] = False
                report["errors"].append(f"[SOP] Hay más de 1 SOP por subarea_id: ejemplos {dup_vals[:10]}")

    if get("SOPFraccion") is not None and get("SOP") is not None:
        bad = fk_check(get("SOPFraccion"), "sop_id", get("SOP"), "sop_id", allow_null=False)
        if bad:
            report["ok"] = False
            report["errors"].append(f"[SOPFraccion] sop_id no existe en SOP: ejemplos {bad[:10]}")

    if get("SOPFraccion") is not None and get("Fraccion") is not None:
        bad = fk_check(get("SOPFraccion"), "fraccion_id", get("Fraccion"), "fraccion_id", allow_null=False)
        if bad:
            report["ok"] = False
            report["errors"].append(f"[SOPFraccion] fraccion_id no existe en Fraccion: ejemplos {bad[:10]}")

    if get("SOPFraccionDetalle") is not None and get("SOPFraccion") is not None:
        bad = fk_check(get("SOPFraccionDetalle"), "sop_fraccion_id", get("SOPFraccion"), "sop_fraccion_id", allow_null=False)
        if bad:
            report["ok"] = False
            report["errors"].append(f"[SOPFraccionDetalle] sop_fraccion_id no existe en SOPFraccion: ejemplos {bad[:10]}")

    # NivelLimpieza usado en varios
    if get("NivelLimpieza") is not None:
        if get("Metodologia") is not None:
            bad = fk_check(get("Metodologia"), "nivel_limpieza_id", get("NivelLimpieza"), "nivel_limpieza_id", allow_null=False)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[Metodologia] nivel_limpieza_id no existe en NivelLimpieza: ejemplos {bad[:10]}")

        if get("ElementoSet") is not None:
            bad = fk_check(get("ElementoSet"), "nivel_limpieza_id", get("NivelLimpieza"), "nivel_limpieza_id", allow_null=False)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[ElementoSet] nivel_limpieza_id no existe en NivelLimpieza: ejemplos {bad[:10]}")

        if get("SOPFraccionDetalle") is not None:
            bad = fk_check(get("SOPFraccionDetalle"), "nivel_limpieza_id", get("NivelLimpieza"), "nivel_limpieza_id", allow_null=False)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[SOPFraccionDetalle] nivel_limpieza_id no existe en NivelLimpieza: ejemplos {bad[:10]}")

        # ✅ Kit.nivel_limpieza_id puede ser NULL (kit general)
        if get("Kit") is not None and "nivel_limpieza_id" in get("Kit").columns:
            bad = fk_check(get("Kit"), "nivel_limpieza_id", get("NivelLimpieza"), "nivel_limpieza_id", allow_null=True)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[Kit] nivel_limpieza_id no existe en NivelLimpieza: ejemplos {bad[:10]}")

    # Kit -> Fraccion (NO NULL)
    if get("Kit") is not None and get("Fraccion") is not None:
        bad = fk_check(get("Kit"), "fraccion_id", get("Fraccion"), "fraccion_id", allow_null=False)
        if bad:
            report["ok"] = False
            report["errors"].append(f"[Kit] fraccion_id no existe en Fraccion: ejemplos {bad[:10]}")

    # KitDetalle -> Kit / Herramienta
    if get("KitDetalle") is not None:
        if get("Kit") is not None:
            bad = fk_check(get("KitDetalle"), "kit_id", get("Kit"), "kit_id", allow_null=False)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[KitDetalle] kit_id no existe en Kit: ejemplos {bad[:10]}")
        if get("Herramienta") is not None:
            bad = fk_check(get("KitDetalle"), "herramienta_id", get("Herramienta"), "herramienta_id", allow_null=False)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[KitDetalle] herramienta_id no existe en Herramienta: ejemplos {bad[:10]}")

    # RecetaDetalle -> Receta / Quimico
    if get("RecetaDetalle") is not None:
        if get("Receta") is not None:
            bad = fk_check(get("RecetaDetalle"), "receta_id", get("Receta"), "receta_id", allow_null=False)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[RecetaDetalle] receta_id no existe en Receta: ejemplos {bad[:10]}")
        if get("Quimico") is not None:
            bad = fk_check(get("RecetaDetalle"), "quimico_id", get("Quimico"), "quimico_id", allow_null=False)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[RecetaDetalle] quimico_id no existe en Quimico: ejemplos {bad[:10]}")

    # Metodologia -> Fraccion / MetodologiaBase
    if get("Metodologia") is not None:
        if get("Fraccion") is not None:
            bad = fk_check(get("Metodologia"), "fraccion_id", get("Fraccion"), "fraccion_id", allow_null=False)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[Metodologia] fraccion_id no existe en Fraccion: ejemplos {bad[:10]}")
        if get("MetodologiaBase") is not None:
            bad = fk_check(get("Metodologia"), "metodologia_base_id", get("MetodologiaBase"), "metodologia_base_id", allow_null=False)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[Metodologia] metodologia_base_id no existe en MetodologiaBase: ejemplos {bad[:10]}")

    # Elemento / ElementoSet / ElementoDetalle
    if get("Elemento") is not None and get("SubArea") is not None:
        bad = fk_check(get("Elemento"), "subarea_id", get("SubArea"), "subarea_id", allow_null=False)
        if bad:
            report["ok"] = False
            report["errors"].append(f"[Elemento] subarea_id no existe en SubArea: ejemplos {bad[:10]}")

    if get("ElementoSet") is not None:
        if get("SubArea") is not None:
            bad = fk_check(get("ElementoSet"), "subarea_id", get("SubArea"), "subarea_id", allow_null=False)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[ElementoSet] subarea_id no existe en SubArea: ejemplos {bad[:10]}")
        if get("Fraccion") is not None:
            bad = fk_check(get("ElementoSet"), "fraccion_id", get("Fraccion"), "fraccion_id", allow_null=False)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[ElementoSet] fraccion_id no existe en Fraccion: ejemplos {bad[:10]}")

    if get("ElementoDetalle") is not None:
        if get("ElementoSet") is not None:
            bad = fk_check(get("ElementoDetalle"), "elemento_set_id", get("ElementoSet"), "elemento_set_id", allow_null=False)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[ElementoDetalle] elemento_set_id no existe en ElementoSet: ejemplos {bad[:10]}")
        if get("Elemento") is not None:
            bad = fk_check(get("ElementoDetalle"), "elemento_id", get("Elemento"), "elemento_id", allow_null=False)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[ElementoDetalle] elemento_id no existe en Elemento: ejemplos {bad[:10]}")

        # opcionales
        if get("Kit") is not None and "kit_id" in get("ElementoDetalle").columns:
            bad = fk_check(get("ElementoDetalle"), "kit_id", get("Kit"), "kit_id", allow_null=True)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[ElementoDetalle] kit_id no existe en Kit: ejemplos {bad[:10]}")
        if get("Receta") is not None and "receta_id" in get("ElementoDetalle").columns:
            bad = fk_check(get("ElementoDetalle"), "receta_id", get("Receta"), "receta_id", allow_null=True)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[ElementoDetalle] receta_id no existe en Receta: ejemplos {bad[:10]}")

    # Consumo usado en SOPFraccionDetalle y ElementoDetalle
    if get("Consumo") is not None:
        if get("SOPFraccionDetalle") is not None and "consumo_id" in get("SOPFraccionDetalle").columns:
            bad = fk_check(get("SOPFraccionDetalle"), "consumo_id", get("Consumo"), "consumo_id", allow_null=True)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[SOPFraccionDetalle] consumo_id no existe en Consumo: ejemplos {bad[:10]}")

        if get("ElementoDetalle") is not None and "consumo_id" in get("ElementoDetalle").columns:
            bad = fk_check(get("ElementoDetalle"), "consumo_id", get("Consumo"), "consumo_id", allow_null=True)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[ElementoDetalle] consumo_id no existe en Consumo: ejemplos {bad[:10]}")

    # SOPFraccionDetalle opcionales
    if get("SOPFraccionDetalle") is not None:
        df = get("SOPFraccionDetalle")
        cols = df.columns

        if get("Kit") is not None and "kit_id" in cols:
            bad = fk_check(df, "kit_id", get("Kit"), "kit_id", allow_null=True)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[SOPFraccionDetalle] kit_id no existe en Kit: ejemplos {bad[:10]}")

        if get("Receta") is not None and "receta_id" in cols:
            bad = fk_check(df, "receta_id", get("Receta"), "receta_id", allow_null=True)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[SOPFraccionDetalle] receta_id no existe en Receta: ejemplos {bad[:10]}")

        if get("ElementoSet") is not None and "elemento_set_id" in cols:
            bad = fk_check(df, "elemento_set_id", get("ElementoSet"), "elemento_set_id", allow_null=True)
            if bad:
                report["ok"] = False
                report["errors"].append(f"[SOPFraccionDetalle] elemento_set_id no existe en ElementoSet: ejemplos {bad[:10]}")

        # Regla: elemento_set_id => NO kit/receta
        if "elemento_set_id" in cols and ("kit_id" in cols or "receta_id" in cols):
            bad_rows = df[
                df["elemento_set_id"].apply(lambda v: not is_blank(v))
                & (
                    (df["kit_id"].apply(lambda v: not is_blank(v)) if "kit_id" in cols else False)
                    | (df["receta_id"].apply(lambda v: not is_blank(v)) if "receta_id" in cols else False)
                )
            ]
            if len(bad_rows):
                report["ok"] = False
                ids = bad_rows["sop_fraccion_detalle_id"].head(10).tolist() if "sop_fraccion_detalle_id" in cols else []
                report["errors"].append(
                    f"[SOPFraccionDetalle] Regla rota: elemento_set_id tiene valor pero kit_id/receta_id también. Ejemplos: {ids}"
                )

    # warnings
    if get("SubArea") is not None and "superficie_subarea" in get("SubArea").columns:
        empty = int(get("SubArea")["superficie_subarea"].apply(is_blank).sum())
        if empty:
            report["warnings"].append(
                f"[SubArea] {empty} filas con superficie_subarea vacía (permitido, pero puede afectar cálculos)."
            )

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
