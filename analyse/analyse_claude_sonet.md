# Analyse de `app.py`

Application Flask (751 lignes) du cabinet de neurologie : patients, rendez-vous, comptes-rendus de consultation. Tout le HTML est généré en Python (f-strings), sans gabarit. Persistance SQLite via `sqlite3`, une connexion par requête (`contextlib.closing`). 13 routes.

Conclusion : code propre, cohérent avec `SPECIFICATION.md`, échappement et requêtes paramétrées corrects. Les points à traiter sont (1) le chemin relatif de la base, (2) les clés étrangères non appliquées, (3) `debug=True` en dur. Les risques de sécurité (authentification, CSRF) sont connus et acceptés par la spec pour un usage local.

## 1. Structure

| Section | Lignes | Rôle |
|---|---|---|
| Docstring, imports | 1–24 | Présentation, `re`, `sqlite3`, `closing`, `date/datetime`, Flask, `escape` |
| Constantes | 26–75 | `PAGES`, `CHAMPS_*`, `SEXES`, `STATUTS_RDV`, `ID_MAX`, `CSS` |
| Base et utilitaires | 78–158 | connexion, `entier`, `date_valide`, `heure_valide`, `chercher_ou_404`, `patient_existe`, `lire_formulaire`, `ou_null`, `afficher` |
| Rendu HTML commun | 161–231 | `menu`, `page`, `bouton`, `champ_*`, `options_patients`, `formulaire` |
| Patients | 234–400 | validation, liste, création, fiche, modification |
| Rendez-vous | 402–537 | validation, liste, création, modification, suppression |
| Comptes-rendus | 540–748 | validation, normalisation, liste (filtre médecin), création, détail, modification |

Routes : `/`, `/patients`, `/patients/nouveau`, `/patients/<id>`, `/patients/<id>/modifier`, `/rendez-vous`, `/rendez-vous/nouveau`, `/rendez-vous/<id>/modifier`, `/rendez-vous/<id>/supprimer` (POST), `/consultations`, `/consultations/nouveau`, `/consultations/<id>`, `/consultations/<id>/modifier`.

## 2. Points forts

- **SQL paramétré** pour toutes les valeurs saisies. Les noms de colonnes interpolés dans les `INSERT`/`UPDATE` proviennent uniquement de constantes (`CHAMPS_*`).
- **Échappement** : `markupsafe.escape` appliqué aux saisies (nom, prénom, motif, médecin, valeur de filtre, titres). Vérifié : `/consultations?medecin=<script>…` renvoie `&lt;script&gt;` et aucun `<script>` brut.
- **Identifiants bornés** : `entier()` rejette `0`, les non-numériques et tout entier > `2**63-1`; `chercher_ou_404` renvoie 404 avant d'appeler SQLite (évite `OverflowError`). Vérifié : `/patients/99999999999999999999`, `/consultations/99999999999999999999`, `/patients/0` → 404.
- **Validation serveur** avec réaffichage des valeurs saisies (`formulaire()` + `message_erreur()`).
- **Patron POST/Redirect/GET** respecté sur toutes les écritures.
- **Cohérence métier** : contrôle que le RDV lié appartient au patient choisi (`valider_consultation`) ; suppression d'un RDV qui détache les comptes-rendus (`rendez_vous_id = NULL`) au lieu de les supprimer.
- **Dates** : `date_valide` combine regex et `strptime`. Vérifié : les chiffres Unicode (`٢٠٢٤-٠١-٠١`) passent la regex mais sont rejetés par `strptime`; pas d'anomalie.

## 3. Problèmes identifiés

### 3.1 Robustesse et bugs

| # | Problème | Emplacement | Gravité |
|---|---|---|---|
| R1 | **Chemin relatif** `database/cabinet.db`, résolu par rapport au répertoire courant. Lancer depuis un autre dossier : `sqlite3.connect` crée une base vide et l'application lève `no such table` (500). Non testé, déduit du code. | `se_connecter_a_la_base` | Moyenne |
| R2 | **Clés étrangères non appliquées.** Le schéma (`create_db.py`) déclare `FOREIGN KEY`, mais SQLite ne les active que avec `PRAGMA foreign_keys = ON`, absent du code. L'intégrité repose uniquement sur la validation Python. Sans effet visible aujourd'hui (aucune suppression de patient). | `se_connecter_a_la_base` | Faible |
| R3 | **`ORDER BY` sans clé de départage** pour les RDV : `date_rdv, heure_rdv` seul dans `liste_rendez_vous`, `fiche_patient`, `patients_et_rendez_vous`. Deux RDV à la même date et heure ont un ordre non déterministe. Les comptes-rendus, eux, ont `, id`. | `liste_rendez_vous`, `fiche_patient`, `patients_et_rendez_vous` | Faible |
| R4 | **Aucune gestion d'erreur SQL** autour des `INSERT`/`UPDATE` : une exception non prévue donne une 500. Acceptable en usage local ; la page de debug expose la trace. | Routes POST | Faible |
| R5 | **Pas de limite de longueur** sur les champs texte (`textarea`, `input`). | `champ_saisie`, `champ_texte_long` | Faible |
| R6 | **Syntaxe Python 3.12+** : guillemets identiques imbriqués dans les f-strings (`f"…{bouton(f'/consultations/{cr['id']}', …)}…"`, dans `fiche_patient` et `modifier_compte_rendu`). Non compatible avec Python 3.11 et antérieur (PEP 701). Non documenté dans l'en-tête. | `fiche_patient`, `modifier_compte_rendu` | Faible |

### 3.2 Sécurité et conformité (données médicales)

La spec (section « Limites connues ») acte : usage local, poste unique, aucune authentification ni CSRF. Ces points restent des risques si l'application est exposée sur un réseau.

| # | Problème | Gravité |
|---|---|---|
| S1 | **Aucune authentification.** Antécédents, diagnostics et traitements sont accessibles à quiconque atteint le serveur. | Haute si réseau élargi |
| S2 | **Aucune protection CSRF** sur les POST (création, modification, suppression de RDV). Un site tiers peut soumettre ces formulaires depuis le navigateur d'un utilisateur connecté au réseau. | Haute si exposé |
| S3 | **`app.run(debug=True)` en dur** (ligne 751) : console Werkzeug interactive, exécution de code à distance si atteignable. À piloter par variable d'environnement, désactivé par défaut. | Haute si exposé |
| S4 | **Pas de journal d'audit** (qui consulte ou modifie un dossier) ; pas de HTTPS dans le code. | Moyenne (données de santé) |
| S5 | **Suppression sans historique** : seule la suppression de RDV existe, sans trace. | Faible (conforme spec) |

### 3.3 Maintenabilité

- **Liste des sexes dupliquée** : `formulaire_patient` redéfinit `[("", "—"), ("F", "F"), ("M", "M"), ("Autre", "Autre")]` au lieu d'utiliser `SEXES`. Risque de divergence au prochain changement.
- **Patron INSERT/UPDATE répété trois fois** (patients, RDV, consultations) avec la même construction de requête. Un helper générique réduirait la duplication.
- **`valeurs_depuis_formulaire_*`** : trois fonctions quasi identiques (`patient`, `rendez-vous`, `consultation`) ; seule la lecture diffère par le `CHAMPS_*` utilisé. `lire_formulaire(CHAMPS_…)` suffit déjà.
- **Requête patients en double** : `liste_patients` réécrit `liste_des_patients` avec une colonne de plus.
- **Fonctions longues** : `fiche_patient` (~55 lignes) mélange requêtes, mise en forme et rendu HTML.
- **Pas de tests automatisés** (confirmé par la spec). Les validations `entier`/`ID_MAX`, `valider_consultation` et `valider_rendez_vous` sont des cibles naturelles.

## 4. Vérifications effectuées

| Vérification | Méthode | Résultat |
|---|---|---|
| `entier` : overflow, zéro, borne `2**63-1` | `import app` puis appel direct | `None`, `None`, `9223372036854775807` |
| Routes avec identifiant hors plage ou inexistant | `app.test_client().get(...)` (lecture seule) | 404 pour les cinq cas testés |
| Échappement du filtre `medecin` | `GET /consultations?medecin=<script>…` | Échappé, pas de `<script>` brut |
| Dates Unicode | `re.fullmatch` + `strptime` | Regex accepte, `strptime` rejette : pas de bug |
| Schéma SQL et clés étrangères | Lecture de `database/create_db.py` ; absence de `PRAGMA` dans `app.py` | Clés déclarées, non activées |
| Conformité à la spec | Comparaison routes, validations, messages avec `SPECIFICATION.md` | Concordant ; limites connues confirmées |

Non vérifié : comportement avec un chemin de lancement différent (R1), comportement sous Python < 3.12 (R6), charge et accès concurrents.

## 5. Recommandations priorisées

1. **R1** : chemin absolu basé sur le fichier, par exemple `Path(__file__).resolve().parent / "database" / "cabinet.db"`.
2. **S3** : `debug` piloté par variable d'environnement (`FLASK_DEBUG`), désactivé par défaut.
3. **R2** : ajouter `PRAGMA foreign_keys = ON` dans `se_connecter_a_la_base`. Vérifier qu'aucun flux existant ne viole les clés (aucun flux connu ne le fait).
4. **M1** : `formulaire_patient` utilise `SEXES` (avec libellé `"—"` pour la valeur vide).
5. **R3** : ajouter `, id` aux `ORDER BY` des RDV.
6. **R6** : documenter la version minimale de Python (3.12) dans `README.md` ou remplacer les guillemets imbriqués par des variables intermédiaires.
7. **S1, S2, S4** : hors périmètre de la spec (usage local). À traiter avant tout déploiement réseau : authentification, protection CSRF (par exemple Flask-WTF), HTTPS, journal d'audit.
8. **Tests** : ajouter une suite ciblée sur `entier`, `date_valide`, `valider_rendez_vous`, `valider_consultation` et sur les routes 404.
