# Déploiement Kubernetes (kind + kustomize)

```bash
make k8s-up     # cluster kind, images, secret depuis .env, manifestes, attente
make k8s-down   # supprime le cluster
```

Détails, choix et commandes de diagnostic : [docs/kubernetes.md](../docs/kubernetes.md).

```
k8s/
├── kind-config.yaml            cluster à 1 nœud ; ports 9001 (API) et 9180 (Keycloak)
├── base/                       manifestes communs
│   ├── configmap.yaml          configuration non secrète
│   ├── secret.example.yaml     modèle du Secret (le vrai est créé depuis .env, jamais commité)
│   ├── data-pvc.yaml           volume partagé : fichiers des sources, base du faux CRM
│   ├── postgres/               StatefulSet + volume + Service ; init.sql monté en ConfigMap
│   ├── mock-crm/               Deployment + Service
│   ├── keycloak/               Deployment (realm importé depuis une ConfigMap) + NodePort
│   ├── api/                    Deployment (migrations Alembic en initContainer) + NodePort
│   └── pipeline/               Job d'initialisation + CronJob quotidien
└── overlays/
    ├── dev/                    ressources réduites (WSL)
    └── prod/                   exemple : 2 réplicas de l'API
```
