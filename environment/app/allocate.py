#!/usr/bin/env python3
"""Starter cash-flow allocator using a cheapest-first heuristic."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("REFUSED: expected input and output paths", file=sys.stderr)
        return 2
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("REFUSED: unreadable input", file=sys.stderr)
        return 2

    years = payload["years"]
    bonds = sorted(payload["instruments"], key=lambda item: (item["price"], item["id"]))
    coverage = [0.0] * years
    purchases = {bond["id"]: 0 for bond in bonds}
    for bond in bonds:
        while purchases[bond["id"]] < bond["max_lots"] and any(
            coverage[year] + 1e-9 < payload["liabilities"][year]
            for year in range(years)
        ):
            purchases[bond["id"]] += 1
            for year in range(bond["maturity"]):
                coverage[year] += bond["coupon"]
            coverage[bond["maturity"] - 1] += bond["face"]
    if any(
        coverage[year] + 1e-9 < payload["liabilities"][year]
        for year in range(years)
    ):
        result = {"status": "infeasible"}
    else:
        cost = sum(
            purchases[bond["id"]] * bond["price"]
            for bond in bonds
        )
        a_cost = sum(
            purchases[bond["id"]] * bond["price"]
            for bond in bonds
            if bond["rating"] in {"AAA", "AA", "A"}
        )
        result = {
            "a_share": round(a_cost / cost, 3),
            "cost": round(cost, 3),
            "coverage": [round(value, 3) for value in coverage],
            "purchases": purchases,
            "status": "ok",
        }
    target.write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
