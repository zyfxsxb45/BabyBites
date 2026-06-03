"""
用户反馈数据存储。

持久化到 JSON 文件，支持添加/查询/统计。

数据结构：
    {
        "records": [
            {
                "id": "fb_001",
                "food_name": "鸡蛋",
                "reaction": "rash",      # rash / diarrhea / vomiting / refusal / none
                "severity": "mild",      # mild / moderate / severe
                "date": "2026-06-01",
                "notes": "吃完2小时脸上出红点",
                "created_at": "2026-06-01T20:00:00"
            }
        ]
    }
"""

import json
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Optional


class FeedbackStore:
    """用户反馈存储"""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = str(Path(__file__).parent / "feedback.json")
        self._path = Path(data_dir)
        self._data = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            text = self._path.read_text(encoding="utf-8").strip()
            if text:
                return json.loads(text)
        return {"records": []}

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ===== CRUD =====

    def add(self, food_name: str, reaction: str, severity: str = "mild",
            feedback_date: str = None, notes: str = "") -> dict:
        """记录一条反馈"""
        record = {
            "id": f"fb_{uuid.uuid4().hex[:8]}",
            "food_name": food_name,
            "reaction": reaction,
            "severity": severity,
            "date": feedback_date or date.today().isoformat(),
            "notes": notes,
            "created_at": datetime.now().isoformat(),
        }
        self._data["records"].append(record)
        self._save()
        return record

    def get_all(self) -> list[dict]:
        return list(self._data["records"])

    def get_by_food(self, food_name: str) -> list[dict]:
        return [r for r in self._data["records"] if r["food_name"] == food_name]

    def get_recent(self, days: int = 14) -> list[dict]:
        cutoff = date.today().isoformat()
        return [
            r for r in self._data["records"]
            if r.get("date", "") >= cutoff
        ]

    def delete(self, record_id: str) -> bool:
        before = len(self._data["records"])
        self._data["records"] = [
            r for r in self._data["records"] if r["id"] != record_id
        ]
        if len(self._data["records"]) < before:
            self._save()
            return True
        return False

    # ===== 分析 =====

    def get_avoid_foods(self) -> set[str]:
        """需要避免的食材（有过 moderate/severe 反应）"""
        return {
            r["food_name"]
            for r in self._data["records"]
            if r.get("severity") in ("moderate", "severe")
        }

    def get_caution_foods(self) -> set[str]:
        """需要谨慎的食材（有过 mild 反应）"""
        return {
            r["food_name"]
            for r in self._data["records"]
            if r.get("severity") == "mild"
            and r.get("reaction") != "none"
        }

    def get_food_safety_label(self, food_name: str) -> str:
        """
        查某食材的当前安全标签。
        Returns: "avoid" | "caution" | "suitable"
        """
        records = self.get_by_food(food_name)
        if not records:
            return "suitable"

        severities = [r.get("severity", "mild") for r in records]
        reactions = [r.get("reaction", "") for r in records]

        if "severe" in severities:
            return "avoid"
        if "moderate" in severities:
            return "avoid"
        if "mild" in severities and all(r != "none" for r in reactions):
            return "caution"

        return "suitable"

    def get_matching_feedback(self, food_names: list[str]) -> list[dict]:
        """查询一批食材中哪些有反馈记录"""
        return [
            r for r in self._data["records"]
            if r["food_name"] in food_names
        ]

    @property
    def summary(self) -> dict:
        """反馈汇总统计"""
        records = self._data["records"]
        reactions = {}
        severities = {}
        for r in records:
            rx = r.get("reaction", "unknown")
            sv = r.get("severity", "unknown")
            reactions[rx] = reactions.get(rx, 0) + 1
            severities[sv] = severities.get(sv, 0) + 1

        return {
            "total": len(records),
            "foods_tracked": len(set(r["food_name"] for r in records)),
            "avoid_foods": list(self.get_avoid_foods()),
            "caution_foods": list(self.get_caution_foods()),
            "by_reaction": reactions,
            "by_severity": severities,
        }
