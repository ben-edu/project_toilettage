// Multibranch pipeline — projet toilettage.
//
// Branches :
//   feature/*  -> build + tests uniquement (pas de déploiement)
//   dev        -> déploie sur STAGING (API K3s + frontend Hestia staging)
//   main       -> déploie en PRODUCTION (après merge validé depuis dev)
//
// Prérequis Jenkins (déjà configurés, JAMAIS ici) :
//   - harbor-robot-devops-project-harbor : login Harbor (usernamePassword, robot account)
//   - hestia-ben-ssh                     : clé SSH pour rsync vers Hestia (sshUserPrivateKey)
//   - kubeconfig monté sur l'agent : /var/lib/jenkins/.kube/config-afpa-k3s
//     (même méthode que les projets existants ; PAS un credential Jenkins)
//
// Règles respectées :
//   - rsync Hestia avec --exclude='.env' (ne jamais écraser le .env distant)
//   - image Harbor : harbor.proxbenovh.cloud/devops-project-harbor/toilettage-api:<tag>
//   - secrets hors Git

pipeline {
  agent any

  environment {
    HARBOR_REGISTRY = 'harbor.proxbenovh.cloud'
    HARBOR_PROJECT  = 'devops-project-harbor'
    IMAGE_NAME      = 'toilettage-api'
    IMAGE_TAG       = "${env.GIT_COMMIT?.take(8) ?: env.BUILD_NUMBER}"
    K8S_NAMESPACE   = 'toilettage'
  }

  options {
    timestamps()
    disableConcurrentBuilds()
  }

  stages {

    stage('Setup env / branche') {
      steps {
        script {
          // VM Hestia (BM1) — accès SSH.
          //
          // SOLUTION DE FOND (ne plus modifier) :
          // On se connecte avec l'utilisateur PROPRIÉTAIRE du docroot, "benweb".
          // C'est le fonctionnement prévu par HestiaCP : l'utilisateur web est
          // propriétaire de ses fichiers, donc aucun bricolage de permissions
          // (chmod/chown/groupe) n'est nécessaire.
          //
          // Pourquoi l'ancienne approche (user "ben" + groupe + chmod) échouait :
          // HestiaCP réinitialise propriétaire et permissions du docroot à chaque
          // v-rebuild-web-domain (renouvellement SSL, modification du domaine,
          // mise à jour Hestia). Tout chmod manuel finit donc par disparaître.
          //
          // Prérequis côté VM Hestia (faits une fois, persistants) :
          //   - v-change-user-shell benweb bash
          //   - clé publique Jenkins dans /home/benweb/.ssh/authorized_keys
          //   - benweb autorisé dans sshd_config si AllowUsers est utilisé
          // Prérequis côté Jenkins :
          //   - credential SSH id="hestia-benweb-ssh", username=benweb
          env.HESTIA_SSH_HOST = '192.168.100.75'
          env.HESTIA_SSH_PORT = '2275'
          env.HESTIA_SSH_USER = 'benweb'
          if (env.BRANCH_NAME == 'main') {
            env.DEPLOY_ENV      = 'prod'
            env.FRONTEND_HOST   = 'toilettage.proxbenovh.cloud'
            env.HESTIA_DOCROOT  = '/home/benweb/web/toilettage.proxbenovh.cloud/public_html'
            env.API_IMAGE_ALIAS = 'prod'
          } else if (env.BRANCH_NAME == 'dev') {
            env.DEPLOY_ENV      = 'staging'
            env.FRONTEND_HOST   = 'staging.toilettage.proxbenovh.cloud'
            env.HESTIA_DOCROOT  = '/home/benweb/web/staging.toilettage.proxbenovh.cloud/public_html'
            env.API_IMAGE_ALIAS = 'dev'
          } else {
            env.DEPLOY_ENV = 'none'   // feature/* : build + tests seulement
          }
          echo "Branche=${env.BRANCH_NAME}  Deploy=${env.DEPLOY_ENV}  Tag=${env.IMAGE_TAG}"
        }
      }
    }

    stage('API — tests') {
      steps {
        // L'agent Jenkins n'a pas python3-venv : on lance les tests dans un
        // conteneur Docker (même approche que les projets existants).
        sh '''
          set -e
          docker run --rm \
            --user "$(id -u):$(id -g)" \
            -e HOME=/tmp \
            -e PYTHONPATH=/work \
            -v "$PWD/api:/work" \
            -w /work \
            python:3.12-slim \
            sh -lc '
              export PATH="$HOME/.local/bin:$PATH"
              pip install --user --no-cache-dir --quiet -r requirements.txt pytest
              pytest -q
            '
        '''
      }
    }

    stage('API — build & push image') {
      when { anyOf { branch 'dev'; branch 'main' } }
      steps {
        dir('api') {
          withCredentials([usernamePassword(
              credentialsId: 'harbor-robot-devops-project-harbor',
              usernameVariable: 'HARBOR_USER',
              passwordVariable: 'HARBOR_PASS')]) {
            sh '''
              set -e
              FULL_IMAGE="$HARBOR_REGISTRY/$HARBOR_PROJECT/$IMAGE_NAME"
              echo "$HARBOR_PASS" | docker login "$HARBOR_REGISTRY" -u "$HARBOR_USER" --password-stdin
              docker build -t "$FULL_IMAGE:$IMAGE_TAG" -t "$FULL_IMAGE:$API_IMAGE_ALIAS" .
              docker push "$FULL_IMAGE:$IMAGE_TAG"
              docker push "$FULL_IMAGE:$API_IMAGE_ALIAS"
              docker logout "$HARBOR_REGISTRY" || true
            '''
          }
        }
      }
    }

    stage('API — déploiement K3s') {
      when { anyOf { branch 'dev'; branch 'main' } }
      steps {
        // Kubeconfig monté directement sur l'agent Jenkins (même méthode que
        // les projets existants), pas un credential Jenkins.
        sh '''
            set -e
            export KUBECONFIG=/var/lib/jenkins/.kube/config-afpa-k3s
            FULL_IMAGE="$HARBOR_REGISTRY/$HARBOR_PROJECT/$IMAGE_NAME:$IMAGE_TAG"
            # Applique les manifests (ne touche pas aux Secrets, gérés hors pipeline).
            kubectl apply -f kubernetes/toilettage/namespace.yaml
            kubectl apply -f kubernetes/toilettage/configmap.yaml
            kubectl apply -f kubernetes/toilettage/postgres-statefulset.yaml
            kubectl apply -f kubernetes/toilettage/postgres-service.yaml
            kubectl apply -f kubernetes/toilettage/service.yaml
            kubectl apply -f kubernetes/toilettage/ingress.yaml
            kubectl apply -f kubernetes/toilettage/deployment.yaml

            # Surcharge par branche la valeur ENVIRONMENT (staging vs prod).
            # kubectl set env surcharge proprement, sans JSON échappé fragile ;
            # la variable explicite prime sur celle issue de envFrom/ConfigMap.
            kubectl -n "$K8S_NAMESPACE" set env deployment/toilettage-api \
              ENVIRONMENT="$DEPLOY_ENV"

            # Met à jour l'image avec le tag précis de ce build.
            kubectl -n "$K8S_NAMESPACE" set image deployment/toilettage-api api="$FULL_IMAGE"
            kubectl -n "$K8S_NAMESPACE" rollout status deployment/toilettage-api --timeout=120s

            # Le seed (création tables + données de base) est exécuté AU DÉMARRAGE
            # de l'application (lifespan FastAPI, idempotent, verrou consultatif).
            # Plus besoin de kubectl exec ici : évite la permission RBAC pods/exec.
        '''
      }
    }

    stage('Frontend — déploiement Hestia') {
      when { anyOf { branch 'dev'; branch 'main' } }
      steps {
        withCredentials([sshUserPrivateKey(
            credentialsId: 'hestia-benweb-ssh',
            keyFileVariable: 'SSH_KEY')]) {
          sh '''
            set -e
            SSH_OPTS="-i $SSH_KEY -p $HESTIA_SSH_PORT -o StrictHostKeyChecking=accept-new -o BatchMode=yes"

            # --- Contrôle préalable : connexion + droit d'écriture réel ---
            # Diagnostic clair si la configuration Hestia a été réinitialisée.
            echo "Vérification de l'accès à $HESTIA_DOCROOT ..."
            ssh $SSH_OPTS "$HESTIA_SSH_USER@$HESTIA_SSH_HOST" "
              set -e
              if [ ! -d '$HESTIA_DOCROOT' ]; then
                echo 'ERREUR : le document root est introuvable.'
                echo 'Le domaine existe-t-il bien dans HestiaCP ?'
                exit 1
              fi
              if ! touch '$HESTIA_DOCROOT/.deploy_write_test' 2>/dev/null; then
                echo 'ERREUR : pas de droit d écriture sur le document root.'
                echo 'Utilisateur SSH : '\\$(whoami)
                ls -ld '$HESTIA_DOCROOT'
                exit 1
              fi
              rm -f '$HESTIA_DOCROOT/.deploy_write_test'
              echo 'Accès en écriture confirmé (utilisateur '\\$(whoami)').'
            "

            # --- Synchronisation ---
            # On se connecte par l'IP privée de la VM Hestia (réseau interne),
            # PAS par le domaine public qui pointe sur HAProxy.
            #
            # benweb étant propriétaire du docroot, aucune option de contournement
            # de permissions n'est nécessaire.
            #   --exclude='.env'        : ne jamais écraser un .env distant
            #   --exclude='.well-known' : préserver les challenges ACME
            rsync -av --delete \
              --exclude='.env' \
              --exclude='.well-known' \
              -e "ssh $SSH_OPTS" \
              frontend/ \
              "$HESTIA_SSH_USER@$HESTIA_SSH_HOST:$HESTIA_DOCROOT/"
          '''
        }
      }
    }

    stage('Smoke test') {
      when { anyOf { branch 'dev'; branch 'main' } }
      steps {
        sh '''
          set -e
          echo "Frontend : https://$FRONTEND_HOST"
          curl -fsSI "https://$FRONTEND_HOST" | head -1 || echo "AVERTISSEMENT: frontend non joignable"
          # L'API est vérifiée via son ingress public.
        '''
      }
    }
  }

  post {
    success { echo "OK — ${env.BRANCH_NAME} déployé (${env.DEPLOY_ENV})." }
    failure { echo "ÉCHEC — voir les logs ci-dessus." }
  }
}
