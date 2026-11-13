#!/bin/bash
# Punto di avvio compatibile: prepara e avvia l’app completa.
set -euo pipefail
cd "$(dirname "$0")/.."
exec bash './Avvia AgroPlan.command' "$@"
