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

I file Lottie si installano e si catalogano GIA' OGGI (tab Animati,
badge "Lottie" al posto dell'anteprima); prenderanno vita quando il
renderer viene integrato. Aggiungere rlottie-python richiede prima la
riga in LICENSING.md, come da regola 4.9.

## 4. Prossimi passi (in ordine)

1. **Composizione nel motore**: uno sticker sul video e' un clip su una
   corsia "Sticker" (posizione libera come la corsia Color), con
   trasformazione per clip (x, y, scala, rotazione). Il motore
   rasterizza l'SVG UNA volta alla dimensione necessaria (cache per
   size) e fonde con alpha premoltiplicato — stessa promessa dei colori:
   anteprima ed export identici perche' tirano lo stesso grafo.
2. **Motion preset**: ricette JSON di keyframe (bounce, pulse, spin,
   slide-in...) applicabili a QUALUNQUE sticker statico — la via
   economica all'animazione, complementare a Lottie.
3. **Renderer Lottie** (rlottie-python, dopo LICENSING.md): "frame N a
   WxH" e' l'API naturale del grafo pull.
4. GIF/WebP animati come sorgenti sticker (decodifica FFmpeg gia' in
   casa).

Test: `tests/test_stickers.py` (catalogo, validita' SVG/Lottie,
degradazione), `tests/visual/test_stickers_panel.py` (tab, famiglie,
pixel dell'SVG renderizzato).
