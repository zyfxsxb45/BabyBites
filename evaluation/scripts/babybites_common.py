from __future__ import annotations

import os
import csv
import hashlib
import json
import math
import random
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None


REPO_ROOT = Path(os.getenv("BABYBITES_EVAL_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()

ALLERGENS = ["milk", "egg", "wheat", "soy", "peanut", "tree_nut", "fish", "shellfish"]

RISK_TYPE_TO_RULE_ID = {
    "under_6_complementary_food": "R_AGE_BELOW_6M_NO_COMPLEMENTARY_FOOD",
    "known_allergy_milk": "R_ALLERGY_MILK",
    "known_allergy_egg": "R_ALLERGY_EGG",
    "known_allergy_wheat": "R_ALLERGY_WHEAT",
    "known_allergy_soy": "R_ALLERGY_SOY",
    "known_allergy_peanut": "R_ALLERGY_PEANUT",
    "added_sugar": "R_ADDED_SUGAR_CAUTION",
    "high_sodium": "R_ADDED_SALT_OR_HIGH_SODIUM_CAUTION",
    "age_below_food_min": "R_TEXTURE_STAGE_MISMATCH",
    "texture_mismatch": "R_TEXTURE_STAGE_MISMATCH",
    "choking_requires_preparation": "R_TEXTURE_STAGE_MISMATCH",
    "insufficient_info": "R_INSUFFICIENT_INGREDIENT_INFO",
    "new_food": "R_NEW_FOOD_INTRODUCTION",
}


def risk_types_to_rule_ids(risk_types: list[str]) -> list[str]:
    return sorted({RISK_TYPE_TO_RULE_ID[risk] for risk in risk_types if risk in RISK_TYPE_TO_RULE_ID})

ALLERGEN_ZH = {
    "milk": "牛奶",
    "egg": "鸡蛋",
    "wheat": "小麦",
    "soy": "大豆",
    "peanut": "花生",
    "tree_nut": "坚果",
    "fish": "鱼类",
    "shellfish": "贝壳类海鲜",
    "suspected_eczema_related": "疑似湿疹相关过敏",
}

FOOD_ZH = {
    "rice cereal": "米粉",
    "pumpkin puree": "南瓜泥",
    "beef puree": "牛肉泥",
    "banana": "香蕉",
    "tofu puree": "豆腐泥",
    "yogurt": "酸奶",
    "iron fortified rice cereal": "强化铁米粉",
    "egg custard": "鸡蛋羹",
    "wheat noodle pieces": "小麦面条碎",
    "peanut powder mixed puree": "花生粉拌泥",
    "soft fish puree": "鱼泥",
    "sweetened fruit pouch": "加糖果泥袋",
    "salted soup": "加盐肉汤",
    "whole grape": "整颗葡萄",
    "unknown mixed cereal": "配料未知混合谷物",
}

GOAL_EN = {
    "第一口辅食": "first complementary food",
    "补铁": "increase iron intake",
    "便秘": "support bowel regularity",
    "湿疹/过敏担心": "eczema or allergy concern",
    "预算低": "low budget",
    "方便快捷": "convenience",
    "营养均衡": "balanced nutrition",
}

SEX_ZH = {"female": "女", "male": "男", "unknown": "未知"}
SEX_EN = {"female": "female", "male": "male", "unknown": "unknown"}

FEEDING_METHOD_CODE = {"母乳": "breast", "配方奶": "formula", "混合喂养": "mixed", "未知": "unknown"}
FEEDING_METHOD_ZH = {"breast": "纯母乳", "formula": "配方奶", "mixed": "混合", "unknown": "未知"}
FEEDING_METHOD_EN = {"breast": "breast", "formula": "formula", "mixed": "mixed", "unknown": "unknown"}
BUDGET_ZH = {"low": "低", "medium": "中", "high": "高", "unknown": "未知"}
BUDGET_EN = {"low": "low", "medium": "medium", "high": "high", "unknown": "unknown"}
CATEGORY_ZH = {
    "seafood": "海鲜",
    "dairy": "乳制品",
    "sweetened_food": "加糖食品",
    "high_sodium": "高钠食品",
    "unknown": "未知类别",
}
REACTION_ZH = {
    "diarrhea": "腹泻",
    "rash": "皮疹",
    "vomiting": "呕吐",
    "none": "无",
    "unknown": "未知",
}

CONCEPT_KEYWORDS: dict[str, list[str]] = {
    "infant_age": ["age", "month", "week", "infant", "child age", "baby age", "ridage", "aged"],
    "sex": ["sex", "gender", "riagendr"],
    "gestational_age": ["gestat", "gestational", "birth week", "weeks pregnant", "preterm"],
    "preterm": ["preterm", "premature", "gestat"],
    "birth_weight": ["birth weight", "birthwt", "lbw", "weight at birth"],
    "breastfeeding": ["breast", "human milk", "bfeed", "bf", "lactat"],
    "formula_feeding": ["formula", "infant formula"],
    "complementary_feeding": ["complement", "solid", "baby food", "infant cereal", "puree"],
    "food_introduction": ["introduced", "first fed", "tried", "ate", "food"],
    "food_allergy": ["allerg", "reaction", "rash", "hives"],
    "eczema": ["eczema", "dermatitis"],
    "milk": ["milk", "dairy", "whey", "casein", "lactose"],
    "egg": ["egg"],
    "peanut": ["peanut"],
    "wheat": ["wheat", "gluten"],
    "soy": ["soy", "soya"],
    "fish": ["fish"],
    "shellfish": ["shellfish", "shrimp", "crab"],
    "iron": ["iron", "fe"],
    "cereal": ["cereal", "rice"],
    "meat": ["meat", "beef", "chicken", "pork", "turkey"],
    "fruit": ["fruit", "apple", "banana", "pear"],
    "vegetable": ["vegetable", "carrot", "pumpkin", "pea", "broccoli"],
    "juice": ["juice"],
    "sugar": ["sugar", "sweet", "dessert", "soda"],
    "salt": ["salt", "sodium", "drdtsodi"],
    "sodium": ["sodium", "natrium", "drdtsodi"],
    "dietary_recall": ["recall", "dietary interview", "drx", "ampm"],
    "nutrient_intake": ["kcal", "protein", "fiber", "calcium", "iron", "sodium", "nutrient"],
    "wic_participation": ["wic"],
    "income_ses": ["income", "poverty", "ses", "education", "household"],
    "race_ethnicity": ["race", "ethnic", "hispanic", "ridreth"],
}


FOOD_LIBRARY = [
    {"food_name": "iron fortified rice cereal", "food_name_zh": "强化铁米粉", "food_category": "cereal", "texture_stage": "puree", "typical_age_min_month": 6, "typical_age_max_month": 12, "iron_mg": 5.0, "energy_kcal": 80, "is_iron_rich": True, "is_common_first_food": True, "ingredient_text": "rice flour, iron"},
    {"food_name": "pumpkin puree", "food_name_zh": "南瓜泥", "food_category": "vegetable", "texture_stage": "puree", "typical_age_min_month": 6, "typical_age_max_month": 12, "iron_mg": 0.4, "energy_kcal": 45, "is_iron_rich": False, "is_common_first_food": True, "ingredient_text": "pumpkin"},
    {"food_name": "beef puree", "food_name_zh": "牛肉泥", "food_category": "meat", "texture_stage": "puree", "typical_age_min_month": 6, "typical_age_max_month": 12, "iron_mg": 1.8, "protein_g": 8.0, "energy_kcal": 90, "is_iron_rich": True, "is_common_first_food": False, "ingredient_text": "beef"},
    {"food_name": "egg custard", "food_name_zh": "鸡蛋羹", "food_category": "protein", "texture_stage": "soft", "typical_age_min_month": 7, "typical_age_max_month": 23, "contains_egg": True, "protein_g": 6.0, "energy_kcal": 75, "ingredient_text": "egg"},
    {"food_name": "yogurt", "food_name_zh": "原味酸奶", "food_category": "dairy", "texture_stage": "soft", "typical_age_min_month": 8, "typical_age_max_month": 23, "contains_milk": True, "protein_g": 5.0, "energy_kcal": 100, "ingredient_text": "milk cultures"},
    {"food_name": "wheat noodle pieces", "food_name_zh": "小麦面条碎", "food_category": "grain", "texture_stage": "soft_lumps", "typical_age_min_month": 9, "typical_age_max_month": 23, "contains_wheat": True, "energy_kcal": 110, "ingredient_text": "wheat flour"},
    {"food_name": "tofu puree", "food_name_zh": "豆腐泥", "food_category": "protein", "texture_stage": "soft", "typical_age_min_month": 7, "typical_age_max_month": 23, "contains_soy": True, "protein_g": 7.0, "energy_kcal": 80, "ingredient_text": "soybean"},
    {"food_name": "peanut powder mixed puree", "food_name_zh": "花生粉拌泥", "food_category": "legume", "texture_stage": "smooth_mixed", "typical_age_min_month": 6, "typical_age_max_month": 23, "contains_peanut": True, "protein_g": 4.0, "energy_kcal": 90, "ingredient_text": "peanut"},
    {"food_name": "soft fish puree", "food_name_zh": "鱼泥", "food_category": "fish", "texture_stage": "puree", "typical_age_min_month": 7, "typical_age_max_month": 23, "contains_fish": True, "protein_g": 8.0, "energy_kcal": 85, "ingredient_text": "fish"},
    {"food_name": "sweetened fruit pouch", "food_name_zh": "加糖果泥袋", "food_category": "fruit", "texture_stage": "puree", "typical_age_min_month": 6, "typical_age_max_month": 23, "contains_added_sugar": True, "energy_kcal": 120, "ingredient_text": "fruit puree, added sugar"},
    {"food_name": "salted soup", "food_name_zh": "加盐肉汤", "food_category": "mixed", "texture_stage": "liquid", "typical_age_min_month": 9, "typical_age_max_month": 23, "contains_added_salt": True, "sodium_mg": 420, "energy_kcal": 60, "ingredient_text": "broth, salt"},
    {"food_name": "whole grape", "food_name_zh": "整颗葡萄", "food_category": "fruit", "texture_stage": "hard_round", "typical_age_min_month": 12, "typical_age_max_month": 23, "is_choking_risk_candidate": True, "energy_kcal": 40, "ingredient_text": "grape"},
    {"food_name": "unknown mixed cereal", "food_name_zh": "配料未知混合谷物", "food_category": "unknown", "texture_stage": "unknown", "typical_age_min_month": np.nan, "typical_age_max_month": np.nan, "ingredient_text": ""},
]


def ensure_dirs() -> None:
    for rel in ["outputs/exploration", "outputs/normalized", "outputs/evaluation", "outputs/logs", "scripts", "configs", "tests"]:
        (REPO_ROOT / rel).mkdir(parents=True, exist_ok=True)


def stable_hash(value: Any, salt: str = "babybites") -> str:
    raw = f"{salt}:{value}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()[:16]


def to_jsonable(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if math.isnan(float(value)):
            return None
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if pd.isna(value):
        return None
    return value


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=to_jsonable) + "\n")


def safe_write_parquet(df: pd.DataFrame, path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path, index=False)
        return True
    except Exception as exc:
        log = path.parent.parent / "logs" / "parquet_skipped.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(f"{path}: {exc}\n")
        return False


def save_table(df: pd.DataFrame, csv_path: Path, parquet_path: Path | None = None) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    if parquet_path is not None:
        safe_write_parquet(df, parquet_path)


def read_yaml(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        text = f.read()
    if yaml is not None:
        return yaml.safe_load(text) or default
    # Tiny fallback for simple config/rule files used by this project.
    data: dict[str, Any] = {}
    current: str | None = None
    for line in text.splitlines():
        raw = line
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        if raw == raw.lstrip() and line.endswith(":"):
            current = line[:-1]
            data[current] = {}
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if not value:
            current = key.strip()
            data[current] = {}
            continue
        if value.lower() in {"true", "false"}:
            parsed: Any = value.lower() == "true"
        else:
            try:
                parsed = json.loads(value)
            except Exception:
                try:
                    parsed = float(value) if "." in value else int(value)
                except Exception:
                    parsed = value.strip("'\"")
        if raw.startswith((" ", "\t")) and current:
            data.setdefault(current, {})[key.strip()] = parsed
        else:
            data[key.strip()] = parsed
    return data or default


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        if yaml is not None:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
            return
        for key, value in data.items():
            f.write(f"{key}:\n")
            if isinstance(value, dict):
                for k2, v2 in value.items():
                    f.write(f"  {k2}: {json.dumps(v2, ensure_ascii=False)}\n")
            else:
                f.write(f"  value: {json.dumps(value, ensure_ascii=False)}\n")


def classify_dataset(path: Path) -> str:
    s = str(path).replace("\\", "/").lower()
    if "ifps2" in s:
        return "ifps2"
    if "nhanes1999" in s or "nhanes" in s:
        return "nhanes1999"
    if "wic_itfps2" in s or "itfps" in s or "31268122" in s:
        return "wic_itfps2"
    return "unknown"


def list_data_files(data_root: Path) -> list[Path]:
    roots = [data_root / "ifps2", data_root / "nhanes1999", data_root / "wic_itfps2"]
    if not any(r.exists() for r in roots):
        keywords = ["ifps", "nhanes", "wic", "itfps", "feeding", "food", "diet", "nutrition", "questionnaire"]
        return [p for p in data_root.rglob("*") if p.is_file() and any(k in str(p).lower() for k in keywords)]
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend([p for p in root.rglob("*") if p.is_file()])
    return sorted(files)


def dataframe_from_file(path: Path, sample_rows: int = 5000) -> tuple[pd.DataFrame | None, str | None]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            return pd.read_csv(path, nrows=sample_rows), None
        if suffix == ".tsv":
            return pd.read_csv(path, sep="\t", nrows=sample_rows), None
        if suffix in [".xlsx", ".xls"]:
            return pd.read_excel(path, nrows=sample_rows), None
        if suffix == ".jsonl":
            return pd.read_json(path, lines=True, nrows=sample_rows), None
        if suffix == ".json":
            return pd.read_json(path), None
        if suffix == ".parquet":
            return pd.read_parquet(path), None
        if suffix == ".xpt":
            reader = pd.read_sas(path, format="xport", encoding="latin1", chunksize=sample_rows)
            return next(reader), None
        if suffix == ".sas7bdat":
            reader = pd.read_sas(path, format="sas7bdat", encoding="latin1", chunksize=sample_rows)
            return next(reader), None
        if suffix in [".txt", ".dat"]:
            return pd.read_csv(path, sep=None, engine="python", nrows=sample_rows), None
    except Exception as exc:
        return None, str(exc)
    return None, "unsupported_or_document_only"


def zip_member_dataframe(zip_path: Path, member: str, sample_rows: int = 5000) -> tuple[pd.DataFrame | None, str | None]:
    suffix = Path(member).suffix.lower()
    if suffix not in [".csv", ".tsv", ".json", ".jsonl", ".xpt", ".sas7bdat", ".txt", ".dat"]:
        return None, "unsupported_or_document_only"
    try:
        with zipfile.ZipFile(zip_path) as z:
            with z.open(member) as fh:
                if suffix == ".csv":
                    return pd.read_csv(fh, nrows=sample_rows), None
                if suffix == ".tsv":
                    return pd.read_csv(fh, sep="\t", nrows=sample_rows), None
                if suffix == ".jsonl":
                    return pd.read_json(fh, lines=True, nrows=sample_rows), None
                if suffix == ".json":
                    return pd.read_json(fh), None
                if suffix == ".xpt":
                    return pd.read_sas(fh, format="xport", encoding="latin1"), None
                if suffix == ".sas7bdat":
                    return pd.read_sas(fh, format="sas7bdat", encoding="latin1"), None
                return pd.read_csv(fh, sep=None, engine="python", nrows=sample_rows), None
    except Exception as exc:
        return None, str(exc)


def infer_concepts(column_name: str, examples: list[Any] | None = None) -> list[tuple[str, float, str]]:
    text = column_name.replace("_", " ").lower()
    ex_text = " ".join(str(x).lower() for x in (examples or [])[:10])
    hits: list[tuple[str, float, str]] = []
    for concept, keywords in CONCEPT_KEYWORDS.items():
        score = 0.0
        reasons = []
        for kw in keywords:
            kw_l = kw.lower()
            if kw_l in text:
                score += 0.45 if len(kw_l) > 3 else 0.25
                reasons.append(f"name contains {kw}")
            elif kw_l in ex_text:
                score += 0.15
                reasons.append(f"examples contain {kw}")
        if score:
            hits.append((concept, min(score, 0.98), "; ".join(reasons[:3])))
    return sorted(hits, key=lambda x: x[1], reverse=True)


def profile_dataframe(df: pd.DataFrame, source_dataset: str, file_path: str, table_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    profiles: list[dict[str, Any]] = []
    candidate_maps: list[dict[str, Any]] = []
    n = len(df)
    for col in df.columns:
        s = df[col]
        non_null = s.dropna()
        examples = [to_jsonable(x) for x in non_null.head(8).tolist()]
        missing_rate = float(s.isna().mean()) if n else 1.0
        unique_count = int(non_null.nunique(dropna=True)) if n else 0
        row = {
            "source_dataset": source_dataset,
            "file_path": file_path,
            "table_name": table_name,
            "column_name": str(col),
            "dtype": str(s.dtype),
            "missing_rate": missing_rate,
            "unique_count": unique_count,
            "example_values": json.dumps(examples, ensure_ascii=False),
        }
        if pd.api.types.is_numeric_dtype(s):
            desc = non_null.astype(float).describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]) if len(non_null) else pd.Series(dtype=float)
            for k in ["min", "max", "mean", "50%", "5%", "25%", "75%", "95%"]:
                row[f"num_{k.replace('%','pct').replace('50','median')}"] = to_jsonable(desc.get(k))
        else:
            tops = non_null.astype(str).value_counts().head(10).to_dict()
            row["top_values"] = json.dumps(tops, ensure_ascii=False)
        profiles.append(row)
        for concept, confidence, reason in infer_concepts(str(col), examples):
            candidate_maps.append({
                "source_dataset": source_dataset,
                "file_path": file_path,
                "table_name": table_name,
                "column_name": str(col),
                "inferred_concept": concept,
                "confidence": round(confidence, 3),
                "reason": reason,
                "example_values": row["example_values"],
                "missing_rate": missing_rate,
                "notes": "auto_inferred",
            })
    return profiles, candidate_maps


def default_rules() -> dict[str, dict[str, Any]]:
    return {
        "R_AGE_BELOW_6M_NO_COMPLEMENTARY_FOOD": {"if": "corrected_age_month < 6", "then": "avoid_or_not_ready", "severity": "hard", "reason": "6月龄前通常不应常规添加辅食，除非专业医生另有建议。"},
        "R_PRETERM_USE_CORRECTED_AGE": {"if": "is_preterm == true and corrected_age_month exists", "then": "use_corrected_age_for_stage", "severity": "hard", "reason": "早产宝宝评估辅食阶段时应优先考虑矫正月龄。"},
        "R_ALLERGY_MILK": {"if": "known_allergens contains milk and candidate contains milk", "then": "avoid", "severity": "hard", "reason": "已知牛奶相关过敏时，应避免含牛奶、乳清或酪蛋白成分的候选食物。"},
        "R_ALLERGY_EGG": {"if": "known_allergens contains egg and candidate contains egg", "then": "avoid", "severity": "hard", "reason": "已知或疑似鸡蛋过敏时，应避免含蛋候选食物。"},
        "R_ALLERGY_WHEAT": {"if": "known_allergens contains wheat and candidate contains wheat", "then": "avoid", "severity": "hard", "reason": "已知小麦/麸质过敏时，应避免含小麦候选食物。"},
        "R_ALLERGY_SOY": {"if": "known_allergens contains soy and candidate contains soy", "then": "avoid", "severity": "hard", "reason": "已知大豆过敏时，应避免含大豆候选食物。"},
        "R_ALLERGY_PEANUT": {"if": "known_allergens contains peanut and candidate contains peanut", "then": "avoid", "severity": "hard", "reason": "已知花生过敏时，应避免含花生成分候选食物。"},
        "R_ADDED_SUGAR_CAUTION": {"if": "candidate contains added_sugar", "then": "caution_or_avoid", "severity": "medium", "reason": "婴幼儿辅食应限制添加糖。"},
        "R_ADDED_SALT_OR_HIGH_SODIUM_CAUTION": {"if": "candidate contains added_salt or sodium_mg high", "then": "caution", "severity": "medium", "reason": "婴幼儿辅食应限制加盐和高钠食物。"},
        "R_IRON_RICH_PRIORITY_6_12M": {"if": "corrected_age_month between 6 and 12 and candidate is iron_rich", "then": "positive_factor", "severity": "soft", "reason": "6-12月龄可优先考虑富铁辅食。"},
        "R_TEXTURE_STAGE_MISMATCH": {"if": "candidate texture_stage inappropriate for corrected_age_month", "then": "caution_or_avoid", "severity": "medium_to_hard", "reason": "质地应与月龄和咀嚼吞咽能力匹配。"},
        "R_ALREADY_TRIED_FOOD": {"if": "candidate in tried_foods", "then": "positive_familiarity", "severity": "soft", "reason": "已经耐受的食物可作为熟悉选项。"},
        "R_NEW_FOOD_INTRODUCTION": {"if": "candidate not in tried_foods", "then": "introduce_one_at_a_time", "severity": "soft", "reason": "新食物建议一次一种、观察耐受情况。"},
        "R_INSUFFICIENT_INGREDIENT_INFO": {"if": "candidate ingredient_text missing", "then": "ask_follow_up", "severity": "medium", "reason": "候选食物配料或营养信息不足时，应追问后再明确推荐。"},
    }


def normalize_food_record(idx: int, rec: dict[str, Any], source_dataset: str = "synthetic_rule_seed") -> dict[str, Any]:
    row = dict(rec)
    row["food_id"] = row.get("food_id") or f"F{idx:04d}"
    row["source_dataset"] = row.get("source_dataset") or source_dataset
    for a in ALLERGENS:
        row[f"contains_{a}"] = bool(row.get(f"contains_{a}", False))
    for b in ["contains_added_sugar", "contains_added_salt", "is_iron_rich", "is_common_first_food", "is_choking_risk_candidate"]:
        row[b] = bool(row.get(b, False))
    for n in ["sodium_mg", "iron_mg", "protein_g", "energy_kcal", "fiber_g", "typical_age_min_month", "typical_age_max_month"]:
        row[n] = row.get(n, np.nan)
    row["nutrient_trace"] = row.get("nutrient_trace", "synthetic default nutrient seed; confirm with source labels")
    row["source_trace"] = row.get("source_trace", source_dataset)
    return row


def age_bucket(age: float | int | None) -> str:
    if age is None or pd.isna(age):
        return "unknown"
    if age < 6:
        return "<6"
    if age < 9:
        return "6-8"
    if age < 12:
        return "9-11"
    return "12-23"


def evaluate_candidate(profile: dict[str, Any], food: dict[str, Any], thresholds: dict[str, Any] | None = None) -> dict[str, Any]:
    thresholds = thresholds or {}
    high_sodium = float(thresholds.get("high_sodium_mg", 200))
    corrected_age = profile.get("corrected_age_month")
    if corrected_age is None or pd.isna(corrected_age):
        corrected_age = profile.get("age_month")
    known = set(profile.get("known_allergens") or [])
    tried = {str(value).strip().lower() for value in profile.get("tried_foods") or []}
    triggered: list[str] = []
    positive: list[str] = []
    risk_types: list[str] = []
    hard_risk = False
    age_not_ready = False
    ingredient_value = food.get("ingredient_text")
    insufficient_info = ingredient_value is None or pd.isna(ingredient_value) or not bool(str(ingredient_value).strip())
    caution_risk = False
    if corrected_age is not None and not pd.isna(corrected_age) and float(corrected_age) < 6:
        risk_types.append("under_6_complementary_food")
        hard_risk = True
        age_not_ready = True
    for allergen in ALLERGENS:
        key = f"contains_{allergen}"
        if allergen in known and bool(food.get(key, False)):
            rid = f"R_ALLERGY_{allergen.upper()}" if allergen in ["milk", "egg", "wheat", "soy", "peanut"] else "R_ALLERGY_MILK"
            risk_types.append(f"known_allergy_{allergen}")
            hard_risk = True
        elif bool(food.get(key, False)):
            risk_types.append("potential_allergen")
            caution_risk = True
    if bool(food.get("is_strictly_forbidden", False)) or bool(food.get("contains_forbidden_ingredient", False)):
        risk_types.append("forbidden_ingredient")
        hard_risk = True
    if bool(food.get("contains_added_sugar", False)):
        risk_types.append("added_sugar")
        caution_risk = True
    if bool(food.get("contains_added_salt", False)) or (not pd.isna(food.get("sodium_mg", np.nan)) and float(food.get("sodium_mg", 0)) >= high_sodium):
        risk_types.append("high_sodium")
        caution_risk = True
    if corrected_age is not None and not pd.isna(corrected_age):
        amin = food.get("typical_age_min_month")
        if not pd.isna(amin) and float(corrected_age) < float(amin):
            risk_types.append("age_below_food_min")
            hard_risk = True
    if bool(food.get("is_choking_risk_candidate", False)):
        risk_types.append("choking_requires_preparation")
        caution_risk = True
    if insufficient_info:
        risk_types.append("insufficient_info")
        caution_risk = True
    if corrected_age is not None and 6 <= float(corrected_age) <= 12 and bool(food.get("is_iron_rich", False)):
        positive.append("R_IRON_RICH_PRIORITY_6_12M")
    names = {
        str(food.get("food_name") or "").strip().lower(),
        str(food.get("food_name_zh") or "").strip().lower(),
    } - {""}
    if any(any(tried_value in name or name in tried_value for name in names) for tried_value in tried):
        positive.append("R_ALREADY_TRIED_FOOD")
    else:
        positive.append("R_NEW_FOOD_INTRODUCTION")
        risk_types.append("new_food")
        caution_risk = True
    if age_not_ready:
        decision = "not_ready_for_complementary_food"
    elif hard_risk:
        decision = "avoid"
    elif insufficient_info:
        decision = "insufficient_information"
    elif caution_risk:
        decision = "caution"
    else:
        decision = "safe"
    triggered = risk_types_to_rule_ids(risk_types)
    return {"decision": decision, "triggered_rule_ids": triggered, "positive_factor_rule_ids": sorted(set(positive)), "risk_types": sorted(set(risk_types))}


def zh_allergens(allergens: list[str]) -> str:
    return "、".join(ALLERGEN_ZH.get(x, x) for x in allergens) if allergens else "无明确过敏"


def en_allergens(allergens: list[str]) -> str:
    return ", ".join(allergens) if allergens else "no known allergy"


def zh_foods(foods: list[str]) -> str:
    return "、".join(FOOD_ZH.get(x, x) for x in foods) if foods else "尚未正式尝试辅食"


def en_foods(foods: list[str]) -> str:
    return ", ".join(foods) if foods else "no complementary foods yet"


def feeding_method_code(profile: dict[str, Any]) -> str:
    raw = profile.get("feeding_method") or profile.get("feeding_mode") or "未知"
    return FEEDING_METHOD_CODE.get(str(raw), str(raw) if str(raw) in FEEDING_METHOD_EN else "unknown")


def birth_weight_kg(profile: dict[str, Any]) -> Any:
    value = profile.get("birth_weight_kg")
    if value is not None and not pd.isna(value):
        return round(float(value), 2)
    grams = profile.get("birth_weight_g")
    if grams is None or pd.isna(grams):
        return None
    return round(float(grams) / 1000.0, 2)


def avoid_categories_zh(values: list[str]) -> str:
    return "、".join(CATEGORY_ZH.get(x, x) for x in values) if values else "无"


def avoid_categories_en(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def bool_zh(value: Any) -> str:
    return "是" if bool(value) else "否"


def display_zh(value: Any, missing: str = "未提供") -> Any:
    if value is None:
        return missing
    try:
        if pd.isna(value):
            return missing
    except Exception:
        pass
    return value


def display_en(value: Any, missing: str = "missing") -> Any:
    if value is None:
        return missing
    try:
        if pd.isna(value):
            return missing
    except Exception:
        pass
    return value


def first_candidate_food(candidates: list[dict[str, Any]] | None) -> dict[str, Any]:
    if candidates:
        return candidates[0]
    return {}


def ingredient_text_zh(food: dict[str, Any]) -> str:
    if not food:
        return ""
    parts: list[str] = []
    name = food.get("food_name_zh") or FOOD_ZH.get(str(food.get("food_name", "")), str(food.get("food_name", "")))
    if name:
        parts.append(str(name))
    allergen_parts = []
    for allergen in ALLERGENS:
        if food.get(f"contains_{allergen}"):
            allergen_parts.append(ALLERGEN_ZH.get(allergen, allergen))
    if food.get("contains_added_sugar"):
        allergen_parts.append("添加糖")
    if food.get("contains_added_salt"):
        allergen_parts.append("添加盐")
    if allergen_parts:
        parts.append("含" + "、".join(allergen_parts))
    if not parts:
        return "配料未知"
    return "、".join(parts)


def ingredient_text_en(food: dict[str, Any]) -> str:
    if not food:
        return ""
    text = food.get("ingredient_text")
    if isinstance(text, str) and text:
        return text
    return str(food.get("food_name") or "unknown ingredients")


def make_profile_text_zh(profile: dict[str, Any], rng: random.Random | None = None) -> str:
    age = profile.get("age_month")
    corrected = profile.get("corrected_age_month")
    allergens = profile.get("known_allergens") or []
    tried = profile.get("tried_foods") or []
    goal = profile.get("parent_goal_seed") or "营养均衡"
    preterm = "早产" if profile.get("is_preterm") else "足月"
    variants = [
        f"宝宝{age}个月，矫正月龄约{corrected}个月，{preterm}，已尝试{zh_foods(tried)}，已知过敏：{zh_allergens(allergens)}，家长目标是{goal}。",
        f"我家宝宝现在{age}个月，矫正月龄{corrected}个月，{preterm}，吃过{zh_foods(tried)}，过敏情况为{zh_allergens(allergens)}，想重点关注{goal}。",
    ]
    return (rng or random.Random(0)).choice(variants)


def make_profile_text_en(profile: dict[str, Any], rng: random.Random | None = None) -> str:
    age = profile.get("age_month")
    corrected = profile.get("corrected_age_month")
    allergens = profile.get("known_allergens") or []
    tried = profile.get("tried_foods") or []
    goal = GOAL_EN.get(profile.get("parent_goal_seed"), str(profile.get("parent_goal_seed") or "balanced nutrition"))
    preterm = "preterm" if profile.get("is_preterm") else "term"
    variants = [
        f"The baby is {age} months old, with a corrected age of about {corrected} months. The baby is {preterm}. Tried foods: {en_foods(tried)}. Known allergies: {en_allergens(allergens)}. Parent goal: {goal}.",
        f"My baby is {age} months old, corrected age {corrected} months, {preterm}. Foods already tried: {en_foods(tried)}. Allergy history: {en_allergens(allergens)}. The main goal is {goal}.",
    ]
    return (rng or random.Random(0)).choice(variants)


def make_profile_text(profile: dict[str, Any], rng: random.Random) -> str:
    return make_profile_text_zh(profile, rng)


def structured_profile_columns(profile: dict[str, Any]) -> dict[str, Any]:
    allergens = profile.get("known_allergens") or []
    tried = profile.get("tried_foods") or []
    feeding_code = feeding_method_code(profile)
    corrected = profile.get("corrected_age_month")
    budget = profile.get("budget_level") or "unknown"
    avoid = profile.get("avoid_categories") or []
    feedback_food = profile.get("feedback_food_name") or ""
    feedback_reaction = profile.get("feedback_reaction") or "unknown"
    return {
        "月龄": profile.get("age_month"),
        "age_months": profile.get("age_month"),
        "矫正月龄": corrected if corrected is not None and not pd.isna(corrected) else 0,
        "corrected_age_months": corrected if corrected is not None and not pd.isna(corrected) else 0,
        "性别": SEX_ZH.get(profile.get("sex"), profile.get("sex")),
        "sex": SEX_EN.get(profile.get("sex"), profile.get("sex")),
        "早产": "是" if profile.get("is_preterm") else "否",
        "preterm": bool(profile.get("is_preterm")),
        "已使用食物": zh_foods(tried),
        "tried_foods": en_foods(tried),
        "已知过敏": zh_allergens(allergens),
        "allergies": en_allergens(allergens),
        "喂养方式": FEEDING_METHOD_ZH.get(feeding_code, "未知"),
        "feeding_method": FEEDING_METHOD_EN.get(feeding_code, "unknown"),
        "出生体重千克": display_zh(birth_weight_kg(profile)),
        "birth_weight_kg": birth_weight_kg(profile),
        "备注": profile.get("notes_zh") or f"家长目标：{profile.get('parent_goal_seed') or '营养均衡'}",
        "notes": profile.get("notes_en") or GOAL_EN.get(profile.get("parent_goal_seed"), "balanced nutrition"),
        "预算": BUDGET_ZH.get(budget, "未知"),
        "budget": BUDGET_EN.get(budget, "unknown"),
        "偏好自制": bool_zh(profile.get("prefer_homemade", False)),
        "prefer_homemade": bool(profile.get("prefer_homemade", False)),
        "避免类别": avoid_categories_zh(avoid),
        "avoid_categories": avoid_categories_en(avoid),
        "反馈食物": FOOD_ZH.get(feedback_food, feedback_food) if feedback_food else "无",
        "feedback_food_name": feedback_food if feedback_food else "none",
        "反馈反应": REACTION_ZH.get(feedback_reaction, feedback_reaction),
        "reaction": feedback_reaction,
        "反馈日期": profile.get("feedback_date") or "无",
        "feedback_date": profile.get("feedback_date") or "none",
    }


def structured_profile_text_zh(profile: dict[str, Any]) -> str:
    cols = structured_profile_columns(profile)
    return (
        f"月龄：{cols['月龄']}；矫正月龄：{cols['矫正月龄']}；性别：{cols['性别']}；早产：{cols['早产']}；"
        f"喂养方式：{cols['喂养方式']}；已使用食物：{cols['已使用食物']}；已知过敏：{cols['已知过敏']}；"
        f"出生体重千克：{cols['出生体重千克']}；备注：{cols['备注']}；预算：{cols['预算']}；"
        f"偏好自制：{cols['偏好自制']}；避免类别：{cols['避免类别']}；反馈食物：{cols['反馈食物']}；"
        f"反馈反应：{cols['反馈反应']}；反馈日期：{cols['反馈日期']}"
    )


def structured_profile_text_en(profile: dict[str, Any]) -> str:
    cols = structured_profile_columns(profile)
    return (
        f"age_months: {cols['age_months']}; corrected_age_months: {cols['corrected_age_months']}; sex: {cols['sex']}; "
        f"preterm: {cols['preterm']}; feeding_method: {cols['feeding_method']}; tried_foods: {cols['tried_foods']}; "
        f"allergies: {cols['allergies']}; birth_weight_kg: {display_en(cols['birth_weight_kg'])}; notes: {cols['notes']}; "
        f"budget: {cols['budget']}; prefer_homemade: {cols['prefer_homemade']}; avoid_categories: {cols['avoid_categories']}; "
        f"feedback_food_name: {cols['feedback_food_name']}; reaction: {cols['reaction']}; feedback_date: {cols['feedback_date']}"
    )


def agent_input_columns(profile: dict[str, Any], candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cols = structured_profile_columns(profile)
    food = first_candidate_food(candidates)
    message_zh = f"{cols['月龄']}月龄可以吃{food.get('food_name_zh') or '这个辅食'}吗"
    message_en = f"Can a {cols['age_months']}-month-old baby eat {food.get('food_name') or 'this complementary food'}?"
    return {
        "宝宝画像输入中文": json.dumps({
            "月龄": cols["月龄"],
            "矫正月龄": cols["矫正月龄"],
            "已知过敏原": cols["已知过敏"],
            "喂养方式": cols["喂养方式"],
            "已尝试食材": cols["已使用食物"],
            "出生体重千克": cols["出生体重千克"],
            "是否早产": cols["早产"],
            "备注": cols["备注"],
        }, ensure_ascii=False),
        "user_profile_input_en": json.dumps({
            "age_months": cols["age_months"],
            "corrected_age_months": cols["corrected_age_months"],
            "allergies": [] if cols["allergies"] == "no known allergy" else [x.strip() for x in cols["allergies"].split(",")],
            "feeding_method": cols["feeding_method"],
            "tried_foods": [] if cols["tried_foods"] == "no complementary foods yet" else [x.strip() for x in cols["tried_foods"].split(",")],
            "birth_weight_kg": cols["birth_weight_kg"],
            "preterm": cols["preterm"],
            "notes": cols["notes"],
        }, ensure_ascii=False),
        "配料表输入中文": json.dumps({"配料原文": ingredient_text_zh(food), "月龄": cols["月龄"]}, ensure_ascii=False),
        "label_parsing_input_en": json.dumps({"ingredient_text": ingredient_text_en(food), "age_months": cols["age_months"]}, ensure_ascii=False),
        "聊天输入中文": json.dumps({"消息": message_zh, "历史": [{"问题": "宝宝便秘", "回答": "请结合月龄、已尝试食物和饮水情况判断。"}]}, ensure_ascii=False),
        "chat_input_en": json.dumps({"message": message_en, "history": [{"question": "The baby is constipated.", "answer": "Consider age, tried foods, and fluid intake."}]}, ensure_ascii=False),
        "前端侧边栏输入中文": json.dumps({
            "月龄": cols["月龄"],
            "矫正月龄": cols["矫正月龄"],
            "喂养方式": cols["喂养方式"],
            "已知过敏原": cols["已知过敏"],
            "已尝试食材": cols["已使用食物"],
        }, ensure_ascii=False),
        "frontend_sidebar_input_en": json.dumps({
            "age_months": cols["age_months"],
            "corrected_age_months": cols["corrected_age_months"],
            "feeding_method": cols["feeding_method"],
            "allergies": [] if cols["allergies"] == "no known allergy" else [x.strip() for x in cols["allergies"].split(",")],
            "tried_foods": [] if cols["tried_foods"] == "no complementary foods yet" else [x.strip() for x in cols["tried_foods"].split(",")],
        }, ensure_ascii=False),
        "预算偏好输入中文": json.dumps({"预算": cols["预算"], "偏好自制": cols["偏好自制"], "避免类别": cols["避免类别"]}, ensure_ascii=False),
        "preference_input_en": json.dumps({"budget": cols["budget"], "prefer_homemade": cols["prefer_homemade"], "avoid_categories": [] if cols["avoid_categories"] == "none" else [x.strip() for x in cols["avoid_categories"].split(",")]}, ensure_ascii=False),
        "反馈闭环输入中文": json.dumps({"食物名称": cols["反馈食物"], "反应": cols["反馈反应"], "日期": cols["反馈日期"]}, ensure_ascii=False),
        "feedback_input_en": json.dumps({"food_name": cols["feedback_food_name"], "reaction": cols["reaction"], "date": cols["feedback_date"]}, ensure_ascii=False),
    }


def load_rules(path: Path | None = None) -> dict[str, dict[str, Any]]:
    if path and path.exists():
        return read_yaml(path, {})
    default = REPO_ROOT / "outputs/normalized/rules.yaml"
    if default.exists():
        return read_yaml(default, {})
    return default_rules()
