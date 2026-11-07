-- Схема БД «ЭлектроСмета». SQLite.
PRAGMA foreign_keys = ON;

-- Каталог материалов и оборудования (цены — ориентировочные, замените своим прайсом)
CREATE TABLE IF NOT EXISTS products (
    sku              TEXT PRIMARY KEY,
    category         TEXT NOT NULL,      -- breaker | rcd | rcbo | spd | relay | enclosure | panel_acc | cable | device | material | extra
    name             TEXT NOT NULL,
    unit             TEXT NOT NULL DEFAULT 'шт',
    price            REAL NOT NULL CHECK (price >= 0),
    poles            INTEGER,            -- число полюсов (для аппаратов защиты)
    rating_a         INTEGER,            -- номинальный ток, А
    curve            TEXT,               -- характеристика B / C
    modules          INTEGER,            -- ширина в DIN-модулях (18 мм)
    section_mm2      REAL,               -- сечение жилы (для кабеля)
    cores            INTEGER,            -- число жил (для кабеля)
    capacity_modules INTEGER             -- вместимость щита в модулях
);

-- Допустимые токи медного кабеля (скрытая прокладка) и макс. номинал автомата для сечения
CREATE TABLE IF NOT EXISTS cable_sections (
    section_mm2    REAL PRIMARY KEY,
    iz_a           REAL    NOT NULL,
    max_breaker_a  INTEGER NOT NULL
);

-- Справочник электроприборов, которые пользователь расставляет на плане
CREATE TABLE IF NOT EXISTS appliances (
    code          TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    short         TEXT NOT NULL,         -- подпись на плане
    power_w       REAL NOT NULL,         -- мощность (для param_unit — на единицу, напр. Вт/м²)
    cos_phi       REAL NOT NULL DEFAULT 1.0,
    three_phase   INTEGER NOT NULL DEFAULT 0,   -- 1 = можно подключить на 380 В
    connection    TEXT NOT NULL CHECK (connection IN ('line','plug')),  -- line: отдельная линия, plug: в розетку
    curve         TEXT NOT NULL DEFAULT 'B',
    outlet_h      REAL NOT NULL DEFAULT 0.3,    -- высота точки подключения, м
    wet           INTEGER NOT NULL DEFAULT 0,
    kc            REAL NOT NULL DEFAULT 0.8,    -- коэффициент спроса
    min_in_a      INTEGER NOT NULL DEFAULT 10,
    param_unit    TEXT,                          -- напр. 'м²'
    param_default REAL,
    accessory_sku TEXT REFERENCES products(sku)  -- обязательная комплектующая (терморегулятор, силовая розетка)
);

-- Расценки на работы
CREATE TABLE IF NOT EXISTS works (
    code  TEXT PRIMARY KEY,
    name  TEXT NOT NULL,
    unit  TEXT NOT NULL,
    price REAL NOT NULL
);

-- Сохранённые проекты пользователей
CREATE TABLE IF NOT EXISTS projects (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    data       TEXT NOT NULL,            -- JSON плана
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
