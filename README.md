# Buscador de Listados — CPE Santa Cruz

Buscador por DNI de listados docentes, armado a partir de PDFs oficiales.
Cada vez que sale un listado nuevo (por ejemplo un complementario), lo
subís a la carpeta `/pdfs` en GitHub y el sitio se actualiza solo —
no hace falta correr nada en tu PC.

## Cómo funciona

- Los PDFs viven en la carpeta `/pdfs` de este repo.
- Cuando hacés un cambio en GitHub (subís, borrás o reemplazás un PDF),
  Netlify detecta el push y reconstruye el sitio automáticamente.
- Durante esa construcción, `build.py` abre **todos** los PDFs de
  `/pdfs`, extrae los datos de cada uno (con `pdfplumber`) y genera un
  único archivo `public/index.html` que junta la información de todos
  los listados. Ese archivo es el sitio que se publica.
- Los DNI se buscan en el conjunto combinado de todos los listados: si
  una persona aparece en el listado original y también en un
  complementario, el buscador va a mostrar las dos tarjetas (una por
  cada listado), cada una con su posición y su total correctos —
  aunque el nombre del cargo sea el mismo en los dos.

## Subir un listado nuevo (uso normal, de acá en adelante)

1. Entrá al repo en GitHub y abrí la carpeta `pdfs`.
2. `Add file` → `Upload files` → arrastrá el PDF nuevo (cualquier
   nombre de archivo sirve) → `Commit changes` directo en `main`.
3. Esperá 1-2 minutos. Netlify reconstruye el sitio solo. Podés ver el
   progreso en el panel de Netlify, pestaña **Deploys**.
4. Listo — el buscador ya incluye el listado nuevo, sumado a los que
   ya estaban.

Si un listado queda obsoleto y no querés que aparezca más, borrá ese
PDF de la carpeta `pdfs` (también desde GitHub) y hacé commit; en el
próximo build deja de contarse.

## Configuración inicial (una sola vez)

1. **Crear el repositorio en GitHub** (si todavía no existe) y subir
   todo el contenido de esta carpeta, incluyendo el/los PDF que ya
   tenías (el que usaste para generar tu `buscador_mobile.html`) dentro
   de `/pdfs`.
2. **Conectar el repo a Netlify**:
   - En Netlify: `Add new site` → `Import an existing project` →
     elegí GitHub y el repositorio.
   - Netlify va a detectar el archivo `netlify.toml` de este proyecto
     y va a completar solo el comando de build (`pip install -r
     requirements.txt && python build.py`) y la carpeta a publicar
     (`public`). No hace falta tocar nada ahí.
   - Confirmá y esperá el primer deploy.
3. Ya con eso, el sitio queda con una URL de Netlify (se puede cambiar
   el subdominio o conectar un dominio propio después, como hiciste
   con `escuelasrg.netlify.app`).

## Sobre las columnas (Título, Antigüedad, etc.)

Cada PDF tiene columnas de puntaje (Título, Antigüedad, Concepto,
etc.). La primera vez que el sistema ve una columna nueva le asigna
una sigla corta automáticamente (por ejemplo "Antigüedad Título" →
`AT`) y la guarda en `column_map.json`, que queda versionado en el
repo. Los listados siguientes que tengan esa misma columna van a
reusar la misma sigla, así que el buscador se mantiene consistente
listado tras listado. Si alguna sigla te queda fea o poco clara,
podés editarla a mano en `column_map.json` (el valor es solo una
etiqueta visual, no afecta la búsqueda).

## Probarlo en tu PC antes de subir (opcional)

```bash
pip install -r requirements.txt
python build.py
```

Esto genera `public/index.html`. Abrilo con el navegador para
revisarlo antes de confiar en que Netlify lo va a construir bien.

## Estructura del repo

```
├── build.py            # se corre solo, en cada build de Netlify
├── requirements.txt     # dependencias de Python (pdfplumber)
├── netlify.toml         # comando de build y carpeta a publicar
├── column_map.json       # siglas de columnas ya aprendidas (se actualiza solo)
├── pdfs/                 # ahí van los PDF de los listados
└── public/               # salida generada — no se sube a git
```
