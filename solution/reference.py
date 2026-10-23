#!/usr/bin/env python3
"""Reference solver for rounded bond cash-flow matching."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Any


INPUT_KEYS = {"schema", "years", "liabilities", "instruments", "min_a_share"}
BOND_ID = re.compile(r"BND-[A-Z0-9]{4}\Z")
RATINGS = {"AAA", "AA", "A", "BBB", "BB"}
A_RATINGS = {"AAA", "AA", "A"}
EPSILON = 1e-9


class Refused(ValueError):
    pass


def _number(value: Any, label: str, minimum: float, strict: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Refused(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise Refused(f"{label} must be finite")
    if number < minimum or (strict and number <= minimum):
        raise Refused(f"{label} is outside its allowed range")
    return number


def _integer(value: Any, low: int, high: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Refused(f"{label} must be an integer")
    if not low <= value <= high:
        raise Refused(f"{label} is outside its allowed range")
    return value


def parse_input(path: Path) -> tuple[int, list[float], float, list[dict[str, Any]]]:
    # 结构、类型或值域有瑕疵时统一拒收，避免坏券进入优化。
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Refused("input cannot be read") from exc
    except json.JSONDecodeError as exc:
        raise Refused("input is not valid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != INPUT_KEYS:
        raise Refused("top-level keys do not match cash-match-v1")
    if payload.get("schema") != "cash-match-v1":
        raise Refused("unsupported schema")
    years = _integer(payload.get("years"), 3, 8, "years")
    raw_liabilities = payload.get("liabilities")
    if not isinstance(raw_liabilities, list) or len(raw_liabilities) != years:
        raise Refused("liabilities must match the year count")
    liabilities = [
        _number(value, f"liability {index + 1}", 0.0)
        for index, value in enumerate(raw_liabilities)
    ]
    if not any(value > 0.0 for value in liabilities):
        raise Refused("at least one liability must be positive")
    min_a_share = _number(payload.get("min_a_share"), "min_a_share", 0.0)
    if min_a_share > 1.0:
        raise Refused("min_a_share exceeds one")

    raw_bonds = payload.get("instruments")
    if not isinstance(raw_bonds, list) or not 2 <= len(raw_bonds) <= 8:
        raise Refused("instruments must contain two to eight entries")
    instruments: list[dict[str, Any]] = []
    seen: set[str] = set()
    expected = {"id", "price", "coupon", "face", "maturity", "max_lots", "rating"}
    for index, item in enumerate(raw_bonds):
        if not isinstance(item, dict) or set(item) != expected:
            raise Refused(f"instrument {index} has an invalid key set")
        bond_id = item.get("id")
        if not isinstance(bond_id, str) or BOND_ID.fullmatch(bond_id) is None:
            raise Refused(f"instrument {index} has an invalid id")
        if bond_id in seen:
            raise Refused("instrument ids must be unique")
        seen.add(bond_id)
        rating = item.get("rating")
        if not isinstance(rating, str) or rating not in RATINGS:
            raise Refused(f"instrument {bond_id} has an unsupported rating")
        instruments.append(
            {
                "id": bond_id,
                "price": _number(item.get("price"), f"{bond_id} price", 0.0, True),
                "coupon": _number(item.get("coupon"), f"{bond_id} coupon", 0.0),
                "face": _number(item.get("face"), f"{bond_id} face", 0.0, True),
                "maturity": _integer(
                    item.get("maturity"), 1, years, f"{bond_id} maturity"
                ),
                "max_lots": _integer(
                    item.get("max_lots"), 0, 8, f"{bond_id} max_lots"
                ),
                "rating": rating,
            }
        )
    instruments.sort(key=lambda item: item["id"])
    return years, liabilities, min_a_share, instruments


def optimize(
    years: int,
    liabilities: list[float],
    min_a_share: float,
    instruments: list[dict[str, Any]],
) -> dict[str, Any]:
    cash = [
        [
            bond["coupon"] + (bond["face"] if year + 1 == bond["maturity"] else 0.0)
            if year < bond["maturity"]
            else 0.0
            for year in range(years)
        ]
        for bond in instruments
    ]
    remaining = [[0.0] * years for _ in range(len(instruments) + 1)]
    for index in range(len(instruments) - 1, -1, -1):
        for year in range(years):
            remaining[index][year] = (
                remaining[index + 1][year]
                + cash[index][year] * instruments[index]["max_lots"]
            )

    quantities = [0] * len(instruments)
    coverage = [0.0] * years
    best_cost: float | None = None
    best_counts: tuple[int, ...] | None = None
    best_coverage: list[float] | None = None
    best_a_share = 0.0

    def visit(index: int, cost: float, a_cost: float) -> None:
        nonlocal best_cost, best_counts, best_coverage, best_a_share
        if best_cost is not None and cost > best_cost + EPSILON:
            return
        for year in range(years):
            if coverage[year] + remaining[index][year] + EPSILON < liabilities[year]:
                return
        if index == len(instruments):
            if any(
                coverage[year] + EPSILON < liabilities[year]
                for year in range(years)
            ):
                return
            if cost <= 0.0:
                return
            a_share = a_cost / cost
            if a_share + EPSILON < min_a_share:
                return
            counts = tuple(quantities)
            if (
                best_cost is None
                or cost < best_cost - EPSILON
                or (
                    abs(cost - best_cost) <= EPSILON
                    and (best_counts is None or counts < best_counts)
                )
            ):
                best_cost = cost
                best_counts = counts
                best_coverage = list(coverage)
                best_a_share = a_share
            return

        bond = instruments[index]
        for lots in range(bond["max_lots"] + 1):
            quantities[index] = lots
            for year in range(years):
                coverage[year] += cash[index][year] * lots
            visit(
                index + 1,
                cost + bond["price"] * lots,
                a_cost + (bond["price"] * lots if bond["rating"] in A_RATINGS else 0.0),
            )
            for year in range(years):
                coverage[year] -= cash[index][year] * lots
        quantities[index] = 0

    visit(0, 0.0, 0.0)
    if best_counts is None or best_cost is None or best_coverage is None:
        return {"status": "infeasible"}
    return {
        "a_share": round(best_a_share, 3),
        "cost": round(best_cost, 3),
        "coverage": [round(value, 3) for value in best_coverage],
        "purchases": {
            bond["id"]: count for bond, count in zip(instruments, best_counts)
        },
        "status": "ok",
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("REFUSED: expected input and output paths", file=sys.stderr)
        return 2
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    try:
        years, liabilities, min_a_share, instruments = parse_input(source)
        result = optimize(years, liabilities, min_a_share, instruments)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    target.write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
