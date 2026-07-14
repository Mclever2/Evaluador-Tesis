"""Test obligatorio del plan: sobre una carátula de ejemplo, el anonimizador
elimina nombres de autores, DNI, ORCID, correo y nombre del asesor."""

from __future__ import annotations

from anonymizer.anonymizer import anonimizar
from ingest.extractors import DocumentoExtraido, Pagina

CARATULA = """UNIVERSIDAD PRIVADA ANTENOR ORREGO
FACULTAD DE INGENIERÍA
ESCUELA PROFESIONAL DE INGENIERÍA DE SISTEMAS

PROYECTO DE TESIS PARA OBTENER EL TÍTULO PROFESIONAL DE INGENIERO DE SISTEMAS

Sistema web para la gestión de inventarios en una pyme de Trujillo, 2026

AUTORES:
Bach. GARCÍA LÓPEZ, MARÍA FERNANDA  DNI: 71234567  ORCID: 0000-0002-1234-5678
Bach. Torres Quispe, José Luis  DNI 74561234

ASESOR:
Dr. Ramírez Salazar, Pedro Antonio
ORCID: orcid.org/0000-0001-9876-5432

Contacto: maria.garcia@upao.edu.pe
Celular: +51 974 922 918
Celular: 993763267
TRUJILLO - PERÚ
2026
"""

CUERPO = """1. TÍTULO DEL PROYECTO
Como señala el presente proyecto elaborado por María Fernanda García López y
José Luis Torres Quispe bajo la asesoría de Pedro Antonio Ramírez Salazar,
el objetivo es medir el efecto del sistema web sobre la gestión de inventarios.
Según Hernández-Sampieri (2018), el planteamiento debe ser preciso.
"""


def _doc() -> DocumentoExtraido:
    return DocumentoExtraido(
        nombre="proyecto_prueba.pdf",
        tipo="pdf",
        paginas=[Pagina(numero=1, texto=CARATULA), Pagina(numero=2, texto=CUERPO)],
        paginacion_real=True,
    )


class TestAnonimizador:
    def test_elimina_todos_los_datos_identificatorios(self):
        anonimo, _, _ = anonimizar(_doc())
        texto = anonimo.texto_completo
        for dato in [
            "GARCÍA LÓPEZ", "MARÍA FERNANDA", "Torres Quispe", "José Luis",
            "Ramírez Salazar", "Pedro Antonio",
            "71234567", "74561234",
            "0000-0002-1234-5678", "0000-0001-9876-5432",
            "maria.garcia@upao.edu.pe",
            "974 922 918", "993763267",
        ]:
            assert dato not in texto, f"quedó expuesto: {dato}"

    def test_enmascara_tambien_las_menciones_del_cuerpo(self):
        """Los nombres en orden 'Nombres Apellidos' del cuerpo también se enmascaran."""
        anonimo, _, _ = anonimizar(_doc())
        cuerpo = anonimo.paginas[1].texto
        assert "María Fernanda" not in cuerpo
        assert "[AUTOR_1]" in cuerpo
        assert "[ASESOR_1]" in cuerpo
        # Las citas académicas no se tocan
        assert "Hernández-Sampieri (2018)" in cuerpo

    def test_mapeo_local_correcto(self):
        _, _, mapeo = anonimizar(_doc())
        assert mapeo["[AUTOR_1]"] == "GARCÍA LÓPEZ, MARÍA FERNANDA"
        assert mapeo["[AUTOR_2]"] == "Torres Quispe, José Luis"
        assert mapeo["[ASESOR_1]"] == "Ramírez Salazar, Pedro Antonio"
        assert "71234567" in mapeo.values()
        assert "maria.garcia@upao.edu.pe" in mapeo.values()

    def test_reporte_cuenta_reemplazos(self):
        _, reporte, _ = anonimizar(_doc())
        assert reporte.reemplazos["autor"] >= 2
        assert reporte.reemplazos["asesor"] >= 1
        assert reporte.reemplazos["dni"] == 2
        assert reporte.reemplazos["orcid"] == 2
        assert reporte.reemplazos["correo"] == 1
        assert reporte.reemplazos["telefono"] == 2
        assert reporte.advertencias == []

    def test_advierte_si_no_detecta_autores(self):
        doc = DocumentoExtraido(
            nombre="x.pdf",
            tipo="pdf",
            paginas=[Pagina(numero=1, texto="PROYECTO DE TESIS\nSin datos de autoría\n")],
            paginacion_real=True,
        )
        _, reporte, mapeo = anonimizar(doc)
        assert mapeo == {}
        assert any("autores" in a.lower() for a in reporte.advertencias)
