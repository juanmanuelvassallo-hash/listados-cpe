#!/usr/bin/env python3
"""
build.py — Generador combinado del Buscador de Listados CPE Santa Cruz
========================================================================
Este script se ejecuta SOLO cuando Netlify construye el sitio (no hace
falta correrlo a mano). Toma TODOS los PDF que estén en la carpeta
/pdfs y genera un único buscador (public/index.html) que junta los
datos de todos los listados encontrados.

Para agregar un listado nuevo (por ejemplo un complementario):
    Subí el PDF a la carpeta /pdfs en GitHub. Netlify reconstruye el
    sitio solo y el buscador queda actualizado en 1-2 minutos.

Uso local (opcional, para probar antes de subir):
    pip install -r requirements.txt
    python build.py
    (el resultado queda en public/index.html)
"""

import os
import re
import json
import glob
import unicodedata
import pdfplumber

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDFS_DIR = os.path.join(BASE_DIR, 'pdfs')
OUT_DIR = os.path.join(BASE_DIR, 'public')
MAP_PATH = os.path.join(BASE_DIR, 'column_map.json')

# Claves reservadas: nunca se usan como sigla auto-generada de columna.
RESERVADAS = {'d', 'n', 'l', 'o', 'c', 'P', 'tot', 'src'}


# ─────────────────────────────────────────────
# UTILIDADES DE COLUMNAS
# ─────────────────────────────────────────────

def normalizar(txt):
    txt = (txt or '').strip().lower()
    txt = unicodedata.normalize('NFKD', txt)
    txt = ''.join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r'\s+', ' ', txt)
    return txt


def cargar_column_map():
    if os.path.exists(MAP_PATH):
        with open(MAP_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def guardar_column_map(mapa):
    with open(MAP_PATH, 'w', encoding='utf-8') as f:
        json.dump(mapa, f, ensure_ascii=False, indent=2, sort_keys=True)


def limpiar_codigo(header_text):
    """Deja el encabezado tal como viene en el PDF (TIT, OT, AT...),
    sólo le sacan acentos y caracteres raros. Si el PDF ya trae la
    columna abreviada -que es lo habitual en estos listados- el
    resultado es exactamente esa sigla, sin inventar una nueva."""
    txt = unicodedata.normalize('NFKD', header_text or '')
    txt = ''.join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r'[^A-Za-z0-9]', '', txt)
    return txt.upper()


def generar_codigo(header_text, usados):
    base = limpiar_codigo(header_text) or 'X'
    codigo = base
    i = 2
    # Sólo se agrega un número si esa sigla ya está tomada por OTRO
    # encabezado distinto (colisión real), no como paso obligatorio.
    while codigo in usados or codigo in RESERVADAS:
        codigo = f'{base}{i}'
        i += 1
    return codigo


def clave_para_columna(header_text, column_map, usados):
    """Devuelve la sigla corta para una columna de 'desglose' (Título,
    Antigüedad, etc). Si ya se vio esa columna en un listado anterior,
    reusa la misma sigla (queda guardada en column_map.json)."""
    norm = normalizar(header_text)
    if norm in column_map:
        return column_map[norm]
    codigo = generar_codigo(header_text, usados)
    column_map[norm] = codigo
    usados.add(codigo)
    return codigo


# ─────────────────────────────────────────────
# EXTRACCIÓN DE UN PDF
# ─────────────────────────────────────────────

def extraer_pdf(pdf_path, column_map, usados):
    registros = []
    cargo_actual = None
    columnas = None
    conteo_cargo = {}

    nombre_archivo = os.path.basename(pdf_path)
    print(f"\n📄 Procesando: {nombre_archivo}")

    with pdfplumber.open(pdf_path) as pdf:
        total_paginas = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            print(f"   Página {i + 1}/{total_paginas}...", end='\r')

            tables = page.extract_tables()
            if not tables:
                continue

            for table in tables:
                for row in table:
                    if not row or not any(c for c in row if c):
                        continue

                    non_empty = [c.strip() for c in row if c and c.strip()]
                    first = row[0].strip() if row[0] else ''

                    # ── Nombre de cargo (única celda, empieza con '(') ──
                    if (len(non_empty) == 1 and first.startswith('(')
                            and len(first) > 3 and not first[0].isdigit()):
                        cargo_actual = first
                        conteo_cargo.setdefault(cargo_actual, 0)
                        continue

                    # ── Fila de encabezados ──
                    if first == 'Ord' and len(non_empty) >= 3:
                        columnas = [c.strip() if c else '' for c in row]
                        continue

                    # ── Títulos de página, saltear ──
                    if ('LISTADO' in first.upper() or 'Localidad' in first
                            or first.strip() == 'CARGOS'):
                        continue

                    # ── Fila de datos ──
                    if (cargo_actual and columnas and first
                            and first[0].isdigit() and len(row) >= 4):

                        try:
                            doc_idx = next(
                                j for j, c in enumerate(columnas)
                                if c and 'ocumento' in c
                            )
                        except StopIteration:
                            doc_idx = 3

                        doc = (row[doc_idx].strip().replace(' ', '')
                               if len(row) > doc_idx and row[doc_idx] else '')
                        if not doc or not doc.isdigit():
                            continue

                        conteo_cargo[cargo_actual] += 1
                        pos = conteo_cargo[cargo_actual]

                        reg = {'c': cargo_actual, 'o': pos, 'd': doc, 'src': nombre_archivo}

                        for j, col_name in enumerate(columnas):
                            if not col_name or j == doc_idx:
                                continue
                            val = row[j].strip() if j < len(row) and row[j] else ''
                            if not val:
                                continue

                            norm = normalizar(col_name)
                            if norm == 'ord':
                                continue  # ya está en 'o' (posición calculada)
                            elif 'egajo' in norm:
                                reg['l'] = val
                            elif 'pellido' in norm:
                                reg['n'] = val
                            elif 'puntaje' in norm or norm == 'pje':
                                reg['P'] = val
                            else:
                                key = clave_para_columna(col_name, column_map, usados)
                                reg[key] = val

                        registros.append(reg)

    # Completar el total de cada cargo en cada registro (posición "de N")
    for reg in registros:
        reg['tot'] = conteo_cargo.get(reg['c'], '?')

    print(f"\n   → {len(registros)} registros en {len(conteo_cargo)} cargos")
    return registros


# ─────────────────────────────────────────────
# GENERACIÓN DEL HTML
# ─────────────────────────────────────────────

def generar_html(registros, fuentes, column_map):
    cargos = sorted(set(r['c'] for r in registros))

    # Orden estable de las columnas de desglose: por orden de aparición
    # en column_map.json (así el buscador no "salta" de un build a otro)
    desglose_cols = list(dict.fromkeys(column_map.values()))

    data_json = json.dumps(registros, ensure_ascii=False, separators=(',', ':'))
    desglose_json = json.dumps(desglose_cols, ensure_ascii=False, separators=(',', ':'))
    fuentes_json = json.dumps(fuentes, ensure_ascii=False, separators=(',', ':'))

    n_listados = len(fuentes)
    subtitulo_listados = (f"{n_listados} listado{'s' if n_listados != 1 else ''} combinado{'s' if n_listados != 1 else ''}")

    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<title>Buscador de Listados — CPE Santa Cruz</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent;}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;min-height:100vh;color:#e2e8f0;}}

.header{{
  background:linear-gradient(135deg,#4f46e5,#7c3aed);
  padding:20px 16px 16px;text-align:center;
  position:sticky;top:0;z-index:100;
  box-shadow:0 4px 20px rgba(0,0,0,0.4);
}}
.header h1{{font-size:18px;font-weight:700;color:white;letter-spacing:-0.3px;}}
.header p{{font-size:11px;color:rgba(255,255,255,0.7);margin-top:3px;}}
.header .autor{{font-size:11px;color:rgba(255,255,255,0.85);margin-top:6px;font-weight:600;letter-spacing:0.3px;}}

.search-wrap{{padding:16px;background:#1e293b;border-bottom:1px solid #334155;}}

.tab-row{{display:flex;background:#0f172a;border-radius:10px;padding:3px;margin-bottom:12px;gap:3px;}}
.tab-btn{{flex:1;padding:8px 4px;border:none;background:transparent;color:#94a3b8;
  font-size:13px;font-weight:600;border-radius:8px;cursor:pointer;transition:all 0.2s;}}
.tab-btn.active{{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:white;}}

.input-row{{display:flex;gap:8px;align-items:stretch;}}
.dni-input{{flex:1;padding:13px 16px;background:#0f172a;border:2px solid #334155;border-radius:12px;
  color:#e2e8f0;font-size:18px;font-weight:600;letter-spacing:1px;-webkit-appearance:none;
  transition:border-color 0.2s;}}
.dni-input:focus{{outline:none;border-color:#6366f1;}}
.dni-input::placeholder{{font-size:14px;font-weight:400;letter-spacing:0;color:#475569;}}
.multi-area{{flex:1;padding:13px 16px;background:#0f172a;border:2px solid #334155;border-radius:12px;
  color:#e2e8f0;font-size:15px;font-family:inherit;resize:vertical;min-height:100px;-webkit-appearance:none;}}
.multi-area:focus{{outline:none;border-color:#6366f1;}}
.buscar-btn{{padding:13px 18px;background:linear-gradient(135deg,#4f46e5,#7c3aed);border:none;
  border-radius:12px;color:white;font-size:15px;font-weight:700;cursor:pointer;white-space:nowrap;
  box-shadow:0 4px 15px rgba(99,102,241,0.4);-webkit-appearance:none;transition:transform 0.1s;}}
.buscar-btn:active{{transform:scale(0.97);}}
.multi-hint{{font-size:11px;color:#64748b;margin-bottom:8px;padding:8px 10px;
  background:#0f172a;border-radius:8px;border-left:3px solid #4f46e5;}}

.panel{{display:none;}}
.panel.active{{display:block;}}

.results{{padding:16px;}}
.empty-state{{text-align:center;padding:60px 20px;color:#475569;}}
.empty-icon{{font-size:56px;margin-bottom:16px;}}
.empty-title{{font-size:18px;font-weight:600;color:#64748b;margin-bottom:8px;}}
.empty-sub{{font-size:13px;line-height:1.5;}}
.fuentes-list{{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-top:16px;}}
.fuente-tag{{background:#1e293b;border:1px solid #334155;color:#94a3b8;font-size:11px;
  padding:5px 10px;border-radius:20px;}}

.stats-badge{{background:#1e293b;border:1px solid #334155;border-radius:12px;
  padding:14px 16px;margin-bottom:12px;border-left:4px solid #6366f1;}}
.stats-badge .name{{font-size:18px;font-weight:700;color:#e2e8f0;margin-bottom:4px;}}
.stats-badge .sub{{font-size:13px;color:#64748b;}}
.stats-badge .sub span{{color:#94a3b8;font-weight:600;}}

.cargo-card{{background:#1e293b;border:1px solid #334155;border-radius:14px;
  padding:16px;margin-bottom:12px;position:relative;overflow:hidden;}}
.cargo-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,#4f46e5,#7c3aed);}}
.cargo-name{{font-size:13px;font-weight:700;color:#818cf8;margin-bottom:2px;
  text-transform:uppercase;letter-spacing:0.3px;padding-top:4px;}}
.cargo-src{{font-size:10px;color:#64748b;margin-bottom:12px;letter-spacing:0.3px;}}

.pos-row{{display:flex;align-items:center;gap:12px;margin-bottom:10px;}}
.pos-circle{{width:56px;height:56px;border-radius:50%;
  background:linear-gradient(135deg,#4f46e5,#7c3aed);
  display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0;}}
.pos-num{{font-size:20px;font-weight:800;color:white;line-height:1;}}
.pos-total{{font-size:9px;color:rgba(255,255,255,0.7);margin-top:1px;}}
.pos-pje{{background:#0f172a;border-radius:10px;padding:8px 14px;text-align:center;}}
.pos-pje-label{{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;}}
.pos-pje-val{{font-size:24px;font-weight:800;color:#818cf8;line-height:1.1;}}

.desglose{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;
  margin-top:12px;padding-top:12px;border-top:1px solid #334155;}}
.dsgl-item{{background:#0f172a;border-radius:8px;padding:6px 4px;text-align:center;}}
.dsgl-lbl{{font-size:9px;color:#475569;text-transform:uppercase;}}
.dsgl-val{{font-size:13px;font-weight:700;color:#94a3b8;}}

.m-cargo-card{{background:#1e293b;border:1px solid #334155;border-radius:14px;margin-bottom:12px;overflow:hidden;}}
.m-cargo-title{{padding:12px 16px;background:linear-gradient(135deg,rgba(79,70,229,0.3),rgba(124,58,237,0.3));
  border-bottom:1px solid #334155;}}
.m-cargo-name{{font-size:13px;font-weight:700;color:#818cf8;text-transform:uppercase;}}
.m-cargo-sub{{font-size:11px;color:#475569;margin-top:2px;}}

.m-doc-row{{padding:12px 16px;border-bottom:1px solid #0f172a;display:grid;
  grid-template-columns:44px 1fr 60px;gap:10px;align-items:center;}}
.m-doc-row.ganador{{background:rgba(34,197,94,0.08);border-left:3px solid #22c55e;}}
.m-pos{{font-size:22px;font-weight:800;color:#818cf8;text-align:center;}}
.m-doc-row.ganador .m-pos{{color:#22c55e;}}
.m-nombre{{font-size:14px;font-weight:600;color:#e2e8f0;}}
.m-dni-lbl{{font-size:11px;color:#64748b;margin-top:2px;}}
.m-pje-val{{font-size:20px;font-weight:800;color:#818cf8;text-align:right;}}
.m-doc-row.ganador .m-pje-val{{color:#22c55e;}}
.ganador-badge{{display:inline-block;background:#22c55e;color:white;font-size:10px;font-weight:700;
  padding:2px 7px;border-radius:10px;margin-top:3px;}}

.toast{{position:fixed;bottom:20px;left:50%;transform:translateX(-50%) translateY(100px);
  background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:12px 20px;border-radius:12px;
  font-size:14px;font-weight:600;transition:transform 0.3s;z-index:999;
  box-shadow:0 8px 30px rgba(0,0,0,0.5);white-space:nowrap;}}
.toast.show{{transform:translateX(-50%) translateY(0);}}

.loading{{text-align:center;padding:40px;color:#64748b;}}
.spinner{{width:32px;height:32px;border:3px solid #1e293b;border-top:3px solid #6366f1;
  border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 12px;}}
@keyframes spin{{100%{{transform:rotate(360deg);}}}}

.totales{{background:#1e293b;border:1px solid #334155;border-radius:12px;
  padding:12px 16px;margin-bottom:16px;display:flex;gap:16px;}}
.tot-item{{text-align:center;flex:1;}}
.tot-val{{font-size:24px;font-weight:800;color:#818cf8;}}
.tot-lbl{{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;}}
</style>
</head>
<body>

<div class="header">
  <h1>🎓 Buscador de Listados</h1>
  <p>CPE Santa Cruz — {subtitulo_listados}</p>
  <p class="autor">👤 Desarrollado por Mg. Vassallo</p>
</div>

<div class="search-wrap">
  <div class="tab-row">
    <button class="tab-btn active" id="tabInd" onclick="switchTab('ind')">🔍 Por DNI</button>
    <button class="tab-btn" id="tabMul" onclick="switchTab('mul')">👥 Comparar varios</button>
  </div>

  <div class="panel active" id="panelInd">
    <div class="input-row">
      <input class="dni-input" type="tel" id="dniInput"
        placeholder="DNI sin puntos" maxlength="9"
        inputmode="numeric" pattern="[0-9]*"
        onkeypress="if(event.key==='Enter')buscar()">
      <button class="buscar-btn" onclick="buscar()">Buscar</button>
    </div>
  </div>

  <div class="panel" id="panelMul">
    <div class="multi-hint">💡 Un DNI por línea o separados por coma. Ctrl+Enter para buscar.</div>
    <div class="input-row">
      <textarea class="multi-area" id="dnisInput"
        placeholder="26290082&#10;26602600&#10;30503051"
        onkeypress="if(event.key==='Enter'&&event.ctrlKey)buscarMulti()"></textarea>
      <button class="buscar-btn" onclick="buscarMulti()">Buscar</button>
    </div>
  </div>
</div>

<div class="results" id="results"></div>

<div class="toast" id="toast"></div>

<footer style="text-align:center;padding:28px 16px 36px;border-top:1px solid #1e293b;margin-top:8px;">
  <div style="font-size:12px;color:#64748b;">Desarrollado por</div>
  <div style="font-size:17px;font-weight:800;color:#818cf8;margin-top:3px;letter-spacing:0.2px;">Mg. Juan Manuel Vassallo</div>
</footer>

<script>
const DATA = {data_json};
const DESGLOSE_COLS = {desglose_json};
const N_CARGOS = {len(cargos)};
const FUENTES = {fuentes_json};

const idx = {{}};
for (const r of DATA) {{
  if (!idx[r.d]) idx[r.d] = [];
  idx[r.d].push(r);
}}

document.getElementById('results').innerHTML = emptyState();

function switchTab(tab) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('tab' + (tab==='ind'?'Ind':'Mul')).classList.add('active');
  document.getElementById('panel' + (tab==='ind'?'Ind':'Mul')).classList.add('active');
  if (tab==='ind') document.getElementById('dniInput').focus();
  else document.getElementById('dnisInput').focus();
  document.getElementById('results').innerHTML = emptyState();
}}

function emptyState() {{
  const listado = FUENTES.length
    ? `<div class="fuentes-list">${{FUENTES.map(f => `<span class="fuente-tag">${{fmtSrc(f)}}</span>`).join('')}}</div>`
    : '';
  return `<div class="empty-state">
    <div class="empty-icon">🗂️</div>
    <div class="empty-title">{subtitulo_listados}</div>
    <div class="empty-sub">
      <strong style="color:#818cf8;">${{DATA.length.toLocaleString()}}</strong> docentes cargados<br>
      en <strong style="color:#818cf8;">${{N_CARGOS}}</strong> cargos distintos
    </div>
    ${{listado}}
  </div>`;
}}

function buscar() {{
  const raw = document.getElementById('dniInput').value.trim().replace(/\\D/g,'');
  if (!raw) {{ toast('Ingresá un DNI'); return; }}
  const res = document.getElementById('results');
  res.innerHTML = '<div class="loading"><div class="spinner"></div><p>Buscando...</p></div>';
  setTimeout(() => {{
    const resultados = idx[raw] || [];
    if (!resultados.length) {{
      res.innerHTML = `<div class="empty-state">
        <div class="empty-icon">🔍</div>
        <div class="empty-title">No encontrado</div>
        <div class="empty-sub">El DNI <strong>${{fmtDNI(raw)}}</strong> no figura en ningún listado cargado.</div>
      </div>`; return;
    }}
    const r0 = resultados[0];
    let html = `<div class="stats-badge">
      <div class="name">${{r0.n||''}}</div>
      <div class="sub">DNI: <span>${{fmtDNI(raw)}}</span> &nbsp;|&nbsp; Legajo: <span>${{r0.l||'—'}}</span></div>
      <div class="sub" style="margin-top:4px;">Aparece en <span>${{resultados.length}}</span> cargo${{resultados.length>1?'s':''}}</div>
    </div>`;
    for (const r of resultados) {{
      html += `<div class="cargo-card">
        <div class="cargo-name">${{r.c}}</div>
        <div class="cargo-src">${{fmtSrc(r.src)}}</div>
        <div class="pos-row">
          <div class="pos-circle">
            <div class="pos-num">${{r.o}}</div>
            <div class="pos-total">de ${{r.tot}}</div>
          </div>
          <div class="pos-pje">
            <div class="pos-pje-label">Puntaje</div>
            <div class="pos-pje-val">${{r.P||'—'}}</div>
          </div>
        </div>
        <div class="desglose">${{DESGLOSE_COLS.map(c => r[c] ? dsgl(c, r[c]) : '').join('')}}</div>
      </div>`;
    }}
    res.innerHTML = html;
  }}, 50);
}}

function buscarMulti() {{
  const raw = document.getElementById('dnisInput').value.trim();
  if (!raw) {{ toast('Ingresá al menos un DNI'); return; }}
  const dnis = raw.split(/[\\n,;]+/).map(d=>d.trim().replace(/\\D/g,'')).filter(d=>d.length>0);
  if (!dnis.length) {{ toast('No se encontraron DNIs válidos'); return; }}
  const res = document.getElementById('results');
  res.innerHTML = `<div class="loading"><div class="spinner"></div><p>Buscando ${{dnis.length}} DNI${{dnis.length>1?'s':''}}...</p></div>`;
  setTimeout(() => {{
    const todos = dnis.flatMap(d => (idx[d]||[]));
    if (!todos.length) {{
      res.innerHTML = `<div class="empty-state">
        <div class="empty-icon">🔍</div>
        <div class="empty-title">Sin resultados</div>
        <div class="empty-sub">Ninguno de los DNIs figura en los listados cargados.</div>
      </div>`; return;
    }}
    const dnisEnc = [...new Set(todos.map(r=>r.d))];
    const porCargo = {{}};
    todos.forEach(r => {{ if(!porCargo[r.c]) porCargo[r.c]=[]; porCargo[r.c].push(r); }});
    Object.values(porCargo).forEach(arr => arr.sort((a,b)=>(a.o||0)-(b.o||0)));

    let html = `<div class="totales">
      <div class="tot-item"><div class="tot-val">${{dnisEnc.length}}</div><div class="tot-lbl">Docentes</div></div>
      <div class="tot-item"><div class="tot-val">${{Object.keys(porCargo).length}}</div><div class="tot-lbl">Cargos</div></div>
    </div>`;
    for (const cargo of Object.keys(porCargo).sort()) {{
      const docs = porCargo[cargo];
      html += `<div class="m-cargo-card">
        <div class="m-cargo-title">
          <div class="m-cargo-name">${{cargo}}</div>
          <div class="m-cargo-sub">${{docs.length}} de ${{dnis.length}} encontrado${{docs.length>1?'s':''}}</div>
        </div>`;
      docs.forEach((r,i) => {{
        html += `<div class="m-doc-row${{i===0?' ganador':''}}">
          <div class="m-pos">${{r.o}}</div>
          <div>
            <div class="m-nombre">${{r.n||''}}</div>
            <div class="m-dni-lbl">DNI: ${{fmtDNI(r.d)}} · de ${{r.tot}} · ${{fmtSrc(r.src)}}</div>
            ${{i===0?'<span class="ganador-badge">✓ Mejor</span>':''}}
          </div>
          <div class="m-pje-val">${{r.P||'—'}}</div>
        </div>`;
      }});
      html += '</div>';
    }}
    res.innerHTML = html;
  }}, 50);
}}

function dsgl(lbl, val) {{
  return `<div class="dsgl-item"><div class="dsgl-lbl">${{lbl}}</div><div class="dsgl-val">${{val}}</div></div>`;
}}
function fmtSrc(src) {{
  if (!src) return '';
  return src.replace(/\\.pdf$/i, '').replace(/[-_]+/g, ' ').trim();
}}
function fmtDNI(d) {{ return (d||'').replace(/\\B(?=(\\d{{3}})+(?!\\d))/g,'.'); }}
function toast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}}
</script>
</body>
</html>'''

    return html


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    pdfs = sorted(glob.glob(os.path.join(PDFS_DIR, '*.pdf')))

    column_map = cargar_column_map()
    usados = set(column_map.values())

    todos = []
    fuentes = []

    if not pdfs:
        print("⚠️  No hay PDFs en /pdfs todavía. Genero un buscador vacío.")
    else:
        for pdf_path in pdfs:
            registros = extraer_pdf(pdf_path, column_map, usados)
            todos.extend(registros)
            fuentes.append(os.path.basename(pdf_path))

    guardar_column_map(column_map)

    cargos = sorted(set(r['c'] for r in todos))
    print(f"\n✅ Total combinado: {len(todos)} registros · {len(cargos)} cargos · {len(pdfs)} PDF(s) fuente")

    html = generar_html(todos, fuentes, column_map)
    out_path = os.path.join(OUT_DIR, 'index.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"🏗  {out_path} generado ({size_mb:.2f} MB)")


if __name__ == '__main__':
    main()
