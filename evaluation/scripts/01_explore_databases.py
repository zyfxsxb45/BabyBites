from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

import pandas as pd

from babybites_common import (
    REPO_ROOT,
    classify_dataset,
    dataframe_from_file,
    ensure_dirs,
    list_data_files,
    profile_dataframe,
    save_table,
)


def explore_file(path: Path, out: Path, sample_rows: int) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    inventory: list[dict] = []
    summaries: list[dict] = []
    profiles: list[dict] = []
    candidates: list[dict] = []
    source_dataset = classify_dataset(path)
    rel = str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                member_path = f"{rel}!{info.filename}"
                inventory.append({
                    "source_dataset": source_dataset,
                    "file_path": member_path,
                    "file_format": Path(info.filename).suffix.lower() or "zip_member",
                    "size_bytes": info.file_size,
                    "read_status": "inventory_only",
                    "read_error": "",
                })
                # Keep zip exploration bounded: public SAS files are large and may not be readable without pyreadstat.
                if Path(info.filename).suffix.lower() not in [".csv", ".tsv", ".json", ".jsonl", ".xpt", ".txt", ".dat"]:
                    continue
        return inventory, summaries, profiles, candidates
    df, error = dataframe_from_file(path, sample_rows=sample_rows)
    inventory.append({
        "source_dataset": source_dataset,
        "file_path": rel,
        "file_format": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
        "read_status": "readable" if df is not None else "skipped",
        "read_error": error or "",
    })
    if df is None:
        return inventory, summaries, profiles, candidates
    table_name = path.stem
    summaries.append({
        "source_dataset": source_dataset,
        "file_path": rel,
        "table_name": table_name,
        "row_count_sampled": len(df),
        "column_count": len(df.columns),
        "columns": json.dumps(list(map(str, df.columns)), ensure_ascii=False),
    })
    p, c = profile_dataframe(df, source_dataset, rel, table_name)
    profiles.extend(p)
    candidates.extend(c)
    return inventory, summaries, profiles, candidates


def write_report(out: Path, inv: pd.DataFrame, summ: pd.DataFrame, cmap: pd.DataFrame) -> None:
    counts = inv.groupby(["source_dataset", "read_status"]).size().reset_index(name="n") if not inv.empty else pd.DataFrame()
    concept_counts = cmap.groupby(["source_dataset", "inferred_concept"]).size().reset_index(name="n") if not cmap.empty else pd.DataFrame()
    def md_table(df: pd.DataFrame) -> str:
        if df.empty:
            return ""
        cols = list(df.columns)
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
        for row in df.astype(str).to_dict("records"):
            lines.append("| " + " | ".join(row[c] for c in cols) + " |")
        return "\n".join(lines)
    lines = [
        "# 数据库结构探索报告",
        "",
        "## 数据源概况",
        "本报告由本地文件自动扫描生成，未联网。IFPS2 当前主要为 PDF 表格/说明文档；NHANES1999 包含 XPT 数据表和 HTML codebook；WIC_ITFPS-2 当前为压缩包，内含 codebook、数据说明和 SAS7BDAT 公共使用数据文件。",
        "",
        "## 文件读取状态",
        md_table(counts) if not counts.empty else "未发现文件。",
        "",
        "## 可用于宝宝画像的候选字段",
        "自动识别到的候选概念包括年龄、性别、早产/胎龄、喂养方式、WIC、收入/族裔等。需要人工确认变量含义，尤其是 NHANES/ITFPS 编码题项。",
        "",
        "## 可用于食物、营养和过敏源生成的字段",
        "NHANES DRXTOT/DRXIFF 等表可提供膳食回顾、食物和营养摄入候选字段；IFPS2/WIC_ITFPS-2 的文档可作为变量映射依据。过敏字段自动识别置信度较低时，后续脚本会使用规则化 synthetic injection 并记录 trace。",
        "",
        "## 可用于评估规则的字段",
        "优先使用年龄/月龄、矫正月龄、已知或疑似过敏、候选食物成分、添加糖/盐/钠、铁含量、质地阶段等字段。缺失字段会进入 data_quality_flags 或待人工确认清单。",
        "",
        "## 缺失和限制",
        "IFPS2 目前只有 PDF，未直接抽取结构化个体表；WIC_ITFPS-2 ZIP 内 SAS7BDAT 在当前环境未强制读取，避免长时间和依赖失败；pyarrow 未安装时 parquet 输出会跳过并记录日志。",
        "",
        "## 当前适合生成的评估样本",
        "适合生成年龄/过敏/食物成分/营养风险驱动的候选选择、规则触发、画像抽取、反事实一致性和 RAG judge 输入样本。真实字段映射不足的部分采用统计分布和规则化合成，不复制真实受试者。",
        "",
        "## 待人工确认字段清单",
        md_table(concept_counts) if not concept_counts.empty else "暂无自动候选字段。",
    ]
    (out / "exploration_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="./data")
    parser.add_argument("--out", default="outputs/exploration")
    parser.add_argument("--sample-rows", type=int, default=5000)
    args = parser.parse_args()
    ensure_dirs()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    files = list_data_files(Path(args.data_root))
    inv: list[dict] = []
    summ: list[dict] = []
    prof: list[dict] = []
    cmap: list[dict] = []
    for path in files:
        i, s, p, c = explore_file(path, out, args.sample_rows)
        inv.extend(i)
        summ.extend(s)
        prof.extend(p)
        cmap.extend(c)
    inv_df = pd.DataFrame(inv)
    summ_df = pd.DataFrame(summ)
    prof_df = pd.DataFrame(prof)
    cmap_df = pd.DataFrame(cmap)
    save_table(inv_df, out / "file_inventory.csv")
    save_table(summ_df, out / "table_summary.csv")
    save_table(prof_df, out / "column_profile.csv", out / "column_profile.parquet")
    save_table(cmap_df, out / "candidate_variable_map.csv")
    write_report(out, inv_df, summ_df, cmap_df)
    print(f"explored_files={len(inv_df)} readable_tables={len(summ_df)} candidate_mappings={len(cmap_df)}")


if __name__ == "__main__":
    main()
