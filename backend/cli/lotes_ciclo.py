"""Atiende los lotes hasta terminar: descarga lo completado y envía las partes pendientes.

Uso (desde backend\\, con EVAL_BATCH_DIR definido):  python -m cli.lotes_ciclo [segundos_entre_consultas]
"""

from __future__ import annotations

import sys
import time

from cli import lotes as cli_lotes


def pendientes_y_activos() -> tuple[int, int]:
    cliente = cli_lotes._cliente()
    hechos = cli_lotes._ids_respondidos()
    activos = 0
    for r in cli_lotes._leer_registro():
        b = cliente.batches.retrieve(r["batch_id"])
        if b.status in ("validating", "in_progress", "finalizing"):
            activos += 1
    total = sum(1 for sols in cli_lotes._solicitudes().values() for s in sols if s["custom_id"] not in hechos)
    return total, activos


def main() -> int:
    espera = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    while True:
        cli_lotes.descargar()
        pendientes, activos = pendientes_y_activos()
        print(f"[{time.strftime('%H:%M:%S')}] solicitudes sin respuesta: {pendientes} · lotes en curso: {activos}",
              flush=True)
        if pendientes == 0:
            print("Listo: todas las solicitudes tienen respuesta.")
            return 0
        if activos == 0:
            cli_lotes.enviar()
        time.sleep(espera)


if __name__ == "__main__":
    raise SystemExit(main())
