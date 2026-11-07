"""Генерирует seed.sql (запускается один раз, результат лежит в репозитории)."""
import os

rows = []


def esc(s):
    if isinstance(s, str):
        return "'" + s.replace("'", "''") + "'"
    return "NULL" if s is None else str(s)


def prod(sku, cat, name, price, unit="шт", poles=None, rating=None, curve=None,
         modules=None, section=None, cores=None, cap=None):
    vals = [sku, cat, name, unit, price, poles, rating, curve, modules, section, cores, cap]
    rows.append("INSERT INTO products VALUES (" + ", ".join(esc(v) for v in vals) + ");")


R1 = [6, 10, 16, 20, 25, 32, 40, 50, 63]
for c in "BC":
    for r in R1:
        prod(f"mcb1_{c}{r}", "breaker", f"Автомат 1P {c}{r} 4.5кА",
             round(190 + 6 * r + (5 if c == "C" else 0)), poles=1, rating=r, curve=c, modules=1)
for r in [16, 20, 25, 32, 40, 50, 63]:
    prod(f"mcb2_C{r}", "breaker", f"Автомат 2P C{r} 6кА (вводной)",
         round((190 + 6 * r) * 2.1), poles=2, rating=r, curve="C", modules=2)
for r in [16, 25, 32, 40, 50, 63]:
    prod(f"mcb4_C{r}", "breaker", f"Автомат 4P C{r} 6кА (вводной)",
         round((190 + 6 * r) * 4.3), poles=4, rating=r, curve="C", modules=4)
for r, p in [(25, 1900), (40, 2200), (63, 3300)]:
    prod(f"rcd2_{r}", "rcd", f"УЗО 2P {r}А 30мА тип A", p, poles=2, rating=r, modules=2)
for c in "BC":
    for r in [10, 16, 20, 25, 32, 40, 50, 63]:
        prod(f"rcbo2_{c}{r}", "rcbo", f"Дифавтомат 1P+N {c}{r} 30мА тип A",
             1700 + 25 * r, poles=2, rating=r, curve=c, modules=2)
        prod(f"rcbo4_{c}{r}", "rcbo", f"Дифавтомат 3P+N {c}{r} 30мА тип A",
             5000 + 40 * r, poles=4, rating=r, curve=c, modules=4)
prod("spd_1ph", "spd", "УЗИП класс II 1P+N (защита от импульсных перенапряжений)", 2800, poles=2, modules=2)
prod("spd_3ph", "spd", "УЗИП класс II 3P+N", 6500, poles=4, modules=4)
prod("vr_1ph", "relay", "Реле напряжения 63А 1ф", 2300, poles=2, modules=3, rating=63)
prod("vr_3ph", "relay", "Реле контроля фаз и напряжения 3ф", 4800, poles=4, modules=3)
for cap, p in [(12, 1500), (24, 2700), (36, 4000), (54, 6500), (72, 9000), (96, 12500), (120, 17000), (144, 22000)]:
    prod(f"encl_{cap}", "enclosure", f"Щит встраиваемый IP41 на {cap} модулей", p, cap=cap)
prod("bus_pe", "panel_acc", "Шина PE (земля) на DIN-рейку", 420)
prod("bus_n", "panel_acc", "Шина N (ноль) на DIN-рейку", 420)
prod("comb_1p", "panel_acc", "Шина-гребёнка PIN 1P на 12 модулей", 280)
prod("lugs_kit", "panel_acc", "Наконечники НШВИ, набор", 650)
prod("label_kit", "panel_acc", "Маркировка линий (набор)", 300)
for s, p in [(1.5, 58), (2.5, 90), (4, 140), (6, 205), (10, 340), (16, 520)]:
    sn = str(s).replace(".", "_")
    prod(f"cab_3x{sn}", "cable", f"Кабель ВВГнг(А)-LS 3×{s}", p, unit="м", section=s, cores=3)
for s, p in [(2.5, 160), (4, 245), (6, 360), (10, 590), (16, 900)]:
    sn = str(s).replace(".", "_")
    prod(f"cab_5x{sn}", "cable", f"Кабель ВВГнг(А)-LS 5×{s}", p, unit="м", section=s, cores=5)
prod("socket_16a", "device", "Розетка с заземлением 16А (скрытая)", 190)
prod("socket_ip44", "device", "Розетка с заземлением 16А IP44 (влагозащищённая)", 420)
prod("switch_1", "device", "Выключатель 1-клавишный", 160)
prod("power_socket_32", "device", "Силовая розетка 32А с вилкой (для варочной панели/плиты)", 1100)
prod("thermostat_floor", "device", "Терморегулятор для тёплого пола 16А", 3200)
prod("box_60", "material", "Подрозетник 68×45", 25)
prod("junction_box", "material", "Распределительная коробка 100×100 IP54", 120)
prod("corr_16", "material", "Гофра ПВХ d16 с протяжкой", 14, unit="м")
prod("corr_20", "material", "Гофра ПВХ d20 с протяжкой", 18, unit="м")
prod("clip", "material", "Дюбель-хомут для гофры", 4)
prod("wago_3", "material", "Клемма 3-проводная рычажная", 18)
prod("wago_5", "material", "Клемма 5-проводная рычажная", 30)
prod("leak_kit", "extra", "Защита от протечек (2 датчика + шаровой кран с приводом)", 6500)
prod("motion", "extra", "Датчик движения для освещения", 1100)
prod("ups_mini", "extra", "ИБП мини для роутера/котла", 3500)

works = [
    ("W_POINT", "Монтаж розетки/выключателя (подрозетник, подключение)", "шт", 450),
    ("W_LIGHT", "Монтаж светоточки (вывод провода под светильник)", "шт", 350),
    ("W_APPL", "Подключение выделенной линии к прибору", "шт", 900),
    ("W_CABLE", "Прокладка кабеля в гофре", "м", 70),
    ("W_STRO", "Штробление стен под кабель", "м", 450),
    ("W_PANEL", "Сборка и монтаж электрощита", "модуль", 450),
    ("W_MEASURE", "Замеры и испытания линий (мегаомметр, петля фаза-ноль)", "линия", 500),
]
sec = [(1.5, 19, 10), (2.5, 27, 20), (4, 38, 25), (6, 46, 32), (10, 70, 50), (16, 85, 63)]
# code, name, short, power_w, cos, 3ph, conn, curve, outlet_h, wet, kc, min_in, param_unit, param_default, accessory
appl = [
    ("hob", "Варочная панель электрическая", "ВП", 7200, 1.0, 1, "line", "B", 0.3, 0, 0.7, 25, None, None, "power_socket_32"),
    ("stove", "Электроплита с духовкой", "ЭП", 10500, 1.0, 1, "line", "B", 0.3, 0, 0.7, 32, None, None, "power_socket_32"),
    ("oven", "Духовой шкаф", "ДШ", 3000, 1.0, 0, "line", "B", 0.3, 0, 0.7, 16, None, None, None),
    ("washer", "Стиральная машина", "СМ", 2200, 0.95, 0, "line", "C", 0.3, 1, 0.7, 16, None, None, None),
    ("dishwasher", "Посудомоечная машина", "ПММ", 2000, 0.95, 0, "line", "C", 0.3, 1, 0.7, 16, None, None, None),
    ("boiler", "Водонагреватель накопительный", "ВН", 2000, 1.0, 0, "line", "B", 1.8, 1, 0.8, 16, None, None, None),
    ("flow_heater", "Водонагреватель проточный 5 кВт", "ВП5", 5000, 1.0, 0, "line", "B", 1.5, 1, 0.8, 25, None, None, None),
    ("ac", "Кондиционер (сплит-система)", "КН", 2500, 0.85, 0, "line", "C", 2.2, 0, 0.7, 16, None, None, None),
    ("floor", "Тёплый пол электрический (150 Вт/м²)", "ТП", 150, 1.0, 0, "line", "B", 0.9, 1, 0.8, 10, "м²", 4, "thermostat_floor"),
    ("fridge", "Холодильник", "Хл", 400, 0.9, 0, "plug", "B", 0.3, 0, 0.6, 10, None, None, None),
    ("microwave", "Микроволновая печь", "МВ", 1200, 0.95, 0, "plug", "B", 1.1, 0, 0.5, 10, None, None, None),
    ("kettle", "Электрочайник / тостер", "Чн", 2200, 1.0, 0, "plug", "B", 1.1, 0, 0.5, 10, None, None, None),
    ("hood", "Вытяжка", "Вт", 200, 0.9, 0, "plug", "B", 2.0, 0, 0.6, 10, None, None, None),
    ("tv", "Телевизор / ТВ-зона", "ТВ", 200, 0.9, 0, "plug", "B", 0.6, 0, 0.6, 10, None, None, None),
    ("pc", "Рабочее место (ПК)", "ПК", 500, 0.9, 0, "plug", "B", 0.3, 0, 0.6, 10, None, None, None),
]
out = ["-- Начальные данные (сгенерировано tools/gen_seed.py). Цены ориентировочные, руб.", "BEGIN;"]
out += rows
out += [f"INSERT INTO cable_sections VALUES ({s}, {i}, {b});" for s, i, b in sec]
out += ["INSERT INTO works VALUES (" + ", ".join(esc(v) for v in w) + ");" for w in works]
out += ["INSERT INTO appliances VALUES (" + ", ".join(esc(v) for v in a) + ");" for a in appl]
out.append("COMMIT;")
target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "seed.sql")
with open(target, "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print(len(rows), "products")
