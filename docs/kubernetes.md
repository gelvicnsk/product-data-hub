# Kubernetes

## Prérequis (WSL Ubuntu)

```bash
# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -m 0755 kubectl /usr/local/bin/kubectl && rm kubectl
# kind
curl -Lo kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64
sudo install -m 0755 kind /usr/local/bin/kind && rm kind
kubectl version --client && kind version
```

Mémoire : Postgres, Keycloak, l'API et le Job pipeline demandent environ 3 Go. Si WSL
manque de mémoire, l'augmenter dans `C:\Users\<toi>\.wslconfig` (`[wsl2]` puis
`memory=8GB`), puis `wsl --shutdown` depuis PowerShell.

## Ce que fait `make k8s-up`

1. crée le cluster kind `product-hub` (s'il n'existe pas) ;
2. construit les images `mock-crm`, `api`, `pipeline` et les charge dans le cluster
   (`kind load docker-image` : pas de registre nécessaire) ;
3. crée le Secret `product-hub-secrets` à partir de `.env` (rien n'est écrit sur disque) ;
4. applique l'overlay `dev` avec kustomize ;
5. attend Postgres, le faux CRM, Keycloak, le Job d'initialisation, puis l'API.

## Choix

| Sujet | Choix | Pourquoi |
|---|---|---|
| Base de données | StatefulSet + PersistentVolumeClaim | identité et stockage stables ; en production : service managé ou opérateur (CloudNativePG) |
| Configuration | ConfigMap ; `init.sql` et le realm Keycloak générés depuis `infra/` | une seule source de vérité pour Compose et Kubernetes |
| Secrets | Secret créé depuis `.env` par le script | jamais dans Git ; en production : External Secrets / Vault |
| Moindre privilège | l'API ne reçoit que les identifiants de ses deux rôles ; Keycloak que les siens | un pod compromis n'obtient pas le mot de passe propriétaire |
| Migrations | initContainer Alembic dans le Deployment de l'API | idempotent, toujours exécuté avant le démarrage |
| Pipeline | Job d'initialisation + CronJob quotidien | alternative native à Airflow pour un batch simple |
| Exposition | NodePort + ports publiés par kind | pas besoin de contrôleur Ingress en local |
| Santé | readinessProbe sur `/health` (API, CRM) et `/health/ready` (Keycloak) | le trafic n'arrive qu'aux pods prêts |

## Diagnostic

```bash
kubectl -n product-hub get pods
kubectl -n product-hub describe pod <pod>          # événements : image absente, probe en échec...
kubectl -n product-hub logs deploy/api -c migrate  # migrations Alembic
kubectl -n product-hub logs job/pipeline-init      # ingestion + dbt
kubectl -n product-hub logs job/pipeline-init -c simulate
kubectl -n product-hub port-forward svc/postgres 5434:5432   # psql -h localhost -p 5434
kubectl -n product-hub create job --from=cronjob/pipeline-daily run-now   # lancer le CronJob à la main
```

Jeton et appel de l'API déployée :

```bash
TOKEN=$(curl -s localhost:9180/realms/product-hub/protocol/openid-connect/token \
  -d grant_type=password -d client_id=product-hub-cli -d username=alice \
  --data-urlencode password="$KC_DEMO_READER_PASSWORD" | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
curl -s -H "Authorization: Bearer $TOKEN" "localhost:9001/products?page_size=3" | python3 -m json.tool
```

## Non couvert ici

Airflow sur Kubernetes (chart Helm officiel `apache-airflow/airflow`), un contrôleur Ingress
avec TLS, la haute disponibilité de Postgres et de Keycloak.
