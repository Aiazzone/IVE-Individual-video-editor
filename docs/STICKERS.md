# IVE — Sticker

Deciso il 2026-08-11. Regole e forma del sistema sticker; catalogo,
pannello, composizione sul video, player Lottie e maniglie nel preview
implementati.

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

**Anteprime vive all'hover (2026-08-19)**: passando il mouse su una
card animata l'animazione PARTE — una striscia di 12 fotogrammi rlottie
(quadrati, trasparenti, campionati lungo tutta l'animazione) salvata
come un solo PNG cachato (`Stickers.preview_strip`) e riprodotta da
`components/AnimatedPreview.qml` (lo stesso componente delle card
transizioni): un offset di texture per tick, niente rendering live.
Trappola nomi: l'objectName dell'anteprima e' `anim_preview_*`, NON
`sticker_*` — gli id animati iniziano gia' per "anim_" e i test contano
le card per prefisso.

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

## 4-bis. Maniglie nel preview (FATTO 2026-08-18)

Con il playhead in pausa dentro lo span, sopra ogni sticker composto
appare una cornice (`qml/shell/StickerHandles.qml`, primo figlio
dell'overlay layer cosi' transport e pannelli restano cliccabili sopra).
Click = selezione; trascinare la cornice sposta, il pomello d'angolo
scala (distanza dal centro), lo stelo sopra ruota (snap a 3 gradi dai
multipli di 90). Tutto in bianco fisso con ombra: sta sul video, che
non segue il tema. La mappatura frazioni-canvas → pixel replica la
regola "cover" di PreviewItem (canvas `Playback.aspect` scalato a
coprire l'item e centrato), quindi la cornice siede esattamente sui
pixel composti anche col canvas "auto".

**Il gesto e' in due fasi** — la parte da non rompere:

1. **Live**: a ogni mouse-move la QML chiama
   `Playback.set_sticker_live(clip_id, x, y, scale, rotation)`. Il
   transport muta GLI STESSI dict di span che il filtro `Overlays` (e le
   closure sprite) leggono a process-time — per questo `attach_sprites`
   attacca in place e non su copie, il builder passa i dict originali
   senza convertirli (la conversione secondi→frame avviene nel filtro,
   sono una manciata di span), e le closure leggono scale/rotation dal
   dict a ogni chiamata. Poi ri-richiede il frame in pausa: lo sticker
   segue la mano SENZA rebuild del grafo e SENZA toccare l'undo stack.
   Letture/scritture di scalari sono atomiche sotto il GIL: il thread
   che tira il grafo non vede mai valori strappati.
2. **Commit**: al rilascio parte UNA `timeline.set_clip_transform` →
   un solo passo di undo per l'intero trascinamento, rebuild dal
   modello (regola ENGINE.md §3: il grafo derivato dal modello; il
   percorso live e' l'eccezione documentata, e il commit riallinea).

Dettagli: la rotazione degli sticker statici e' cotta nel raster con
cache per (altezza, rotazione arrotondata a 0.1°, cap 64 voci — un drag
di rotazione spazza centinaia di angoli); per gli animati il frame
Lottie e' cachato NON ruotato e la rotazione si applica al volo
(`_rotate_rgba`, ~0.5 ms), o la cache esploderebbe. `Stickers.aspect()`
da' alla cornice il rapporto w/h della grafica.
`sequence_sticker_spans()` spoglia le closure prima di consegnare gli
span all'export (attraversano un confine di thread come QVariantMap).

## 5. Prossimi passi

1. **Motion preset**: ricette JSON di keyframe (bounce, pulse, spin,
   slide-in...) applicabili a QUALUNQUE sticker statico.
2. GIF/WebP animati come sorgenti sticker (decodifica FFmpeg gia' in
   casa).

Test: `tests/test_stickers.py` (catalogo, validita' SVG/Lottie,
degradazione), `tests/test_sticker_compositing.py` (modello+undo, oro
dentro lo span / grigio fuori, la pallina Lottie che CADE fra due
istanti, export con gli stessi pixel),
`tests/test_sticker_handles.py` (attach in place, x/scala/rotazione
mutati sul grafo VIVO, clamp e no-undo di set_sticker_live, span
spogliati per l'export), `tests/visual/test_stickers_panel.py` (tab,
famiglie, drag reale sulla timeline, pixel del preview composito),
`tests/visual/test_sticker_handles_ui.py` (gesti reali: move con
verifica mid-drag, scala, rotazione, un passo di undo per gesto, pixel
prima/dopo).
