# IVE — Testo e titoli

Implementato il 2026-08-18. Un titolo e' un OVERLAY come uno sticker:
stessa corsia libera, stesso filtro di composizione, stesse maniglie sul
video, stesso percorso live. Cio' che cambia e' solo la sorgente dei
pixel: parole + stile invece di un file grafico.

## 1. Modello

`TimelineClip` con `text` non vuoto — il testo E' il discriminante,
come `sticker_id` per gli sticker e `effect_id` per il colore. Corsia
**Text = track 3**, posizionamento libero. Campi di stile piatti e
serializzabili: `font` ("" = carattere dell'applicazione), `color`
(#RRGGBB), `outline` ("" = nessun contorno; il default e' nero),
`bold`, `italic`. La trasformazione riusa x/y/scale/rotation in
FRAZIONI di canvas.

**`scale` = altezza del BLOCCO di testo** come frazione dell'altezza
canvas: piu' righe = lettere piu' piccole. E' la scelta prevedibile —
il riquadro che l'utente ha trascinato resta quel riquadro.

Regole: `add_text`/`set_clip_text` rifiutano parole vuote (svuotare un
titolo ne cancellerebbe l'identita'; eliminare il clip e' un gesto
esplicito, diverso). Lo split copia parole, stile e trasformazione: un
titolo tagliato mostra lo stesso testo nello stesso punto da entrambe
le parti.

## 2. Rendering (`ive/src/ive/text/raster.py`)

Il gemello di `stickers/raster.py` — il modulo `ive/text/` sta
all'INFRASTRUCTURE come `ive/stickers/`: il motore non importa mai Qt
ne' conosce font o parole.

- Il testo e' un **QPainterPath**: prima lo stroke del contorno (8%
  della dimensione del font, cap e join rotondi), poi il fill — cosi'
  il contorno abbraccia ogni glifo.
- Layout a **dimensione di riferimento fissa** (128 px) poi scalato
  all'altezza richiesta: le metriche non derivano mentre l'utente
  scala. Righe centrate orizzontalmente.
- `attach_text_sprites(spans)` attacca IN PLACE la closure
  `sprite(canvas_h, local_seconds)`; la closure legge parole, stile,
  scala e rotazione **dal dict a ogni chiamata** (cache per chiave
  completa, cap 64 — un drag di scala/rotazione spazza molte varianti).
- `text_aspect(...)` da' il rapporto w/h del blocco per la cornice
  delle maniglie (`Project.overlay_aspect` sceglie fra testo e sticker).

## 3. Composizione e percorso live

Gli span di testo viaggiano nel filtro `Overlays` INSIEME a quelli
sticker, DOPO di loro nella lista: i titoli disegnano sopra gli
sticker, ed entrambi sopra il grading (un titolo tiene i suoi colori
sotto qualunque look). Il transport risolve la corsia in span puri
(`sequence_text_spans()` per l'export, closure spogliate), e il worker
di export li riattacca — identico agli sticker.

Percorso live, due slot sul transport:

- `set_overlay_live(clip_id, x, y, scale, rotation)` — condiviso con
  gli sticker: le maniglie sul video muovono un titolo esattamente come
  uno sticker.
- `set_text_live(clip_id, text, font, color, outline, bold, italic)` —
  mentre si SCRIVE nel pannello, il frame in pausa mostra le parole a
  ogni tasto, senza rebuild e senza voci di undo; l'uscita dal campo
  committa UNA `timeline.set_clip_text`.

**Attivita' su numeri di frame TRONCATI** (`engine/filters.py`): lo
span e' attivo su `int(start*fps) <= frame < int(end*fps)` — la stessa
convenzione del transport per il frame mostrato. Il confronto in
secondi lasciava un overlay piazzato AL playhead invisibile proprio sul
frame sotto di esso ("Aggiungi titolo" a 1.5 s mostrava il frame 37,
il cui tempo 1.48 s stava 20 ms prima dello span). Uno span piu' corto
di un frame vale comunque un frame.

## 4. UI

- **Pannello Text** (`qml/shell/TextContent.qml`, sezione "text" della
  rail): "Aggiungi un titolo" lo piazza al playhead (3 s) e lo
  seleziona; sotto, l'editor del titolo SELEZIONATO — parole
  (multiriga), B/I, sette swatch di colore, contorno nessuno/nero/
  bianco, e la lista dei font di sistema mostrata ognuno col proprio
  carattere. Posizione/scala/rotazione NON stanno nel pannello: sono
  delle maniglie sul video, dove sta l'occhio.
- **Selezione condivisa** via `Shell.v.selectedClipId` (stato runtime
  di ShellState, scritto da timeline e maniglie): toccare un titolo sul
  video o sulla timeline apre le sue parole nel pannello. E' lo stesso
  meccanismo che le maniglie usano per sapere cosa incorniciare.
- **Corsia "Text"** viola (`Theme.c.clipText`) col nome = prime parole;
  split e Canc dal toolbox contestuale come le altre corsie overlay.
- Le **maniglie** (`StickerHandles.qml`) includono i clip di testo:
  stesso riquadro, stessi pomelli, `Project.overlay_aspect(clip_id)`
  misura il blocco renderizzato.

## 5. Prossimi passi

1. Preset di stile (JSON condivisibili come gli effetti colore:
   font+colori+contorno pronti).
2. Animazioni di ingresso/uscita del titolo (fade, slide) — insieme ai
   motion preset degli sticker.
3. Sfondo/riquadro dietro al testo per la leggibilita' su video mossi.

Test: `tests/test_text_titles.py` (modello, split, round-trip,
renderer con fill+contorno, grafo dentro/fuori span, edit live sul
grafo VIVO, servizio+undo, export coi pixel del titolo),
`tests/visual/test_text_ui.py` (pannello reale: aggiungi, scrivi con
verifica mid-typing, swatch rosso sui pixel del frame, drag del titolo
col riquadro, quattro undo fino a zero).
