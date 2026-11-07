"""ЭлектроСмета — Flask-приложение."""
import json
import os

from flask import Flask, jsonify, render_template, request

import db
from calc import ROOM_TYPES, CalcError, calculate

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024
db.init_db()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/catalog")
def catalog():
    conn = db.connect()
    rows = [dict(r) for r in conn.execute(
        "SELECT code, name, short, power_w, cos_phi, three_phase, connection, wet, param_unit, param_default "
        "FROM appliances ORDER BY connection DESC, power_w DESC")]
    conn.close()
    return jsonify({"appliances": rows, "room_types": ROOM_TYPES})


@app.get("/api/sample")
def sample():
    with open(os.path.join(db.BASE, "sample_project.json"), encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.post("/api/calc")
def api_calc():
    project = request.get_json(silent=True)
    conn = db.connect()
    try:
        return jsonify(calculate(project, conn))
    except CalcError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()


@app.post("/api/projects")
def save_project():
    project = request.get_json(silent=True)
    if not isinstance(project, dict):
        return jsonify({"error": "Некорректный проект"}), 400
    name = str(project.get("name") or "Без названия")[:80]
    conn = db.connect()
    cur = conn.execute("INSERT INTO projects (name, data) VALUES (?, ?)",
                       (name, json.dumps(project, ensure_ascii=False)))
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return jsonify({"id": pid})


@app.get("/api/projects/<int:pid>")
def load_project(pid):
    conn = db.connect()
    row = conn.execute("SELECT data FROM projects WHERE id = ?", (pid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Проект не найден"}), 404
    return jsonify(json.loads(row["data"]))


if __name__ == "__main__":
    app.run(debug=True)
