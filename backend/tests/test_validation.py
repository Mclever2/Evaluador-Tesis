"""Tests de la validación psicométrica: QWK con fixtures de valor conocido,
acuerdos, ICC, Landis-Koch y el pipeline completo de cli.validate sobre datos
sintéticos. Sin llamadas a OpenAI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli.validate import (
    acuerdo_interno_panel,
    generar_reporte,
    linea_base_humana,
    mediana_jurados,
    sistema_contra_humanos,
)
from metrics.psychometrics import (
    acuerdo_adyacente,
    acuerdo_exacto,
    icc21,
    interpretar_kappa,
    kappa_promedio_pares,
    mae,
    qwk,
)


class TestQWK:
    def test_acuerdo_perfecto_es_1(self):
        assert qwk([0, 1, 2, 3, 2, 1], [0, 1, 2, 3, 2, 1], [0, 1, 2, 3]) == pytest.approx(1.0)

    def test_fixture_con_valor_conocido_menos_1(self):
        """Caso calculable a mano: a=[0,3], b=[3,0] con pesos cuadráticos.

        O = desacuerdo máximo en ambas celdas extremas; E reparte 0.5 en cada
        celda → QWK = 1 - 18/9 = -1.0 exacto.
        """
        assert qwk([0, 3], [3, 0], [0, 1, 2, 3]) == pytest.approx(-1.0)

    def test_fixture_binario_equivale_a_kappa_simple(self):
        """Con 2 categorías el QWK coincide con kappa de Cohen: po=pe → 0."""
        assert qwk([0, 0, 1, 1], [0, 1, 0, 1], [0, 1, 2, 3]) == pytest.approx(0.0)

    def test_castiga_mas_los_desacuerdos_lejanos(self):
        cercano = qwk([0, 1, 2, 3] * 5, [1, 2, 3, 3] * 5, [0, 1, 2, 3])
        lejano = qwk([0, 1, 2, 3] * 5, [3, 3, 0, 0] * 5, [0, 1, 2, 3])
        assert cercano > lejano


class TestAcuerdosYErrores:
    def test_acuerdo_exacto_y_adyacente(self):
        a, b = [0, 1, 2, 3], [1, 2, 3, 3]
        assert acuerdo_exacto(a, b) == 0.25
        assert acuerdo_adyacente(a, b) == 1.0

    def test_mae(self):
        assert mae([80.0, 90.0], [85.0, 88.0]) == pytest.approx(3.5)

    def test_icc21_alta_con_raters_casi_identicos(self):
        # Ruido variable (no un desplazamiento constante) para que la varianza
        # residual sea > 0 y el ICC(2,1) esté bien definido.
        totales = {
            "raterA": {f"p{i}": float(10 * i) for i in range(1, 7)},
            "raterB": {f"p{i}": float(10 * i + (i % 3)) for i in range(1, 7)},
        }
        assert icc21(totales) > 0.95

    @pytest.mark.parametrize(
        "valor, banda",
        [(0.05, "leve"), (0.3, "aceptable"), (0.5, "moderado"), (0.7, "sustancial"),
         (0.9, "casi perfecto"), (-0.2, "pobre (peor que el azar)")],
    )
    def test_landis_koch(self, valor, banda):
        assert interpretar_kappa(valor) == banda

    def test_kappa_promedio_pares(self):
        series = {"j1": [0, 1, 2, 3], "j2": [0, 1, 2, 3], "j3": [3, 2, 1, 0]}
        resultado = kappa_promedio_pares(series, [0, 1, 2, 3])
        assert resultado["j1|j2"] == pytest.approx(1.0)
        assert resultado["j1|j3"] == pytest.approx(-1.0)
        assert resultado["promedio"] == pytest.approx((1.0 - 1.0 - 1.0) / 3)


# ── Datos sintéticos del modo concordancia (ficha 0-3, 4 ítems, 4 proyectos) ──

ITEMS = ["1", "2", "3", "4"]


def _resultado_sistema(proyecto: str, puntajes: dict[str, int]) -> dict:
    return {
        "project_id": proyecto,
        "rubric_id": "ficha_upao_v1",
        "total": float(sum(puntajes.values())),
        "secciones": [
            {
                "id": "B01",
                "items": [
                    {
                        "id": item,
                        "nivel_final": puntaje,
                        "puntaje": float(puntaje),
                        "niveles_jueces": {"juez1": puntaje, "juez2": puntaje, "juez3": max(0, puntaje - 1)},
                    }
                    for item, puntaje in puntajes.items()
                ],
            }
        ],
    }


PUNTAJES = {
    "tesis_a": {"1": 3, "2": 2, "3": 3, "4": 1},
    "tesis_b": {"1": 2, "2": 2, "3": 1, "4": 0},
    "tesis_c": {"1": 3, "2": 3, "3": 2, "4": 2},
    "tesis_d": {"1": 1, "2": 0, "3": 1, "4": 2},
}


@pytest.fixture()
def entorno_validacion(tmp_path: Path):
    carpeta_sistema = tmp_path / "results"
    carpeta_sistema.mkdir()
    for proyecto, puntajes in PUNTAJES.items():
        (carpeta_sistema / f"{proyecto}.json").write_text(
            json.dumps(_resultado_sistema(proyecto, puntajes)), encoding="utf-8"
        )
    # Jurado1 = idéntico al sistema; Jurado2 = un nivel menos en el ítem 1
    filas = ["proyecto_id,jurado_id,item_id,puntaje"]
    for proyecto, puntajes in PUNTAJES.items():
        for item, puntaje in puntajes.items():
            filas.append(f"{proyecto},J1,{item},{puntaje}")
            ajustado = max(0, puntaje - 1) if item == "1" else puntaje
            filas.append(f"{proyecto},J2,{item},{ajustado}")
    ruta_jurados = tmp_path / "jurados.csv"
    ruta_jurados.write_text("\n".join(filas), encoding="utf-8")
    return carpeta_sistema, ruta_jurados, tmp_path / "validation"


class TestValidacionEndToEnd:
    def test_mediana_jurados_usa_mediana_inferior_con_dos(self):
        por_jurado = {"J1": {"1": 3, "2": 2}, "J2": {"1": 1, "2": 2}}
        assert mediana_jurados(por_jurado) == {"1": 1, "2": 2}

    def test_linea_base_humana(self, entorno_validacion):
        _, ruta_jurados, _ = entorno_validacion
        from cli.validate import cargar_jurados

        base = linea_base_humana(cargar_jurados(ruta_jurados))
        assert "J1|J2" in base["qwk_items_global"]
        assert 0 < base["qwk_items_global"]["J1|J2"] < 1  # difieren solo en el ítem 1
        assert len(base["qwk_items_por_proyecto"]) == 4

    def test_sistema_contra_humanos(self, entorno_validacion):
        carpeta_sistema, ruta_jurados, _ = entorno_validacion
        from cli.validate import cargar_jurados, cargar_sistema

        contra = sistema_contra_humanos(
            cargar_sistema(carpeta_sistema, "ficha_upao_v1"),
            cargar_jurados(ruta_jurados),
            n_bootstrap=50,
        )
        # El sistema es idéntico al jurado J1
        assert contra["contra_jurados"]["J1"]["qwk_items"] == pytest.approx(1.0)
        assert contra["contra_jurados"]["J1"]["acuerdo_exacto"] == 1.0
        # La mediana inferior de (J1, J2) difiere solo donde J2 restó un nivel
        med = contra["contra_mediana"]
        assert 0 < med["qwk_items"] < 1
        assert med["acuerdo_adyacente"] == 1.0
        # Totales: J1 = sistema, J2 = sistema - 1 → mediana continua = t - 0.5
        assert med["mae_totales"] == pytest.approx(0.5)
        assert med["qwk_items_ic95"][0] <= med["qwk_items"] <= med["qwk_items_ic95"][1]
        assert med["correlaciones"]["pearson"] > 0.9

    def test_acuerdo_interno_del_panel(self, entorno_validacion):
        carpeta_sistema, _, _ = entorno_validacion
        panel = acuerdo_interno_panel(carpeta_sistema, "ficha_upao_v1")
        assert panel["juez1|juez2"] == pytest.approx(1.0)
        assert panel["juez1|juez3"] < 1.0
        assert "promedio" in panel

    def test_generar_reporte_completo(self, entorno_validacion):
        carpeta_sistema, ruta_jurados, salida = entorno_validacion
        ruta = generar_reporte(
            carpeta_sistema, ruta_jurados, salida,
            rubrica_id="ficha_upao_v1", n_bootstrap=50,
        )
        contenido = ruta.read_text(encoding="utf-8")
        assert "Línea base humano-humano" in contenido
        assert "sistema vs mediana de jurados" in contenido
        assert "Landis y Koch" in contenido
        assert "ICC(2,1)" in contenido
        assert (salida / "qwk_pares_jurados.csv").exists()
        assert (salida / "sistema_vs_jurados.csv").exists()
        assert (salida / "totales.csv").exists()
