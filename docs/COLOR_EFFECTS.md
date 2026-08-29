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
  sezione, contiene una lista). 41 effetti in 10 sezioni: subject
  (soggetto IA — aura, ritratto, colore selettivo), artistic (artistici —
  matita, fumetto, pittura), nostalgia, film (pellicola), cinema,
  cyberpunk, summer (estate), nordic, bw (bianco e nero), base.
  Una sezione nuova richiede la chiave `color.section.<id>` nei 4 locale.
- **Dell'utente**: `user_data/effects/color/*.json` — copiare li' un file
  ricevuto da chiunque E' l'installazione. Un id gia' esistente viene
  ignorato con warning (mai override silenzioso dei builtin).
- **Un'op sconosciuta degrada con warning**: una ricetta scritta da una
  versione futura deve caricarsi, non esplodere.

### Vocabolario delle `ops` (completo, 2026-08-11)

L'ordine nella lista CONTA: le op si applicano una dopo l'altra, e dopo
ognuna il risultato e' clippato a [0,1]. Implementazione di riferimento in
`engine/filters.py::apply_colour_ops`.

| op | parametro | range utile | neutro | effetto |
|---|---|---|---|---|
| `brightness` | `amount` | −1 … +1 | 0 | somma luce a tutto il frame |
| `contrast` | `amount` | 0 … ~2 | 1 | pivot sul grigio medio |
| `saturation` | `amount` | 0 … ~2 | 1 | 0 = b/n; lavora sul luma Rec.601 |
| `gamma` | `value` | ~0.5 … ~2 | 1 | curva sui mezzitoni; <1 schiarisce |
| `temperature` | `amount` | −1 … +1 | 0 | caldo positivo (R su, B giu') |
| `tint` | `amount` | −1 … +1 | 0 | magenta positivo (G giu') |
| `fade` | `amount` | 0 … 1 | 0 | solleva i neri (look "stampa vecchia") |
| `shadows` | `amount` | −1 … +1 | 0 | solo le ombre: peso (1−x)², +alza / −affonda |
| `highlights` | `amount` | −1 … +1 | 0 | solo le luci: peso x², +spinge / −recupera |
| `vignette` | `strength` | 0 … 1 | 0 | angoli scuri, caduta quadratica |
| `matrix` | `m` 3×3, `offset?` | — | identita' | matrice colore arbitraria (seppia, duotone, b/n virati) |
| `intensity` | `amount` | 0 … 1 | 1 | fonde TUTTO cio' che la precede con il frame originale: il "dosaggio" dell'intera ricetta |
| `sketch` | `mode?` gray/color, `shade?` 0…1 | — | — | disegno a matita (dodge blend + inchiostro adattivo); `color` = matite colorate |
| `cartoon` | `smooth?` 0…1, `lines?` 0…1 | — | — | colori appiattiti (bilateral su piramide) + linee a china |
| `paint` | `strength?` 0…1 | — | — | pittura: bilateral iterato a quarto di risoluzione |

| `aura` | `color?`, `width?` 0…1, `strength?` 0…1 | — | — | bagliore additivo ATTORNO al soggetto (maschera IA), mai sopra |
| `bg_blur` | `amount?` 0…1 | — | — | sfondo sfocato (piramide), soggetto nitido |
| `bg_gray` | `amount?` 0…1 | — | — | sfondo in grigio, soggetto a colori |
| `bg_zoom` | `amount?` 0…1 | — | — | parallasse 2.5D: la scena zooma col tempo del clip (progress `_t` iniettato da TimedColor), il soggetto sta fermo; blur crescente maschera il bordo doppio |

`sketch`/`cartoon`/`paint` sono op **SPAZIALI** (guardano i pixel vicini,
sezione "artistic" del catalogo, 2026-08-28): richiedono OpenCV — senza,
degradano a pass-through con warning come le op sconosciute — e restano
FUORI dalla 3D LUT cotta (un reticolo di colori non e' una scena) e dal
fallback numpy. Il lavoro pesante gira su copia ridotta in piramide:
12–50 ms a 720p misurati (cv2.stylization pieno costava 1,2 s), 19–42 ms
sul proxy 540p. Il read-ahead li assorbe e l'audio-first garantisce che
sotto carico degradi il video, mai il suono.

`aura`/`bg_blur`/`bg_gray` (sezione "subject", 2026-08-28) sono spaziali
E **a maschera**: chiedono al motore "quali pixel sono il soggetto" via
il provider iniettato con `filters.set_mask_provider` (l'app lo cabla a
`ive/ai/segmentation.mask_provider()` in `app.py`; il motore NON importa
l'AI). Senza provider, o senza modello installato, degradano a
pass-through con un warning una-tantum. Costo: ~34 ms a maschera su
DirectML (446 su CPU nuda — vedi AI_FEATURES §6-bis) + pochi ms per l'op;
la primissima maschera carica la sessione ONNX (~3-4 s, una volta per
processo) — dal 2026-08-28 sera `app._warm_masks` la PRERISCALDA in un
thread appena un effetto a maschera entra in timeline
(`segmentation.warm_up()`), quindi nell'uso normale l'attesa non si
vede; resta possibile sul primissimo drop a sessione fredda (il frame
in pausa puo' restare vecchio finche' non si tocca il playhead).

Regole per `intensity`: metterla **ultima** e comunque **prima di una
vignette finale** — nella via compilata fonderebbe anche la vignette gia'
applicata, mentre il fallback LUT (che tiene la vignette fuori dalla
tabella) non potrebbe: con vignette dopo intensity le vie restano
identiche. `shadows`/`highlights` sono per-canale (fondono nella LUT
compilata) e monotone: niente banding ne' inversioni.
- Catalogo: `ive/src/ive/color/library.py` (cache, `reload()`); bridge QML
  `ColorFx` (`ui/color_service.py`) con nomi gia' localizzati.

## 1-bis. Come si applica VELOCE (deciso 2026-08-09, sera)

La catena numpy di riferimento (`apply_colour_ops`) costa ~150 ms a frame
720p: da usare SOLO per cuocere/testare, mai per fotogramma. `ColorGrade`
**compila** la ricetta al primo uso:

- run di op per-canale (brightness, contrast, gamma, temperature, tint,
  fade, shadows, highlights) → UNA curva `cv2.LUT` (1x256x3);
- saturation e matrix (mixano i canali; saturation E' una matrice verso il
  luma) → composte in UNA `cv2.transform` affine 3x4;
- vignette → un `cv2.multiply` con maschera radiale uint8 cachata per size;
- intensity → un `cv2.addWeighted` col frame d'ingresso (mai mutato in
  place dai passi precedenti, quindi E' l'originale).

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

## 3-bis. Due pannelli, un catalogo (2026-08-28, Fase C effetti)

Il catalogo e' UNO, ma si sfoglia da due pannelli: l'icona **Effetti**
della rail (tasto 3, `EffectsContent.qml` = `ColorContent { catalog:
"fx" }`) mostra le sezioni "spettacolari" — `subject` (IA) e `artistic`
— mentre l'icona **Colore** tiene le famiglie di grading e le nove
manopole manuali. La spartizione vive in UN punto:
`ive/color/library.py::FX_SECTIONS` / `catalog_of()`; il bridge QML
espone `catalog` su sezioni ed effetti e `ColorContent` filtra. Un
effetto piazzato e' lo stesso clip della corsia Color da qualunque
pannello arrivi: i progetti non sanno nulla dei pannelli. I preferiti
sono una lista sola, ma ogni pannello mostra i suoi.

## 3-ter. La corsia Effects e la regola "vince l'ultimo" (2026-08-28)

- **Track 5 = corsia "Effects"** (pillole VIOLA, `clipFx` nel tema),
  libera come la Color. `Project.add_effect` smista per catalogo:
  ricette di grading → Color (track 1), ricette fx (subject/artistic) →
  Effects (track 5). `clear_lane("fx")`, tap → apre il pannello Effetti.
- **Dove piu' clip colore/effetto si SOVRAPPONGONO nel tempo (stessa
  corsia o corsie diverse), si applica SOLO l'ultimo inserito**: una
  matita sopra un bianco-e-nero lo SOSTITUISCE nel tratto comune, non
  si sommano; affiancati, ognuno governa il suo tratto. Implementazione:
  ogni span porta `order` = posizione del clip nella lista del progetto
  (transport), e `TimedColor` applica solo lo span attivo con l'`order`
  massimo. Spostare un clip effetto lo ri-appende in coda alla lista:
  "l'ultimo inserito" legge come "l'ultimo gesto deliberato".
- **La timeline non mente** (sera): piazzare, spostare o allungare un
  clip effetto RITAGLIA fisicamente gli altri clip Color/Effects che
  copre (`Project.carve_effect_lanes`): coperto intero → rimosso; testa
  o coda → accorciato; in mezzo → spezzato in due attorno al nuovo.
  Cosi' il rettangolo vecchio non resta mai sotto quello nuovo a
  mostrare un effetto che li' non suona piu'. La priorita' `order` nel
  motore resta come cintura per i progetti salvati con sovrapposizioni.
  Tutto dentro lo stesso passo di undo (il carve avviene nella stessa
  mutazione catturata da `_edit`).
- Le regolazioni MANUALI restano parte del clip che le porta (si
  compilano nello stesso span), quindi la regola vale anche per loro.
- L'audio segue gia' la stessa filosofia da sempre: un clip ha UN
  `audio_effect_id` — applicarne un altro sostituisce il precedente.
- Test: `tests/test_fx_lane.py` (smistamento, last-wins, move re-append)
  e `tests/visual/test_fx_lane_ui.py` (lo scenario dell'utente a pixel:
  noir 0-10 + matita 0-5 → carta bianca nel tratto comune, grigio dopo).

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

## 4-ter. La regolazione manuale (2026-08-27)

Nove manopole in cima al pannello (`color.dial.*`): luminosita',
contrasto, saturazione, gamma, temperatura, tinta, ombre, luci,
vignettatura. Vivono su un clip della corsia Colore — quello di un
effetto (le correzioni si SOMMANO alla ricetta, in coda) oppure un clip
«Regolazione» nudo (bottone nel pannello: adotta lo span del clip video
sotto il playhead, come il drop degli effetti).

Com'e' fatto: `ive/color/grade.py` — il grade e' un dict di manopole
FUORI dal default (`TimelineClip.grade`, persistito) e compila nello
STESSO vocabolario di op delle ricette (`ops_from_grade`), quindi il
motore non sa nulla di nuovo e anteprima ed export restano identici per
costruzione. Una manopola al default sparisce dal dict: il grade dice
esattamente cosa l'utente ha toccato. Ogni commit di slider = un'azione
`timeline.set_clip_grade` = un passo di undo. Restano: curve, HSL per
gamma, LUT `.cube` (la 3D LUT in numpy costa ~50+ ms/frame: quando
serve, valutare un'approssimazione o il futuro backend GPU).

## 5. Aggiungere un effetto nuovo

1. Copiare un JSON esistente, cambiare `id`, `name`, `section`, `ops`.
2. Metterlo in `user_data/effects/color/` (o mandarlo a un altro utente,
   che fa lo stesso). Sezioni nuove compaiono da sole in coda.
3. Niente riavvio necessario in futuro (`ColorFx.refresh()`); oggi al
   prossimo avvio.

Test: `tests/test_color_effects.py` (ops, catalogo, TimedColor, grafo),
`tests/test_artistic_effects.py` (op spaziali, esclusione LUT, catalogo),
`tests/visual/test_color_panel.py` (pannello, corsia, anteprima davvero
colorata, delete).
