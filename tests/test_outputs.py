from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ENTRY = os.environ.get("PORTFOLIO_ENTRY", "/app/allocate.py")


def _run(payload: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, ENTRY, str(payload), str(output)],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _base_payload(min_a_share: float = 0.4) -> dict[str, object]:
    return {
        "schema": "cash-match-v1",
        "years": 3,
        "liabilities": [100, 120, 50],
        "min_a_share": min_a_share,
        "instruments": [
            {"id": "BND-9A1B", "price": 100, "coupon": 10, "face": 100, "maturity": 1, "max_lots": 3, "rating": "AA"},
            {"id": "BND-7B2C", "price": 60, "coupon": 0, "face": 100, "maturity": 1, "max_lots": 3, "rating": "BB"},
            {"id": "BND-3C3D", "price": 80, "coupon": 30, "face": 100, "maturity": 2, "max_lots": 3, "rating": "A"},
            {"id": "BND-5D4E", "price": 50, "coupon": 15, "face": 100, "maturity": 3, "max_lots": 3, "rating": "BBB"},
        ],
    }


def test_gate_covering_portfolio_has_complete_ledger(tmp_path: Path) -> None:
    # case_id: CF-OUT-01 CF-CONTEXT-01 CF-INPUT-01 CF-POOL-01 CF-FIELDS-01 CF-FIELDCOUNT-01 CF-OUT-02
    """题面：
    「年金账户明年起有三个集中给付日，投资同事手里只有一批面值固定、但票息和到期年份各异的」
    「总成本计算。无解时只写 `status`，值为 `"infeasible"`。」
    """

    source = tmp_path / "base.json"
    output = tmp_path / "base.out.json"
    _write(source, _base_payload())
    completed = _run(source, output)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert result["status"] == "ok"
    assert set(result) == {"status", "purchases", "cost", "coverage", "a_share"}
    assert result["coverage"] == [145.0, 145.0, 115.0]


def test_coupon_timing_beats_cheapest_per_face_value(tmp_path: Path) -> None:
    # case_id: CF-INT-01 CF-FLOW-01 CF-GREEDY-01 CF-PURCH-01
    """题面：
    「一手债券在第 1 年到到期年每年带来一次 `coupon`，到期年另加一次 `face`。购买手数只能」
    """

    source = tmp_path / "timing.json"
    output = tmp_path / "timing.out.json"
    _write(source, _base_payload())
    completed = _run(source, output)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert abs(result["cost"] - 190.0) < 0.001
    assert result["purchases"] == {
        "BND-3C3D": 1,
        "BND-5D4E": 1,
        "BND-7B2C": 1,
        "BND-9A1B": 0,
    }


def test_credit_floor_forces_replacement_of_cheap_bb_bond(tmp_path: Path) -> None:
    # case_id: CF-CREDIT-01
    """题面：
    「必须正好带 `id`、`price`、`coupon`、`face`、`maturity`、`max_lots`、`rating`。」
    """

    source = tmp_path / "quality.json"
    output = tmp_path / "quality.out.json"
    _write(source, _base_payload(0.7))
    completed = _run(source, output)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert abs(result["cost"] - 230.0) < 0.001
    assert abs(result["a_share"] - 0.783) < 0.001
    assert result["purchases"]["BND-9A1B"] == 1
    assert result["purchases"]["BND-7B2C"] == 0


def test_cash_surplus_cannot_cover_an_earlier_shortfall(tmp_path: Path) -> None:
    # case_id: CF-CASH-01
    """题面：
    「`maturity` 是 1 到 `years` 的整数，`max_lots` 是 0 到 8 的整数，`rating` 只能取」
    """

    payload = {
        "schema": "cash-match-v1",
        "years": 3,
        "liabilities": [300, 0, 0],
        "min_a_share": 0.0,
        "instruments": [
            {"id": "BND-1111", "price": 50, "coupon": 0, "face": 100, "maturity": 1, "max_lots": 2, "rating": "AA"},
            {"id": "BND-2222", "price": 50, "coupon": 0, "face": 200, "maturity": 2, "max_lots": 2, "rating": "AA"},
        ],
    }
    source = tmp_path / "shortfall.json"
    output = tmp_path / "shortfall.out.json"
    _write(source, payload)
    completed = _run(source, output)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert result == {"status": "infeasible"}


def test_eight_lots_per_instrument_is_accepted(tmp_path: Path) -> None:
    # case_id: CF-TIE-01 CF-LIMIT-01
    """题面：
    「调用方式保持 `python3 /app/allocate.py <input.json> <output.json>`。程序依靠镜像内的」
    """

    payload = {
        "schema": "cash-match-v1",
        "years": 3,
        "liabilities": [0, 0, 100],
        "min_a_share": 0.0,
        "instruments": [
            {"id": "BND-AAAA", "price": 100, "coupon": 0, "face": 100, "maturity": 3, "max_lots": 8, "rating": "AA"},
            {"id": "BND-BBBB", "price": 101, "coupon": 0, "face": 100, "maturity": 3, "max_lots": 8, "rating": "A"},
        ],
    }
    source = tmp_path / "eight.json"
    output = tmp_path / "eight.out.json"
    _write(source, payload)
    completed = _run(source, output)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert result["status"] == "ok"
    assert result["purchases"] == {"BND-AAAA": 1, "BND-BBBB": 0}


def test_nine_lots_per_instrument_is_refused(tmp_path: Path) -> None:
    # case_id: CF-LIMIT-02 CF-FAIL-01 CF-FAIL-02
    """题面：
    「`REFUSED: <原因>`，并以退出码 2 结束。成功时不打印内容；结果去掉空白、键字母升序，」
    """

    payload = {
        "schema": "cash-match-v1",
        "years": 3,
        "liabilities": [0, 0, 100],
        "min_a_share": 0.0,
        "instruments": [
            {"id": "BND-AAAA", "price": 100, "coupon": 0, "face": 100, "maturity": 3, "max_lots": 9, "rating": "AA"},
            {"id": "BND-BBBB", "price": 101, "coupon": 0, "face": 100, "maturity": 3, "max_lots": 8, "rating": "A"},
        ],
    }
    source = tmp_path / "nine.json"
    output = tmp_path / "nine.out.json"
    _write(source, payload)
    completed = _run(source, output)
    assert completed.returncode == 2
    assert completed.stderr.startswith("REFUSED: ")
    assert not output.exists()


def test_uncoverable_liability_returns_business_infeasible(tmp_path: Path) -> None:
    # case_id: CF-INF-01
    """题面：
    「`"ok"`，`purchases` 覆盖券池里的每只券并给出整数手数，`coverage` 按年给出三位小数的」
    """

    payload = _base_payload()
    payload["liabilities"] = [100, 120, 900]
    source = tmp_path / "uncoverable.json"
    output = tmp_path / "uncoverable.out.json"
    _write(source, payload)
    completed = _run(source, output)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert result == {"status": "infeasible"}


def test_duplicate_bond_id_is_refused_without_output(tmp_path: Path) -> None:
    # case_id: CF-SCHEMA-01
    """题面：
    「券池含 2 到 8 只债券。债券号写成 `BND-` 后接四位大写字母或数字，且不能重复。每只券」
    """

    payload = _base_payload()
    payload["instruments"][1]["id"] = payload["instruments"][0]["id"]
    source = tmp_path / "duplicate.json"
    output = tmp_path / "duplicate.out.json"
    _write(source, payload)
    completed = _run(source, output)
    assert completed.returncode == 2
    assert completed.stderr.startswith("REFUSED: ")
    assert not output.exists()


def test_zero_bond_price_is_refused_without_output(tmp_path: Path) -> None:
    # case_id: CF-SCHEMA-02
    """题面：
    「是整数，既不能超过 `max_lots`，也不能为负。账户没有期初现金，每年收到的本息只覆盖」
    """

    payload = _base_payload()
    payload["instruments"][0]["price"] = 0.0
    source = tmp_path / "zero-price.json"
    output = tmp_path / "zero-price.out.json"
    report = tmp_path / "allocate-report.json"
    summary = tmp_path / "allocate-summary.json"
    _write(source, payload)
    completed = _run(source, output)
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr.startswith("REFUSED: ")
    assert not output.exists()
    assert not report.exists()
    assert not summary.exists()


def test_success_output_is_canonical_and_stdout_empty(tmp_path: Path) -> None:
    # case_id: CF-SER-01 CF-SER-02 CF-SER-03
    """题面：
    「输入对象只含这五个键：」
    """

    source = tmp_path / "base.json"
    output = tmp_path / "canonical.json"
    _write(source, _base_payload())
    completed = _run(source, output)
    raw = output.read_bytes()
    parsed = json.loads(raw)
    canonical = (
        json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    assert completed.returncode == 0
    assert completed.stdout == ""
    assert raw == canonical


def test_wrong_argument_count_keeps_rejection_contract(tmp_path: Path) -> None:
    # case_id: CF-ARG-01
    """题面：
    「现在只按单价从低到高扫货，请把它改成能给出最低初始成本的整数手数方案。」
    """

    source = tmp_path / "base.json"
    output = tmp_path / "allocate.out.json"
    report = tmp_path / "allocate-report.json"
    journal = tmp_path / "allocate-journal.jsonl"
    summary = tmp_path / "allocate-summary.json"
    completed = subprocess.run(
        [sys.executable, ENTRY, str(source)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 2
    assert completed.stderr.startswith("REFUSED: ")
    assert not output.exists()
    assert not report.exists()
    assert not journal.exists()
    assert not summary.exists()
