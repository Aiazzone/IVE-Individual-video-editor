# IVE — Strumenti AI

Contratti, vincoli e struttura del modulo `ai/`. Le licenze dei modelli
citati stanno in `docs/LICENSING.md` §4 e **vanno riverificate alla fonte**
prima di ogni integrazione.

---

## 1. Principi

1. **L'AI non e' un requisito.** L'app deve installarsi, aprirsi e montare un
   video senza un solo modello scaricato. Le funzioni AI non disponibili si
   mostrano **disabilitate con una spiegazione**, non nascoste.
2. **I pesi non sono nel bundle.** Si scaricano su richiesta esplicita, con
   licenza e dimensione mostrate prima del download. Nessun download
   silenzioso, mai.
3. **Tutto e' annullabile.** Ogni risultato AI entra nel progetto tramite un
   `Command`. Un Ctrl+Z annulla l'intera operazione.
4. **Tutto e' un'Action.** Ogni funzione AI e' registrata nell'Action
   Registry, quindi e' anche invocabile dall'assistente in linguaggio
   naturale e dagli script.
5. **Tutto e' un Job.** Nessuna inferenza sul thread GUI. Progresso,
   cancellazione ed errori passano da `JobService`.
6. **Tutto e' correggibile a mano.** L'AI produce un punto di partenza
   modificabile: sottotitoli editabili, maschere ritoccabili, tracking con
   keyframe correggibili. Mai un risultato opaco.
7. **Elaborazione locale di default.** Nessun contenuto utente esce dalla
   macchina senza consenso esplicito e per-operazione.

---

## 2. Struttura

```
ai/
├── base.py              AITask: contratto comune
├── model_registry.py    catalogo modelli: id, url, checksum, licenze, size
├── downloader.py        download con verifica checksum, ripresa, cancellazione
├── runtime/
│   ├── session.py         wrapper unico sulle sessioni di inferenza
│   ├── providers.py       onnxruntime / openvino, ordine di preferenza
│   └── detect.py          rilevamento device disponibili
├── subtitles/
├── translate/
├── matting/
├── tracking/
└── interpolation/
```

### Contratto `AITask`

```python
class AITask(Protocol):
    id: str
    required_models: list[str]

    def is_available(self) -> AvailabilityStatus: ...
        # READY | MODEL_MISSING | BACKEND_MISSING | UNSUPPORTED_PLATFORM

    def estimate(self, inputs: TaskInputs) -> Estimate: ...
        # durata stimata, VRAM/RAM richiesta

    def run(self, inputs: TaskInputs, progress: ProgressReporter,
            cancel: CancelToken) -> TaskResult: ...
```

Vincoli su `run()`:
- gira **sempre** su un worker, mai sul thread GUI;
- riporta il progresso in modo granulare (almeno 1 aggiornamento/secondo);
- controlla `cancel` a ogni step e si ferma in modo pulito;
- non mutua il modello di progetto: **ritorna dati**, il `Command` li applica;
- solleva eccezioni tipizzate (`ModelNotFoundError`, `InferenceError`,
  `UnsupportedInputError`), mai eccezioni generiche.

---

## 3. Selezione del backend

Ordine di preferenza di default, con fallback automatico verso il basso:

| Piattaforma | Ordine |
|---|---|
| Windows + NVIDIA | CUDA → DirectML → CPU |
| Windows + AMD/Intel | DirectML → OpenVINO → CPU |
| Linux + NVIDIA | CUDA → CPU |
| Linux + AMD | ROCm → CPU |
| Linux/Windows + Intel | OpenVINO → CPU |
| macOS | CoreML → CPU |

Regole:
- l'ordine e' sovrascrivibile dai settings;
- un fallimento di inizializzazione **o durante l'inferenza** scala al
  backend successivo, con WARNING nel log e notifica non bloccante;
- il backend attivo e' visibile nella status bar;
- il percorso CPU e' sempre presente e sempre testato.

---

## 4. Sottotitoli automatici

**Pipeline:** estrazione audio → VAD → speech-to-text → allineamento a livello
di parola → segmentazione in righe → clip di testo sulla timeline.

Punti importanti:
- **Timestamp a livello di parola**, non solo di frase: servono per il
  karaoke/highlight e per un taglio pulito delle righe.
- Segmentazione con regole configurabili: caratteri massimi per riga, righe
  massime, durata minima e massima, gap minimo tra sottotitoli.
- L'output e' un **track di testo editabile**, non un burn-in. Il burn-in e'
  una scelta separata al momento dell'export.
- Import/export SRT, VTT e ASS.
- Rilevamento automatico della lingua, sovrascrivibile.
- Deve funzionare a velocita' accettabile su CPU: e' la funzione AI che gli
  utenti useranno di piu'.
- Un modello grande su un video lungo puo' richiedere molto tempo: mostrare
  una stima **prima** di partire.

**Candidato principale:** `faster-whisper` (CTranslate2) — licenza
permissiva, buona velocita' su CPU, timestamp per parola. Alternativa
leggera: `whisper.cpp`.

### Stato (2026-08-25): implementati

- `ai/model_registry.py` + `ai/downloader.py`: catalogo con URL ancorati
  a revisione e SHA-256 per file, download streaming con verifica hash,
  ripresa per-file, cancel pulito. Modelli: `whisper-tiny` (~78 MB) e
  `whisper-small` (~486 MB, default), pesi MIT in `models/subtitles/`.
- `ai/subtitles/`: estrazione audio PyAV (16 kHz mono, tempo MEDIA con
  `start_time` sottratto), trascrizione faster-whisper con VAD e
  timestamp per parola, segmentazione in righe (`segment.py`, regole:
  max 42 caratteri, max 5.5 s, min 0.8 s, gap 0.9 s, stacco a fine
  frase) — PER SORGENTE, non sul mix: trim e spostamenti sono rispettati
  per costruzione e la corsia Musica non inquina mai le parole.
- **La trascrizione gira in un PROCESSO separato**
  (`ai/subtitles/worker.py`, protocollo line-JSON su stdin/stdout).
  Non e' solo isolamento dei crash: **ctranslate2 porta il suo
  `libiomp5md.dll`** e nel venv condiviso (torch, runtime Intel in
  Library/bin) l'import nel processo dell'app ABORTISCE con
  `OMP Error #15` prima di qualunque eccezione Python. Il workaround
  (`KMP_DUPLICATE_LIB_OK`) sta nel worker e solo li'; il processo app
  non importa mai faster_whisper/ctranslate2 (la disponibilita' si
  controlla con `find_spec`, senza import).
- `SubtitleService` (`ui/subtitle_service.py`, singleton QML
  `Subtitles`), card nel pannello Testo, azioni
  `timeline.auto_subtitles` / `subtitles.download_model` /
  `subtitles.cancel`; le righe atterrano via `place_subtitles` in UN
  undo come titoli normali (y=0.88, scale 0.05) — modificabili una per
  una. Settings: `ai.subtitles_model`, `ai.subtitles_language`.
- Test: `tests/test_subtitles.py` (57 check: regole, registro,
  downloader su `file://`, trascrizione reale del parlato TTS col tiny,
  worker, servizio con undo e cancel), visual
  `tests/visual/test_subtitles_ui.py`.

Secondo passaggio (2026-08-26), anche questi implementati:

- **SRT/VTT** (`ive/text/subtitle_files.py`): export della corsia Testo
  (dialetto dall'estensione) e import tollerante (BOM, tag, timestamp
  senza ore, cue rotte saltate mai fatali) — azioni
  `subtitles.export_file` / `subtitles.import_file`, bottoni nella card.
- **Karaoke per parola**: i word timestamp stanno nel MODELLO
  (`TimelineClip.words`, clip-locali, sopravvivono a salvataggio e
  spostamenti), lo switch e' per clip (`timeline.set_clip_karaoke`,
  solo su clip CON parole), il renderer colora le parole gia' dette
  (`render_text(highlight, highlight_count)`, path per parola alla
  stessa posizione del blocco) e il closure `sprite` la sceglie dal
  tempo locale — cache a N+1 stati per size, anteprima ed export
  identici per costruzione. Verificato sui pixel.
- **Lingua dalla UI**: chip nella card (Auto/IT/EN/PT/ES/FR/DE →
  `subtitles.set_language`).
- **Schermata "Modelli AI"** (Impostazioni → AI): scelta del modello
  (`subtitles.set_model`), per ogni modello stato/peso su disco/
  licenza, download e rimozione espliciti (`Subtitles.download(id)`,
  `Subtitles.remove(id)`).

Restano: ASS, `estimate()` prima di partire, traduzione (§5).

---

## 5. Traduzione

Due usi distinti:
1. **Traduzione dei sottotitoli** generati o importati.
2. **Traduzione dei testi** (titoli, caption) presenti nel progetto.

> Da non confondere con l'i18n dell'interfaccia (`docs/I18N.md`): moduli
> separati, nessun codice in comune.

### Stato (2026-08-26): la traduzione dei sottotitoli e' implementata

- **Coppie OPUS-MT di Argos caricate DIRETTAMENTE** con ctranslate2 +
  sentencepiece (`ive/ai/translate/`): la libreria argostranslate — che
  trascina stanza, spacy e thinc nel venv — non entra mai. Le righe dei
  sottotitoli sono corte: niente sentence splitter, una riga = un'unita';
  i `\n` interni sopravvivono (le righe si traducono separatamente).
- Coppie a catalogo (registry con URL ancorati e SHA-256): it/pt/es ↔ en.
  Le coppie mancanti fanno **pivot per l'inglese** (`translate_route`).
  Anche queste appaiono nella schermata "Modelli AI" con download e
  rimozione.
- La sorgente e' la lingua fissata nei settings o quella **rilevata**
  dall'ultima trascrizione (il worker la riporta, `detectedLanguage`).
- Inferenza in **processo separato** (`ive/ai/translate/worker.py`) —
  stesso contratto e stesse ragioni dei sottotitoli (OpenMP + crash).
- I timing NON si toccano; il testo cambia in UN undo
  (`apply_translations`); word timestamp e karaoke vengono azzerati
  (appartengono alle parole della lingua originale) e il Ctrl+Z riporta
  TUTTO, karaoke compreso. Le righe la cui traduzione supera ~21
  caratteri/secondo vengono contate e segnalate, mai troncate.
- UI nella card sottotitoli: chip di destinazione (EN/IT/PT/ES),
  bottone Traduci, download coppia con dimensione, progresso e annulla;
  azioni `subtitles.translate` / `set_translate_target` /
  `download_translate_models`.
- Test: `tests/test_translate.py` (26 check, coppie reali it→en e pivot
  it→es), visual esteso in `test_subtitles_ui.py`.

Punti gia' fissati dal progetto e ancora validi:
- Traduzione **locale** di default (Argos Translate / OPUS-MT).
- Il risultato e' una **nuova traccia di sottotitoli**, l'originale resta.
- Un glossario per-progetto permette di forzare la traduzione di termini
  specifici (nomi propri, brand).
- La traduzione preserva i timing dell'originale; se il testo tradotto e'
  troppo lungo per la durata, si segnala invece di troncare in silenzio.
- Modelli con pesi non-commercial (es. NLLB-200) sono selezionabili ma
  **dichiarati** in UI.

---

## 6. Rimozione sfondo (matting)

**Pipeline:** frame → matting → alpha matte → composizione, con coerenza
temporale tra frame consecutivi.

Punti importanti:
- Il flickering tra frame e' il problema principale: preferire modelli
  **video-aware** (con memoria temporale) a un matting per-frame; in
  alternativa, smoothing temporale della matte.
- Output = **canale alpha sulla clip**, non un rendering distruttivo.
- Anteprima a risoluzione ridotta, elaborazione finale a piena risoluzione
  all'export.
- Refinement manuale: pennello per correggere la matte, feather, choke,
  soglia — l'AI e' il punto di partenza.
- Cache della matte su disco per non ricalcolare a ogni seek.
- Alternativa sempre disponibile senza AI: chroma key classico.

**Attenzione licenze:** Robust Video Matting e' GPL-3.0; MODNet ha pesi spesso
non-commercial. Questa e' l'area con i vincoli piu' stretti — vedi §4 di
`docs/LICENSING.md`.

### 6-bis. Segmentazione del soggetto (IMPLEMENTATA, 2026-08-28 — Fase A)

L'ingrediente comune degli effetti a maschera del pannello Effetti
(aura attorno al soggetto, sfondo sfocato/b\&n/in movimento): una
maschera soft per frame di "cio' che e' in evidenza" — persona,
animale od oggetto, senza classi.

- **Modulo**: `ive/ai/segmentation/` — `SubjectSegmenter.mask(frame_rgb,
  size=None) -> uint8` (0 = scena, 255 = soggetto, bordi morbidi);
  `availability()` = ready / model_missing / backend_missing (stato,
  mai errore). Qt-free; il motore non lo importa — il builder
  attacchera' una closure maschera come fa con gli sprite (Fase B).
- **Modello**: `u2netp` (U²-Net small, ~4,6 MB, Apache-2.0; ONNX di
  rembg, MIT) nel registry con URL+SHA-256; input fisso 320x320,
  normalizzazione ImageNet, output min-max normalizzato (post-process
  di riferimento U²-Net). Compare da solo nel tab Modelli AI.
- **Provider a runtime**: DirectML quando disponibile, CPU altrimenti.
  Misurato sul dev PC (NVIDIA T500 / Iris Xe): **34 ms** a maschera su
  DirectML, **446 ms** su CPU — su CPU nuda serviranno cache/stride
  delle maschere (stile proxy) prima dell'uso live; su GPU e' gia'
  vicino al budget frame.
- Una sola istanza per processo (la sessione costa); `run` e'
  thread-safe per contratto ONNX Runtime.
- Test: `tests/test_segmentation.py`.

**Fase B (2026-08-28, stessa giornata)**: le op a maschera nel motore —
`aura`, `bg_blur`, `bg_gray` nel vocabolario colore (COLOR_EFFECTS.md) —
e la sezione di fabbrica "subject" con 6 ricette (aure, Ritratto, Colore
selettivo, Sognante). Il ponte: `filters.set_mask_provider(fn)` iniettato
da `app.py` con `segmentation.mask_provider()` (disponibilita' verificata
per chiamata: un modello scaricato a meta' sessione inizia a rispondere
senza riavvio; LRU su fingerprint 8x8 per i frame ripetuti). Verificato
end-to-end nell'app (`tests/visual/test_subject_effects.py`: aura dorata
sui pixel dell'anteprima) e a motore nudo con provider stub
(`tests/test_masked_effects.py`). Nota: la prima maschera carica la
sessione (~3-4 s una tantum) e il watchdog registra uno stallo GUI —
miglioria futura: preriscaldare la sessione quando un effetto subject
entra in timeline.

**Fase C (2026-08-28)**: il pannello **Effetti** (icona della rail,
tasto 3) sfoglia le sezioni `subject` e `artistic`; il pannello Colore
tiene solo il grading. Stesso browser (`ColorContent` con `catalog:
"fx"`), stesso catalogo — vedi COLOR_EFFECTS.md §3-bis. Corsia
"Effects" (track 5) e regola "vince l'ultimo inserito": §3-ter.

**Fase D (2026-08-28, sera)**: op `bg_zoom` (parallasse 2.5D, ricetta
"Parallasse"; progress `_t` iniettato da TimedColor, blur crescente a
mascherare il bordo doppio — non c'e' inpainting) e **warm-up della
sessione**: `segmentation.warm_up()` (thread daemon sul segmenter
condiviso `shared_segmenter()`) chiamato da `app._warm_masks` appena un
effetto a maschera entra in timeline. Rinviato: cache delle maschere su
disco stile proxy (utile solo per macchine senza GPU DX12).

---

## 7. Motion tracking

**Pipeline:** selezione della regione → tracking → traiettoria di keyframe →
applicazione a un altro elemento (testo, effetto, maschera, mosaico).

Punti importanti:
- Baseline **senza modelli AI**: `TrackerMIL` di OpenCV, sempre disponibile
  senza download (solo posizione: il suo riquadro non cambia dimensione).
  CSRT/KCF sarebbero baseline migliori ma stanno in `opencv-contrib`, che
  il progetto non spedisce (il venv ha `opencv-python` 4.11).
- Livello di qualita': `TrackerVit` di OpenCV con i pesi VitTrack
  (~0,7 MB, Apache-2.0, nel registry come `vittrack`). Segue posizione **e
  dimensione**, da' uno score di confidenza; ~16 ms/frame su CPU.
- Livello AI opzionale (futuro) per point tracking robusto a occlusioni.

**Stato (2026-11-01) — Fase A fatta** (`ive/ai/tracking/`, test
`tests/test_tracking.py`):
- `tracker.py`: ViT o MIL dietro un'interfaccia sola; perdita = score <
  0,30 per 4 frame di fila (un frame sfocato non chiude il tracking).
- `mapping.py`: sorgente <-> canvas in geometria pura (crop, poi fit / fill
  / blur, oppure placement libero con rotazione) — verificata contro i
  pixel del motore vero entro 2 px. Si traccia la SORGENTE, non il
  composito: il composito contiene l'overlay stesso che si sta muovendo.
- `task.py`: finestra = sovrapposizione overlay/clip A/V dall'istante del
  riquadro in avanti (un taglio e' un'altra inquadratura: ci si ferma);
  decode sequenziale a 480p; frame troncati come il transport.
- `path.py`: l'overlay conserva la distanza dal soggetto che aveva
  all'inizio (scalata con lui se segue la dimensione); media mobile, poi
  Ramer-Douglas-Peucker (~2 px a 1080p): 75 frame -> ~11 pin.
- Risultato = keyframe ordinari dell'overlay via
  `Project.apply_tracked_path` (riscrive x/y/scale SOLO nella finestra,
  conserva rotazione/opacita' messe a mano; un Command, un Ctrl+Z).
  Prerequisito fatto nella stessa fase: **le overlay (sticker, titoli)
  leggono i keyframe** (filtro `Overlays`; il preset motion modula sopra).
- `ui/tracking_service.py` (thread worker, progresso, annullamento) +
  Action `overlay.track` / `overlay.track_cancel`. Codici d'errore
  tradotti in `tracking.err.*`.

**Fase B — fatta (2026-11-01)** (test `tests/visual/test_tracking_ui.py`):
- `components/TrackingCard.qml` nei pannelli Sticker e Testo, sotto la
  scheda Animazione: "Disegna il soggetto" arma la preview
  (`Tracking.drawingFor`, stato condiviso nel servizio), progresso +
  stop, esito (pin posati, punto di perdita) o errore tradotto, avviso
  "solo posizione" quando VitTrack manca.
- Strato di disegno in `StickerHandles.qml` (sopra ogni maniglia, Esc
  annulla, riquadri < 8 px ignorati): converte col mapping "cover" e
  invoca `overlay.track` all'istante della testina in pausa.
- Le maniglie delle overlay seguono i keyframe. **Regola del drag** su
  un'overlay con keyframe: testina SU un diamante (±50 ms, lo stesso
  criterio che accende il bottone keyframe) = corregge quel pin;
  testina FRA i pin = sposta TUTTO il percorso
  (`timeline.shift_clip_path`; anteprima live con `shift` nello span,
  `transport.set_overlay_shift_live`). Lo spostamento NON fa clamp sui
  pin: un percorso tracciato puo' uscire dal canvas e va traslato, non
  piegato.
- Diamanti dei keyframe anche sulle corsie Sticker/Testo; il bottone
  keyframe della timeline vale anche per le overlay.

**Poi**: tracking all'indietro (serve un buffer di frame: il decoder
all'indietro costa un seek per frame); re-tracking parziale dalla UI
(dal motore c'e' gia': la finestra riscritta parte dalla testina).
- Il risultato e' una **serie di keyframe modificabili**, non una curva
  opaca: l'utente deve poter correggere un frame sbagliato.
- Supporto a tracking all'indietro dal punto corrente e a re-tracking
  parziale di un intervallo.
- Rilevare la perdita del target e fermarsi, invece di produrre dati
  spazzatura.

---

## 8. Frame interpolation

**Usi:** slow motion fluido, aumento del frame rate, riempimento di gap.

Punti importanti:
- E' la funzione **piu' costosa** in assoluto: mai in tempo reale sul
  preview. Anteprima su un intervallo breve, applicazione come render
  in background con risultato cached.
- Il risultato e' cachato su disco e legato alla clip: cambiare i parametri
  della clip a monte invalida la cache.
- Falliscono su cambi di scena e movimenti molto rapidi: rilevare i cut e non
  interpolare attraverso di essi.
- Fallback sempre disponibile: duplicazione o blending di frame, senza AI.
- Mostrare una stima di tempo prima di partire.

**Attenzione licenze:** alcune release dei pesi RIFE sono non-commercial;
FILM (Apache-2.0) e' l'alternativa permissiva da valutare.

---

## 9. Assistente in linguaggio naturale

Non e' un modulo AI come gli altri: e' un **livello di orchestrazione** sopra
l'Action Registry (`automation/`, vedi `ARCHITECTURE.md` §4).

Punti importanti:
- Non ha logica di editing propria: traduce la richiesta in una sequenza di
  action id + parametri. Se un'operazione non e' un'Action, l'assistente non
  la puo' fare — ed e' un bene.
- Il piano viene **mostrato prima dell'esecuzione** quando contiene
  operazioni distruttive o non annullabili.
- L'esecuzione e' una **singola transazione** dell'undo stack.
- Provider dietro interfaccia: locale (llama.cpp / Ollama) o remoto,
  configurabile. Nessun provider e' obbligatorio.
- **Privacy:** nessun contenuto del progetto viene inviato a un servizio
  remoto senza consenso esplicito. Di default si inviano solo la richiesta
  testuale e uno schema del progetto (numero e tipo di tracce, durate) —
  mai i file media. Il livello di condivisione e' un'impostazione visibile.
- Ogni azione eseguita finisce in un transcript ispezionabile.
- L'app resta **pienamente funzionale con l'assistente disattivato**.

---

## 10. Gestione dei modelli

- I pesi vivono in `models/<task>/<model_id>/`, sorella del programma: **non**
  vengono toccati dagli update dell'app.
- `model_registry.py` e' la fonte di verita': id, versione, URL, checksum
  SHA-256, dimensione, licenza codice, licenza pesi,
  `commercial_use_allowed`, backend supportati.
- Il download verifica il checksum. Un file corrotto viene scartato, non
  usato.
- Una schermata "Modelli AI" nei settings mostra: cosa e' installato, quanto
  occupa, quale licenza, e permette di rimuovere.
- Modelli caricati **lazy** e scaricati dalla memoria dopo un periodo di
  inattivita' configurabile: tenerne diversi residenti esaurisce la RAM.
- Un modello mancante non e' un errore: e' uno stato `MODEL_MISSING` che la
  UI presenta come invito al download.

---

## 11. Checklist per una nuova funzione AI

1. [ ] Licenza del codice **e** dei pesi verificata e registrata
2. [ ] Implementa il contratto `AITask` (`is_available`, `estimate`, `run`)
3. [ ] Registrata in `model_registry.py` con checksum
4. [ ] Gira su `JobService`, con progresso e cancellazione funzionanti
5. [ ] Ha un percorso CPU funzionante
6. [ ] Degrada correttamente se il modello non e' installato
7. [ ] Il risultato entra nel progetto via `Command` (annullabile)
8. [ ] Il risultato e' correggibile a mano
9. [ ] Registrata come Action, con chiavi di traduzione
10. [ ] Nessun dato utente lascia la macchina senza consenso esplicito
11. [ ] Testata con input degeneri: clip di 1 frame, audio muto, video nero,
        risoluzione anomala, file corrotto
