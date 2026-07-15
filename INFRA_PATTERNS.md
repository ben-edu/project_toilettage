# INFRA_PATTERNS.md — Toilettage Canin à Domicile

> Conventions et patterns réels du cluster K3s (BM2) relevés le 2026-07-15.
> À suivre pour la conception de la stack toilettage.

---

## 1. INGRESS + TLS

### ingressClassName

Tous les Ingress utilisent **`traefik`** :

```yaml
spec:
  ingressClassName: traefik
```

### Domaine unique

Tous les services exposés sont sur le domaine **`*.soria-academie.fr`**.
Aucun Ingress n'existe sur `*.proxbenovh.cloud`.

### TLS

Le TLS est déclaré dans l'Ingress **sans `secretName`** explicite :

```yaml
spec:
  tls:
  - hosts:
    - fastapi.soria-academie.fr
    - api-fastapi.soria-academie.fr
```

Le certificat est délivré automatiquement par **Traefik** (intégration Let's Encrypt
via le chart Helm K3s par défaut). Il n'y a **pas de cert-manager** dans le cluster.
Aucune annotation particulière n'est nécessaire.

### Exemple complet (FastAPI Platform)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  annotations: {}               # aucune annotation TLS requise
  name: fastapi-platform
  namespace: fastapi-platform
spec:
  ingressClassName: traefik
  rules:
  - host: fastapi.soria-academie.fr
    http:
      paths:
      - backend:
          service:
            name: frontend
            port:
              number: 80
        path: /
        pathType: Prefix
  - host: api-fastapi.soria-academie.fr
    http:
      paths:
      - backend:
          service:
            name: backend
            port:
              number: 8000
        path: /
        pathType: Prefix
  tls:
  - hosts:
    - fastapi.soria-academie.fr
    - api-fastapi.soria-academie.fr
```

**Pattern à copier** : Un seul Ingress par namespace, avec la section `tls` listant
tous les hosts. Pas de secret TLS manuel.

---

## 2. SERVICE FASTAPI (pattern deployment)

### Deux patterns existants

**Pattern A — fastapi-platform** (namespace `fastapi-platform`) :
- Backend + Frontend = 2 conteneurs séparés
- 2 replicas chacun
- Node anti-affinité `control-plane` (ne pas scheduler sur master)
- ImagePullSecrets: `harbor-regcred`
- Probes HTTP

**Pattern B — soria-academie** (namespace `soria-academie`) :
- API seule (1 conteneur)
- 1 replica
- ImagePullSecrets: `harbor-regcred`
- Probes HTTP

### Détail du conteneur Backend (pattern le plus complet)

```yaml
# extrait du déploiement backend - fastapi-platform
containers:
- env:
  - name: ENVIRONMENT              # → ConfigMap fastapi-config
  - name: POSTGRES_SERVER           # → ConfigMap
  - name: POSTGRES_DB               # → ConfigMap
  - name: POSTGRES_USER             # → ConfigMap
  - name: POSTGRES_PASSWORD         # → Secret fastapi-secrets / POSTGRES_PASSWORD
  - name: SECRET_KEY                # → Secret fastapi-secrets
  # ... autres vars
  image: harbor.proxbenovh.cloud/devops-project-harbor/fastapi-backend:5b8ae40
  imagePullPolicy: Always
  livenessProbe:
    httpGet:
      path: /api/v1/utils/health-check/
      port: 8000
    initialDelaySeconds: 30
    periodSeconds: 20
  readinessProbe:
    httpGet:
      path: /api/v1/utils/health-check/
      port: 8000
    initialDelaySeconds: 15
    periodSeconds: 10
  resources:
    limits:
      cpu: 500m
      memory: 768Mi
    requests:
      cpu: 100m
      memory: 256Mi
imagePullSecrets:
- name: harbor-regcred
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: node-role.kubernetes.io/control-plane
          operator: DoesNotExist
```

### Variables d'environnement — organisation

| Source | Mécanisme |
|---|---|
| ConfigMap (non sensibles) | `valueFrom.configMapKeyRef` |
| Secret (mots de passe, tokens, clés API) | `valueFrom.secretKeyRef` |
| Variables "plat" (URLs fixes) | `value:` directement |

**ConfigMap type** (`fastapi-config`) :
```
ENVIRONMENT=production
PROJECT_NAME=FastAPI Platform
FRONTEND_HOST=https://fastapi.soria-academie.fr
BACKEND_CORS_ORIGINS=["https://..."]
POSTGRES_SERVER=postgres
POSTGRES_PORT=5432
POSTGRES_DB=app
POSTGRES_USER=appuser
DOMAIN=soria-academie.fr
STACK_NAME=fastapi-platform
```

**ConfigMap type** (`academie-api-config`) — plus moderne, utilise `envFrom`:
```yaml
spec:
  containers:
  - envFrom:
    - configMapRef:
        name: academie-api-config    # injecte toutes les clés d'un coup
    env:
    - name: DATABASE_URL             # sensible → secretKeyRef séparé
      valueFrom:
        secretKeyRef:
          key: DATABASE_URL
          name: academie-api-secret
```

### Service

```yaml
# Backend API (interne au cluster)
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: fastapi-platform
spec:
  type: ClusterIP        # pas d'exposition directe
  ports:
  - port: 8000
  selector:
    app: backend

# Frontend (interne, exposé via Ingress)
apiVersion: v1
kind: Service
metadata:
  name: frontend
  namespace: fastapi-platform
spec:
  type: ClusterIP
  ports:
  - port: 80
  selector:
    app: frontend
```

**Ports conventionnels** :
- Backend API : **8000** (port conteneur)
- Frontend statique : **80**

---

## 3. POSTGRESQL (méthode de déploiement)

### Deux patterns

**Pattern A — Deployment + PVC manuelle** (fastapi-platform)
```yaml
# postgres est un Deployment, pas un StatefulSet
spec:
  replicas: 1
  containers:
  - image: postgres:18
    env:
    - name: POSTGRES_DB         # ConfigMap fastapi-config
    - name: POSTGRES_USER       # ConfigMap fastapi-config
    - name: POSTGRES_PASSWORD   # Secret fastapi-secrets
    - name: PGDATA
      value: /var/lib/postgresql/data/pgdata
    livenessProbe:
      exec:
        command: [sh, -c, 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"']
    readinessProbe:
      exec:
        command: [sh, -c, 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"']
    volumeMounts:
    - mountPath: /var/lib/postgresql/data
      name: postgres-data
  volumes:
  - name: postgres-data
    persistentVolumeClaim:
      claimName: postgres-data
---
# PVC séparée, créée manuellement
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
  namespace: fastapi-platform
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi
  storageClassName: local-path   # implicite (default)
```

**Pattern B — StatefulSet + volumeClaimTemplates** (soria-academie — plus récent/recommandé)
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: academie-postgres
  namespace: soria-academie
spec:
  serviceName: academie-postgres     # Headless Service obligatoire
  replicas: 1
  selector:
    matchLabels:
      app: academie-postgres
  template:
    spec:
      containers:
      - image: postgres:16-alpine
        env:
        - name: POSTGRES_USER
          value: soria                # valeur en dur (pas sensible)
        - name: POSTGRES_DB
          value: soria_academie       # valeur en dur
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              key: POSTGRES_PASSWORD
              name: academie-api-secret
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
        readinessProbe:
          exec:
            command: [sh, -c, 'pg_isready -U soria -d soria_academie']
        volumeMounts:
        - mountPath: /var/lib/postgresql/data
          name: data
  volumeClaimTemplates:               # PVC créée automatiquement
  - metadata:
      name: data
    spec:
      accessModes: [ReadWriteOnce]
      resources:
        requests:
          storage: 5Gi
```

**Résumé des différences** :

| Aspect | fastapi-platform (Deployment) | soria-academie (StatefulSet) |
|---|---|---|
| Image | `postgres:18` | `postgres:16-alpine` |
| Stockage | PVC séparée (10Gi) | `volumeClaimTemplates` (5Gi) |
| Service | ClusterIP | Headless (ClusterIP: None) |
| Création PVC | Manuelle | Automatique |
| Âge | 127 j | 6 j (plus récent) |

**Recommandation** : suivre le pattern StatefulSet (plus récent, auto-provisioning
du PVC).

### Stockage

Uniquement **`local-path`** (rancher.io/local-path, `WaitForFirstConsumer`).
Pas de stockage réseau externe.

---

## 4. HARBOR (registry privé)

### URL du registry

```
harbor.proxbenovh.cloud
```

### Format des chemins d'images

```
harbor.proxbenovh.cloud/devops-project-harbor/<image>:<tag>
```

| Application | Image complète |
|---|---|
| FastAPI Backend | `harbor.proxbenovh.cloud/devops-project-harbor/fastapi-backend:5b8ae40` |
| FastAPI Frontend | `harbor.proxbenovh.cloud/devops-project-harbor/fastapi-frontend:5b8ae40` |
| Soria Académie API | `harbor.proxbenovh.cloud/devops-project-harbor/academie-api:7813338` |

Projet Harbor : **`devops-project-harbor`** (un seul projet pour toutes les images).

### imagePullSecret

Nom : **`harbor-regcred`** (type `kubernetes.io/dockerconfigjson`).

Namespace où il est présent :
- `fastapi-platform`
- `fastapi-platform-dev`
- `soria-academie`
- `soria-prospecting`

**Pattern** : chaque namespace qui utilise Harbor doit avoir son propre
`harbor-regcred` (exclu `default` qui ne l'a pas).

### Utilisation dans les Deployments

```yaml
spec:
  template:
    spec:
      imagePullSecrets:
      - name: harbor-regcred
```

---

## 5. CONFIRMATION DNS / RÉSEAU

### Domaines actifs

| Domaine | Usage |
|---|---|
| `*.soria-academie.fr` | **Tous** les services exposés via Traefik |
| `*.proxbenovh.cloud` | Registry Harbor et services OVH internes |

Aucun Ingress sur `*.proxbenovh.cloud` — ce domaine est réservé aux usages
internes/infra.

### Chemin réseau public → Traefik

```
Internet → OVH (IP publique / range) → OPNsense (Proxmox BM2, 172.20.100.1)
  → K3s nodes (172.20.100.21-23) → Service Traefik LoadBalancer
  → Ingress → Service ClusterIP → Pod
```

| Étape | Détail |
|---|---|
| **OPNsense** | Firewall sur le Proxmox BM2 (`delfan`), fait office de gateway pour le VLAN K3s |
| **Traefik Service** | Type `LoadBalancer`, External IPs = `172.20.100.21,22,23` (IP des nœuds K3s) |
| **NodePort sous-jacents** | 80 → 31681 / 443 → 32508 (redirection OPNsense vers ces ports ?) |
| **External Traffic Policy** | `Cluster` (le traffic peut arriver sur n'importe quel nœud) |

Le **Traefik Service n'est pas directement sur l'IP publique** `87.98.174.211`.
La terminaison TLS se fait au niveau Traefik (Let's Encrypt automatique).
Le flux probable est : OPNsense NATte les ports 80/443 vers les IP des nœuds K3s
sur les NodePorts Traefik, ou OVH Load Balancer forwarde vers l'OPNsense
qui reverse-proxy vers Traefik.

---

## Recommandations — conventions à suivre pour le projet toilettage

### Namespace
- Créer `toilettage` comme namespace dédié.

### Ingress
- Classe `traefik`, TLS sans `secretName` (Let's Encrypt automatique).
- Domaine : `*.soria-academie.fr` (ex: `toilettage.soria-academie.fr`,
  `api-toilettage.soria-academie.fr`).
- Un seul Ingress YAML par namespace, listant tous les hosts.

### Backend FastAPI
- Image : `harbor.proxbenovh.cloud/devops-project-harbor/toilettage-api:<tag>`.
- Port conteneur : **8000**.
- Probes HTTP sur `/health` (ou `/api/v1/healthz`).
- Resources : s'inspirer de `100m/256Mi requests, 500m/768Mi limits`.
- Node anti-affinité `control-plane` (pattern standard).
- `imagePullSecrets: [{name: harbor-regcred}]`.
- ConfigMap pour les vars non sensibles, Secret pour les credentials.
- `envFrom` avec ConfigMap (pattern soria-academie, plus moderne).

### Base de données
- **StatefulSet** (pattern soria-academie) avec `volumeClaimTemplates`.
  Image : `postgres:16-alpine` (léger) ou `postgres:18`.
- Stockage : `local-path`, 5-10 Gi (suffisant pour un agenda).
- Service headless ou ClusterIP, port 5432.

### Frontend (Hestia — BM1)
- Déploiement via Jenkins → rsync vers Hestia.
- Domaine : `toilettage.soria-academie.fr`.
- Document root Hestia : à confirmer sur BM1.

### Authentification Keycloak
- Nouveau realm `toilettage` dans le Keycloak existant.
- Issuer URL : `https://keycloak.soria-academie.fr/realms/toilettage`.
- S'inspirer du ConfigMap `academie-api-config` pour les vars Keycloak :
  `KC_ISSUER`, `KC_JWKS_URL`, `KC_AUDIENCE`, `KC_ADMIN_ROLE`.

### CI/CD
- Image poussée sur Harbor → `harbor.proxbenovh.cloud/devops-project-harbor/`.
- Jenkins multibranch (pipeline existant).
- `harbor-regcred` à créer dans le namespace `toilettage` si pas déjà global.

---

*Document généré le 2026-07-15 par commandes kubectl en lecture seule.*
