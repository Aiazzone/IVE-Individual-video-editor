# IVE — Effetti di colore

Deciso e implementato il 2026-08-09. Regole e forma del sistema colore.

## 1. Un effetto e' un file JSON, mai codice

Stessa regola di `CONTENT_PACKS.md`: installare contenuti deve essere
sicuro, quindi un effetto DICHIARA una ricetta e non esegue nulla.

```json
{
  "schema_version": 1,
  "id": "warm_memory",
  "name": {"en": "Warm memory", "it": "Ricordo caldo"},
  "section": "nostalgia",
  "ops": [
    {"op": "temperature", "amount": 0.35},
    {"op": "fade", "amount": 0.4},
    {"op": "vignette", "strength": 0.3}
  ]
}
```

- **Di fabbrica**: `ive/config/defaults/color_effects/*.json` (un file per
  sezione, contiene una lista). 14 effetti in 4 sezioni: nostalgia,
  cyberpunk, cinema, base.
- **Dell'utente**: `user_data/effects/color/*.json` — copiare li' un file
  ricevuto da chiunque E' l'installazione. Un id gia' esistente viene
  ignorato con warning (mai override silenzioso dei builtin).
- Vocabolario delle `ops` (numpy vettoriale, documentato in
  `engine/filters.py::apply_colour_ops`): brightness, contrast,
  saturation, gamma, temperature, tint, fade, vignette, matrix.
  **Un'op sconosciuta degrada con warning**: una ricetta scritta da una
  versione futura deve caricarsi, non esplodere.
- Catalogo: `ive/src/ive/color/library.py` (cache, `reload()`); bridge QML
  `ColorFx` (`ui/color_service.py`) con nomi gia' localizzati.

## 1-bis. Come si applica VELOCE (deciso 2026-08-09, sera)

La catena numpy di riferimento (`apply_colour_ops`) costa ~150 ms a frame
720p: da usare SOLO per cuocere/testare, mai per fotogramma. `ColorGrade`
**compila** la ricetta al primo uso:

- run di op per-canale (brightness, contrast, gamma, temperature, tint,
  fade) → UNA curva `cv2.LUT` (1x256x3);
- saturation e matrix (mixano i canali; saturation E' una matrice verso il
  luma) → composte in UNA `cv2.transform` affine 3x4;
- vignette → un `cv2.multiply` con maschera radiale uint8 cachata per size.

Un look tipico = 2-3 chiamate C a frame: **~7 ms a 720p** (misurato nel
test, budget 33 ms a 30fps). Senza OpenCV il fallback e' una LUT 3D 65^3
cotta dalla catena di riferimento (~55 ms: lento ma corretto).

**Semantica fissata**: ogni op vede input GIA' clippato a [0,1] (pipeline
uint8). Senza questa regola le tre vie (catena, cv2, LUT) divergevano sui
pixel piu' luminosi. Fedelta' verificata: errore massimo 2/255 (cv2) e
5/255 (LUT) contro il riferimento.

OpenCV (`opencv-python`, Apache-2.0) e' gia' nel venv condiviso del
workspace; registrato in LICENSING.md.

## 2. Nel motore: un Filter sul composito, a tempo

`TimedColor(spans)` e' un filtro del tractor: ogni span
`{start, end, ops}` (frame di sequenza) colora SOLO i fotogrammi che
copre. Anteprima ed export tirano lo stesso grafo, quindi la resa e'
identica per costruzione (`GraphBuilder.build(clips, color_spans)`;
l'export riceve gli span da `PlaybackService.sequence_color_spans()`).
Le op sono pigre: colorare un fotogramma di cui nessuno chiede l'immagine
non decodifica nulla.

## 3. Nella timeline: la corsia "Color"

- Un effetto applicato e' un `TimelineClip` su **track 1** con
  `effect_id` e `media_id` vuoto (`Project.add_effect`); la corsia
  etichettata "Color" (pillole ROSA, `clipEffect` nel tema) compare solo
  quando esiste almeno un clip effetto.
- Track 1 e' **a posizione libera** (niente reflow gapless): l'effetto
  sta esattamente dove lo si mette. Trim, drag, calamita, Dividi e Canc
  funzionano come sugli altri clip (kind di selezione: "color").
- Un progetto che referenzia un effetto non piu' installato CARICA
  comunque: quel tratto suona/mostra senza colorazione (ops vuote).

## 4. Nel pannello (icona Colore della rail)

Due livelli: card delle **sezioni** → griglia di **thumbnail dello stesso
fotogramma del video dell'utente** con ogni look applicato (image provider
`thumb` con `?effect=<id>`: un decode per video, un passo numpy per look,
cache di sessione). L'effetto si applica **trascinando la thumbnail sulla
timeline**: rilasciato sopra un clip video ne adotta lo span esatto; sul
vuoto copre 3 secondi, poi ci pensano le maniglie.

## 4-bis. Il pannello: tab e preferiti (2026-08-09, notte)

Il pannello ha due tab: **Colori** (le famiglie — card con solo nome e
conteggio, NIENTE anteprime: quelle vivono solo dentro la famiglia) e
**Preferiti**. Ogni thumbnail porta una **stella in alto a destra**:
vuota (solo contorno) = non preferito, piena **giallo oro** (#FFC53D) =
preferito; il click la commuta via azione `color.toggle_favorite`, e la
lista persiste in settings (`color.favorites`, lista di id nell'ordine di
aggiunta). La tab Preferiti raccoglie gli effetti stellati da tutte le
famiglie, con le stesse thumbnail trascinabili. `ColorFx.favorites`
espone la lista a QML e si aggiorna sul cambio settings.

## 5. Aggiungere un effetto nuovo

1. Copiare un JSON esistente, cambiare `id`, `name`, `section`, `ops`.
2. Metterlo in `user_data/effects/color/` (o mandarlo a un altro utente,
   che fa lo stesso). Sezioni nuove compaiono da sole in coda.
3. Niente riavvio necessario in futuro (`ColorFx.refresh()`); oggi al
   prossimo avvio.

Test: `tests/test_color_effects.py` (ops, catalogo, TimedColor, grafo),
`tests/visual/test_color_panel.py` (pannello, corsia, anteprima davvero
colorata, delete).
