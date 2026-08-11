# IVE — Sticker

Deciso il 2026-08-11. Regole e forma del sistema sticker; catalogo e
pannello implementati, composizione sul video e player Lottie in arrivo.

## 1. Uno sticker e' dati, mai codice

Stessa regola degli effetti colore (`CONTENT_PACKS.md`): installare
contenuti deve essere sicuro, quindi uno sticker e' un file grafico + una
voce di manifest, e non esegue nulla.

```json
{
  "schema_version": 1,
  "id": "shape_star",
  "name": {"en": "Star", "it": "Stella"},
  "section": "shapes",
  "kind": "static",
  "file": "shapes/star.svg"
}
```

- **Di fabbrica**: `ive/config/defaults/stickers/` — `manifest.json` in
  cima, grafiche nelle sottocartelle. 17 sticker: 15 statici in 4 famiglie
  (shapes, goodmorning, greetings, birthday) + 2 animati demo.
- **Dell'utente**: `user_data/stickers/` — manifest `*.json` in cima alla
  cartella, file relativi accanto. Copiare la cartella ricevuta da un
  altro utente E' l'installazione. Id duplicati ignorati con warning.
- **`kind`** decide la tab del pannello: `static` (SVG/PNG) o `animated`
  (Lottie JSON). Una famiglia nuova richiede la chiave
  `sticker.section.<id>` nei 4 locale (altrimenti mostra l'id).
- Voce con file mancante = salta con warning, mai crash (pacchetto
  copiato a meta'). Un JSON che non e' un manifest (es. un'animazione
  Lottie caduta nella cartella sbagliata) viene ignorato in silenzio.

## 2. Statici: SVG prima di tutto

SVG e' il formato preferito: vettoriale (scala dal 720p al 4K senza
sgranare), piccolo, editabile con Inkscape da chiunque, e **sicuro** —
QtSvg renderizza il sottoinsieme statico, nessuno script viene eseguito.
Il pannello li mostra col loader nativo di Qt (`Image` + `sourceSize`),
quindi le anteprime SONO gli sticker: niente worker di thumbnail.
PNG accettato per contenuti raster.

Regole di disegno per gli sticker di fabbrica: viewBox 512x512, forme
piene con contorno scuro (leggibili su qualunque video), testo
`sans-serif` bold solo quando il testo E' lo sticker.

## 3. Animati: il formato e' Lottie (deciso, licenze verificate)

**Lottie** e' il formato aperto e dichiarativo per animazioni vettoriali
(JSON puro → sicuro da installare), lo standard degli sticker animati di
Telegram e TikTok, esportabile da After Effects.

Verifica licenze (2026-08-11):
- **rlottie** (Samsung, il renderer C++ usato da Telegram): **MIT** dalla
  v0.2, con parti terze FTL / BSD-3 / MPL-1.1 — tutte compatibili GPL-3.
- **rlottie-python** (binding pip, bundla la libreria): **LGPL** —
  compatibile col nostro GPL-3.0-or-later.
- **LottieFiles** (lottiefiles.com): le animazioni gratuite sono sotto
  "Lottie Simple License" — uso anche commerciale, senza attribuzione;
  la ridistribuzione deve conservare la stessa licenza. Quindi: l'utente
  puo' scaricarle e installarle liberamente; NOI le bundleremmo solo
  accompagnandole dal testo della licenza (per ora non ne bundliamo:
  i 2 demo di fabbrica sono scritti a mano da noi, GPL).
- Nota di manutenzione: il repo Samsung/rlottie e' poco attivo;
  alternativa da valutare al momento dell'integrazione: ThorVG (MIT).

**rlottie-python e' integrato (2026-08-11)**: dipendenza in
requirements.txt e LICENSING.md. Le card animate mostrano un frame reale
renderizzato da rlottie; sul video l'animazione va in LOOP dal suo punto
zero, ovunque il clip sieda sulla timeline. Misura: ~0,9 ms a frame a
400px — dentro il budget.

## 4. Composizione nel motore (FATTO 2026-08-11)

Uno sticker sul video e' un clip su una corsia **Sticker** (track 2,
posizione libera come la corsia Color), con trasformazione per clip:
centro `(x, y)` in FRAZIONI del canvas (sopravvive a ogni risoluzione
d'export), `scale` = altezza come frazione dell'altezza canvas,
`rotation` in gradi. Azioni: `timeline.place_sticker` (drop dal
pannello, 3 s di default) e `timeline.set_clip_transform`; tutte
annullabili.

Catena: il transport risolve `sticker_id` → file/kind (il grafo non
conosce il catalogo); `stickers/raster.py` attacca a ogni span una
closure `sprite(canvas_h, local_seconds)` (QtSvg per i vettori, rlottie
per i Lottie — che rende BGRA PREMOLTIPLICATO, convertito in RGBA
straight una volta e cachato per frame); il filtro `Overlays` del
tractor (engine/filters.py, numpy puro, il motore resta senza Qt) fonde
alpha-over dentro lo span, ritagliando ai bordi. Gli span viaggiano
verso l'export come DATI PURI (una QVariantMap perderebbe le closure):
il worker li riattacca con `attach_sprites`. Composizione DOPO il
grading: uno sticker tiene i propri colori sotto qualunque look.

## 5. Prossimi passi

1. **Maniglie nel preview**: trascinare/scalare/ruotare lo sticker
   direttamente sul video (oggi si sposta via azione).
2. **Motion preset**: ricette JSON di keyframe (bounce, pulse, spin,
   slide-in...) applicabili a QUALUNQUE sticker statico.
3. GIF/WebP animati come sorgenti sticker (decodifica FFmpeg gia' in
   casa).

Test: `tests/test_stickers.py` (catalogo, validita' SVG/Lottie,
degradazione), `tests/test_sticker_compositing.py` (modello+undo, oro
dentro lo span / grigio fuori, la pallina Lottie che CADE fra due
istanti, export con gli stessi pixel),
`tests/visual/test_stickers_panel.py` (tab, famiglie, drag reale sulla
timeline, pixel del preview composito).
