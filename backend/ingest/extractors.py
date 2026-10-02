"""Extracción de texto de proyectos de tesis (PDF con PyMuPDF, DOCX con python-docx).

La extracción conserva la paginación real en PDF. En DOCX no existe paginación
hasta renderizar, así que se construye una paginación aproximada por bloques de
palabras (`paginacion_real = False`) para que el reporte de indexación pueda
mostrar ubicaciones orientativas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

# Palabras por "página" aproximada al paginar un DOCX.
_PALABRAS_POR_PAGINA_DOCX = 350

# Caracteres de ancho cero / formato que la extracción arrastra desde plantillas
# (la numeración de listas de Google Docs/Word inserta U+200B tras el número).
# Rompen la detección de numeración del segmentador ("1.​ Título" no empata
# con "1. Título") y el emparejamiento de aliases ("​Importancia del
# estudio" no contiene " importancia del estudio "). El ZERO WIDTH SPACE ocupa el
# lugar de un espacio real (jamás parte una palabra en estos documentos), así que
# se sustituye por un espacio; el resto (juntadores, BOM, guion suave) va dentro
# de palabra y se elimina.
_ZWSP = chr(0x200B)  # ZERO WIDTH SPACE
_INVISIBLES_A_ELIMINAR = dict.fromkeys(
    [
        0x200C,  # ZERO WIDTH NON-JOINER
        0x200D,  # ZERO WIDTH JOINER
        0x2060,  # WORD JOINER
        0xFEFF,  # ZERO WIDTH NO-BREAK SPACE (BOM)
        0x00AD,  # SOFT HYPHEN
    ],
    None,
)


def _sanear(texto: str) -> str:
    """Normaliza caracteres invisibles de formato que confunden la segmentación."""
    return texto.replace(_ZWSP, " ").translate(_INVISIBLES_A_ELIMINAR)


class Pagina(BaseModel):
    numero: int  # 1-based
    texto: str


class DocumentoExtraido(BaseModel):
    nombre: str
    tipo: Literal["pdf", "docx"]
    paginas: list[Pagina]
    paginacion_real: bool

    @property
    def texto_completo(self) -> str:
        return "\n".join(p.texto for p in self.paginas)

    @property
    def total_palabras(self) -> int:
        return len(self.texto_completo.split())


def extraer_documento(ruta: str | Path, limpiar_plantilla: bool = True) -> DocumentoExtraido:
    """Extrae el texto. Por defecto quita el relleno y las instrucciones de la
    plantilla UPAO (ver ingest.plantilla): lo que no escribió el estudiante no
    es contenido evaluable."""
    ruta = Path(ruta)
    sufijo = ruta.suffix.lower()
    if sufijo == ".pdf":
        doc = _extraer_pdf(ruta)
    elif sufijo == ".docx":
        doc = _extraer_docx(ruta)
    else:
        raise ValueError(f"Formato no soportado: {sufijo!r}. Se aceptan .pdf y .docx")
    if limpiar_plantilla:
        from ingest.plantilla import limpiar_paginas

        textos, _ = limpiar_paginas([p.texto for p in doc.paginas])
        for pagina, texto in zip(doc.paginas, textos):
            pagina.texto = texto
    return doc


def _extraer_pdf(ruta: Path) -> DocumentoExtraido:
    import fitz  # PyMuPDF

    paginas: list[Pagina] = []
    with fitz.open(ruta) as pdf:
        for i, pagina in enumerate(pdf, start=1):
            paginas.append(Pagina(numero=i, texto=_sanear(pagina.get_text("text"))))
    if not any(p.texto.strip() for p in paginas):
        raise ValueError(
            f"{ruta.name}: el PDF no contiene texto extraíble (¿es un escaneo sin OCR?)."
        )
    return DocumentoExtraido(nombre=ruta.name, tipo="pdf", paginas=paginas, paginacion_real=True)


_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"


def _texto_parrafo_docx(elemento) -> str:
    """Texto de un párrafo incluyendo runs dentro de w:sdt e hipervínculos.

    `Paragraph.text` de python-docx omite los controles de contenido (w:sdt)
    con los que las plantillas UPAO marcan campos de la carátula: se perdían
    "Autores:", "Asesor:", el nombre del programa, etc., y con ellos la
    detección de nombres del anonimizador. Se omite mc:Fallback para no
    duplicar dibujos con representación alternativa."""
    partes: list[str] = []

    def caminar(nodo) -> None:
        for hijo in nodo:
            if hijo.tag == _MC_FALLBACK:
                continue
            if hijo.tag == _W_NS + "t":
                partes.append(hijo.text or "")
            elif hijo.tag == _W_NS + "tab":
                partes.append("\t")
            elif hijo.tag in (_W_NS + "br", _W_NS + "cr"):
                partes.append("\n")
            else:
                caminar(hijo)

    caminar(elemento)
    return _sanear("".join(partes))


def _texto_celda_docx(tc) -> str:
    """Texto de una celda: sus párrafos (a cualquier profundidad) unidos con \\n."""
    return "\n".join(
        _texto_parrafo_docx(p) for p in tc.findall(".//" + _W_NS + "p")
    ).strip()


def _extraer_docx(ruta: Path) -> DocumentoExtraido:
    """Extrae párrafos y tablas EN ORDEN del cuerpo del documento.

    Las tablas importan: la operacionalización de variables y la matriz de
    consistencia suelen estar en tablas; cada fila se aplana con ' | '.
    Los bloques w:sdt a nivel de cuerpo (típicamente la tabla de contenido
    generada por Word) se omiten a propósito: sus entradas duplicarían los
    encabezados reales y confundirían al segmentador.
    """
    import docx
    from docx.table import Table

    documento = docx.Document(str(ruta))
    bloques: list[str] = []
    for elemento in documento.element.body.iterchildren():
        if elemento.tag.endswith("}p"):
            texto = _texto_parrafo_docx(elemento)
            if texto.strip():
                bloques.append(texto)
        elif elemento.tag.endswith("}tbl"):
            tabla = Table(elemento, documento)
            for fila in tabla.rows:
                celdas = [_texto_celda_docx(celda._element) for celda in fila.cells]
                if any(celdas):
                    bloques.append(" | ".join(celdas))

    # Paginación aproximada por bloques de ~350 palabras.
    paginas: list[Pagina] = []
    actual: list[str] = []
    palabras = 0
    for bloque in bloques:
        actual.append(bloque)
        palabras += len(bloque.split())
        if palabras >= _PALABRAS_POR_PAGINA_DOCX:
            paginas.append(Pagina(numero=len(paginas) + 1, texto="\n".join(actual)))
            actual, palabras = [], 0
    if actual:
        paginas.append(Pagina(numero=len(paginas) + 1, texto="\n".join(actual)))
    if not paginas:
        raise ValueError(f"{ruta.name}: el DOCX no contiene texto.")
    return DocumentoExtraido(nombre=ruta.name, tipo="docx", paginas=paginas, paginacion_real=False)
