(() => {
  "use strict";
  const PLAN_W = 16, PLAN_H = 11;
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const r1 = (v) => Math.round(v * 10) / 10;
  const fmt = (n) => Math.round(n).toLocaleString("ru-RU");
  const money = (n) => fmt(n) + " ₽";

  const ROOM_FILL = {
    living: "#dbe9f6", bedroom: "#e4e1f4", kitchen: "#fbecc9", hall: "#e3ebdf",
    bathroom: "#d3ecef", toilet: "#d9e8ec", balcony: "#e2eed9", other: "#e9edf1",
  };
  const BASE_TOOLS = [
    { id: "select", ic: "↖", name: "Выбрать / двигать" },
    { id: "room", ic: "▭", name: "Комната" },
    { id: "panel", ic: "Щ", name: "Электрощит" },
    { id: "socket", ic: "◒", name: "Розетка" },
    { id: "switch", ic: "⌐", name: "Выключатель" },
    { id: "light", ic: "⊗", name: "Точка света" },
  ];
  const HINTS = {
    select: "Тяните объекты мышью. Угол комнаты — изменить размер. Delete — удалить.",
    room: "Протяните прямоугольник — это комната. Тип комнаты задаётся справа.",
    panel: "Кликните, где будет электрощит (обычно у входа).",
    socket: "Кликайте, чтобы ставить розетки. Esc — вернуться к выбору.",
    switch: "Кликайте, чтобы ставить выключатели.",
    light: "Кликайте, чтобы ставить точки света.",
  };

  let catalog = { appliances: [], room_types: {} };
  let state = fresh();
  let tool = "select", sel = null, drag = null, draft = null;
  let result = null, stale = false, estimate = [];
  let uid = 1;

  function fresh() {
    return { name: "Моя квартира", settings: { ceiling_h: 2.7, panel_h: 1.6, phases: 1, allowed_kw: 15 }, rooms: [], items: [], panel: null };
  }
  const nid = (p) => p + uid++ + "_" + Math.random().toString(36).slice(2, 5);
  const apOf = (code) => catalog.appliances.find((a) => a.code === code);

  /* ------------------------------------------------ инструменты слева */
  function renderTools() {
    const mk = (id, ic, name, extra = "", cls = "") =>
      `<button class="tool ${cls} ${tool === id ? "active" : ""}" data-tool="${id}"><span class="ic">${esc(ic)}</span>${esc(name)}${extra}</button>`;
    $("#toolList").innerHTML = BASE_TOOLS.map((t) => mk(t.id, t.ic, t.name)).join("");
    const kw = (a) => `<small>${a.param_unit ? "150 Вт/" + a.param_unit : (a.power_w / 1000).toFixed(a.power_w >= 1000 ? 1 : 2).replace(".", ",") + " кВт"}</small>`;
    $("#applLine").innerHTML = catalog.appliances.filter((a) => a.connection === "line")
      .map((a) => mk("ap:" + a.code, a.short, a.name.replace(/ \(.*\)/, ""), kw(a))).join("");
    $("#applPlug").innerHTML = catalog.appliances.filter((a) => a.connection === "plug")
      .map((a) => mk("ap:" + a.code, a.short, a.name, kw(a), "plug")).join("");
    $("#stageHint").textContent = HINTS[tool] || "Кликайте по плану, чтобы ставить прибор. Esc — вернуться к выбору.";
    $("#plan").dataset.tool = tool === "select" ? "select" : "place";
  }
  function setTool(t) { tool = t; draft = null; renderTools(); }

  /* ------------------------------------------------ SVG-план */
  const plan = $("#plan");
  function pos(e) {
    const pt = plan.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    const p = pt.matrixTransform(plan.getScreenCTM().inverse());
    return { x: Math.min(Math.max(r1(p.x), 0), PLAN_W), y: Math.min(Math.max(r1(p.y), 0), PLAN_H) };
  }
  function glyph(it) {
    if (it.kind === "socket") return `<circle r=".17" fill="#fff" stroke="#0f1b2a" stroke-width=".04"/><path d="M-.17 0A.17.17 0 0 0 .17 0Z" fill="#0f1b2a"/>`;
    if (it.kind === "switch") return `<circle r=".1" fill="#fff" stroke="#0f1b2a" stroke-width=".04"/><path d="M.07 -.07L.28 -.28M.2 -.3L.3 -.2" stroke="#0f1b2a" stroke-width=".05" fill="none"/>`;
    if (it.kind === "light") return `<circle r=".2" fill="#fff" stroke="#0f1b2a" stroke-width=".04"/><path d="M-.14 -.14L.14 .14M.14 -.14L-.14 .14" stroke="#0f1b2a" stroke-width=".04"/>`;
    const a = apOf(it.appliance);
    const line = a && a.connection === "line";
    const lab = a ? a.short : "?";
    return `<rect x="-.3" y="-.2" width=".6" height=".4" rx=".05" fill="${line ? "#ffc400" : "#fff"}" stroke="#0f1b2a" stroke-width=".04"/>` +
      `<text y=".1" text-anchor="middle" font-size=".26" font-weight="600" fill="#0f1b2a">${esc(lab)}</text>`;
  }
  function renderPlan() {
    let s = `<defs>
      <pattern id="g1" width=".5" height=".5" patternUnits="userSpaceOnUse"><path d="M.5 0H0V.5" fill="none" stroke="var(--grid)" stroke-width=".012"/></pattern>
      <pattern id="g2" width="1" height="1" patternUnits="userSpaceOnUse"><path d="M1 0H0V1" fill="none" stroke="var(--grid-major)" stroke-width=".02"/></pattern></defs>
      <rect width="${PLAN_W}" height="${PLAN_H}" fill="url(#g1)"/><rect width="${PLAN_W}" height="${PLAN_H}" fill="url(#g2)"/>`;
    for (const r of state.rooms) {
      const on = sel && sel.type === "room" && sel.id === r.id;
      s += `<g data-type="room" data-id="${r.id}"><rect x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" fill="${ROOM_FILL[r.type] || ROOM_FILL.other}" fill-opacity=".85" stroke="${on ? "#ffc400" : "#0f1b2a"}" stroke-width="${on ? ".1" : ".07"}"/>
        <text x="${r.x + .15}" y="${r.y + .45}" font-size=".34" font-weight="600" fill="#0f1b2a" pointer-events="none">${esc(r.name)}</text>
        <text x="${r.x + .15}" y="${r.y + .82}" font-size=".26" fill="#3d4f61" pointer-events="none">${r1(r.w)}×${r1(r.h)} м · ${r1(r.w * r.h)} м²</text></g>`;
      if (on) s += `<rect data-type="handle" data-id="${r.id}" x="${r.x + r.w - .17}" y="${r.y + r.h - .17}" width=".34" height=".34" fill="#ffc400" stroke="#0f1b2a" stroke-width=".04" style="cursor:nwse-resize"/>`;
    }
    if (draft) {
      const x = Math.min(draft.x0, draft.x1), y = Math.min(draft.y0, draft.y1);
      s += `<rect x="${x}" y="${y}" width="${Math.abs(draft.x1 - draft.x0)}" height="${Math.abs(draft.y1 - draft.y0)}" fill="none" stroke="#1f6fb2" stroke-width=".06" stroke-dasharray=".2 .12" pointer-events="none"/>`;
    }
    if (result && $("#showRoutes").checked) {
      const col = { light: "#d99100", socket: "#1f6fb2", dedicated: "#c23b2e" };
      for (const l of result.lines) {
        s += `<polyline points="${l.route.map((p) => p.join(",")).join(" ")}" fill="none" stroke="${col[l.kind]}" stroke-width=".06" stroke-linejoin="round" opacity=".75" pointer-events="none"/>`;
      }
    }
    for (const it of state.items) {
      const on = sel && sel.type === "item" && sel.id === it.id;
      s += `<g data-type="item" data-id="${it.id}" transform="translate(${it.x} ${it.y})">${on ? `<circle r=".42" fill="rgba(255,196,0,.35)" stroke="#ffc400" stroke-width=".05"/>` : ""}<circle r=".34" fill="transparent"/>${glyph(it)}</g>`;
    }
    if (state.panel) {
      const on = sel && sel.type === "panel";
      s += `<g data-type="panel" data-id="panel" transform="translate(${state.panel.x} ${state.panel.y})">${on ? `<circle r=".6" fill="rgba(255,196,0,.35)" stroke="#ffc400" stroke-width=".05"/>` : ""}
        <rect x="-.28" y="-.4" width=".56" height=".8" fill="#0f1b2a" stroke="#0f1b2a" stroke-width=".04"/>
        <path d="M.06 -.3L-.12 .04H.0L-.06 .3L.14 -.06H.02Z" fill="#ffc400"/></g>`;
    }
    plan.innerHTML = s;
    $("#empty").style.display = state.rooms.length || state.items.length ? "none" : "grid";
  }

  plan.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const p = pos(e);
    const tgt = e.target.closest("[data-type]");
    if (tool === "select") {
      if (!tgt) { sel = null; renderAll(); return; }
      const type = tgt.dataset.type, id = tgt.dataset.id;
      if (type === "handle") { drag = { mode: "resize", id }; sel = { type: "room", id }; }
      else {
        sel = { type, id };
        const obj = type === "room" ? state.rooms.find((r) => r.id === id) : type === "item" ? state.items.find((i) => i.id === id) : state.panel;
        drag = { mode: "move", type, id, sx: p.x, sy: p.y, ox: obj.x, oy: obj.y, moved: false, carried: [] };
        if (type === "room") {
          drag.carried = state.items.filter((i) => i.x >= obj.x && i.x <= obj.x + obj.w && i.y >= obj.y && i.y <= obj.y + obj.h).map((i) => ({ i, ox: i.x, oy: i.y }));
          if (state.panel && state.panel.x >= obj.x && state.panel.x <= obj.x + obj.w && state.panel.y >= obj.y && state.panel.y <= obj.y + obj.h) drag.carried.push({ i: state.panel, ox: state.panel.x, oy: state.panel.y });
        }
      }
      plan.setPointerCapture(e.pointerId);
      renderAll();
    } else if (tool === "room") {
      draft = { x0: p.x, y0: p.y, x1: p.x, y1: p.y };
      plan.setPointerCapture(e.pointerId);
    } else if (tool === "panel") {
      state.panel = { x: p.x, y: p.y }; sel = { type: "panel", id: "panel" }; changed();
    } else {
      const it = { id: nid("i"), kind: tool.startsWith("ap:") ? "appliance" : tool, x: p.x, y: p.y };
      if (tool.startsWith("ap:")) {
        it.appliance = tool.slice(3);
        const a = apOf(it.appliance);
        if (a && a.param_unit) it.value = a.param_default;
      }
      state.items.push(it); sel = { type: "item", id: it.id }; changed();
    }
  });
  plan.addEventListener("pointermove", (e) => {
    const p = pos(e);
    if (draft) { draft.x1 = p.x; draft.y1 = p.y; renderPlan(); return; }
    if (!drag) return;
    if (drag.mode === "resize") {
      const r = state.rooms.find((x) => x.id === drag.id);
      r.w = Math.max(r1(p.x - r.x), 0.8); r.h = Math.max(r1(p.y - r.y), 0.8);
    } else {
      const dx = r1(p.x - drag.sx), dy = r1(p.y - drag.sy);
      if (dx || dy) drag.moved = true;
      const obj = drag.type === "room" ? state.rooms.find((r) => r.id === drag.id) : drag.type === "item" ? state.items.find((i) => i.id === drag.id) : state.panel;
      obj.x = r1(Math.min(Math.max(drag.ox + dx, 0), PLAN_W)); obj.y = r1(Math.min(Math.max(drag.oy + dy, 0), PLAN_H));
      for (const c of drag.carried) { c.i.x = r1(c.ox + dx); c.i.y = r1(c.oy + dy); }
    }
    renderPlan(); renderInspector();
  });
  const endDrag = () => {
    if (draft) {
      const x = Math.min(draft.x0, draft.x1), y = Math.min(draft.y0, draft.y1);
      const w = Math.abs(draft.x1 - draft.x0), h = Math.abs(draft.y1 - draft.y0);
      draft = null;
      if (w >= 0.8 && h >= 0.8) {
        const room = { id: nid("r"), name: "Комната " + (state.rooms.length + 1), type: "living", x, y, w, h };
        state.rooms.push(room); sel = { type: "room", id: room.id }; changed();
      } else renderPlan();
    } else if (drag) {
      const moved = drag.mode === "resize" || drag.moved;
      drag = null;
      if (moved) changed(); else renderAll();
    }
  };
  plan.addEventListener("pointerup", endDrag);
  plan.addEventListener("pointercancel", endDrag);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { document.activeElement.blur(); setTool("select"); sel = null; renderAll(); return; }
    if (/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) return;
    if ((e.key === "Delete" || e.key === "Backspace") && sel) { removeSel(); e.preventDefault(); }
  });
  function removeSel() {
    if (!sel) return;
    if (sel.type === "room") state.rooms = state.rooms.filter((r) => r.id !== sel.id);
    else if (sel.type === "item") state.items = state.items.filter((i) => i.id !== sel.id);
    else state.panel = null;
    sel = null; changed();
  }

  /* ------------------------------------------------ инспектор */
  function renderInspector() {
    const el = $("#inspector");
    const num = (id, label, v, step = 0.1, min = 0) => `<label>${label}<input type="number" data-f="${id}" value="${v}" step="${step}" min="${min}"></label>`;
    if (!sel) {
      const area = state.rooms.reduce((a, r) => a + r.w * r.h, 0);
      const cnt = (k) => state.items.filter((i) => i.kind === k).length;
      el.innerHTML = `<h3>Проект</h3><dl>
        <dt>Комнат</dt><dd>${state.rooms.length}</dd><dt>Площадь</dt><dd>${r1(area)} м²</dd>
        <dt>Розеток</dt><dd>${cnt("socket")}</dd><dt>Выключателей</dt><dd>${cnt("switch")}</dd>
        <dt>Точек света</dt><dd>${cnt("light")}</dd><dt>Приборов</dt><dd>${cnt("appliance")}</dd>
        <dt>Щит</dt><dd>${state.panel ? "стоит" : "не задан"}</dd></dl>
        <p>Порядок работы: нарисуйте комнаты → поставьте щит → расставьте розетки, свет и приборы → «Рассчитать».</p>`;
      return;
    }
    if (sel.type === "room") {
      const r = state.rooms.find((x) => x.id === sel.id);
      if (!r) return;
      el.innerHTML = `<h3>Комната</h3>
        <label>Название<input type="text" data-f="name" value="${esc(r.name)}" maxlength="40"></label>
        <label class="row">Тип<select data-f="type">${Object.entries(catalog.room_types).map(([k, v]) => `<option value="${k}" ${k === r.type ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
        <div class="grid2">${num("x", "X, м", r.x)}${num("y", "Y, м", r.y)}${num("w", "Ширина, м", r.w, 0.1, 0.8)}${num("h", "Длина, м", r.h, 0.1, 0.8)}</div>
        <p>В ванной, санузле и на балконе розетки автоматически считаются влагозащищёнными.</p>
        <button class="danger" data-act="del">Удалить комнату</button>`;
    } else if (sel.type === "item") {
      const it = state.items.find((x) => x.id === sel.id);
      if (!it) return;
      const a = it.kind === "appliance" ? apOf(it.appliance) : null;
      const names = { socket: "Розетка", switch: "Выключатель", light: "Точка света" };
      el.innerHTML = `<h3>${esc(a ? a.name : names[it.kind])}</h3>
        ${a ? `<dl><dt>Мощность</dt><dd>${a.param_unit ? "150 Вт/" + a.param_unit : fmt(a.power_w) + " Вт"}</dd><dt>Подключение</dt><dd>${a.connection === "line" ? "отдельная линия" : "в розетку"}</dd></dl>` : ""}
        ${a && a.param_unit ? `<div class="row">${num("value", "Площадь, " + a.param_unit, it.value ?? a.param_default, 0.5, 0.5)}</div>` : ""}
        <div class="grid2">${num("x", "X, м", it.x)}${num("y", "Y, м", it.y)}</div>
        <button class="danger" data-act="del">Удалить</button>`;
    } else {
      el.innerHTML = `<h3>Электрощит</h3><div class="grid2">${num("x", "X, м", state.panel.x)}${num("y", "Y, м", state.panel.y)}</div>
        <p>Длины кабелей считаются от этой точки. Высота щита — в параметрах слева.</p><button class="danger" data-act="del">Убрать щит</button>`;
    }
  }
  $("#inspector").addEventListener("input", (e) => {
    const f = e.target.dataset.f;
    if (!f || !sel) return;
    const obj = sel.type === "room" ? state.rooms.find((r) => r.id === sel.id) : sel.type === "item" ? state.items.find((i) => i.id === sel.id) : state.panel;
    if (!obj) return;
    const val = e.target.type === "number" ? parseFloat(e.target.value) : e.target.value;
    if (e.target.type === "number" && !Number.isFinite(val)) return;
    obj[f] = val;
    stale = !!result; renderPlan(); updateStale();
  });
  $("#inspector").addEventListener("change", (e) => { if (e.target.dataset.f) { stale = !!result; renderPlan(); updateStale(); } });
  $("#inspector").addEventListener("click", (e) => { if (e.target.dataset.act === "del") removeSel(); });

  /* ------------------------------------------------ общие события */
  function updateStale() { $("#stale").hidden = !(stale && result); }
  function renderAll() { renderPlan(); renderInspector(); updateStale(); }
  function changed() { stale = !!result; renderAll(); }
  function toast(msg, err) {
    const t = $("#toast");
    t.textContent = msg; t.className = "toast" + (err ? " err" : ""); t.hidden = false;
    clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), err ? 6000 : 3200);
  }
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-tool]");
    if (b) setTool(b.dataset.tool);
  });
  $("#projName").addEventListener("input", (e) => (state.name = e.target.value));
  $("#showRoutes").addEventListener("change", renderPlan);
  const bindSetting = (id, key, parse) => $(id).addEventListener("change", (e) => { const v = parse(e.target.value); if (Number.isFinite(v)) { state.settings[key] = v; changed(); } });
  bindSetting("#sCeil", "ceiling_h", parseFloat);
  bindSetting("#sPanelH", "panel_h", parseFloat);
  bindSetting("#sPhases", "phases", (v) => parseInt(v, 10));
  bindSetting("#sAllowed", "allowed_kw", parseFloat);

  function syncSettings() {
    $("#sCeil").value = state.settings.ceiling_h; $("#sPanelH").value = state.settings.panel_h;
    $("#sPhases").value = state.settings.phases; $("#sAllowed").value = state.settings.allowed_kw;
    $("#projName").value = state.name;
  }
  function loadProject(p) {
    state = { ...fresh(), ...p, settings: { ...fresh().settings, ...(p.settings || {}) } };
    state.items.forEach((i) => { i.id = i.id || nid("i"); });
    result = null; stale = false; sel = null; estimate = [];
    $("#results").hidden = true; $("#btnEstimate").disabled = true;
    syncSettings(); renderAll();
  }

  $("#btnSample").addEventListener("click", async () => {
    const r = await fetch("/api/sample");
    loadProject(await r.json());
    toast("Загружен пример квартиры. Нажмите «Рассчитать».");
  });
  $("#btnClear").addEventListener("click", () => {
    if (state.rooms.length + state.items.length && !confirm("Очистить план?")) return;
    loadProject(fresh());
  });
  $("#btnSave").addEventListener("click", async () => {
    const r = await fetch("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state) });
    const d = await r.json();
    if (!r.ok) return toast(d.error || "Не удалось сохранить", true);
    const url = location.origin + location.pathname + "?p=" + d.id;
    history.replaceState(null, "", url);
    try { await navigator.clipboard.writeText(url); toast("Сохранено. Ссылка скопирована."); } catch { toast("Сохранено: " + url); }
  });
  $("#btnCalc").addEventListener("click", calc);
  $("#btnEstimate").addEventListener("click", () => { showTab("estimate"); $("#results").scrollIntoView({ behavior: "smooth" }); });
  document.querySelector(".tabbar").addEventListener("click", (e) => { if (e.target.dataset.tab) showTab(e.target.dataset.tab); });
  function showTab(t) {
    document.querySelectorAll(".tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.tab === t));
    document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("active", p.id === "pane-" + t));
  }

  async function calc() {
    const btn = $("#btnCalc"); btn.disabled = true;
    try {
      const r = await fetch("/api/calc", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state) });
      const d = await r.json();
      if (!r.ok) { toast(d.error || "Ошибка расчёта", true); return; }
      result = d; stale = false;
      estimate = d.bom.map((b) => ({ ...b, on: !b.optional || b.default }));
      renderResults(); renderAll();
      $("#results").hidden = false; $("#btnEstimate").disabled = false;
      showTab("lines");
      $("#results").scrollIntoView({ behavior: "smooth" });
    } catch { toast("Нет связи с сервером", true); }
    finally { btn.disabled = false; }
  }

  /* ------------------------------------------------ результаты */
  function renderResults() {
    const s = result.summary;
    const card = (v, l, hot) => `<div class="card ${hot ? "hot" : ""}"><b>${v}</b><span>${l}</span></div>`;
    $("#cards").innerHTML =
      card(`${s.main_in} А`, `вводной автомат (${s.phases === 3 ? "3 фазы" : "1 фаза"})`, true) +
      card(`${(s.P_demand / 1000).toFixed(1).replace(".", ",")} кВт`, "расчётная мощность") +
      card(`${(s.P_installed / 1000).toFixed(1).replace(".", ",")} кВт`, "установленная мощность") +
      card(`${s.I_calc} А`, s.phases === 3 ? "расчётный ток (макс. фаза)" : "расчётный ток") +
      card(s.lines, "линий в щите") + card(`${s.cable_total} м`, "кабеля по линиям") +
      card(`${s.panel_capacity} мод.`, `щит (занято ${s.panel_modules})`);
    $("#warnings").innerHTML = result.warnings.map((w) => `<div class="warn">${esc(w)}</div>`).join("");
    $("#notes").innerHTML = "<b>Допущения расчёта</b><ul>" + result.notes.map((n) => `<li>${esc(n)}</li>`).join("") + "</ul>";
    renderLines(); renderPanel(); renderEstimate();
  }

  function renderLines() {
    const rows = result.lines.map((l) => `<tr>
      <td class="num">${l.no}</td>
      <td><span class="dot k-${l.kind}"></span>${esc(l.name)}<span class="reason">${l.points} ${l.points === 1 ? "точка" : "точ."}</span></td>
      <td>${esc(l.phase)}</td><td class="num">${fmt(l.P)}</td><td class="num">${String(l.Ib).replace(".", ",")}</td>
      <td>${l.poles} ${esc(l.curve)}${l.In}<span class="reason">${esc(l.protection)}</span></td>
      <td>${esc(l.cable)}</td><td class="num">${l.length}</td><td class="num">${String(l.du).replace(".", ",")}</td></tr>`).join("");
    $("#pane-lines").innerHTML = `<div class="scroll-x"><table class="t"><thead><tr>
      <th class="num">№</th><th>Линия</th><th>Фаза</th><th class="num">P, Вт</th><th class="num">Iрасч, А</th><th>Автомат</th><th>Кабель</th><th class="num">Длина, м</th><th class="num">ΔU, %</th>
      </tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function renderPanel() {
    const P = result.panel, MW = 30, ROW_H = 132, GAP = 34, PAD = 16;
    const W = P.row_modules * MW + PAD * 2, Hh = P.rows * (ROW_H + GAP) + PAD * 2 + 6;
    const col = {
      main: ["#0f1b2a", "#fff"], spd: ["#ffc400", "#1a1400"], relay: ["#9fb1c1", "#0f1b2a"],
      rcd: ["#1f6fb2", "#fff"], mcb: ["#eef2f6", "#0f1b2a"], rcbo: ["#cde9d9", "#0f1b2a"],
    };
    const rating = (n) => ((n.match(/\b([BC]\d+)\b/) || n.match(/(\d+)\s?А/) || [])[1] || "");
    const shortName = (d, ln) => {
      if (ln) {
        if (ln.kind === "dedicated") return ln.name.split(" — ")[0];
        return (ln.kind === "light" ? "Свет: " : "Розетки: ") + ln.rooms.join(", ");
      }
      return { main: "Ввод", spd: "УЗИП", relay: "Реле напряжения", rcd: "УЗО 30 мА" }[d.type] || d.name;
    };
    let s = `<svg viewBox="0 0 ${W} ${Hh}" xmlns="http://www.w3.org/2000/svg" font-family="IBM Plex Sans, Segoe UI, sans-serif">
      <rect x="2" y="2" width="${W - 4}" height="${Hh - 4}" rx="6" fill="none" stroke="#0f1b2a" stroke-width="3"/>`;
    P.placed.forEach((row, ri) => {
      const y = PAD + ri * (ROW_H + GAP) + 18;
      s += `<rect x="${PAD}" y="${y + ROW_H / 2 - 5}" width="${P.row_modules * MW}" height="10" fill="#b9c6d2"/>`;
      let used = 0;
      for (const d of row) {
        const x = PAD + d.x * MW, w = d.w * MW - 2, c = col[d.type] || col.mcb;
        const ln = d.line ? result.lines[d.line - 1] : null;
        const fs = d.w > 1 ? 11 : 9.5, maxc = Math.floor((ROW_H - 46) / (fs * 0.58));
        let nm = shortName(d, ln);
        if (nm.length > maxc) nm = nm.slice(0, maxc - 1) + "…";
        s += `<g><title>${esc(d.label)} — ${esc(d.name)}${ln ? " · " + esc(ln.name) : ""}</title>
          <rect x="${x + 1}" y="${y}" width="${w}" height="${ROW_H}" rx="3" fill="${c[0]}" stroke="#0f1b2a" stroke-width="1.5"/>
          <text x="${x + w / 2 + 1}" y="${y + 15}" text-anchor="middle" font-size="${fs}" font-weight="600" fill="${c[1]}">${esc(d.label)}</text>
          <text x="${x + w / 2 + 1}" y="${y + 29}" text-anchor="middle" font-size="${fs - 1.5}" fill="${c[1]}">${esc(rating(d.name))}</text>
          <text transform="translate(${x + w / 2 + 4} ${y + ROW_H - 8}) rotate(-90)" font-size="${fs}" fill="${c[1]}">${esc(nm)}</text></g>`;
        used = d.x + d.w;
      }
      if (used < P.row_modules) s += `<rect x="${PAD + used * MW + 1}" y="${y}" width="${(P.row_modules - used) * MW - 2}" height="${ROW_H}" rx="3" fill="none" stroke="#7d8fa0" stroke-dasharray="5 4"/>`;
    });
    s += "</svg>";
    $("#pane-panel").innerHTML = `<p class="est-note">${esc(P.enclosure)}. Занято ${result.summary.panel_modules} из ${P.capacity} модулей, свободно ${P.free} — запас на будущие линии. Наведите курсор на аппарат, чтобы увидеть полное название.</p>
      <div class="panel-fig">${s}</div>
      <div class="legend"><span><i style="background:#0f1b2a"></i>Вводной автомат</span><span><i style="background:#ffc400"></i>УЗИП</span><span><i style="background:#9fb1c1"></i>Реле напряжения</span>
      <span><i style="background:#1f6fb2"></i>УЗО 30 мА</span><span><i style="background:#eef2f6"></i>Автомат</span><span><i style="background:#cde9d9"></i>Дифавтомат 30 мА</span><span><i style="background:none;border-style:dashed"></i>Свободные модули</span></div>`;
  }

  /* ------------------------------------------------ смета */
  const GROUPS = [
    ["panel", "Щит и аппараты защиты"], ["cable", "Кабель"], ["devices", "Электроустановочные изделия"],
    ["materials", "Монтажные материалы"], ["recommended", "Рекомендуем дополнительно"], ["works", "Работы (по желанию)"],
  ];
  function renderEstimate() {
    let rows = "";
    for (const [g, title] of GROUPS) {
      const idxs = estimate.map((e, i) => (e.group === g ? i : -1)).filter((i) => i >= 0);
      if (!idxs.length) continue;
      const allOn = idxs.every((i) => estimate[i].on);
      const master = g === "works" || g === "recommended" ? `<label class="chk"><input type="checkbox" data-grp="${g}" ${allOn ? "checked" : ""}> все</label>` : "";
      rows += `<tr class="grp"><td colspan="6">${title} ${master}</td></tr>`;
      for (const i of idxs) {
        const e = estimate[i];
        rows += `<tr data-i="${i}" class="${e.on ? "" : "off"}">
          <td>${e.optional ? `<input type="checkbox" class="chk" data-on="${i}" ${e.on ? "checked" : ""} aria-label="Включить в смету">` : ""}</td>
          <td>${esc(e.name)}${e.reason ? `<span class="reason">${esc(e.reason)}</span>` : ""}</td>
          <td>${esc(e.unit)}</td>
          <td class="num"><input type="number" min="0" step="1" value="${e.qty}" data-q="${i}" aria-label="Количество"></td>
          <td class="num">${money(e.price)}</td><td class="num" data-s="${i}">${money(e.on ? e.qty * e.price : 0)}</td></tr>`;
      }
    }
    $("#pane-estimate").innerHTML = `<p class="est-note">Цены ориентировочные (из справочника БД). Количество можно править вручную; необязательные позиции включаются галочкой.</p>
      <div class="scroll-x"><table class="t"><thead><tr><th></th><th>Наименование</th><th>Ед.</th><th class="num">Кол-во</th><th class="num">Цена</th><th class="num">Сумма</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="total" id="totals"></div>
      <div class="est-actions"><button class="btn dark" id="btnCsv">Скачать CSV</button><button class="btn dark" id="btnPrint">Печать / PDF</button></div>`;
    updateTotals();
  }
  function updateTotals() {
    const sum = (f) => estimate.filter((e) => e.on && f(e)).reduce((a, e) => a + e.qty * e.price, 0);
    const mat = sum((e) => ["panel", "cable", "devices", "materials"].includes(e.group));
    const rec = sum((e) => e.group === "recommended"), wrk = sum((e) => e.group === "works");
    $("#totals").innerHTML = `<table><tr><td>Материалы</td><td>${money(mat)}</td></tr>
      ${rec ? `<tr><td>Рекомендуемое дополнительно</td><td>${money(rec)}</td></tr>` : ""}
      ${wrk ? `<tr><td>Работы</td><td>${money(wrk)}</td></tr>` : ""}
      <tr class="sum"><td>Итого</td><td>${money(mat + rec + wrk)}</td></tr></table>`;
    estimate.forEach((e, i) => {
      const c = document.querySelector(`[data-s="${i}"]`);
      if (c) { c.textContent = money(e.on ? e.qty * e.price : 0); c.parentElement.classList.toggle("off", !e.on); }
    });
  }
  $("#pane-estimate").addEventListener("change", (e) => {
    const t = e.target;
    if (t.dataset.on !== undefined) { estimate[+t.dataset.on].on = t.checked; updateTotals(); }
    else if (t.dataset.q !== undefined) { estimate[+t.dataset.q].qty = Math.max(0, parseFloat(t.value) || 0); updateTotals(); }
    else if (t.dataset.grp) {
      estimate.forEach((x, i) => { if (x.group === t.dataset.grp) { x.on = t.checked; const cb = document.querySelector(`[data-on="${i}"]`); if (cb) cb.checked = t.checked; } });
      updateTotals();
    }
  });
  $("#pane-estimate").addEventListener("click", (e) => {
    if (e.target.id === "btnPrint") window.print();
    if (e.target.id === "btnCsv") {
      const names = Object.fromEntries(GROUPS);
      const q = (v) => `"${String(v).replace(/"/g, '""')}"`;
      const lines = ["Раздел;Наименование;Ед.;Кол-во;Цена;Сумма"];
      let total = 0;
      for (const x of estimate) {
        if (!x.on) continue;
        const sm = x.qty * x.price; total += sm;
        lines.push([q(names[x.group]), q(x.name), q(x.unit), x.qty, x.price, sm].join(";"));
      }
      lines.push(["", q("ИТОГО"), "", "", "", total].join(";"));
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" }));
      a.download = (state.name || "smeta") + ".csv"; a.click(); URL.revokeObjectURL(a.href);
    }
  });

  /* ------------------------------------------------ старт */
  (async function init() {
    try { catalog = await (await fetch("/api/catalog")).json(); } catch { toast("Не удалось загрузить справочник", true); }
    renderTools(); syncSettings(); renderAll();
    const pid = new URLSearchParams(location.search).get("p");
    if (pid) {
      const r = await fetch("/api/projects/" + encodeURIComponent(pid));
      if (r.ok) loadProject(await r.json()); else toast("Проект не найден", true);
    }
  })();
})();
