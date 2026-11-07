"""Движок расчёта: по плану (комнаты, точки, приборы) считает линии, автоматы,
сечения кабеля, метраж, состав щита и смету.

Все допущения собраны в константах ниже и в списке notes результата.
Расчёт ориентировочный и не заменяет проект, выполненный специалистом.
"""
import math

STD_IN = [6, 10, 16, 20, 25, 32, 40, 50, 63]
U1, U3 = 230.0, 400.0
COS_DEFAULT = 0.95
GAMMA = 48.0            # проводимость меди при рабочей температуре, См·м/мм²
DU_LIMIT = 3.0          # допустимое падение напряжения на групповой линии, %
LIGHT_W = 50            # на одну точку света, Вт
SOCKET_W = 200          # средняя нагрузка одной розетки, Вт
SOCKET_SIM = 0.8        # коэффициент одновременности для розеточной группы
SOCKET_MAX_PTS = 8
SOCKET_MAX_I = 14.0     # А, чтобы остаться в пределах автомата 16 А
LIGHT_MAX_PTS = 12
LIGHT_MAX_I = 8.0
KC_LIGHT, KC_SOCKET = 0.8, 0.5
WET_ROOMS = {"bathroom", "toilet", "balcony"}
SOCKET_H, SWITCH_H = 0.3, 0.9
INPUT_CABLE_M = 3
ENCLOSURES = [(1, 12), (2, 12), (3, 12), (3, 18), (4, 18), (4, 24), (5, 24), (6, 24)]  # (рядов, модулей в ряду)
ROOM_TYPES = {
    "living": "Гостиная", "bedroom": "Спальня", "kitchen": "Кухня", "hall": "Прихожая / коридор",
    "bathroom": "Ванная", "toilet": "Санузел", "balcony": "Балкон / лоджия", "other": "Другое",
}


class CalcError(ValueError):
    pass


def _f(v, default=0.0):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


def _next_std(x, floor=6, ceil=63):
    for r in STD_IN:
        if r >= max(x, floor):
            return min(r, ceil)
    return ceil


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class Catalog:
    def __init__(self, conn):
        self.products = {r["sku"]: dict(r) for r in conn.execute("SELECT * FROM products")}
        self.sections = [dict(r) for r in conn.execute("SELECT * FROM cable_sections ORDER BY section_mm2")]
        self.appliances = {r["code"]: dict(r) for r in conn.execute("SELECT * FROM appliances")}
        self.works = {r["code"]: dict(r) for r in conn.execute("SELECT * FROM works")}
        self.missing = set()

    def p(self, sku):
        if sku not in self.products:
            self.missing.add(sku)
            return {"sku": sku, "name": f"{sku} (нет в каталоге)", "unit": "шт", "price": 0, "modules": 1,
                    "category": "unknown"}
        return self.products[sku]


# ---------------------------------------------------------------- геометрия

def _room_of(x, y, rooms):
    best = None
    for r in rooms:
        if r["x"] <= x <= r["x"] + r["w"] and r["y"] <= y <= r["y"] + r["h"]:
            a = r["w"] * r["h"]
            if best is None or a < best[0]:
                best = (a, r)
    return best[1] if best else None


def _nn_order(start, pts):
    rem, out, cur = list(pts), [], start
    while rem:
        j = min(range(len(rem)), key=lambda i: _dist((rem[i]["x"], rem[i]["y"]), cur))
        p = rem.pop(j)
        out.append(p)
        cur = (p["x"], p["y"])
    return out


def _route(panel, pts, H, hp):
    """Трасса по потолку: щит -> вверх -> по плану (Манхэттен) -> спуск к каждой точке."""
    order = _nn_order((panel["x"], panel["y"]), pts)
    length = max(H - hp, 0)
    cx, cy = panel["x"], panel["y"]
    poly = [[cx, cy]]
    for i, p in enumerate(order):
        length += abs(p["x"] - cx) + abs(p["y"] - cy)
        poly += [[p["x"], cy], [p["x"], p["y"]]]
        drop = max(H - p["h"], 0)
        length += drop if i == len(order) - 1 else 2 * drop
        cx, cy = p["x"], p["y"]
    length = length * 1.1 + 0.3 * len(order) + 0.5   # запас 10 %, разделка на точках
    return math.ceil(length), poly, order


def _chunk(atoms, power_fn, max_pts, max_i, sim, cos=COS_DEFAULT):
    """Раскладывает «атомы» (списки точек, обычно по комнате) в группы по лимитам."""
    def fits(n, p):
        return n <= max_pts and p * sim / (U1 * cos) <= max_i

    groups, cur = [], []

    def total(pts):
        return sum(power_fn(p) for p in pts)

    for atom in atoms:
        if not atom:
            continue
        if fits(len(cur) + len(atom), total(cur + atom)):
            cur += atom
        elif fits(len(atom), total(atom)):
            if cur:
                groups.append(cur)
            cur = list(atom)
        else:  # комната сама по себе не помещается — режем по точкам
            if cur:
                groups.append(cur)
                cur = []
            for p in atom:
                if cur and not fits(len(cur) + 1, total(cur + [p])):
                    groups.append(cur)
                    cur = []
                cur.append(p)
    if cur:
        groups.append(cur)
    return groups


# ---------------------------------------------------------------- разбор проекта

def _parse(project):
    if not isinstance(project, dict):
        raise CalcError("Некорректный проект")
    s = project.get("settings") or {}
    settings = {
        "ceiling_h": min(max(_f(s.get("ceiling_h"), 2.7), 2.0), 5.0),
        "panel_h": min(max(_f(s.get("panel_h"), 1.6), 0.5), 2.2),
        "phases": 3 if int(_f(s.get("phases"), 1)) == 3 else 1,
        "allowed_kw": max(_f(s.get("allowed_kw"), 0), 0),
    }
    rooms = []
    for i, r in enumerate((project.get("rooms") or [])[:60]):
        w, h = _f(r.get("w")), _f(r.get("h"))
        if w <= 0 or h <= 0:
            continue
        t = r.get("type") if r.get("type") in ROOM_TYPES else "other"
        rooms.append({"id": str(r.get("id", f"r{i}")), "name": str(r.get("name") or f"Комната {i + 1}")[:40],
                      "type": t, "x": _f(r.get("x")), "y": _f(r.get("y")), "w": w, "h": h})
    items = []
    for i, it in enumerate((project.get("items") or [])[:600]):
        items.append({"id": str(it.get("id", f"i{i}")), "kind": str(it.get("kind", "")),
                      "x": _f(it.get("x")), "y": _f(it.get("y")), "code": it.get("appliance"),
                      "value": _f(it.get("value"), 0)})
    pnl = project.get("panel")
    panel = {"x": _f(pnl.get("x")), "y": _f(pnl.get("y"))} if isinstance(pnl, dict) else None
    return settings, rooms, items, panel


# ---------------------------------------------------------------- основной расчёт

def calculate(project, conn):
    cat = Catalog(conn)
    settings, rooms, items, panel = _parse(project)
    warnings, notes = [], []
    if not panel:
        raise CalcError("Поставьте на плане электрощит (инструмент «Щит»).")
    if not items:
        raise CalcError("На плане нет ни одной точки: добавьте розетки, свет или приборы.")
    H, hp, three = settings["ceiling_h"], settings["panel_h"], settings["phases"] == 3

    # 1. Точки
    points = []
    for it in items:
        room = _room_of(it["x"], it["y"], rooms)
        if room is None:
            warnings.append(f"Точка «{it['kind']}» стоит вне комнат — отнесена к «вне помещения».")
        rt = room["type"] if room else "other"
        rname = room["name"] if room else "вне помещения"
        pt = {"id": it["id"], "x": it["x"], "y": it["y"], "room": room, "rtype": rt, "rname": rname,
              "kind": it["kind"], "ap": None, "power": 0.0}
        if it["kind"] == "socket":
            pt.update(h=SOCKET_H, power=SOCKET_W)
        elif it["kind"] == "switch":
            pt.update(h=SWITCH_H)
        elif it["kind"] == "light":
            pt.update(h=H, power=LIGHT_W)
        elif it["kind"] == "appliance":
            ap = cat.appliances.get(it["code"])
            if not ap:
                warnings.append(f"Неизвестный прибор «{it['code']}» пропущен.")
                continue
            val = it["value"] if ap["param_unit"] and it["value"] > 0 else (ap["param_default"] or 1)
            pt.update(ap=ap, h=ap["outlet_h"], power=ap["power_w"] * (val if ap["param_unit"] else 1), value=val)
        else:
            continue
        points.append(pt)

    def is_wet(p):
        return p["rtype"] in WET_ROOMS

    lines = []

    def add_line(kind, name, pts, **kw):
        ln = {"kind": kind, "name": name, "points": pts, "phases": 1, "cos": COS_DEFAULT, "curve": "B",
              "wet": False, "kc": 1.0, "min_in": 6, "sim": 1.0, "rooms": sorted({p["rname"] for p in pts})}
        ln.update(kw)
        lines.append(ln)
        return ln

    centre = lambda r: (r["x"] + r["w"] / 2, r["y"] + r["h"] / 2)
    pc = (panel["x"], panel["y"])

    def rooms_sorted(pts):
        by = {}
        for p in pts:
            by.setdefault(p["room"]["id"] if p["room"] else "_out", []).append(p)
        def key(lst):
            r = lst[0]["room"]
            return _dist(centre(r), pc) if r else 1e9
        return sorted(by.values(), key=key)

    # 2. Освещение
    lt = [p for p in points if p["kind"] in ("light", "switch")]
    for g in _chunk(rooms_sorted(lt), lambda p: p["power"], LIGHT_MAX_PTS, LIGHT_MAX_I, 1.0):
        if not any(p["kind"] == "light" for p in g):
            warnings.append("Выключатель без светильников в той же группе — проверьте расстановку.")
        add_line("light", "Освещение: " + ", ".join(sorted({p["rname"] for p in g})), g,
                 min_in=10, curve="B", kc=KC_LIGHT, fixed_in=10)

    # 3. Розетки (включая приборы «в розетку»)
    sk = [p for p in points if p["kind"] == "socket" or (p["kind"] == "appliance" and p["ap"]["connection"] == "plug")]
    kitchen = [p for p in sk if p["rtype"] == "kitchen"]
    wet = [p for p in sk if is_wet(p)]
    dry = [p for p in sk if p["rtype"] != "kitchen" and not is_wet(p)]

    def sock_groups(pts, atoms, title, rcbo):
        groups = _chunk(atoms, lambda p: p["power"], SOCKET_MAX_PTS, SOCKET_MAX_I, SOCKET_SIM)
        names = ["Розетки: " + ", ".join(sorted({p["rname"] for p in g})) for g in groups]
        seen = {}
        for g, nm in zip(groups, names):
            seen[nm] = seen.get(nm, 0) + 1
            suffix = f" ({seen[nm]})" if names.count(nm) > 1 else ""
            add_line("socket", nm + suffix, g, min_in=16, curve="B", kc=KC_SOCKET, sim=SOCKET_SIM,
                     fixed_in=16, wet=rcbo)

    if kitchen:
        atoms = [[p] for p in _nn_order(pc, kitchen)]
        sock_groups(kitchen, atoms, "кухня", True)
    if wet:
        sock_groups(wet, rooms_sorted(wet), "влажные", True)
    if dry:
        sock_groups(dry, rooms_sorted(dry), "прочие", False)

    # 4. Выделенные линии
    for p in points:
        if p["kind"] == "appliance" and p["ap"]["connection"] == "line":
            ap = p["ap"]
            ph3 = three and bool(ap["three_phase"])
            add_line("dedicated", f"{ap['name']} — {p['rname']}", [p], phases=3 if ph3 else 1, cos=ap["cos_phi"],
                     curve=ap["curve"], wet=True, kc=ap["kc"], min_in=ap["min_in_a"], ap=ap, sim=1.0)

    # 5. Электрические параметры линий
    for ln in lines:
        ln["P"] = sum(p["power"] for p in ln["points"])
        k, U = (math.sqrt(3), U3) if ln["phases"] == 3 else (1.0, U1)
        ln["Ib"] = ln["P"] * ln["sim"] / (k * U * ln["cos"])
        if ln.get("fixed_in"):
            In = ln["fixed_in"]
        else:
            In = _next_std(ln["Ib"] * 1.1, floor=ln["min_in"])
            if ln["Ib"] * 1.1 > 63:
                warnings.append(f"Линия «{ln['name']}»: ток {ln['Ib']:.0f} А превышает 63 А — нужен индивидуальный расчёт.")
        ln["In"] = In
        length, poly, order = _route(panel, ln["points"], H, hp)
        ln["length"], ln["route"], ln["order"] = length, poly, order
        secs = cat.sections
        idx = next((i for i, s in enumerate(secs) if s["max_breaker_a"] >= In and s["iz_a"] >= In), len(secs) - 1)

        def du(i):
            S = secs[i]["section_mm2"]
            if ln["phases"] == 3:
                return math.sqrt(3) * length * ln["Ib"] * ln["cos"] / (GAMMA * S) / U3 * 100
            return 2 * length * ln["Ib"] * ln["cos"] / (GAMMA * S) / U1 * 100

        while du(idx) > DU_LIMIT and idx < len(secs) - 1:
            idx += 1
        ln["section"] = secs[idx]["section_mm2"]
        ln["du"] = round(du(idx), 2)
        if ln["du"] > DU_LIMIT:
            warnings.append(f"Линия «{ln['name']}»: падение напряжения {ln['du']}% выше {DU_LIMIT}% даже на максимальном сечении.")
        ln["cores"] = 5 if ln["phases"] == 3 else 3
        ln["rcbo"] = ln["kind"] == "dedicated" or ln["wet"]
        ln["Pdem"] = ln["P"] * ln["kc"]

    # 6. Фазы
    load = {"L1": 0.0, "L2": 0.0, "L3": 0.0}
    if three:
        for ln in sorted([l for l in lines if l["phases"] == 1], key=lambda l: -l["Pdem"]):
            ph = min(load, key=load.get)
            ln["phase"] = ph
            load[ph] += ln["Pdem"] / (U1 * COS_DEFAULT)
        for ln in lines:
            if ln["phases"] == 3:
                ln["phase"] = "L1-L3"
                for ph in load:
                    load[ph] += ln["Pdem"] / (math.sqrt(3) * U3 * ln["cos"])
        phase_I = load
    else:
        for ln in lines:
            ln["phase"] = "L"
        phase_I = {"L": sum(l["Pdem"] for l in lines) / (U1 * COS_DEFAULT)}

    # 7. Вводной автомат
    P_inst = sum(l["P"] for l in lines)
    P_dem = sum(l["Pdem"] for l in lines)
    I_calc = max(phase_I.values())
    main_in = _next_std(I_calc * 1.1, floor=16 if three else 25)
    if I_calc * 1.1 > 63:
        warnings.append(f"Расчётный ток {I_calc:.0f} А превышает 63 А — потребуется трёхфазный ввод/индивидуальный проект.")
        main_in = 63
    allowed = settings["allowed_kw"]
    if allowed and P_dem / 1000 > allowed:
        warnings.append(f"Расчётная мощность {P_dem/1000:.1f} кВт выше выделенной {allowed:g} кВт — запросите увеличение мощности у сетевой организации.")
    if not three and P_dem / 1000 > 15:
        warnings.append("Для такой нагрузки обычно нужен трёхфазный ввод (380 В).")

    # 8. Состав щита
    devs = []
    def dev(kind, sku, label, **kw):
        pr = cat.p(sku)
        d = {"type": kind, "sku": sku, "label": label, "name": pr["name"], "modules": int(pr.get("modules") or 1)}
        d.update(kw)
        devs.append(d)
        return d

    main_sku = f"mcb4_C{main_in}" if three else f"mcb2_C{main_in}"
    b_main = [dev("main", main_sku, "QF")]
    b_prot = [dev("spd", "spd_3ph" if three else "spd_1ph", "FV"),
              dev("relay", "vr_3ph" if three else "vr_1ph", "KV")]
    blocks = [{"devs": b_main + b_prot, "split": False}]

    for n, ln in enumerate(lines, 1):
        ln["no"] = n
        ln["short"] = ln["name"].split(":")[0] if ln["kind"] != "dedicated" else ln["ap"]["short"]

    # УЗО-группы для обычных групп (освещение + сухие розетки)
    plain = [l for l in lines if not l["rcbo"]]
    for ph in (["L1", "L2", "L3"] if three else ["L"]):
        pl = [l for l in plain if l["phase"] == ph]
        cur = []
        groups, cur = [], []
        for l in pl:
            if cur and (sum(x["Ib"] for x in cur + [l]) * 1.25 > 63 or len(cur) >= 6):
                groups.append(cur)
                cur = []
            cur.append(l)
        if cur:
            groups.append(cur)
        for g in groups:
            rated = _next_std(sum(x["Ib"] for x in g) * 1.25, floor=25)
            rated = 25 if rated <= 25 else (40 if rated <= 40 else 63)
            d_rcd = dev("rcd", f"rcd2_{rated}", "QSD", phase=ph)
            kids = []
            for l in g:
                kids.append(dev("mcb", f"mcb1_{l['curve']}{l['In']}", "QF", line=l["no"]))
                l["device"] = kids[-1]
            blocks.append({"devs": [d_rcd] + kids, "split": False})

    rb = []
    for l in [x for x in lines if x["rcbo"]]:
        pre = "rcbo4" if l["phases"] == 3 else "rcbo2"
        d = dev("rcbo", f"{pre}_{l['curve']}{l['In']}", "QFD", line=l["no"])
        l["device"] = d
        rb.append(d)
    if rb:
        blocks.append({"devs": rb, "split": True})

    # номера на схеме
    for l in lines:
        d = l.get("device")
        if d:
            d["label"] = f"QF{l['no']}"
    for i, d in enumerate([d for d in devs if d["type"] == "rcd"], 1):
        d["label"] = f"QSD{i}"
    devs[0]["label"], devs[1]["label"], devs[2]["label"] = "QF", "FV1", "KV1"

    need = sum(d["modules"] for d in devs)
    layout = None
    for rows_n, row_m in ENCLOSURES:
        cap = rows_n * row_m
        if cap < math.ceil(need * 1.2) + 1:
            continue
        rows = _pack(blocks, rows_n, row_m)
        if rows is not None:
            layout = {"rows": rows_n, "row_modules": row_m, "capacity": cap, "placed": rows}
            break
    if layout is None:
        warnings.append("Аппараты не помещаются в самый большой типовой щит — разделите на два щита.")
        layout = {"rows": 6, "row_modules": 24, "capacity": 144, "placed": _pack(blocks, 6, 24, force=True)}
    layout["need"], layout["free"] = need, layout["capacity"] - need
    enclosure_sku = f"encl_{layout['capacity']}"

    # 9. Смета
    bom = {}

    def add(sku, qty, group, reason="", optional=False, default=True):
        if qty <= 0:
            return
        pr = cat.p(sku)
        e = bom.setdefault(sku, {"sku": sku, "name": pr["name"], "unit": pr["unit"], "price": pr["price"],
                                 "qty": 0, "group": group, "reason": reason, "optional": optional, "default": default})
        e["qty"] += qty

    for d in devs:
        add(d["sku"], 1, "panel")
    add(enclosure_sku, 1, "panel", "с запасом ≥ 20 % свободных модулей")
    add("bus_pe", 1, "panel")
    add("bus_n", 1, "panel")
    n_mcb = sum(1 for d in devs if d["type"] == "mcb")
    add("comb_1p", math.ceil(n_mcb / 10), "panel", "для питания автоматов от УЗО")
    add("lugs_kit", 1, "panel")
    add("label_kit", 1, "panel")

    cable_len = {}
    for l in lines:
        key = (l["cores"], l["section"])
        cable_len[key] = cable_len.get(key, 0) + l["length"]
    input_sec = next((s["section_mm2"] for s in cat.sections if s["max_breaker_a"] >= main_in), 16)
    key = (5 if three else 3, input_sec if not (three and input_sec < 2.5) else 2.5)
    cable_len[key] = cable_len.get(key, 0) + INPUT_CABLE_M
    for (cores, s), m in cable_len.items():
        add(f"cab_{cores}x{s:g}".replace(".", "_"), math.ceil(m), "cable",
            "включая вводной кабель ~3 м" if key == (cores, s) else "")
    total_cable = sum(l["length"] for l in lines)

    n_sock = sum(1 for p in points if p["kind"] == "socket" or (p["kind"] == "appliance" and p["ap"]["connection"] == "plug"))
    n_ip44 = sum(1 for p in points if (p["kind"] == "socket" or (p["kind"] == "appliance" and p["ap"]["connection"] == "plug")) and is_wet(p))
    n_sw = sum(1 for p in points if p["kind"] == "switch")
    n_light = sum(1 for p in points if p["kind"] == "light")
    add("socket_16a", n_sock - n_ip44, "devices")
    add("socket_ip44", n_ip44, "devices", "в ванной, санузле и на балконе")
    add("switch_1", n_sw, "devices")
    acc_boxes = 0
    for p in points:
        if p["kind"] == "appliance" and p["ap"].get("accessory_sku"):
            add(p["ap"]["accessory_sku"], 1, "devices", f"для: {p['ap']['name']}")
            acc_boxes += 1
    add("box_60", n_sock + n_sw + acc_boxes, "materials")
    rooms_used = {p["room"]["id"] for p in points if p["room"] and p["kind"] in ("socket", "switch", "light")}
    add("junction_box", len(rooms_used), "materials", "по одной на помещение")
    for l in lines:
        add("corr_16" if l["section"] <= 1.5 else "corr_20", l["length"], "materials", "гофра на всю длину трассы")
    add("clip", math.ceil(total_cable * 2), "materials", "~2 шт. на метр")
    add("wago_3", n_sock + n_sw + 2 * n_light, "materials")
    add("wago_5", 2 * len(rooms_used), "materials")

    # рекомендации
    wet_apps = [p for p in points if p["kind"] == "appliance" and p["ap"]["wet"] and p["ap"]["code"] in ("washer", "dishwasher", "boiler", "flow_heater")]
    if wet_apps or any(p["rtype"] == "bathroom" for p in points):
        add("leak_kit", max(1, math.ceil(len(wet_apps) / 2)), "recommended",
            "кран перекрывает воду при протечке у стиралки, ПММ, бойлера", optional=True, default=True)
    n_motion = len({p["room"]["id"] for p in points if p["room"] and p["rtype"] in ("hall", "toilet") and p["kind"] == "switch"})
    if n_motion:
        add("motion", n_motion, "recommended", "свет в коридоре и санузле без выключателя", optional=True, default=False)
    add("ups_mini", 1, "recommended", "питание роутера/сигнализации при отключениях", optional=True, default=False)

    # работы
    w = cat.works
    def add_work(code, qty):
        if code in w and qty > 0:
            e = w[code]
            bom["work:" + code] = {"sku": code, "name": e["name"], "unit": e["unit"], "price": e["price"],
                                   "qty": math.ceil(qty), "group": "works", "reason": "", "optional": True, "default": False}
    add_work("W_POINT", n_sock + n_sw + acc_boxes)
    add_work("W_LIGHT", n_light)
    add_work("W_APPL", sum(1 for l in lines if l["kind"] == "dedicated"))
    add_work("W_CABLE", total_cable)
    add_work("W_STRO", total_cable * 0.6)
    add_work("W_PANEL", need)
    add_work("W_MEASURE", len(lines))

    if cat.missing:
        warnings.append("В каталоге нет позиций: " + ", ".join(sorted(cat.missing)) + " (цена 0).")
    notes += [
        f"Трасса: от щита вверх до потолка ({H:g} м), далее по потолку по прямым линиям (по «манхэттену»), спуски к точкам; запас 10 %.",
        f"Розеточные группы: до {SOCKET_MAX_PTS} точек и ≤ {SOCKET_MAX_I:g} А, автомат B16, кабель не менее 3×2,5. Освещение: до {LIGHT_MAX_PTS} точек, B10, 3×1,5.",
        f"Нагрузка точки: розетка {SOCKET_W} Вт, светильник {LIGHT_W} Вт (приборы — по справочнику). Коэффициенты спроса: свет {KC_LIGHT}, розетки {KC_SOCKET}, приборы — по справочнику.",
        f"Сечение — по длительно допустимому току меди и падению напряжения ≤ {DU_LIMIT}%.",
        "Ванная, санузел, балкон, кухонные розетки и все выделенные линии — на дифавтоматах 30 мА; остальные группы — под общими УЗО 30 мА.",
        "Светильники, сами приборы, счётчик и работы по вводу в смету не входят. Цены — из справочника БД (ориентировочные).",
    ]
    if three:
        notes.append("Трёхфазный ввод: однофазные линии распределены по фазам по нагрузке; плита/варочная панель — на 3 фазы, если допускает прибор.")

    area = sum(r["w"] * r["h"] for r in rooms)
    line_out = []
    for l in lines:
        line_out.append({
            "no": l["no"], "name": l["name"], "kind": l["kind"], "rooms": l["rooms"], "phase": l["phase"],
            "points": len(l["points"]), "P": round(l["P"]), "Ib": round(l["Ib"], 1), "In": l["In"],
            "curve": l["curve"], "protection": "Дифавтомат 30 мА" if l["rcbo"] else "Автомат + общее УЗО",
            "poles": "3P+N" if l["phases"] == 3 else "1P+N" if l["rcbo"] else "1P",
            "cable": f"ВВГнг(А)-LS {l['cores']}×{l['section']:g}", "length": l["length"], "du": l["du"],
            "route": [[round(x, 2), round(y, 2)] for x, y in l["route"]],
        })
    return {
        "summary": {
            "area": round(area, 1), "P_installed": round(P_inst), "P_demand": round(P_dem),
            "I_calc": round(I_calc, 1), "main_in": main_in, "phases": 3 if three else 1,
            "lines": len(lines), "cable_total": total_cable, "panel_modules": need,
            "panel_capacity": layout["capacity"], "sockets": n_sock, "switches": n_sw, "lights": n_light,
            "phase_I": {k: round(v, 1) for k, v in phase_I.items()},
        },
        "lines": line_out,
        "panel": {
            "rows": layout["rows"], "row_modules": layout["row_modules"], "capacity": layout["capacity"],
            "free": layout["free"], "placed": layout["placed"], "enclosure": cat.p(enclosure_sku)["name"],
        },
        "bom": list(bom.values()),
        "warnings": list(dict.fromkeys(warnings)),
        "notes": notes,
    }


def _pack(blocks, rows_n, row_m, force=False):
    """Укладывает аппараты по рядам DIN-рейки. Возвращает список рядов или None."""
    rows = [[] for _ in range(rows_n)]
    used = [0] * rows_n
    r = 0

    def put(d):
        nonlocal r
        while r < rows_n and used[r] + d["modules"] > row_m:
            r += 1
        if r >= rows_n:
            return False
        rows[r].append({"x": used[r], "w": d["modules"], "type": d["type"], "label": d["label"],
                        "name": d["name"], "line": d.get("line"), "phase": d.get("phase")})
        used[r] += d["modules"]
        return True

    for b in blocks:
        size = sum(d["modules"] for d in b["devs"])
        if r < rows_n and used[r] and size <= row_m and used[r] + size > row_m:
            r += 1  # блок целиком переносим на новый ряд
        for d in b["devs"]:
            if not put(d):
                if force:
                    return rows
                return None
    return rows
