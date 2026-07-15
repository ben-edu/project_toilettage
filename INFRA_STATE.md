# INFRA_STATE.md — Toilettage Canin à Domicile

> Relevé de l'infrastructure existante au 2026-07-15.
> Commandes exécutées en lecture seule. Aucune modification.

---

## 1. Cluster K3s (BM2)

**Nœuds** (Proxmox `delfan` — BM2) :

| Name | Role | Internal IP |
|---|---|---|
| k3s-master-01 | control-plane | 172.20.100.21 |
| k3s-worker-01 | worker | 172.20.100.22 |
| k3s-worker-02 | worker | 172.20.100.23 |

**Version** : `v1.34.5+k3s1`

**Namespaces** existants (20+) :

```
bookstack, default, fastapi-platform, fastapi-platform-dev, infra,
keycloak, kube-system, misp, monitoring, moodle, openproject, shuffle,
soria-academie, soria-prospecting, thehive, validation, vault, vaultwarden,
wazuh
```

**StorageClass** :
- `local-path` (default) — `rancher.io/local-path`, `WaitForFirstConsumer`

---

## 2. PostgreSQL

Il y a **plusieurs** instances PostgreSQL indépendantes, une par application :

| Namespace | Service | Type | Port |
|---|---|---|---|
| `keycloak` | `keycloak-postgresql` | ClusterIP | 5432 |
| `fastapi-platform` | `postgres` | ClusterIP | 5432 |
| `fastapi-platform-dev` | `postgres` | ClusterIP | 5432 |
| `openproject` | `openproject-postgresql` | ClusterIP | 5432 |
| `soria-prospecting` | `postgres` | ClusterIP | 5432 |
| `soria-academie` | `academie-postgres` | ClusterIP | 5432 |

Toutes les instances tournent sur le cluster (pas de base externe).  
Les identifiants sont stockés dans des **Secrets Kubernetes** :

- Keycloak : `keycloak-postgresql-secret` (namespace `keycloak`)
- OpenProject : `openproject-postgresql` (namespace `openproject`)
- Autres applications : suivre le même motif (Secret dédié par namespace)

→ Pour le projet Toilettage, prévoir un nouveau Secret `postgres-secret` (ou similaire)
  dans son propre namespace, sans réutiliser les secrets existants.

---

## 3. Keycloak

| Champ | Valeur |
|---|---|
| **URL publique** | `https://keycloak.soria-academie.fr` |
| **Namespace** | `keycloak` |
| **Service** | `keycloak` (ClusterIP, port 80 → targetPort http) |
| **Ingress** | Classe `traefik`, host `keycloak.soria-academie.fr`, path `/` (Prefix) |
| **Version** | `26.3.2` (Bitnami, `docker.io/bitnamilegacy/keycloak`) |
| **Pod** | `keycloak-0` (StatefulSet, 1 replica) |
| **Base de données** | `keycloak-postgresql-0` (StatefulSet dédié) |

**Realms existants** (vérifié via `.well-known/openid-configuration`) :

| Realm | État |
|---|---|
| `master` | Actif (realm admin par défaut) |
| `soria` | Actif (realm métier existant) |

> **Note** : le mot de passe admin stocké dans le Secret `keycloak-admin-secret`
> (`admin-password`) semble ne plus correspondre au mot de passe courant
> (probablement changé via l'UI après le déploiement initial).

**Comment créer un nouveau realm dédié au Toilettage** :

1. Accéder à l'admin console : `https://keycloak.soria-academie.fr`
2. Se connecter avec le compte admin du realm `master`
3. Cliquer sur le dropdown "master" en haut à gauche → "Create realm"
4. Nom suggéré : `toilettage`
5. Configurer un client `toilettage-frontend` (public, pour le frontend)
6. Configurer un client `toilettage-admin` (confidential, pour l'admin panel)

Alternative — via `kcadm.sh` dans le pod (après avoir récupéré / réinitialisé le mot de passe) :
```bash
kubectl exec -n keycloak keycloak-0 -- /opt/bitnami/keycloak/bin/kcadm.sh \
  create realms -s realm=toilettage -s enabled=true
```

---

## 4. Traefik

**ingressClassName** : `traefik`

**Pods** :
- `traefik-788bc4688c-ck7nl` (1 replica, namespace `kube-system`)
- `svclb-traefik-*` (1 par nœud, load-balancer)

**Adresses des load-balancers** : `172.20.100.21`, `172.20.100.22`, `172.20.100.23`

**Exemple d'Ingress typique** (Keycloak) :

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: keycloak
  namespace: keycloak
spec:
  ingressClassName: traefik
  rules:
    - host: keycloak.soria-academie.fr
      http:
        paths:
          - backend:
              service:
                name: keycloak
                port:
                  name: http
            path: /
            pathType: Prefix
  tls:
    - hosts:
        - keycloak.soria-academie.fr
```

**TLS** : géré au niveau Ingress. Pas de `cert-manager` dans le cluster.
Les certificats sont très probablement délivrés par le Let's Encrypt intégré
à Traefik (configuration Helm du chart K3s par défaut).

**Middleware** existant : `soria-auth-proxy` (namespace `soria-prospecting`),
utilisé pour l'authentification OAuth côté frontend.

---

## 5. Hestia (BM1)

**BM1 (delfan2)** est un serveur Proxmox distinct non accessible via les outils
MCP actuels. Il héberge plusieurs VMs, dont :

| Adresse publique | Service | Port SSH |
|---|---|---|
| `87.98.174.211` | Jenkins (Docker) | 2273 |
| `87.98.174.211` | Harbor (Docker) | 2271 |

**Hestia Control Panel** est une VM/service séparé sur BM1 (non accessible
directement depuis la VM de management). Ses caractéristiques présumées :

- OS : Debian ou Ubuntu avec HestiaCP installé
- Document root typique HestiaCP :
  `/home/<user>/web/<nom_du_domaine>/public_html`
- Pour le projet Toilettage, créer un nouveau domaine (ou sous-domaine)
  dans Hestia pour l'application frontend
- Le déploiement se fait par Jenkins (via rsync) depuis le pipeline
  multibranch

**À confirmer** sur BM1 :
- [ ] Nom d'utilisateur Hestia associé au nouveau site
- [ ] Domaine / sous-domaine choisi (ex: `toilettage.soria-academie.fr`)
- [ ] Chemin exact du document root
- [ ] Accès SSH (via bastion ou direct ?)
- [ ] Configuration TLS dans Hestia

---

## 6. Notes pour le déploiement Toilettage

### Frontend (Hestia / BM1)
- Déployé via Jenkins → rsync vers le document root Hestia
- Toujours exclure `.env` du rsync
- Garder staging et production séparés

### Backend API (K3s / BM2)
- Nouveau namespace `toilettage` à créer
- Déploiement FastAPI (image → Harbor → K8s)
- Service ClusterIP + Ingress classe `traefik`
- Domaine API suggéré : `api-toilettage.soria-academie.fr`

### Base de données (K3s / BM2)
- Nouveau StatefulSet PostgreSQL dans le namespace `toilettage`
- Secret dédié pour les identifiants (ne pas réutiliser)
- Service ClusterIP port 5432

### Authentification (Keycloak)
- Nouveau realm `toilettage` à créer
- Client public pour le formulaire public (pas de login requis)
- Client confidentiel pour l'admin panel (avec Keycloak)

---

*Document généré le 2026-07-15 par commandes en lecture seule.*
