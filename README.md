# Sondages présidentielle 2027

Page statique qui montre l'évolution des intentions de vote au premier tour, par candidat, institut et période. Elle est publiée sur GitHub Pages et se met à jour deux fois par jour.

## Fonctionnement

- `scripts/update_polls.py` lit le tableau Wikipédia « Liste de sondages sur l'élection présidentielle française de 2027 » (API MediaWiki) et écrit `site/data/polls.json`.
- `site/index.html` charge ce JSON et dessine le graphique avec d3 (embarqué dans `site/vendor/`). Aucune étape de build.
- `.github/workflows/update.yml` s'exécute deux fois par jour, à 05:17 et 16:17 UTC, lance les tests, met à jour le JSON, le commit s'il a changé, puis déploie `site/` sur Pages.
- Le script refuse d'écraser les données s'il trouve moins de 40 sondages (tableau cassé ou source indisponible).

## Mise en service

1. Pousser ce dépôt sur GitHub (branche `main`).
2. **Settings → Pages → Build and deployment → Source : GitHub Actions.**
3. **Actions → Mise à jour des sondages et déploiement → Run workflow** pour le premier déploiement.

L'adresse sera `https://<utilisateur>.github.io/<dépôt>/`.

## En local

```sh
pip install -r requirements.txt
python -I -m unittest discover -s tests
python scripts/update_polls.py          # met à jour site/data/polls.json
cd site && python -m http.server 8000   # http://localhost:8000
```

## Limites

- Les données viennent de Wikipédia, pas des notices de la Commission des sondages. Les lignes à la mise en forme irrégulière sont ignorées (le script en affiche le nombre).
- GitHub désactive les workflows planifiés après 60 jours sans activité sur le dépôt. Les commits quotidiens de données comptent comme activité tant que les sondages évoluent ; sinon, relancez le workflow à la main.
- Les heures de déclenchement du cron peuvent être retardées de quelques minutes.
