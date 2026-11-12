#!/usr/bin/env bash
# Supprime le cluster kind du Product Data Hub (et donc toutes ses données).
set -euo pipefail
kind delete cluster --name product-hub
