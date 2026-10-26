# Analyse de `app.py`

Application Flask de gestion d'un cabinet de neurologie : patients, rendez-vous, comptes-rendus de consultation. Stockage SQLite (`database/cabinet.db`), HTML généré par f-strings.

Analyse statique du fichier (1071 lignes). Aucun test ni exécution.

## 1. Résumé

- Code lisible, structuré par routes, validateurs et générateurs HTML. Requêtes SQL paramétrées partout : pas d'injection SQL détectée.
- **Risque majeur : données médicales sans authentification, sans protection CSRF, avec le debugger Werkzeug activé.** Ce point prime sur tout le reste.
- Échappement HTML incohérent : plusieurs champs issus de la base sont insérés sans `escape()`.
- Intégrité métier fragile : la modification d'un rendez-vous peut casser l'invariant « le RDV appartient au patient du compte-rendu ».
- Génération HTML manuelle et répétitive : source d'erreurs d'échappement et de maintenance difficile.

## 2. Structure du fichier

| Zone | Lignes | Rôle |
|---|---|---|
| Imports, constantes | 15–60 | Listes de champs (`CHAMPS_*`), statuts, sexes |
| CSS | 62–166 | Feuille de style inline dans une constante |
| Accès base | 169–172 | `se_connecter_a_la_base()` (chemin relatif) |
| Rendu HTML | 175–200, 203–438 | `menu`, `page`, `champ`, `bloc_formulaire`, `formulaire_*` |
| Validation | 210–237, 337–423 | `date_valide`, `heure_valide`, `entier`, `valider_rendez_vous`, `valider_consultation` |
| Routes | 451–1067 | 13 routes, voir tableau ci-dessous |
| Lancement | 1070–1071 | `app.run(debug=True)` |

### Routes

| Méthodes | URL | Fonction | Lignes |
|---|---|---|---|
| GET | `/` | `accueil` | 451 |
| GET | `/patients` | `liste_patients` | 456 |
| GET, POST | `/patients/nouveau` | `nouveau_patient` | 489 |
| GET | `/patients/<id>` | `fiche_patient` | 528 |
| GET, POST | `/patients/<id>/modifier` | `modifier_patient` | 622 |
| GET | `/rendez-vous` | `liste_rendez_vous` | 674 |
| GET, POST | `/rendez-vous/nouveau` | `nouveau_rendez_vous` | 716 |
| GET, POST | `/rendez-vous/<id>/modifier` | `modifier_rendez_vous` | 756 |
| POST | `/rendez-vous/<id>/supprimer` | `supprimer_rendez_vous` | 812 |
| GET | `/consultations` | `liste_consultations` | 832 |
| GET, POST | `/consultations/nouveau` | `nouveau_compte_rendu` | 909 |
| GET | `/consultations/<id>` | `detail_consultation` | 958 |
| GET, POST | `/consultations/<id>/modifier` | `modifier_compte_rendu` | 1013 |

## 3. Points positifs

- **SQL paramétré** partout (`?`), y compris les filtres (`medecin`, L859–860).
- **Validation centralisée** : `valider_rendez_vous` (L362) et `valider_consultation` (L391) vérifient l'existence du patient, le format de date/heure, le statut et la cohérence RDV/patient (L412).
- **`escape()` systématique** sur la plupart des valeurs saisies (`champ`, `afficher`, `page`).
- **404 explicites** sur les ressources inexistantes (`abort(404)`).
- **Suppression de RDV** : détache d'abord les consultations liées (L822–826) puis supprime, dans une seule transaction.
- Docstring de module claire ; fonctions courtes et nommées en français, cohérentes avec le domaine.

## 4. Problèmes identifiés

### 4.1 Critiques / hautes

| # | Sévérité | Lignes | Problème | Recommandation |
|---|---|---|---|---|
| 1 | Critique | toutes les routes | **Aucune authentification ni autorisation.** Dossiers patients (antécédents, diagnostics, traitements) accessibles à quiconque atteint le serveur. | Ajouter une authentification (Flask-Login ou équivalent) et des contrôles d'accès par route. |
| 2 | Critique | 1071 | **`app.run(debug=True)`** : console Werkzeug interactive, exécution de code à distance si l'application est exposée. | Désactiver le debug hors développement (variable d'environnement, `FLASK_DEBUG`). |
| 3 | Haute | 329, 444–447, tous les `POST` | **Pas de protection CSRF.** Un site tiers peut déclencher création, modification ou suppression (`/rendez-vous/<id>/supprimer`). | Ajouter des jetons CSRF (Flask-WTF ou jeton de session vérifié sur chaque POST). |
| 4 | Haute | 170 | **Données de santé en clair** dans un fichier SQLite à chemin relatif. Sauvegardes, droits d'accès fichier et chiffrement non traités dans le code. | Chemin configurable, permissions restrictives, chiffrement au repos selon les exigences (RGPD art. 9, HDS). |

### 4.2 Moyennes

| # | Sévérité | Lignes | Problème | Recommandation |
|---|---|---|---|---|
| 5 | Moyenne | 773–775 | **Invariant cassé.** `modifier_rendez_vous` peut changer `patient_id` d'un RDV déjà lié à une consultation. La consultation garde son ancien `patient_id`, alors que L412 impose que le RDV appartienne au patient. | Interdire le changement de patient si des consultations sont liées, ou mettre à jour / détacher ces consultations dans la même transaction. |
| 6 | Moyenne | 474, 558, 578–579, 581, 597, 690–691, 695, 887, 985, 995 | **Échappement incohérent.** Dates, heures et statuts issus de la base sont insérés sans `escape()`. Risque faible aujourd'hui (valeurs validées), mais c'est une faille latente si une valeur non contrôlée entre en base. | Échapper toutes les valeurs dynamiques, ou passer à un moteur de templates (Jinja2 avec auto-échappement). |
| 7 | Moyenne | 327 | `erreur` est injecté sans échappement dans `bloc_formulaire`. Le commentaire L326 le justifie, mais la garantie repose sur la discipline des appelants. | Échapper `erreur` dans la fonction. |
| 8 | Moyenne | 458, 495, 530, 624, 676, 718, 758, 814, 836, 911, 960, 1015 | **Connexions SQLite non fermées sur exception.** Ouverture et fermeture manuelles dans chaque route, sans `try/finally` ni gestionnaire de contexte. Une exception (ex. `IntegrityError`) laisse la connexion ouverte. | Gestionnaire de contexte ou `try/finally`, ou fixture Flask `teardown_appcontext`. |
| 9 | Moyenne | 748, 800 | Requête inutile : `patients_et_rendez_vous` charge toute la liste des RDV alors que `formulaire_rendez_vous` ne l'utilise pas. Coût croissant avec le volume. | Séparer la requête des patients de celle des RDV. |
| 10 | Moyenne | 170 | Chemin `database/cabinet.db` relatif au répertoire courant : l'application échoue ou crée une base vide si lancée d'ailleurs. | Chemin basé sur `Path(__file__).parent`, ou variable de configuration. |

### 4.3 Basses / maintenabilité

| # | Sévérité | Lignes | Problème | Recommandation |
|---|---|---|---|---|
| 11 | Basse | 266–322 | `champ` gère 7 types de contrôles dans une seule fonction à branches `if/elif`. | Table de rendus par type, ou macros Jinja2. |
| 12 | Basse | 175–1067 | HTML construit par f-strings sur ~900 lignes (cause principale des points 6 et 7). | Templates Jinja2 : séparation présentation / logique. |
| 13 | Basse | 622–630, 757–764, 812–820, 958–972, 1013–1021 | Motif répété « récupérer ou 404 » et « fermer la connexion » dans chaque route. | Fonction utilitaire `charger_ou_404(...)`. |
| 14 | Basse | 392–423 vs 362–377 | Signatures incohérentes : `valider_consultation` retourne 4 valeurs, `valider_rendez_vous` en retourne 3. | Uniformiser (ex. objet résultat ou `dataclass`). |
| 15 | Basse | 230–237 | `entier` accepte `"+5"`, `" 5"`, `"1_0"` (règles `int()` de Python). Sans effet grave ici, mais imprécis pour une validation. | Regex `^\d+$` avant conversion. |
| 16 | Basse | 210–227 | Validation de date/heure sans contrôle de plausibilité : date de naissance future, RDV dans le passé, date de consultation future acceptées. | Ajouter les règles métier si elles sont attendues. |
| 17 | Basse | 169–172 | Pas de `PRAGMA foreign_keys = ON`. L'intégrité repose sur le code applicatif (ex. L823). [INFERENCE] : le schéma SQL n'a pas été lu. | Vérifier le schéma et activer les clés étrangères. |
| 18 | Basse | 62–166 | CSS inline dans une constante Python. | Fichier `static/style.css`. |

## 5. Recommandations prioritaires

1. **Sécurité (avant toute mise en service) :** authentification, protection CSRF, `debug=False`, chemin de base configurable et protégé (points 1 à 4).
2. **Intégrité :** corriger le changement de patient d'un RDV lié à des consultations (point 5).
3. **Robustesse :** gestion des connexions avec `try/finally` ou contexte (point 8).
4. **Maintenabilité :** migrer le HTML vers Jinja2 (points 6, 7, 11, 12). C'est le correctif structurel des problèmes d'échappement.
5. **Nettoyage :** factoriser les 404, supprimer la requête inutile, uniformiser les validateurs (points 9, 13, 14).

## 6. Limites de l'analyse

- Analyse statique du seul `app.py`. Les templates, la configuration, les tests et le schéma SQL n'existent pas dans le périmètre lu.
- Aucun test ni exécution de l'application : les comportements décrits sont déduits du code.
- Les points de sécurité sont évalués en contexte « application exposée sur un réseau » ; un usage strictement local réduit la sévérité des points 1 à 4 sans la supprimer.
