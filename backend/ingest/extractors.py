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


def extraer_documento(ruta: str | Path) -> DocumentoExtraido:
    ruta = Path(ruta)
    sufijo = ruta.suffix.lower()
    if sufijo == ".pdf":
        return _extraer_pdf(ruta)
    if sufijo == ".docx":
        return _extraer_docx(ruta)
    raise ValueError(f"Formato no soportado: {sufijo!r}. Se aceptan .pdf y .docx")


def _extraer_pdf(ruta: Path) -> DocumentoExtraido:
    import fitz  # PyMuPDF

    paginas: list[Pagina] = []
    with fitz.open(ruta) as pdf:
        for i, pagina in enumerate(pdf, start=1):
            paginas.append(Pagina(numero=i, texto=pagina.get_text("text")))
    if not any(p.texto.strip() for p in paginas):
        raise ValueError(
            f"{ruta.name}: el PDF no contiene texto extraíble (¿es un escaneo sin OCR?)."
        )
    return DocumentoExtraido(nombre=ruta.name, tipo="pdf", paginas=paginas, paginacion_real=True)


def _extraer_docx(ruta: Path) -> DocumentoExtraido:
    """Extrae párrafos y tablas EN ORDEN del cuerpo del documento.

    Las tablas importan: la operacionalización de variables y la matriz de
    consistencia suelen estar en tablas; cada fila se aplana con ' | '.
    """
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    documento = docx.Document(str(ruta))
    bloques: list[str] = []
    for elemento in documento.element.body.iterchildren():
        if elemento.tag.endswith("}p"):
            texto = Paragraph(elemento, documento).text
            if texto.strip():
                bloques.append(texto)
        elif elemento.tag.endswith("}tbl"):
            tabla = Table(elemento, documento)
            for fila in tabla.rows:
                celdas = [celda.text.strip() for celda in fila.cells]
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
