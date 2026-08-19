# IVE — Motion preset

Implementati il 2026-08-19 (UI «1+3» decisa in discussione: pannello
come casa dell'animazione + scorciatoia nel toolbox della timeline).
Un motion preset e' una **ricetta JSON di keyframe** che anima un
overlay — sticker o titolo — senza toccare il file grafico: dati, mai
codice, condivisibile come tutto il resto.

## 1. La ricetta

```json
{
  "schema_version": 1,
  "id": "bounce",
  "name": {"en": "Bounce", "it": "Rimbalzo"},
  "kind": "loop",
  "duration": 0.9,
  "tracks": [
    { "parameter": "y",
      "keyframes": [
        {"t": 0.0, "value": 0.0},
        {"t": 0.5, "value": -0.06, "easing": "out_quad"},
        {"t": 1.0, "value": 0.0, "easing": "in_quad"} ] }
  ]
}
```

- **`t` normalizzato 0→1** sulla durata: la stessa ricetta funziona a
  qualunque velocita'.
- **Parametri RELATIVI al transform del clip** (cosi' il preset compone
  con dove l'utente ha trascinato lo sticker): `x`/`y` offset in
  frazioni di canvas, `scale` moltiplicatore attorno a 1, `rotation`
  gradi aggiunti, `opacity` moltiplicatore 0..1.
- **`kind`** ancora la ricetta: `loop` ripete con `duration` come
  periodo per tutto il clip; `in` suona UNA volta sui primi `duration`
  secondi poi tiene l'identita'; `out` tiene l'identita' e suona
  finendo ESATTAMENTE sulla fine del clip.
- **Easing** (set chiuso, `ive/motion/runtime.py`): linear, in/out/
  in_out × quad/cubic, out_back, out_bounce, out_elastic. L'easing su
  un keyframe modella il segmento che ne ESCE. Sconosciuto → linear
  con warning; parametro sconosciuto → saltato. Mai un crash.

Cataloghi: fabbrica in `ive/config/defaults/motion/` (12 preset in 3
tipi), utente in `user_data/motion/`, e i content pack portano i loro
in `motion/` (la libreria li scansiona gia'; la creazione pack li
includera' con la categoria dedicata — prossimo passo).

## 2. Nel motore

Il modello ha `motion_id` sul clip overlay (azione
`timeline.set_clip_motion`, un undo per scelta; lo split lo copia su
entrambe le meta'). Il transport risolve l'id in RICETTA pura
(`motion_recipe` nello span); `ive/motion/runtime.attach_motion` arma
l'evaluatore in place — stesso pattern degli sprite: la ricetta
attraversa i confini di thread, la callable no, il worker d'export
riattacca. Il filtro `Overlays` valuta il motion per frame e modula:
offset sulla posizione, scala/rotazione passate come OVERRIDE alla
closure sprite (nuova firma `sprite(h, s, scale=None, rotation=None)`;
None = leggi lo span, che resta il canale del drag live), opacita'
dentro `_blend_over`. Anteprima ed export identici per costruzione.

## 3. UI

- **Il pannello Sticker e' l'editor dell'animazione del clip
  selezionato**: selezioni uno sticker (timeline o tocco sul video —
  selezione condivisa via Shell) e il pannello mostra la sezione
  «Animazione — <nome>»: card «Nessuna» + una card per preset con il
  chip del tipo (Entrata/Continua/Uscita). Ogni card mostra **QUESTO
  sticker mosso da QUEL preset**: fermo a riposo, vivo all'hover
  (striscia `Stickers.motion_strip`, stesso `AnimatedPreview` di
  transizioni e Lottie, cache su disco per (sticker, preset)).
- **Scorciatoia nel toolbox**: col clip sticker selezionato, il
  bottone «onde» nella toolbar della timeline apre il pannello Sticker
  gia' sulla sezione (segnale `panelRequested` → `openSection`).
- I TITOLI hanno gia' tutto il motore (l'azione accetta clip di testo);
  la sezione Animazione nel pannello Testo e' il prossimo passo.

Test: `tests/test_motion.py` (catalogo, evaluatore con ancoraggi e
degradazioni, pixel del grafo per pulse/fade_in/drop_in, modello+undo,
transport e span d'export, split), `tests/visual/test_motion_ui.py`
(tocco sul video → sezione nel pannello, hover che anima, card che
applica con un undo, «Nessuna», bottone del toolbox che apre il
pannello).
