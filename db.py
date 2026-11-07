"""Работа с SQLite: подключение и первичная инициализация."""
import os
import sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("ELECTRO_DB", os.path.join(BASE, "electro.db"))


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset=False):
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    fresh = not os.path.exists(DB_PATH)
    conn = connect()
    with open(os.path.join(BASE, "schema.sql"), encoding="utf-8") as f:
        conn.executescript(f.read())
    if fresh:
        with open(os.path.join(BASE, "seed.sql"), encoding="utf-8") as f:
            conn.executescript(f.read())
    conn.commit()
    conn.close()


if __name__ == "__main__":
    import sys
    init_db(reset="--reset" in sys.argv)
    print("БД готова:", DB_PATH)
