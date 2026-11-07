"""Запуск: python -m tests.test_calc  (из корня проекта)"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db  # noqa: E402
from calc import CalcError, calculate  # noqa: E402


def load(phases=None):
    with open(os.path.join(db.BASE, "sample_project.json"), encoding="utf-8") as f:
        p = json.load(f)
    if phases:
        p["settings"]["phases"] = phases
    return p


def main():
    db.init_db()
    conn = db.connect()
    r = calculate(load(), conn)
    assert r["summary"]["phases"] == 3 and r["summary"]["main_in"] in (25, 32, 40)
    assert all(l["In"] <= 63 for l in r["lines"])
    for l in r["lines"]:                       # автомат не больше допустимого тока кабеля
        sec = float(l["cable"].split("×")[1].replace(",", "."))
        assert sec >= {10: 1.5, 16: 2.5, 20: 2.5, 25: 4, 32: 6, 40: 10, 50: 10, 63: 16}[l["In"]]
    assert not any("нет в каталоге" in w for w in r["warnings"])
    r1 = calculate(load(1), conn)
    assert r1["summary"]["phases"] == 1 and r1["warnings"]          # 1 фаза: должны быть предупреждения
    try:
        p = load(); p["panel"] = None; calculate(p, conn)
        raise SystemExit("ожидалась ошибка без щита")
    except CalcError:
        pass
    print("OK:", len(r["lines"]), "линий,", r["panel"]["enclosure"])


if __name__ == "__main__":
    main()
