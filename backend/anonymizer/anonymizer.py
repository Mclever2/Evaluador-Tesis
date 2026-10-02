"""Anonimización previa (doble ciego) de proyectos de tesis.

Antes de enviar cualquier texto a un LLM se eliminan o enmascaran los datos que
identifican a autores y asesor: nombres, DNI, correos y ORCID, detectados con
regex y heurísticas sobre la carátula/páginas preliminares y aplicados a todo
el documento (incluidos encabezados repetidos).

El mapeo placeholder → dato original se devuelve para guardarlo LOCALMENTE
(trazabilidad); NUNCA debe enviarse al LLM ni incluirse en los prompts.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from ingest.extractors import DocumentoExtraido, Pagina

# Cuántas páginas iniciales se tratan como carátula/preliminares para las
# heurísticas de nombres y para el DNI "suelto" (8 dígitos sin etiqueta).
_PAGINAS_CARATULA = 6

_RE_CORREO = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_RE_ORCID = re.compile(
    r"(?:https?://)?(?:www\.)?(?:orcid\.org/)?\b(\d{4}-\d{4}-\d{4}-\d{3}[\dXx])\b"
)
_RE_DNI_ETIQUETADO = re.compile(r"\bDNI\s*(?:N[°º.]?\s*)?:?\s*(\d{8})\b", re.IGNORECASE)
_RE_DNI_SUELTO = re.compile(r"\b(\d{8})\b")
# Celulares peruanos (9XXXXXXXX) con o sin +51 y separadores; solo en las
# páginas preliminares para no tocar cifras del cuerpo.
_RE_TELEFONO = re.compile(r"(?:\+?51[\s.\-]?)?\b9\d{2}[\s.\-]?\d{3}[\s.\-]?\d{3}\b")

# Honoríficos y roles con los que suele presentarse a autores y asesor.
_HONORIFICO = r"(?:Bach\.|Br\.|Bachiller|Tesista|Mg\.|Mag\.|MSc\.?|Dr\.|Dra\.|Ing\.|Lic\.)"
_RE_ROL_AUTOR = re.compile(r"^\s*AUTOR(?:ES|A|AS)?\s*:?\s*$", re.IGNORECASE)
_RE_ROL_ASESOR = re.compile(r"^\s*(?:CO-?)?ASESOR(?:ES|A|AS)?\s*:?\s*$", re.IGNORECASE)
_RE_ROL_INLINE = re.compile(
    rf"^\s*(AUTOR(?:ES|A|AS)?|(?:CO-?)?ASESOR(?:A)?)\s*:\s*(?:{_HONORIFICO}\s*)?(.+)$",
    re.IGNORECASE,
)
# Plantilla UPAO (sección GENERALIDADES): "Apellidos y nombres: Ponce Vásquez, McBreck"
_RE_APELLIDOS_NOMBRES = re.compile(
    r"^\s*apellidos?\s+y\s+nombres?\s*:?\s*(.+)$", re.IGNORECASE
)
_RE_HONORIFICO_LINEA = re.compile(rf"^\s*{_HONORIFICO}\s+(.+)$")

# Un nombre plausible: 2 a 6 palabras capitalizadas o en MAYÚSCULAS, admite
# comas ("APELLIDOS, Nombres") y partículas (de, del, la, los, y).
_PARTICULAS = {"de", "del", "la", "las", "los", "y", "e", "da", "dos"}
_RE_TOKEN_NOMBRE = re.compile(r"^[A-ZÁÉÍÓÚÑÜ][\wáéíóúñü'-]*$|^[A-ZÁÉÍÓÚÑÜ'-]{2,}$")


class ReporteAnonimizacion(BaseModel):
    """Resumen para el reporte de indexación (sin datos originales)."""

    reemplazos: dict[str, int] = Field(default_factory=dict)  # tipo → cantidad
    advertencias: list[str] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.reemplazos.values())


def _es_nombre_plausible(texto: str) -> bool:
    limpio = texto.strip().strip(".").replace(",", " ")
    tokens = [t for t in limpio.split() if t]
    if not 2 <= len(tokens) <= 6:
        return False
    significativos = 0
    for token in tokens:
        if token.lower() in _PARTICULAS:
            continue
        if not _RE_TOKEN_NOMBRE.match(token):
            return False
        significativos += 1
    return significativos >= 2


def _limpiar_candidato(texto: str) -> str:
    """Aísla el nombre quitando datos anexos (DNI, ORCID, correo) de la línea."""
    texto = _RE_DNI_ETIQUETADO.sub(" ", texto)
    texto = _RE_ORCID.sub(" ", texto)
    texto = _RE_CORREO.sub(" ", texto)
    # Etiquetas que quedan sueltas tras quitar el dato ("ORCID:", "DNI", "Código: 000123")
    texto = re.sub(r"\b(?:DNI|ORCID|C[óo]digo)\b\s*:?\s*[\w-]*", " ", texto, flags=re.IGNORECASE)
    texto = re.sub(rf"^{_HONORIFICO}\s+", "", texto.strip())
    return re.sub(r"\s{2,}", " ", texto).strip(" \t:;-.")


def _detectar_nombres(paginas: list[Pagina]) -> tuple[list[str], list[str]]:
    """Devuelve (autores, asesores) detectados en las páginas preliminares."""
    autores: list[str] = []
    asesores: list[str] = []
    for pagina in paginas[:_PAGINAS_CARATULA]:
        lineas = pagina.texto.splitlines()
        rol_pendiente: str | None = None
        # Último rol visto en la página: la plantilla UPAO intercala líneas de
        # datos ("Dirección:", "Email:") entre los "Apellidos y nombres:" de
        # cada autor, así que rol_pendiente ya se consumió cuando llega el
        # segundo autor.
        ultimo_rol: str | None = None
        for linea in lineas:
            plana = linea.strip()
            if not plana:
                continue

            # "AUTOR:" / "ASESOR:" en línea propia → los nombres vienen debajo
            if _RE_ROL_AUTOR.match(plana):
                rol_pendiente = ultimo_rol = "autor"
                continue
            if _RE_ROL_ASESOR.match(plana):
                rol_pendiente = ultimo_rol = "asesor"
                continue

            # "ASESOR: Dr. Nombre Apellido" en la misma línea
            rol_inline = _RE_ROL_INLINE.match(plana)
            if rol_inline:
                candidato = _limpiar_candidato(rol_inline.group(2))
                es_asesor = "ASESOR" in rol_inline.group(1).upper()
                destino = asesores if es_asesor else autores
                if _es_nombre_plausible(candidato) and candidato not in destino:
                    destino.append(candidato)
                rol_pendiente = None
                ultimo_rol = "asesor" if es_asesor else "autor"
                continue

            # "Apellidos y nombres: Ponce Vásquez, McBreck" (plantilla UPAO):
            # se asigna según el último rol visto (autor por defecto).
            apellidos_nombres = _RE_APELLIDOS_NOMBRES.match(plana)
            if apellidos_nombres:
                candidato = _limpiar_candidato(apellidos_nombres.group(1))
                if _es_nombre_plausible(candidato):
                    destino = asesores if ultimo_rol == "asesor" else autores
                    if candidato not in destino:
                        destino.append(candidato)
                continue

            # "Bach. APELLIDOS, Nombres" (honorífico al inicio de línea)
            honorifico = _RE_HONORIFICO_LINEA.match(plana)
            if honorifico:
                candidato = _limpiar_candidato(honorifico.group(1))
                es_asesor = bool(re.match(r"^\s*(Mg|Mag|MSc|Dr|Dra)\b", plana))
                destino = asesores if (rol_pendiente == "asesor" or (rol_pendiente is None and es_asesor)) else autores
                if _es_nombre_plausible(candidato) and candidato not in destino:
                    destino.append(candidato)
                continue

            # Línea inmediatamente después de un rol en línea propia
            if rol_pendiente:
                candidato = _limpiar_candidato(plana)
                if _es_nombre_plausible(candidato):
                    destino = autores if rol_pendiente == "autor" else asesores
                    if candidato not in destino:
                        destino.append(candidato)
                    continue  # puede haber varios nombres seguidos bajo el rol
                rol_pendiente = None
    return autores, asesores


def _variantes(nombre: str) -> list[str]:
    """Formas alternativas del mismo nombre para reemplazar en todo el texto:
    la forma detectada, sin coma, y la inversión 'APELLIDOS, Nombres' ⇄ 'Nombres Apellidos'."""
    variantes = {nombre}
    sin_espacios_dobles = re.sub(r"\s{2,}", " ", nombre)
    variantes.add(sin_espacios_dobles)
    if "," in nombre:
        apellidos, _, nombres = nombre.partition(",")
        variantes.add(f"{nombres.strip()} {apellidos.strip()}")
        variantes.add(f"{apellidos.strip()} {nombres.strip()}")
        variantes.add(sin_espacios_dobles.replace(",", ""))
    return sorted(variantes, key=len, reverse=True)


def anonimizar(doc: DocumentoExtraido) -> tuple[DocumentoExtraido, ReporteAnonimizacion, dict[str, str]]:
    """Anonimiza el documento completo.

    Devuelve (documento anonimizado, reporte, mapeo). El mapeo
    {placeholder: dato original} se guarda localmente y jamás viaja al LLM.
    """
    mapeo: dict[str, str] = {}
    conteos: dict[str, int] = {}
    advertencias: list[str] = []

    autores, asesores = _detectar_nombres(doc.paginas)

    reemplazos: list[tuple[str, str]] = []  # (texto original, placeholder)
    for i, nombre in enumerate(autores, start=1):
        placeholder = f"[AUTOR_{i}]"
        mapeo[placeholder] = nombre
        for variante in _variantes(nombre):
            reemplazos.append((variante, placeholder))
    for i, nombre in enumerate(asesores, start=1):
        placeholder = f"[ASESOR_{i}]"
        mapeo[placeholder] = nombre
        for variante in _variantes(nombre):
            reemplazos.append((variante, placeholder))

    def anonimizar_pagina(pagina: Pagina) -> Pagina:
        texto = pagina.texto

        for original, placeholder in reemplazos:
            # \s+ entre tokens: los PDF parten nombres con saltos de línea.
            patron = re.compile(
                r"[ \t\n]+".join(re.escape(token) for token in original.split()),
                re.IGNORECASE,
            )
            texto, n = patron.subn(placeholder, texto)
            if n:
                tipo = "autor" if placeholder.startswith("[AUTOR") else "asesor"
                conteos[tipo] = conteos.get(tipo, 0) + n

        def sustituir(regex: re.Pattern, tipo: str, prefijo: str, texto: str) -> str:
            def reemplazo(m: re.Match) -> str:
                valor = m.group(1) if m.groups() else m.group(0)
                existente = next((k for k, v in mapeo.items() if v == valor), None)
                if existente is None:
                    existente = f"[{prefijo}_{sum(1 for k in mapeo if k.startswith('[' + prefijo)) + 1}]"
                    mapeo[existente] = valor
                conteos[tipo] = conteos.get(tipo, 0) + 1
                return existente

            return regex.sub(reemplazo, texto)

        texto = sustituir(_RE_CORREO, "correo", "CORREO", texto)
        texto = sustituir(_RE_ORCID, "orcid", "ORCID", texto)
        texto = sustituir(_RE_DNI_ETIQUETADO, "dni", "DNI", texto)
        if pagina.numero <= _PAGINAS_CARATULA:
            # DNI sin etiqueta y celulares: solo en preliminares para no tocar
            # cifras del cuerpo del proyecto
            texto = sustituir(_RE_DNI_SUELTO, "dni", "DNI", texto)
            texto = sustituir(_RE_TELEFONO, "telefono", "TELEFONO", texto)
        return Pagina(numero=pagina.numero, texto=texto)

    paginas_anonimas = [anonimizar_pagina(p) for p in doc.paginas]

    if not autores:
        advertencias.append(
            "No se detectaron nombres de autores en la carátula; revisar manualmente "
            "la anonimización antes de evaluar (posible carátula sin anonimizar)."
        )
    if not asesores:
        advertencias.append("No se detectó el nombre del asesor en las páginas preliminares.")

    reporte = ReporteAnonimizacion(reemplazos=conteos, advertencias=advertencias)
    doc_anonimo = DocumentoExtraido(
        nombre=doc.nombre,
        tipo=doc.tipo,
        paginas=paginas_anonimas,
        paginacion_real=doc.paginacion_real,
    )
    return doc_anonimo, reporte, mapeo
