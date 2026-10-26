# Analyse de `app.py`

Application Flask (727 lignes) du cabinet de neurologie : gestion des patients, des rendez-vous et des comptes-rendus de consultation. Tout le HTML est généré en Python (f-strings), sans gabarit externe, SQLite via `sqlite3`.

## 1. Structure

| Section | Lignes (approx.) | Rôle |
|---|---|---|
| Constantes | 27–69 | `PAGES`, `SEXES`, `STATUTS_RDV`, `CHAMPS_*`, `CSS` |
| Base et utilitaires | 72–137 | connexion SQLite, `chercher_ou_404`, échappement, validation id/date/heure |
| Rendu HTML commun | 140–218 | `menu`, `page`, `tableau`, champs de formulaire, boutons |
| Patients | 220–386 | liste, création, fiche, modification |
| Rendez-vous | 389–512 | liste, création, modification, suppression |
| Comptes-rendus | 515–723 | liste (filtre médecin), création, détail, modification |

Routes : 14 au total (`/`, `/patients*`, `/rendez-vous*`, `/consultations*`). Lancement : `app.run(debug=True)`.

## 2. Points forts

- **Échappement centralisé** : `echapper()` / `afficher()` s'appuient sur `markupsafe.escape`, qui protège aussi les guillemets (utile dans les attributs `value="..."`).
- **SQL paramétré** partout pour les valeurs saisies (`?`). Le seul SQL dynamique (`f"SELECT * FROM {table}"` dans `chercher_ou_404`) n'utilise que des noms codés en dur, documenté dans la docstring.
- **Connexions fermées** systématiquement via `contextlib.closing`.
- **Validation** des identifiants (`id_valide`), dates et heures (regex + `strptime`) avant insertion.
- **Patron POST/Redirect/GET** respecté : succès → `redirect`, erreur → réaffichage du formulaire avec les valeurs saisies.
- **Cohérence métier** : suppression d'un rendez-vous conserve les comptes-rendus (`rendez_vous_id = NULL`), contrôle que le rendez-vous appartient au patient choisi.
- Pas d'import inutilisé ; docstrings et commentaires utiles.

## 3. Problèmes identifiés

### 3.1 Bugs

| # | Problème | Emplacement | Gravité |
|---|---|---|---|
| B1 | **Erreur 500 sur identifiant trop grand.** `id_valide` accepte n'importe quel nombre de chiffres ; `sqlite3` lève `OverflowError` au-delà de 64 bits. Constaté : `GET /consultations/99999999999999999999` → **500**, et `GET /patients/99999999999999999999` → `OverflowError` non capturée. Idem pour `patient_id` / `rendez_vous_id` postés dans les formulaires (via `patient_existe` / `valider_consultation`). | `id_valide`, `chercher_ou_404`, `patient_existe`, `valider_consultation` | Moyenne |
| B2 | **Chemin de base relatif** `database/cabinet.db` : résolu par rapport au répertoire courant, pas au fichier. Lancer depuis un autre dossier crée silencieusement une base vide (`sqlite3.connect` crée le fichier) et provoque des `no such table`. | `se_connecter_a_la_base` | Moyenne |
| B3 | **Pas de vérification de chevauchement** des rendez-vous : deux rendez-vous peuvent être pris au même créneau pour le même médecin. (À confronter à `SPECIFICATION.md`.) | `valider_rendez_vous` | [INFERENCE] à confirmer |

### 3.2 Sécurité et conformité (données médicales)

| # | Problème | Gravité |
|---|---|---|
| S1 | **Aucune authentification** : toutes les routes (dossiers patients, comptes-rendus, suppression) sont accessibles à quiconque atteint le serveur. | Haute |
| S2 | **Aucune protection CSRF** visible sur les formulaires POST (création, modification, suppression). | Haute si l'app est accessible depuis un navigateur tiers |
| S3 | **`debug=True`** dans `app.run` : expose le debugger Werkzeug (exécution de code à distance si l'interface est atteignable). À désactiver hors développement. | Haute si déployé |
| S4 | **Aucune trace d'audit** (qui consulte / modifie / supprime un dossier) ni journalisation : exigence fréquente pour des données de santé. La suppression de rendez-vous est physique, sans historique. | Moyenne |
| S5 | Pas de HTTPS ni de configuration de déploiement dans le fichier (hors périmètre si géré en amont). | [INFERENCE] selon déploiement |

### 3.3 Cohérence de l'échappement

La règle énoncée dans la docstring de `echapper` (« toute saisie passe par ici ») n'est pas appliquée partout. Valeurs affichées **sans** échappement :

- `fiche_patient` : `rdv["date_rdv"]`, `rdv["heure_rdv"]`, `rdv["statut"]`, `cr["date_consultation"]`
- `liste_rendez_vous` : `rdv["date_rdv"]`, `rdv["heure_rdv"]`, `rdv["statut"]`
- `liste_consultations` : `cr["date_consultation"]`
- `detail_consultation` : `cr['date_consultation']` dans le corps

Risque actuel faible : ces valeurs sont des dates validées ou des statuts issus d'une liste fermée. Mais un `statut` ou une date écrite directement en base (import, script) passerait sans protection. Correction simple : passer par `afficher()`/`echapper()` partout.

### 3.4 Maintenabilité

- **Duplication** :
  - trois fonctions identiques `valeurs_depuis_formulaire_*` (patient, rendez-vous, consultation) ;
  - listes de colonnes des `INSERT` / `UPDATE` écrites à la main alors que `CHAMPS_*` existent déjà ;
  - construction des options `patients` répétée dans `formulaire_rendez_vous` et `formulaire_consultation` ;
  - `liste_des_patients` existe, mais des requêtes équivalentes sont réécrites ailleurs.
- **Fichier unique de 727 lignes** mélangeant accès données, validation et HTML. Le choix « sans gabarit externe » est explicite dans la docstring ; il rend la maintenance du HTML (`page`, formulaires) plus pénible à mesure que l'interface grossit.
- **Requêtes non filtrées** : `patients_et_rendez_vous` charge tous les rendez-vous pour alimenter le select du formulaire de compte-rendu. Acceptable à petite échelle, à surveiller.
- **Champ `medecin` en texte libre** : `DISTINCT medecin` et le filtre sont sensibles aux fautes de frappe (« Dr Martin » / « Dr. Martin » → deux entrées).
- **Pas de gestion d'erreur globale** (`errorhandler`) ni de logging : les exceptions remontent en 500 brut (cf. B1).
- **Contraintes de clés étrangères** : `PRAGMA foreign_keys` n'est pas activé ici ; la cohérence à la suppression repose sur le `UPDATE` manuel. Vérifier le schéma SQL.

## 4. Recommandations priorisées

1. **Authentification + protection CSRF** (S1, S2) avant tout usage réel ; traçabilité des accès (S4).
2. **Désactiver `debug=True`** hors développement, ou le piloter par variable d'environnement (S3).
3. **Borner les identifiants** dans `id_valide` (ex. `0 < valeur < 2**63`) et/ou capturer `OverflowError` ; ajouter un `errorhandler(404/500)` (B1).
4. **Chemin de la base absolu**, relatif au fichier (`Path(__file__).parent / "database" / "cabinet.db"`), et erreur explicite si le fichier est absent (B2).
5. **Uniformiser l'échappement** : tout passer par `afficher()` (§3.3).
6. **Factoriser** : un seul `valeurs_depuis_formulaire(champs)`, `INSERT`/`UPDATE` construits à partir de `CHAMPS_*`, options de patients partagées (§3.4).
7. Décider de la règle de chevauchement des rendez-vous (B3) et, à terme, de la normalisation du champ `medecin`.
8. Découper en modules (`db.py`, `rendu.py`, `routes/…`) si l'application grossit ; envisager Jinja2 si le HTML devient difficile à maintenir.

## 5. Vérifications effectuées

- Lecture intégrale de `app.py` (727 lignes).
- Test de débordement : `sqlite3` lève `OverflowError: Python int too large to convert to SQLite INTEGER` pour un entier de 20 chiffres.
- Requêtes GET de test via le client Flask (lecture seule, base réelle) :
  - `/consultations/99999999999999999999` → HTTP 500 ;
  - `/patients/99999999999999999999` → `OverflowError` non capturée.
- Non vérifié : comportement en production, contenu de `SPECIFICATION.md` et schéma SQL (clés étrangères, index, contraintes).
