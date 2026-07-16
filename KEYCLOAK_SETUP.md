# Keycloak — Realm « toilettage » (Toutou à Domicile)

## Statut actuel

- **Realm `toilettage`** : créé et actif (displayName: "Toutou à Domicile")
- **Client `toilettage-admin`** : créé, configuré (voir ci-dessous)
- **Utilisateur `toiletteur`** : créé, mot de passe temporaire à définir

## Configuration du realm

| Paramètre | Valeur |
|---|---|
| Nom | `toilettage` |
| Display name | "Toutou à Domicile" |
| URL du serveur | `https://keycloak.soria-academie.fr` |
| Well-known | `https://keycloak.soria-academie.fr/realms/toilettage/.well-known/openid-configuration` |

## Client `toilettage-admin`

| Paramètre | Valeur |
|---|---|
| Type | **Public** (SPA) + PKCE |
| PKCE challenge method | S256 |
| Standard Flow | ✅ activé |
| Direct Access Grants | ❌ désactivé |
| Redirect URIs | `https://admin.toilettage.proxbenovh.cloud/*` |
| | `https://admin.staging.toilettage.proxbenovh.cloud/*` |
| | `http://localhost:5173/*` |
| Web Origins | `https://admin.toilettage.proxbenovh.cloud` |
| | `https://admin.staging.toilettage.proxbenovh.cloud` |
| | `http://localhost:5173` |

## Utilisateurs

| Username | Statut |
|---|---|
| `toiletteur` | Créé, email non défini, mot de passe temporaire NON défini |

## Commandes de référence (exécutées — ne PAS réexécuter sans raison)

```bash
# Connexion au serveur Keycloak (via kcadm.sh depuis le pod keycloak-0)
kubectl -n keycloac exec keycloak-0 -- bash -c '
  export KC_OPTS="-Duser.home=/tmp $KC_OPTS"
  /opt/bitnami/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080 \
    --realm master --user kc-automation-admin
'

# Création du realm
/opt/bitnami/keycloak/bin/kcadm.sh create realms \
  -s realm=toilettage -s enabled=true \
  -s displayName="Toutou à Domicile"

# Création du client (public + PKCE S256)
/opt/bitnami/keycloak/bin/kcadm.sh create clients -r toilettage \
  -s clientId=toilettage-admin \
  -s publicClient=true \
  -s standardFlowEnabled=true \
  -s directAccessGrantsEnabled=false \
  -s 'attributes={"pkce.code.challenge.method":"S256","post.logout.redirect.uris":"+"}' \
  -s 'redirectUris=["https://admin.toilettage.proxbenovh.cloud/*","https://admin.staging.toilettage.proxbenovh.cloud/*","http://localhost:5173/*"]' \
  -s 'webOrigins=["https://admin.toilettage.proxbenovh.cloud","https://admin.staging.toilettage.proxbenovh.cloud","http://localhost:5173"]'

# Création de l'utilisateur toiletteur
/opt/bitnami/keycloak/bin/kcadm.sh create users -r toilettage \
  -s username=toiletteur \
  -s enabled=true \
  -s emailVerified=true

# Définition du mot de passe temporaire (à exécuter quand prêt)
# /opt/bitnami/keycloak/bin/kcadm.sh set-password -r toilettage \
#   --username toiletteur \
#   --new-password '<TEMP>' \
#   --temporary
```

## Rappels

- Ne **JAMAIS** committer de secrets (mots de passe, tokens) dans ce fichier
- Le mot de passe de `kc-automation-admin` et le mot de passe temporaire du toiletteur sont gérés hors Git
- Le realm `soria` sert de modèle pour les conventions (client public, PKCE, etc.)
