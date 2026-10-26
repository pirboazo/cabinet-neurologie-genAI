# Analyse de `app.py`

**Verdict :** application Flask monolithique (830 lignes) pour un cabinet de neurologie : patients, rendez-vous, comptes-rendus de consultation, stockage SQLite. Un bug bloquant est confirmé : le formulaire patient ne fonctionne pas. Le reste relève de la dette technique et de risques de sécurité classiques.

## 1. Structure

| Zone | Lignes | Contenu |
|---|---|---|
| Imports et constantes | 1-49 | Champs, statuts, `SEXES` |
| Helpers HTML | 52-107 | Connexion SQLite, `menu()`, `page()` avec CSS inline |
| Validation | 110-152 | `_strp_date`, `_strp_heure`, `_existe_*` |
| Formulaires | 154-365 | Patient, rendez-vous, consultation |
| Routes | 368-824 | 13 routes |
| Lancement | 827-829 | `app.run(debug=True)` |

## 2. Bug confirmé

### B1. Formulaire patient inutilisable (critique)

- **Où :** `formulaire_patient`, lignes 189-196.
- **Cause :** les lignes sont assemblées par `'...' + v("nom") + '...'`. `v()` renvoie un `Markup` (`escape()`). Avec `str + Markup`, MarkupSafe échappe la chaîne littérale, donc tout le HTML devient du texte.
- **Preuve :** `formulaire_patient('/patients/nouveau', {'nom': 'Dupont'})` ne contient aucune balise `<input>`. La sortie contient `&lt;div class=&#34;champ&#34;&gt;&lt;label&gt;Nom&lt;/label&gt;&lt;input …`.
- **Impact :** création (ligne 395) et modification (ligne 492) de patient impossibles. [INFERENCE] Le formulaire soumet sans champs, donc l'erreur « Le nom et le prénom sont obligatoires » s'affiche à chaque envoi.
- **Correctif :** construire ces lignes en f-string avec `{v("nom")}`, comme dans `formulaire_rendez_vous`.

## 3. Sécurité

| Risque | Lignes | Gravité | Détail |
|---|---|---|---|
| Échappement incohérent | 384-385, 439, 462, 478, 539, 761, 764 | Faible | Dates, statut et `rdv_date` sortis sans `escape()`. Valeurs validées côté serveur, donc exploitation peu probable, mais la règle n'est pas uniforme. |
| Pas de protection CSRF | 395, 492, 550, 577, 617, 693, 776 | Moyenne | Aucun jeton sur les POST. La suppression de RDV (617) n'est protégée que par `confirm()` côté client (275). |
| Pas d'authentification | Toutes les routes | Élevée si exposé | Antécédents, diagnostics et traitements accessibles sans connexion. Données de santé. |
| `debug=True` | 829 | Moyenne si exposé | Le debugger Werkzeug permet l'exécution de code. Sûr uniquement avec le bind par défaut `127.0.0.1`. |
| SQL construit par f-string | 413, 515, 655 | Faible | Les noms de colonnes viennent de constantes, les valeurs sont paramétrées. Sûr aujourd'hui, pattern fragile. |

**Points positifs :** valeurs SQL paramétrées, `escape()` sur la plupart des saisies, contrôle d'appartenance RDV/patient (321), pattern POST-redirect-GET.

## 4. Bugs et robustesse

- **L338 :** `str.isdigit()` accepte `"²"`, mais `int("²")` lève `ValueError`. La valeur vient de `request.form` (715, 800), donc une erreur 500 est possible. [INFERENCE] comportement Python standard, non exécuté.
- **L111, `_strp_date` :** `date.fromisoformat` (Python ≥ 3.11) accepte aussi `20261026`, alors que le commentaire (115) annonce AAAA-MM-JJ. Le nom est trompeur, il n'y a pas de `strptime`.
- **L53 :** chemin relatif `database/cabinet.db`, qui dépend du répertoire de lancement.
- **Connexions :** `close()` manuel dans chaque branche. Une exception (ex. `IntegrityError`) laisse la connexion ouverte, sans `rollback` explicite.
- **L414 et L569 :** `SELECT last_insert_rowid()` au lieu de `cursor.lastrowid`. `new_id` (569) n'est jamais utilisé.
- **L566 :** `'prévu'` codé en dur alors que `vals["statut"]` vaut déjà `"prévu"` (230).
- **L786 :** `str(...) if … is not None else ""` redondant après `or ""`.

## 5. Code mort

| Ligne | Élément | Statut |
|---|---|---|
| 10 | `Iterable` | Importé, non utilisé |
| 37 | `CHAMPS_RDV` | Défini, non référencé |
| 40 | `CHAMPS_CONSULTATION` | Défini, non référencé |
| 569 | `new_id` | Affecté, non utilisé |

## 6. Maintenabilité

- **Duplication :**
  - Parsing de `patient_id` (206-210 et 297-302).
  - Mapping des valeurs INSERT/UPDATE (565-568 et 601-611, 718-733 et 803-821).
  - `int(vals["patient_id"] or "0")` répété 5 fois (567, 571, 604, 724, 811).
- **HTML par concaténation :** presque toutes les fonctions. Aucun template Jinja alors que Flask est utilisé. Le CSS de 35 lignes (68-103) est renvoyé à chaque page.
- **URLs en dur** mélangées à `url_for` : 387, 542, 667, 684 contre 371, 383, 449-451.
- **Transactions :** pas de `try`/`rollback`, pas de gestion d'erreur autre que `abort(404)`.
- **Documentation :** la docstring renvoie à `SPECIFICATION.md`, dont l'existence n'a pas été vérifiée.

## 7. Plan priorisé

1. **Corriger `formulaire_patient`** (B1). Bloquant.
2. **Uniformiser l'échappement** sur toutes les sorties (384-385, 439, 462, 478, 539, 761, 764), ou passer aux templates Jinja avec autoescape.
3. **Gérer les connexions** avec un context manager ou un teardown, et ajouter un `rollback` en cas d'erreur.
4. **Rendre le chemin de la base configurable** (variable d'environnement ou `app.config`).
5. **Sécuriser l'exposition :** CSRF (Flask-WTF), authentification si l'application sort de la machine locale, `debug` piloté par variable d'environnement.
6. **Nettoyer :** imports et constantes morts, `lastrowid`, remplacer `isdigit()` + `int()` par un helper de conversion sûr.
7. **Factoriser :** helpers `_patient_id` et `_params_consultation`, puis templates.

**Méthode :** B1 a été exécuté et reproduit. Les autres points sont issus de la lecture du code, sans exécution.
