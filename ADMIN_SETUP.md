# Panneau d'administration — mise en service

Panneau : `https://admin.toilettage.proxbenovh.cloud`
Authentification : Keycloak, realm `toilettage`, client `toilettage-admin`
(public + PKCE S256). Aucun secret n'est stocké dans le navigateur.

---

## 1. Configuration du client Keycloak

Dans la console Keycloak → realm **`toilettage`** → Clients → **`toilettage-admin`**
→ onglet *Settings*, vérifier / renseigner :

| Champ | Valeur |
|---|---|
| Client authentication | **Off** (client public) |
| Standard flow | **Activé** |
| Direct access grants | **Désactivé** |
| Valid redirect URIs | `https://admin.toilettage.proxbenovh.cloud/*` |
| Valid post logout redirect URIs | `https://admin.toilettage.proxbenovh.cloud/*` |
| Web origins | `https://admin.toilettage.proxbenovh.cloud` |

Onglet *Advanced* → **Proof Key for Code Exchange Code Challenge Method** = `S256`.

> Sans l'entrée *Web origins*, le navigateur bloquera l'échange du code contre
> un token (erreur CORS sur `/protocol/openid-connect/token`).

## 2. Création de l'utilisateur `toiletteur`

Realm `toilettage` → Users → **Add user**

- Username : `toiletteur`
- Email : l'adresse du toiletteur
- Email verified : activé
- **Create**

Puis onglet *Credentials* → **Set password** :

- saisir un mot de passe provisoire ;
- **Temporary : On** → le changement sera demandé à la première connexion.

En ligne de commande (alternative) :

```bash
kcadm.sh create users -r toilettage \
  -s username=toiletteur -s enabled=true -s emailVerified=true
kcadm.sh set-password -r toilettage --username toiletteur \
  --new-password '<mot-de-passe-provisoire>' --temporary
```

> Ne jamais écrire le mot de passe réel dans Git ou dans un ticket.

## 3. Vérifications API

- `CORS_ORIGINS` de l'API doit inclure `https://admin.toilettage.proxbenovh.cloud`
  (valeur par défaut mise à jour dans `app/core/config.py` ; si la variable est
  surchargée dans le ConfigMap Kubernetes, l'y ajouter aussi).
- Les endpoints `/api/v1/admin/*` exigent un token Bearer valide du realm.

## 4. Vérification de bout en bout

1. Ouvrir `https://admin.toilettage.proxbenovh.cloud`
2. Cliquer sur **Se connecter** → redirection vers Keycloak
3. S'identifier avec `toiletteur` → changement du mot de passe provisoire
4. Retour automatique sur le panneau, connecté

Fonctions attendues :

- **Réservations** : liste, filtres par statut, compteurs, actions
  *Confirmer* / *Marquer terminée* / *Annuler*, lien carte vers l'adresse.
- **Prestations** : modification du nom, de la durée, du tarif, de l'ordre et
  de l'activation ; création d'une nouvelle prestation.
- **Horaires** : plage horaire et activation pour chacun des 7 jours.

## 5. En cas de problème

| Symptôme | Cause probable |
|---|---|
| Blocage sur l'écran de connexion | *Valid redirect URIs* absent ou incorrect |
| Erreur CORS sur `/token` | *Web origins* non renseigné dans le client |
| `401` sur les appels API | `CORS_ORIGINS` de l'API, ou token expiré |
| `invalid_grant` après connexion | méthode PKCE ≠ `S256` côté client |

## 6. Notes

- Le panneau n'est pas indexé (`robots.txt` + balise `noindex`).
- Il est déployé **uniquement depuis la branche `main`** (un seul domaine admin).
- Les tokens ne sont jamais placés en `localStorage` ; seul le *refresh token*
  transite par `sessionStorage`, effacé à la fermeture de l'onglet.
