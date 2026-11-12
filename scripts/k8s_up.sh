#!/usr/bin/env bash
# Déploie le Product Data Hub sur un cluster Kubernetes local (kind).
#   scripts/k8s_up.sh          (ou : make k8s-up)
# Prérequis : docker, kind, kubectl ; fichier .env rempli (make env).
set -euo pipefail

cd "$(dirname "$0")/.."
CLUSTER=product-hub
NAMESPACE=product-hub
OVERLAY="${OVERLAY:-k8s/overlays/dev}"

for tool in docker kind kubectl; do
  command -v "$tool" >/dev/null || { echo "outil manquant : $tool (voir docs/kubernetes.md)" >&2; exit 1; }
done
[[ -f .env ]] || { echo ".env manquant : lancer make env" >&2; exit 1; }
set -a; source .env; set +a

echo "== 1. cluster kind"
kind get clusters | grep -qx "$CLUSTER" || kind create cluster --config k8s/kind-config.yaml
kubectl config use-context "kind-$CLUSTER" >/dev/null

echo "== 2. images (construites localement puis chargées dans le cluster)"
docker build -q -f sources/mock_crm/Dockerfile -t product-hub/mock-crm:dev .
docker build -q -f api/Dockerfile -t product-hub/api:dev .
docker build -q -f infra/pipeline/Dockerfile -t product-hub/pipeline:dev .
kind load docker-image --name "$CLUSTER" product-hub/mock-crm:dev product-hub/api:dev product-hub/pipeline:dev

echo "== 3. namespace et secret (depuis .env, jamais écrit sur disque)"
kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"
kubectl -n "$NAMESPACE" create secret generic product-hub-secrets \
  --from-literal=POSTGRES_USER="$POSTGRES_USER" \
  --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  --from-literal=API_DB_USER="${API_DB_USER:-api_reader}" \
  --from-literal=API_DB_PASSWORD="$API_DB_PASSWORD" \
  --from-literal=API_WRITER_DB_USER="${API_WRITER_DB_USER:-api_writer}" \
  --from-literal=API_WRITER_DB_PASSWORD="$API_WRITER_DB_PASSWORD" \
  --from-literal=KC_BOOTSTRAP_ADMIN_PASSWORD="$KEYCLOAK_ADMIN_PASSWORD" \
  --from-literal=KC_DEMO_READER_PASSWORD="$KC_DEMO_READER_PASSWORD" \
  --from-literal=KC_DEMO_STEWARD_PASSWORD="$KC_DEMO_STEWARD_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "== 4. manifestes ($OVERLAY)"
kubectl kustomize --load-restrictor LoadRestrictionsNone "$OVERLAY" | kubectl apply -f -

echo "== 5. attente des services (Keycloak peut prendre 1 à 2 minutes)"
kubectl -n "$NAMESPACE" rollout status statefulset/postgres --timeout=300s
kubectl -n "$NAMESPACE" rollout status deployment/mock-crm --timeout=300s
kubectl -n "$NAMESPACE" rollout status deployment/keycloak --timeout=600s
kubectl -n "$NAMESPACE" wait --for=condition=complete job/pipeline-init --timeout=1200s
kubectl -n "$NAMESPACE" rollout status deployment/api --timeout=300s

echo
echo "Déployé."
echo "  API       http://localhost:9001/docs"
echo "  Keycloak  http://localhost:9180   (admin / KEYCLOAK_ADMIN_PASSWORD)"
echo "  Pods      kubectl -n $NAMESPACE get pods"
echo "  Pipeline  kubectl -n $NAMESPACE logs job/pipeline-init"
