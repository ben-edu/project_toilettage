# Déploiement Kubernetes — API toilettage

Namespace unique `toilettage` sur le cluster K3s (BM2).

## Ordre d'application

Les Secrets doivent exister AVANT le StatefulSet et le Deployment.

```bash
# 1. Namespace
kubectl apply -f namespace.yaml

# 2. Secrets (créés hors Git — voir secret.example.yaml pour les commandes)
#    - toilettage-db-secret
#    - toilettage-api-secret
#    - harbor-regcred (pull secret)

# 3. Base de données
kubectl apply -f postgres-statefulset.yaml
kubectl apply -f postgres-service.yaml

# 4. Config + API
kubectl apply -f configmap.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# 5. Ingress
kubectl apply -f ingress.yaml
```

Ou tout d'un coup (après création des Secrets) :

```bash
kubectl apply -f .
```

## Initialisation des données (première fois)

Après le premier déploiement, créer les tables + données de base :

```bash
kubectl -n toilettage exec deploy/toilettage-api -- python -m app.seed
```

> En production mature, remplacer `app.seed` par des migrations Alembic.

## Vérifications

```bash
kubectl -n toilettage get pods,svc,ingress,pvc
kubectl -n toilettage logs deploy/toilettage-api
kubectl -n toilettage exec deploy/toilettage-api -- curl -s localhost:8000/api/v1/healthz
```

## Rappels

- TLS terminé sur HAProxy (ACME/OVH hors cluster). L'Ingress ne gère pas le TLS.
- Le trafic navigateur va toujours par le domaine public → HAProxy → OPNsense →
  Traefik → Service → Pod. Jamais d'IP privée BM2 côté navigateur.
- Image tirée de Harbor : `harbor.proxbenovh.cloud/devops-project-harbor/toilettage-api:<tag>`.
- Jamais de vrais secrets dans Git.

## DNS à créer (records A → 87.98.174.211)

| Host | Usage |
|---|---|
| `api.toilettage.proxbenovh.cloud` | API prod |
| `api.staging.toilettage.proxbenovh.cloud` | API staging |
| `toilettage.proxbenovh.cloud` | Frontend prod (Hestia) |
| `staging.toilettage.proxbenovh.cloud` | Frontend staging (Hestia) |
