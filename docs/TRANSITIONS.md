# IVE — Transizioni tra clip

Implementate il 2026-08-19. Una transizione e' DATI, mai codice — stessa
regola di colori e sticker — e la primitiva centrale la rende creabile
da chiunque: **una mappa di luminanza**.

## 1. La mappa di luminanza

Un'immagine in scala di grigi dove il valore di ogni pixel dice QUANDO
quel pixel passa dalla clip uscente a quella entrante (0 = subito,
1 = per ultimo), con una banda morbida (`softness`) attorno al bordo in
movimento. Un gradiente orizzontale e' una tendina, uno radiale un
cerchio, e **un PNG disegnato a mano in qualunque editor d'immagini E'
una transizione nuova** — nessun codice, sicura da installare,
condivisibile come file. Le tendine parametriche sono gradienti
generati internamente: un solo percorso di codice per tutte.

## 2. La ricetta JSON

```json
{
  "schema_version": 1,
  "id": "circle_open",
  "name": {"en": "Circle open", "it": "Cerchio che si apre"},
  "section": "wipe",
  "duration": 0.8,
  "easing": "smooth",
  "op": {"kind": "luma", "file": "luma/circle_open.png", "softness": 0.12}
}
```

- **Di fabbrica**: `ive/config/defaults/transitions/` — 16 transizioni
  in 3 famiglie (dissolve, wipe, motion), mappe luma in `luma/`.
- **Dell'utente**: `user_data/transitions/` — manifest `*.json` in cima,
  file relativi accanto. Id duplicati ignorati con warning; file
  mancante = voce saltata, mai crash.
- Vocabolario `op.kind` (engine/transitions.py `make_blender`): `mix`,
  `luma` (file), `wipe` (direction: left/right/up/down/circle_in/
  circle_out), `push`, `slide` (direction), `zoom`, `through_color`
  (color). `easing`: linear / smooth / ease_in / ease_out.

## 3. Semantica sulla timeline (stile CapCut)

La transizione appartiene al **clip uscente** (`transition_id`,
`transition_duration` su TimelineClip): segue il clip nei riordini, e
lo split la sposta sulla meta' che incontra il taglio. Al reflow il
clip successivo viene ANTICIPATO della durata: i due clip si
sovrappongono davvero, entrambi hanno materiale nella finestra, la
sequenza si accorcia di quel tanto e **non servono mai "maniglie"** di
materiale extra. Cap: la sovrapposizione non supera meta' di nessuno
dei due clip, cosi' due transizioni consecutive non si toccano mai.

**Intro e outro** (rivisti 2026-08-19 su feedback): la stessa
transizione funziona anche ai bordi del filmato, verso il NERO.
`transition_id` sull'ULTIMO clip = outro (clip→nero, ultima parte del
clip); `transition_in_id` sul PRIMO clip = intro (nero→clip, prima
parte). Nessuno dei due accorcia la sequenza; l'audio segue con un
fade-in/fade-out equal-power. Azione: `timeline.set_transition` con
`edge: "in" | "out"` ("out" copre giunto e outro: e' sempre "verso cio'
che segue").

UI (rivista 2026-08-19): **niente rombi fissi sui giunti**. Si trascina
la card del pannello DIRETTAMENTE sulla traccia video: il drop si
aggancia al taglio piu' vicino, o alla testa/coda del filmato per
intro/outro. La transizione presente e' una **pillola bianca col rombo
dentro**, sopra la corsia V1, un po' piu' bassa dei clip (si legge "fra
i video"); la sua larghezza E' la finestra del blend. Toccarla la
seleziona; nel **toolbox della timeline** compaiono allora lo **slider
della durata** (0.1-3 s, un undo per commit) e il cestino che la
rimuove; su una pillola larga anche i bordi si trascinano.

Lezioni pagate qui:
- Le MouseArea della pillola hanno `preventStealing` e consumano il
  press: coi pointer handler sparava anche il handler del clip sotto
  (il cestino cancellava il CLIP) e il DragHandler del clip rubava il
  trim a meta' gesto.
- **A zoom 1 su un progetto reale una transizione da 0.7 s e' larga
  pochi pixel**: le due zone di trim da 7 px mangiavano l'intera
  pillola e non restava nulla di cliccabile — riportato dall'utente,
  invisibile nel test (timeline da 6 s → pillola da 155 px). Ora la
  pillola ha larghezza minima 26 px sempre selezionabile, le zone di
  trim esistono solo sopra i 46 px, e la durata si regola comunque
  dallo slider. Il test copre ANCHE la pillola minima.

## 4. Nel motore: A/B roll

Il builder distribuisce i clip video su DUE playlist che si alternano a
ogni giunto con transizione (checkerboard, come MLT): nella finestra
entrambe producono, e un `TimedBlend` sulla traccia superiore fonde con
la ricetta al progresso t della finestra. Fuori dalle finestre la
traccia superiore copre e basta: **costo zero quando non c'e' una
transizione in corso**. Ogni altra finestra ha i ruoli invertiti
(`flipped`): il vecchio clip sta sopra, e le immagini si scambiano
prima del blend — un push non e' simmetrico.

Audio: **crossfade equal-power** (cos/sin) con un `AudioRamp` per lato
della finestra — il volume resta costante attraverso il taglio invece
di calare di ~3 dB come farebbe una rampa lineare.

I blender viaggiano come gli sprite degli sticker: span PURI
(`sequence_transition_spans()`) attraverso il confine di thread, e
`transitions/loader.attach_blenders` li arma (caricando le mappe con
QImage) nel transport e nel worker di export. Anteprime delle card:
il VERO blender del motore a t=0.55 su due lastre blu/arancio, PNG
cachato.

## 5. Performance (misurate, tests/test_transitions.py)

Budget di frame a 25 fps: 40 ms. Costi per frame 1280x720 (canvas di
anteprima):

| blender | ms/frame | come |
|---|---|---|
| crossfade | 2.1 | `cv2.addWeighted` |
| luma/wipe (tutte) | 5.5–6.0 | vedi sotto |
| push/slide | 1.2–1.8 | puro slicing numpy (memcpy) |
| zoom | 4.1 | crop + `cv2.resize` + mix |
| dip nero/bianco | 2.0 | blend scalare |

Pull dal grafo DENTRO la finestra (doppia decodifica + blend):
10.8 ms/frame contro 6.0 fuori — la transizione aggiunge ~5 ms.

**L'ottimizzazione che conta** (104 → 5.7 ms, 18x): il peso di un pixel
luma dipende SOLO dal valore della mappa, quindi e' una **LUT a 256
voci costruita una volta per frame**, applicata con `cv2.LUT` (gather
SIMD) e fusa con `cv2.blendLinear`. La versione numpy "ovvia"
(broadcast uint16 HxWx3) costava 85–110 ms per i temporanei. Altri
accorgimenti gia' dentro: mappa ridimensionata al canvas UNA volta e
cachata per size; mappe file cachate per (path, mtime); fallback numpy
col trucco del delta (una sola widening multiply); niente float nel
percorso senza cv2.

Margini futuri se serviranno: pesi luma quantizzati per riusare la LUT
fra frame vicini; blend sul GPU quando il preview passera' all'item a
texture (la QML API non cambia); SIMD esplicito via cv2.UMat/OpenCL.

## 6. Prossimi passi

1. Piu' mappe di fabbrica (stella, cuore, pennellata) — sono solo PNG.
2. `.ivepack` che impacchetta transizioni + colori + sticker insieme.

Test: `tests/test_transitions.py` (catalogo, loader, modello con
overlap/clamp/split/undo, pixel del grafo per crossfade/wipe/push,
finestra FLIPPED, intro dal nero e outro verso il nero coi fade audio,
rampa audio del crossfade, export accorciato coi pixel giusti, bench
di performance con budget), `tests/visual/test_transitions_ui.py`
(pannello, anteprime reali sulle card, drag sulla TRACCIA che si
aggancia al taglio, pillola bianca misurata sui pixel, trim del bordo,
selezione+cestino, drop in testa che diventa intro, undo).
