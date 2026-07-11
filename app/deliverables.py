"""Tiny CSV-backed 'deliverables register' — stands in for a real system
(SharePoint list, project controls DB, ...) without needing a real database.
"""
import csv
import os
from typing import Dict, Optional

from .models import Deliverable

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DELIVERABLES_CSV = os.path.join(DATA_DIR, "deliverables.csv")


def load_deliverables() -> Dict[str, Deliverable]:
    registry: Dict[str, Deliverable] = {}
    with open(DELIVERABLES_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = Deliverable(
                deliverable_id=row["deliverable_id"],
                name=row["name"],
                discipline=row["discipline"],
                owner=row["owner"] or None,
                planned_date=row["planned_date"] or None,
                status=row["status"],
            )
            registry[d.deliverable_id] = d
    return registry


def get_deliverable(deliverable_id: str) -> Optional[Deliverable]:
    return load_deliverables().get(deliverable_id)
