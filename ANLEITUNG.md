# Anleitung: GitHub-Profil und Startseite veröffentlichen

Dieser Ordner ist das komplette Profil-Repo. Er wird 1:1 als Inhalt von `Fluory/Fluory` übernommen.

```
README.md        → erscheint auf github.com/Fluory
assets/          → animierte SVGs (Banner + Projektkarten, hell und dunkel)
docs/            → Startseite für GitHub Pages (index.html, Impressum, Datenschutz)
tools/           → projects.json (Projektliste) + build.py (erzeugt SVGs und Projektblöcke)
```

## 1. Veröffentlichen

1. Auf GitHub ein **öffentliches** Repo mit dem Namen **`Fluory`** anlegen (genau wie der Benutzername) – ohne README.
2. Den Inhalt dieses Ordners hineinkopieren und pushen:
   ```sh
   git clone https://github.com/Fluory/Fluory.git && cd Fluory
   cp -r <pfad>/profil/. .
   git add -A && git commit -m "Profil und Startseite" && git push
   ```
   Die Datei `ANLEITUNG.md` darf mit, stört nicht.
3. **Pages einschalten:** Repo → Settings → Pages → Source „Deploy from a branch“ → Branch `main`, Ordner `/docs` → Save.
   Nach ein bis zwei Minuten ist die Seite unter `https://fluory.github.io/Fluory/` erreichbar. „Enforce HTTPS“ angehakt lassen.
4. **Sechs Repos anpinnen:** auf github.com/Fluory → „Customize your pins“ → RequestFlow, claude-sync-kit, One Tile a Day,
   Wished into Being, Grow und (sobald öffentlich) eines der vier Projekt-Repos Betriebscockpit, Tourenplaner,
   Rechnungseingang-OS, Stromlast-Prognose.
5. Im Profil (Edit profile) bei „Website“ die Startseite oder die Portfolio-Website eintragen.

## 2. Optional: eigene Domain

Settings → Pages → Custom domain, z. B. `start.deine-domain.de` eintragen. Beim Domain-Anbieter einen CNAME-Eintrag
auf `fluory.github.io` setzen. GitHub legt dann `docs/CNAME` an. Impressum und Datenschutz gelten unverändert.

## 3. Später ändern

- **Projekte** stehen an genau einer Stelle: `tools/projects.json` (Titel, Kurzzeile, Links, Glyphe).
  Danach einmal ausführen:
  ```sh
  pip install fonttools brotli
  python3 tools/build.py
  ```
  Das erzeugt die Karten-SVGs neu und schreibt die Projektblöcke in `README.md` und `docs/index.html`
  (zwischen `<!-- projects:start -->` und `<!-- projects:end -->` – dort nicht von Hand ändern).
- **Betriebscockpit, Tourenplaner, Rechnungseingang, Stromlast-Prognose** liegen im noch privaten Repo
  `Fluory/handwerk`. In `projects.json` tragen sie `"pending": "Repo bald öffentlich"`: Die Karte zeigt diesen Hinweis,
  und nichts verlinkt auf das Repo (sonst landen Besucher auf einer 404-Seite). Nach dem Veröffentlichen die
  `pending`-Zeilen löschen, ggf. Demo-Links ergänzen und `python3 tools/build.py` ausführen.
- **Bewegung in den README-Grafiken** endet von selbst: jede Animation läuft 1,8-mal (rund 20 s) und bleibt dann
  auf dem fertigen Bild stehen (`LOOPS` in `tools/build.py`). GitHub zeigt die Grafiken als Bild; Chromium gibt
  „Bewegung reduzieren“ nicht an Bilder weiter, deshalb hilft nur ein Ende. Die Startseite (`docs/`) schaltet
  die Animationen bei „Bewegung reduzieren“ ganz ab.
- **Prüfen ohne Schreiben:** `python3 tools/build.py --check` meldet, ob Karten und Projektblöcke zu `projects.json` passen.
- **Türen C und D** („Neues Produkt testen“, „Website oder Shop“) zeigen auf `…/de/#offer`, weil die Leistungsseiten
  `/services/prototype/` und `/services/website/` auf der Website noch nicht online sind. Danach in `docs/index.html` umstellen.
- **Texte** der Startseite: direkt in `docs/index.html`. Farben, Abstände, Schriftgrößen: oben in `docs/styles.css`.
- **Impressum/Datenschutz:** `docs/impressum.html`, `docs/datenschutz.html` – bei Adress- oder Mailänderung beide anpassen.
  Der Datenschutztext ist ein Entwurf nach dem Muster der Website, bitte vor dem Veröffentlichen einmal prüfen.
- **Bibliotheken** (three.js, GSAP, Schriften) liegen lokal in `docs/vendor/` und `docs/fonts/`; Versionen und Lizenzen
  stehen in `docs/vendor/README.md`.
