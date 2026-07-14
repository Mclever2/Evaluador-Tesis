"""Biblioteca metodológica opcional (RAG de apoyo).

Ingesta de PDFs de libros de metodología a ChromaDB con embeddings
`intfloat/multilingual-e5-small`. En la evaluación, cada juez puede recibir 1
o 2 pasajes normativos por sección como contexto de criterio: el pasaje JAMÁS
modifica puntajes; solo enriquece la justificación.

Si no hay libros ingresados (o faltan las dependencias pesadas), el sistema
funciona igual sin RAG: `crear_contexto_rag()` devuelve None.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from app.config import get_settings
from rubrics import load_rubric

_COLECCION = "biblioteca_metodologica"
_CHUNK_CHARS = 900
_TOP_K = 2

# e5 exige prefijos "passage: " / "query: " para indexar y consultar.
_PREFIJO_PASAJE = "passage: "
_PREFIJO_CONSULTA = "query: "


def _cliente_y_modelo():
    """Lazy import: chromadb + sentence-transformers solo si se usan."""
    import chromadb
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    cliente = chromadb.PersistentClient(path=str(settings.chroma_dir))
    modelo = SentenceTransformer(settings.embed_model)
    return cliente, modelo


def _fragmentar(texto: str) -> list[str]:
    parrafos = [p.strip() for p in texto.split("\n") if p.strip()]
    fragmentos: list[str] = []
    actual = ""
    for parrafo in parrafos:
        if len(actual) + len(parrafo) > _CHUNK_CHARS and actual:
            fragmentos.append(actual.strip())
            actual = ""
        actual += " " + parrafo
    if actual.strip():
        fragmentos.append(actual.strip())
    return [f for f in fragmentos if len(f) > 120]


def ingestar_pdf(ruta: str | Path) -> int:
    """Ingresa un libro (PDF) a la biblioteca. Devuelve fragmentos indexados."""
    import fitz

    ruta = Path(ruta)
    cliente, modelo = _cliente_y_modelo()
    coleccion = cliente.get_or_create_collection(_COLECCION, metadata={"hnsw:space": "cosine"})

    documentos: list[str] = []
    metadatos: list[dict] = []
    ids: list[str] = []
    with fitz.open(ruta) as pdf:
        for num_pagina, pagina in enumerate(pdf, start=1):
            for i, fragmento in enumerate(_fragmentar(pagina.get_text("text"))):
                documentos.append(fragmento)
                metadatos.append({"libro": ruta.stem, "pagina": num_pagina})
                ids.append(f"{ruta.stem}_p{num_pagina}_{i}")

    if not documentos:
        return 0
    lote = 128
    for inicio in range(0, len(documentos), lote):
        docs = documentos[inicio : inicio + lote]
        embeddings = modelo.encode([_PREFIJO_PASAJE + d for d in docs], normalize_embeddings=True)
        coleccion.upsert(
            ids=ids[inicio : inicio + lote],
            documents=docs,
            metadatas=metadatos[inicio : inicio + lote],
            embeddings=embeddings.tolist(),
        )
    return len(documentos)


def libros_ingresados() -> list[dict]:
    try:
        import chromadb

        settings = get_settings()
        cliente = chromadb.PersistentClient(path=str(settings.chroma_dir))
        coleccion = cliente.get_collection(_COLECCION)
        datos = coleccion.get(include=["metadatas"])
        conteo: dict[str, int] = {}
        for metadato in datos["metadatas"]:
            conteo[metadato["libro"]] = conteo.get(metadato["libro"], 0) + 1
        return [{"libro": nombre, "fragmentos": n} for nombre, n in sorted(conteo.items())]
    except Exception:
        return []


def crear_contexto_rag(rubric_id: str = "especifica_v1") -> Optional[Callable[[str], list[str]]]:
    """Devuelve seccion_id → pasajes formateados, o None si no hay biblioteca."""
    try:
        # Primero verificar que exista una colección con contenido; el modelo
        # de embeddings (descarga y carga pesadas) solo se carga si hace falta.
        import chromadb

        settings = get_settings()
        cliente = chromadb.PersistentClient(path=str(settings.chroma_dir))
        coleccion = cliente.get_collection(_COLECCION)
        if coleccion.count() == 0:
            return None
        from sentence_transformers import SentenceTransformer

        modelo = SentenceTransformer(settings.embed_model)
    except Exception:
        return None

    rubrica = load_rubric(rubric_id)
    consultas = {
        s.id: f"{s.nombre}. Criterios: " + " ".join(i.criterio for i in s.items[:4])
        for s in rubrica.secciones
    }
    cache: dict[str, list[str]] = {}

    def contexto(seccion_id: str) -> list[str]:
        if seccion_id in cache:
            return cache[seccion_id]
        consulta = consultas.get(seccion_id)
        if not consulta:
            return []
        embedding = modelo.encode([_PREFIJO_CONSULTA + consulta], normalize_embeddings=True)
        res = coleccion.query(query_embeddings=embedding.tolist(), n_results=_TOP_K)
        pasajes = [
            f"«{doc[:400]}» ({meta['libro']}, pág. {meta['pagina']})"
            for doc, meta in zip(res["documents"][0], res["metadatas"][0])
        ]
        cache[seccion_id] = pasajes
        return pasajes

    return contexto
