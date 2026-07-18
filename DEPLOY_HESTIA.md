# Déploiement frontend sur Hestia — référence

> À LIRE AVANT DE MODIFIER LE STAGE « Frontend — déploiement Hestia » du Jenkinsfile.
> Ce document existe parce que le problème de permissions a été « re-corrigé »
> plusieurs fois de façon temporaire. La solution ci-dessous est définitive.

## Configuration retenue

| Élément | Valeur |
|---|---|
| Hôte SSH | `192.168.100.75` (IP privée de la VM Hestia) |
| Port SSH | `2275` |
| Utilisateur SSH | `benweb` — **propriétaire du docroot** |
| Credential Jenkins | `hestia-benweb-ssh` (SSH Username with private key) |
| Docroot prod | `/home/benweb/web/toilettage.proxbenovh.cloud/public_html` |
| Docroot staging | `/home/benweb/web/staging.toilettage.proxbenovh.cloud/public_html` |

## Pourquoi `benweb` et pas `ben`

HestiaCP est conçu pour que l'utilisateur web soit propriétaire de ses fichiers.
En se connectant directement en `benweb`, aucun contournement de permissions
n'est nécessaire : ni appartenance à un groupe, ni `chmod g+w`, ni `chown`,
ni options rsync spéciales.

### Ce qui échouait avant

L'approche précédente se connectait en `ben` (seul utilisateur dont Jenkins
avait la clé), puis compensait avec :

- ajout de `ben` au groupe `benweb` ;
- `chmod g+w` et `chown` manuels sur le docroot ;
- options rsync `--no-perms --omit-dir-times --chmod=D2775,F664`.

**Ces correctifs ne tiennent pas dans le temps.** HestiaCP réinitialise le
propriétaire et les permissions du docroot à chaque `v-rebuild-web-domain`
(renouvellement de certificat, modification du domaine, mise à jour d'Hestia).
De plus, la correction n'était appliquée qu'au docroot de staging — d'où l'échec
lors du premier déploiement en production.

## Prérequis (à faire une seule fois sur la VM Hestia)

```bash
# 1. Donner un shell à benweb (commande Hestia = persistant)
v-change-user-shell benweb bash

# 2. Préparer le dossier .ssh
mkdir -p /home/benweb/.ssh
chmod 700 /home/benweb/.ssh
touch /home/benweb/.ssh/authorized_keys
chmod 600 /home/benweb/.ssh/authorized_keys
chown -R benweb:benweb /home/benweb/.ssh

# 3. Ajouter la clé publique dédiée à Jenkins
echo "ssh-ed25519 AAAA... jenkins->hestia-benweb" >> /home/benweb/.ssh/authorized_keys

# 4. Si sshd restreint les utilisateurs, autoriser benweb
grep -REi "allowusers|allowgroups" /etc/ssh/sshd_config /etc/ssh/sshd_config.d/
# puis, le cas échéant : ajouter benweb à la directive et
systemctl reload sshd
```

Côté Jenkins : credential **SSH Username with private key**, id `hestia-benweb-ssh`,
username `benweb`, clé privée correspondante.

## Vérification

```bash
ssh -i <cle_privee> -p 2275 benweb@192.168.100.75 \
  'whoami; touch /home/benweb/web/staging.toilettage.proxbenovh.cloud/public_html/.t \
   && echo OK && rm /home/benweb/web/staging.toilettage.proxbenovh.cloud/public_html/.t'
```

Résultat attendu : `benweb` puis `OK`.

## En cas d'échec futur

Le stage Jenkins effectue un contrôle préalable qui affiche l'utilisateur
courant et les permissions du docroot. Si l'écriture est refusée :

1. Vérifier que la clé publique est toujours dans
   `/home/benweb/.ssh/authorized_keys` (permissions `700` sur `.ssh`, `600` sur
   `authorized_keys`, propriétaire `benweb:benweb`).
2. Vérifier que le shell de `benweb` n'a pas été remis à `nologin`
   (`getent passwd benweb`) — le cas échéant : `v-change-user-shell benweb bash`.
3. Vérifier `sshd_config` (`AllowUsers`).

**Ne pas revenir à l'utilisateur `ben` avec des contournements de permissions.**

## Règles inchangées

- `--exclude='.env'` : ne jamais écraser un fichier `.env` distant.
- `--exclude='.well-known'` : préserver les challenges ACME.
- Le déploiement passe toujours par Jenkins ; aucune copie manuelle sur la VM.
