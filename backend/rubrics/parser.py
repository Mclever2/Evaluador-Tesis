"""Parser de las rúbricas fuente (docs/) a JSON versionado (backend/rubrics/).

Fuentes:
- docs/rubrica_especifica.md → especifica_v1 (15 secciones, 100 puntos,
  3 niveles por ítem con el valor de "parcial" literal de la tabla).
- docs/ficha_upao.md → ficha_upao_v1 (33 ítems, escala 0-3, bloques y tabla
  de conversión vigesimal). PENDIENTE: el archivo aún no fue entregado por el
  autor; este parser NO inventa ítems.

El parser valida la estructura y devuelve advertencias (p. ej. si la suma de
pesos de una sección no coincide con el máximo declarado) sin corregir la
fuente por su cuenta: la rúbrica es un instrumento de medición y sus valores
se respetan tal cual.
"""

from __future__ import annotations

import re
import unicodedata

from rubrics.models import ItemRubrica, NivelCalidad, Rubrica, SeccionRubrica

# ── Expresiones de la rúbrica específica ─────────────────────────────────────
# Encabezado de sección: **1\. Título del proyecto de tesis \[Máximo: 5 pts\]**
_HEADER_RE = re.compile(
    r"^\*\*(\d{1,2})\\?\.\s*(.+?)\s*\\?\[M[áa]ximo:\s*(\d+)\s*pts?\\?\.?\]\*\*\s*$"
)
# Línea de referencia: _Referencia: Hernández-Sampieri (2018), Cap. 2, pp. 35-36; ..._
_REF_RE = re.compile(r"^_Referencia:\s*(.+?)_\s*$")
_ITEM_ID_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})$")
_RANGO_RE = re.compile(r"^(\d+)\s*-\s*(\d+)$")
_MENOR_RE = re.compile(r"^Menor\s+a\s+(\d+)$", re.IGNORECASE)
_SUBTOTAL_NUM_RE = re.compile(r"\*\*(\d+(?:\.\d+)?)\*\*")

# Encabezados alternativos por sección (normalizados: minúsculas, sin tildes).
# Son ayuda de segmentación para localizar la sección en los proyectos reales;
# no forman parte del contenido del instrumento.
_ALIASES: dict[int, list[str]] = {
    1: ["titulo", "titulo del proyecto", "titulo tentativo", "titulo de la investigacion"],
    2: [
        "descripcion del problema",
        "delimitacion del problema",
        "descripcion y delimitacion del problema",
        "realidad problematica",
        "descripcion de la realidad problematica",
        "planteamiento del problema",
    ],
    3: [
        "formulacion del problema",
        "enunciado del problema",
        "pregunta de investigacion",
        "problema general",
        "problema central del estudio",
        "problema central",
    ],
    4: ["objetivos", "objetivos de la investigacion", "objetivo general", "objetivos especificos"],
    5: [
        "justificacion",
        "importancia y justificacion",
        "justificacion del estudio",
        "justificacion de la investigacion",
        "importancia del estudio",
    ],
    6: ["limitaciones", "limitaciones del estudio", "alcances y limitaciones", "viabilidad"],
    7: [
        "marco teorico",
        "antecedentes",
        "antecedentes de la investigacion",
        "bases teoricas",
        "marco referencial",
        "fundamentacion teorica",
        "definicion de terminos",
    ],
    8: [
        "hipotesis",
        "hipotesis y variables",
        "hipotesis general",
        "hipotesis especificas",
        "formulacion de la hipotesis",
        "supuestos basicos",
    ],
    9: [
        "variables",
        "operacionalizacion de variables",
        "operacionalizacion",
        "variables y operacionalizacion",
        "definicion y operacionalizacion de variables",
    ],
    10: ["matriz de consistencia"],
    11: [
        "tipo y metodo de investigacion",
        "tipo de investigacion",
        "metodo de investigacion",
        "enfoque de investigacion",
        "tipo y nivel de investigacion",
    ],
    12: [
        "diseño del estudio",
        "diseño de investigacion",
        "diseño de la investigacion",
        "diseño de contrastacion",
        "diseño metodologico",
    ],
    13: ["poblacion y muestra", "poblacion", "muestra", "muestreo", "unidad de analisis"],
    14: [
        "tecnicas e instrumentos de recoleccion de datos",
        "tecnicas e instrumentos",
        "instrumentos de recoleccion de datos",
        "tecnicas de recoleccion de datos",
        "recoleccion de datos",
    ],
    15: [
        "tecnicas de procesamiento y analisis de datos",
        "procesamiento y analisis de datos",
        "analisis de datos",
        "tratamiento y analisis de datos",
        "tecnicas de analisis de datos",
    ],
}


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar encabezados."""
    descompuesto = unicodedata.normalize("NFD", texto.lower().strip())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _unescape(texto: str) -> str:
    """Quita los escapes de markdown (\\. \\[ \\] etc.) del texto exportado."""
    return re.sub(r"\\([\\.\[\]()\-_*])", r"\1", texto).strip()


def _celdas(linea: str) -> list[str]:
    return [c.strip() for c in linea.strip().strip("|").split("|")]


def _condensar_referencia(cruda: str) -> str:
    """'Hernández-Sampieri (2018), Cap. 2, pp. 35-36; criterios…' → 'HS2018 Cap. 2, pp. 35-36'."""
    texto = re.sub(r"Hern[áa]ndez-Sampieri\s*\(2018\),?", "HS2018", cruda).strip()
    partes = [p.strip() for p in texto.split(";")]
    utiles = [partes[0]] + [p for p in partes[1:] if "Cap." in p or "pp." in p]
    return "; ".join(utiles).replace("HS2018 ,", "HS2018").strip()


def parse_especifica(md: str) -> tuple[Rubrica, list[str]]:
    """Convierte docs/rubrica_especifica.md al esquema JSON de especifica_v1.

    Devuelve (rubrica, advertencias). Las advertencias señalan inconsistencias
    de la fuente que el autor del instrumento debe resolver; el parser nunca
    altera pesos ni criterios.
    """
    advertencias: list[str] = []
    secciones: list[SeccionRubrica] = []

    num_actual: int | None = None
    nombre_actual = ""
    max_actual = 0.0
    referencia_actual: str | None = None
    items_actuales: list[ItemRubrica] = []

    def cerrar_seccion() -> None:
        nonlocal num_actual, items_actuales
        if num_actual is None:
            return
        seccion = SeccionRubrica(
            id=f"S{num_actual:02d}",
            nombre=nombre_actual,
            puntaje_max=max_actual,
            # Los aliases se guardan normalizados (minúsculas, sin tildes ni ñ)
            # porque el segmentador compara contra encabezados normalizados.
            aliases=[normalizar(a) for a in _ALIASES.get(num_actual, [nombre_actual])],
            items=items_actuales,
        )
        if not seccion.items:
            advertencias.append(f"{seccion.id}: no se encontraron ítems en la tabla.")
        elif seccion.suma_pesos() != round(max_actual, 2):
            advertencias.append(
                f"{seccion.id} ({nombre_actual}): los pesos de los ítems suman "
                f"{seccion.suma_pesos()} pero el máximo declarado es {max_actual:g}. "
                "Inconsistencia de la fuente; requiere decisión del autor."
            )
        secciones.append(seccion)
        num_actual = None
        items_actuales = []

    lineas = md.splitlines()
    for linea in lineas:
        encabezado = _HEADER_RE.match(linea.strip())
        if encabezado:
            cerrar_seccion()
            num_actual = int(encabezado.group(1))
            nombre_actual = _unescape(encabezado.group(2))
            max_actual = float(encabezado.group(3))
            referencia_actual = None
            continue

        ref = _REF_RE.match(linea.strip())
        if ref and num_actual is not None:
            referencia_actual = _condensar_referencia(_unescape(ref.group(1)))
            continue

        if num_actual is not None and linea.strip().startswith("|"):
            celdas = _celdas(linea)
            if len(celdas) >= 5 and _ITEM_ID_RE.match(celdas[0]):
                try:
                    peso = float(celdas[2])
                    parcial = float(celdas[4])
                except ValueError:
                    advertencias.append(
                        f"S{num_actual:02d}: fila de ítem {celdas[0]} con números ilegibles."
                    )
                    continue
                items_actuales.append(
                    ItemRubrica(
                        id=celdas[0],
                        criterio=_unescape(celdas[1]),
                        peso=peso,
                        parcial=parcial,
                        referencia=referencia_actual,
                    )
                )
            elif len(celdas) >= 3 and "SUBTOTAL" in celdas[1].upper():
                declarado = _SUBTOTAL_NUM_RE.search(celdas[2])
                if declarado and float(declarado.group(1)) != max_actual:
                    advertencias.append(
                        f"S{num_actual:02d}: el subtotal de la tabla "
                        f"({declarado.group(1)}) difiere del máximo del encabezado "
                        f"({max_actual:g})."
                    )
    cerrar_seccion()

    niveles = _parse_niveles(lineas)
    if len(niveles) != 4:
        advertencias.append(
            f"Se esperaban 4 niveles de calidad y se encontraron {len(niveles)}."
        )
    if len(secciones) != 15:
        advertencias.append(f"Se esperaban 15 secciones y se encontraron {len(secciones)}.")

    rubrica = Rubrica(
        id="especifica_v1",
        nombre="Rúbrica de calidad metodológica UPAO 2026",
        tipo="ponderada_3_niveles",
        escala={"cumple": 1.0, "parcial": 0.5, "no_cumple": 0.0},
        niveles_calidad=niveles,
        secciones=secciones,
    )
    return rubrica, advertencias


def _parse_niveles(lineas: list[str]) -> list[NivelCalidad]:
    """Tabla 'ESCALA DE INTERPRETACIÓN DEL PUNTAJE TOTAL' → bandas continuas.

    Los máximos intermedios se extienden a X.99 (p. ej. 75-89 → 75-89.99) para
    que los totales fraccionarios (los parciales producen decimales) siempre
    caigan en una banda.
    """
    en_escala = False
    crudos: list[tuple[float, float | None, str, str]] = []
    for linea in lineas:
        if "ESCALA DE INTERPRETACI" in linea.upper():
            en_escala = True
            continue
        if not en_escala or not linea.strip().startswith("|"):
            continue
        celdas = _celdas(linea)
        if len(celdas) < 3 or celdas[0].startswith("-") or "Rango" in celdas[0]:
            continue
        rango = _unescape(celdas[0]).replace("**", "").strip()
        etiqueta = _unescape(celdas[1]).split(" - ")[0].strip()
        accion = _unescape(celdas[2])
        m = _RANGO_RE.match(rango)
        if m:
            crudos.append((float(m.group(1)), float(m.group(2)), etiqueta, accion))
            continue
        m = _MENOR_RE.match(rango)
        if m:
            crudos.append((0.0, None, etiqueta, accion))

    crudos.sort(key=lambda fila: fila[0], reverse=True)
    niveles: list[NivelCalidad] = []
    min_banda_superior: float | None = None
    for minimo, maximo, etiqueta, accion in crudos:
        if min_banda_superior is not None:
            maximo = round(min_banda_superior - 0.01, 2)
        niveles.append(NivelCalidad(min=minimo, max=maximo or 0.0, etiqueta=etiqueta, accion=accion))
        min_banda_superior = minimo
    return niveles


# ── Ficha UPAO ───────────────────────────────────────────────────────────────

FICHA_PENDIENTE_MSG = (
    "docs/ficha_upao.md no encontrado. La ficha institucional debe contener "
    "los 33 ítems literales en 7 bloques y la tabla de conversión vigesimal."
)

# Bloques esperados de la ficha (nombre normalizado → id y rango de ítems).
_BLOQUES_FICHA: list[tuple[str, str, tuple[int, int], list[str]]] = [
    ("B01", "Título", (1, 3),
     ["titulo", "titulo del proyecto", "titulo de la investigacion", "titulo tentativo"]),
    ("B02", "Planteamiento del problema", (4, 10),
     ["planteamiento del problema", "el problema", "problema de investigacion",
      "realidad problematica", "descripcion del problema", "plan de investigacion"]),
    ("B03", "Marco teórico", (11, 17),
     ["marco teorico", "antecedentes", "bases teoricas", "fundamentacion teorica",
      "marco referencial"]),
    ("B04", "Hipótesis y variables", (18, 21),
     ["hipotesis y variables", "hipotesis", "variables", "operacionalizacion de variables"]),
    ("B05", "Marco metodológico", (22, 27),
     ["marco metodologico", "metodologia", "material y metodos", "diseño metodologico",
      "metodologia de la investigacion", "materiales y metodos"]),
    ("B06", "Aspectos administrativos", (28, 31),
     ["aspectos administrativos", "cronograma", "presupuesto",
      "administracion del proyecto", "cronograma y presupuesto"]),
    ("B07", "Referencias bibliográficas", (32, 33),
     ["referencias bibliograficas", "referencias", "bibliografia"]),
]

_RE_BLOQUE = re.compile(r"^##\s+(.+?)\s*$")
_RE_ITEM_FICHA = re.compile(r"^(\d{1,2})$")
_RE_RANGO_NOTA = re.compile(r"^(\d{1,3})\s*-\s*(\d{1,3})$")
_RE_MENOR_NOTA = re.compile(r"^<\s*(\d{1,3})$")


def parse_ficha_upao(md: str) -> tuple[Rubrica, list[str]]:
    """Convierte docs/ficha_upao.md a ficha_upao_v1 (33 ítems, escala 0-3,
    bloques y tabla de conversión vigesimal). Verificación: 87 → nota 18."""
    from rubrics.models import ConversionVigesimal

    advertencias: list[str] = []
    items_por_bloque: dict[str, list[ItemRubrica]] = {}
    conversion: list[ConversionVigesimal] = []

    bloque_actual: str | None = None  # id del bloque (B01..B07) o "conversion"
    normalizados = {normalizar(nombre): bid for bid, nombre, _, _ in _BLOQUES_FICHA}

    for linea in md.splitlines():
        encabezado = _RE_BLOQUE.match(linea.strip())
        if encabezado:
            titulo_norm = normalizar(encabezado.group(1))
            if "conversion" in titulo_norm or "vigesimal" in titulo_norm:
                bloque_actual = "conversion"
            else:
                bloque_actual = normalizados.get(titulo_norm)
                if bloque_actual is None:
                    advertencias.append(f"Bloque no reconocido en la fuente: {encabezado.group(1)!r}")
            continue

        if bloque_actual is None or not linea.strip().startswith("|"):
            continue
        celdas = _celdas(linea)
        if len(celdas) < 2 or celdas[0].startswith("-"):
            continue

        if bloque_actual == "conversion":
            rango = _unescape(celdas[0])
            if rango.lower().startswith("puntaje"):
                continue
            try:
                nota = int(celdas[1])
            except ValueError:
                continue
            m = _RE_RANGO_NOTA.match(rango)
            if m:
                conversion.append(
                    ConversionVigesimal(min=int(m.group(1)), max=int(m.group(2)), nota=nota)
                )
                continue
            m = _RE_MENOR_NOTA.match(rango)
            if m:
                conversion.append(ConversionVigesimal(min=0, max=int(m.group(1)) - 1, nota=nota))
            continue

        m = _RE_ITEM_FICHA.match(celdas[0].lstrip("0") or "0")
        if m and not celdas[1].lower().startswith("ítem"):
            items_por_bloque.setdefault(bloque_actual, []).append(
                ItemRubrica(
                    id=str(int(celdas[0])),
                    criterio=_unescape(celdas[1]),
                    peso=3.0,  # máximo por ítem en la escala 0-3
                    parcial=None,
                )
            )

    secciones: list[SeccionRubrica] = []
    for bid, nombre, (desde, hasta), aliases in _BLOQUES_FICHA:
        items = items_por_bloque.get(bid, [])
        ids = [int(i.id) for i in items]
        if ids != list(range(desde, hasta + 1)):
            advertencias.append(
                f"{bid} ({nombre}): se esperaban los ítems {desde}-{hasta} y se "
                f"encontraron {ids or 'ninguno'}."
            )
        secciones.append(
            SeccionRubrica(
                id=bid,
                nombre=nombre,
                puntaje_max=3.0 * len(items),
                aliases=[normalizar(a) for a in aliases],
                items=items,
            )
        )

    if not conversion:
        advertencias.append("No se encontró la tabla de conversión a nota vigesimal.")

    rubrica = Rubrica(
        id="ficha_upao_v1",
        nombre="Ficha de evaluación de proyecto de tesis UPAO",
        tipo="escala_0_3",
        escala={"excelente": 3.0, "bueno": 2.0, "regular": 1.0, "insuficiente": 0.0},
        niveles_calidad=[],
        secciones=secciones,
        conversion_vigesimal=sorted(conversion, key=lambda c: c.min, reverse=True),
    )
    if rubrica.total_items != 33:
        advertencias.append(f"Se esperaban 33 ítems y se encontraron {rubrica.total_items}.")
    if rubrica.puntaje_maximo != 99:
        advertencias.append(f"El máximo debería ser 99 y es {rubrica.puntaje_maximo:g}.")
    return rubrica, advertencias
