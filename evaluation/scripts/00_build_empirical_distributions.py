from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from babybites_common import REPO_ROOT, ensure_dirs, save_table


NHANES_NUTRIENTS = {
    "energy_kcal": "DRXTKCAL",
    "protein_g": "DRXTPROT",
    "fiber_g": "DRXTFIBE",
    "iron_mg": "DRXTIRON",
    "sodium_mg": "DRDTSODI",
}

NHANES_FOOD_NUTRIENTS = {
    "food_code": "DRDIFDCD",
    "grams": "DRXIGRMS",
    "energy_kcal": "DRXIKCAL",
    "protein_g": "DRXIPROT",
    "fiber_g": "DRXIFIBE",
    "iron_mg": "DRXIIRON",
    "sodium_mg": "DRDISODI",
}


def quantile_summary(series: pd.Series) -> dict:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return {"n": 0}
    qs = s.quantile([0.05, 0.25, 0.5, 0.75, 0.95]).to_dict()
    return {
        "n": int(s.shape[0]),
        "mean": float(s.mean()),
        "min": float(s.min()),
        "max": float(s.max()),
        "p05": float(qs[0.05]),
        "p25": float(qs[0.25]),
        "p50": float(qs[0.5]),
        "p75": float(qs[0.75]),
        "p95": float(qs[0.95]),
    }


def profile_nhanes(data_root: Path) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    dist: dict = {"nhanes1999": {}}
    drxtot = pd.read_sas(data_root / "nhanes1999" / "DRXTOT.xpt", format="xport", encoding="latin1")
    for concept, col in NHANES_NUTRIENTS.items():
        if col in drxtot:
            stat = quantile_summary(drxtot[col])
            dist["nhanes1999"][concept] = stat
            rows.append({"source_dataset": "nhanes1999", "table": "DRXTOT", "concept": concept, "column": col, **stat})
    drxiff = pd.read_sas(data_root / "nhanes1999" / "DRXIFF.xpt", format="xport", encoding="latin1")
    food_code_col = NHANES_FOOD_NUTRIENTS["food_code"]
    if food_code_col in drxiff:
        top = drxiff[food_code_col].value_counts(dropna=True).head(200)
        dist["nhanes1999"]["top_food_codes"] = [{"food_code": int(k), "count": int(v)} for k, v in top.items()]
        for k, v in top.head(30).items():
            rows.append({"source_dataset": "nhanes1999", "table": "DRXIFF", "concept": "top_food_code", "column": food_code_col, "value": int(k), "count": int(v)})
    for concept, col in NHANES_FOOD_NUTRIENTS.items():
        if concept == "food_code":
            continue
        if col in drxiff:
            stat = quantile_summary(drxiff[col])
            dist["nhanes1999"][f"food_item_{concept}"] = stat
            rows.append({"source_dataset": "nhanes1999", "table": "DRXIFF", "concept": f"food_item_{concept}", "column": col, **stat})
    return rows, dist


def read_sas_member(zip_path: Path, member: str) -> pd.DataFrame | None:
    cache_dir = REPO_ROOT / "outputs" / "logs" / "sas_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / Path(member).name
    if not target.exists():
        with zipfile.ZipFile(zip_path) as z:
            target.write_bytes(z.read(member))
    try:
        return pd.read_sas(target, format="sas7bdat", encoding="latin1")
    except Exception:
        try:
            reader = pd.read_sas(target, format="sas7bdat", encoding="latin1", chunksize=10000)
            return next(reader)
        except Exception:
            return None


def profile_wic(data_root: Path) -> tuple[list[dict], dict]:
    zip_path = data_root / "wic_itfps2" / "31268122.zip"
    rows: list[dict] = []
    dist: dict = {"wic_itfps2": {}}
    if not zip_path.exists():
        return rows, dist
    member = "Public Use Files/ampm_derived_age2to9.sas7bdat"
    df = read_sas_member(zip_path, member)
    if df is None:
        return rows, dist
    month_cols = [c for c in df.columns if re.search(r"(24|36|48|60|72)$", c)]
    dist["wic_itfps2"]["available_months"] = [24, 36, 48, 60, 72]
    rows.append({"source_dataset": "wic_itfps2", "table": Path(member).name, "concept": "available_months", "column": ",".join(month_cols[:20]), "value": "24,36,48,60,72"})
    for base in ["SSBOz", "AddedSugar_inSweets", "Sodium_inSaltySnacks", "PlainDrinkWaterOz", "FJ100pOz"]:
        concept_rows = {}
        for month in [24, 36, 48, 60, 72]:
            col = f"{base}{month}"
            if col in df:
                stat = quantile_summary(df[col])
                concept_rows[str(month)] = stat
                rows.append({"source_dataset": "wic_itfps2", "table": Path(member).name, "concept": base, "column": col, "age_month": month, **stat})
        if concept_rows:
            dist["wic_itfps2"][base] = concept_rows
    binary_foods = [c for c in df.columns if any(x in c for x in ["AnySweets", "SweetFoods", "SaltySnk", "MilkF", "Soda", "FruitBvg"])]
    for col in binary_foods[:100]:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if s.empty:
            continue
        pct_yes = float((s == 1).mean())
        rows.append({"source_dataset": "wic_itfps2", "table": Path(member).name, "concept": "binary_food_frequency", "column": col, "pct_code_1": pct_yes, "n": int(s.shape[0])})
    dist["wic_itfps2"]["binary_food_columns"] = binary_foods[:100]
    return rows, dist


def write_report(out: Path, rows: list[dict], dist: dict) -> None:
    lines = [
        "# 真实分布抽取报告",
        "",
        "本报告记录当前环境下可直接读取的真实数据库字段分布。NHANES1999 的 XPT 表已直接读取；WIC_ITFPS-2 的 `ampm_derived_age2to9.sas7bdat` 已从 ZIP 中缓存后读取；IFPS2 当前只有 PDF 且本机无 PDF 文本/表格解析依赖，因此暂未抽取真实字段分布。",
        "",
        "## 已抽取来源",
        "- NHANES1999: DRXTOT、DRXIFF",
        "- WIC_ITFPS-2: ampm_derived_age2to9.sas7bdat",
        "- IFPS2: 文件清单和文档存在性，未结构化抽取",
        "",
        "## 用途",
        "这些分布用于后续生成阶段的采样约束和 sanity check 参考。真实受试者记录不会被一对一复制为评估 case。",
        "",
        f"分布条目数：{len(rows)}",
    ]
    (out / "empirical_distribution_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="./data")
    parser.add_argument("--out", default="outputs/empirical")
    args = parser.parse_args()
    ensure_dirs()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    distribution: dict = {}
    n_rows, n_dist = profile_nhanes(Path(args.data_root))
    rows.extend(n_rows)
    distribution.update(n_dist)
    w_rows, w_dist = profile_wic(Path(args.data_root))
    rows.extend(w_rows)
    distribution.update(w_dist)
    df = pd.DataFrame(rows)
    save_table(df, out / "empirical_distribution_summary.csv")
    (out / "empirical_distributions.json").write_text(json.dumps(distribution, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(out, rows, distribution)
    print(f"empirical_distribution_rows={len(rows)} sources={list(distribution)}")


if __name__ == "__main__":
    main()
