# IVE — Roadmap

Sequenza di implementazione. Ogni step si chiude con codice **funzionante,
testato e documentato**, e non rompe gli step precedenti.

Le stime sono relative fra loro (S/M/L/XL), non calendarizzate.

---

## Principio di ordinamento

Le fondamenta si costruiscono dal basso: **modello → command → action →
servizio → UI**. La UI e' l'ultimo strato di ogni step, mai il primo.
Questo garantisce che ogni funzione sia testabile senza interfaccia e
invocabile dall'assistente fin dal primo giorno.

---

## Fase 0 — Fondamenta  ·  L  ·  **COMPLETATA**

Nessuna feature visibile, ma determina tutto quello che viene dopo.

- [x] Scaffolding "tre sorelle": `ive/` · `models/` · `user_data/`
- [x] `utils/paths.py` con i quattro helper + bootstrap idempotente
- [x] `utils/logging_setup.py`: rotating + faulthandler + excepthook + Qt handler
- [x] `settings/`: schema tipizzato, service, default in `config/defaults/`
- [x] `i18n/`: TranslationManager, `en.json`, bridge per `qsTr()`
- [x] `core/events/bus.py`
- [x] `core/actions/`: registry, schema, context, decoratore `@action`
- [x] `core/commands/`: base, UndoStack con transazioni e coalescing
- [x] Finestra QML minima + `Theme.qml` completo + primi componenti
- [x] **Prototipo dello shell immersivo** (`UI_SHELL.md`): avvio a schermo
      intero, `GlassSurface` con le soglie di scrim, `AmbientBackdrop` a
      10 Hz, tool rail, `FloatingPanel` con le regole di ritiro.
      **Misurare subito il costo della sfocatura** su video in riproduzione:
      se il ripiego a tinta piena si rendesse necessario, e' meglio saperlo
      prima di costruirci sopra.
- [x] `requirements.txt`
- [ ] `ruff`, `pytest`, CI su Win/Linux/macOS
- [x] `.gitignore`
- [ ] `LICENSE` — bloccato sulla decisione di `LICENSING.md` §1

**Fatto quando:** l'app si avvia, mostra una finestra vuota tematizzata, ha
log funzionanti su tutte e tre le piattaforme, e un'Action di prova e'
invocabile dai test senza UI.

**Verificato su Windows** (Python 3.10.11, PySide6 6.11, backend Direct3D11):
avvio a schermo intero, zero warning QML, cambio lingua e tema a runtime,
impostazioni persistite. **Da verificare su Linux e macOS.** Tre trappole
PySide6/QML incontrate qui sono documentate in `CODING_STANDARDS.md` §3-bis.

---

## Fase 1 — Modello di progetto e persistenza  ·  M

- [ ] `core/model/`: Project, Sequence, Track, Clip, EffectInstance, Keyframe
- [ ] `utils/timecode.py` con test esaustivi (incluso drop-frame)
- [ ] `project_io/`: serializer JSON versionato + migrations + autosave
- [x] Commands: ogni mutazione del progetto (place/move/remove/split/trim/
      volume/mute/audio/effetto/import/remove media) passa da `ProjectEdit`
      (memento in `core/commands/project_commands.py`) sull'`UndoStack`;
      azioni `edit.undo`/`edit.redo` (Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z),
      bottoni nel Readout, stack azzerato al cambio progetto
- [x] Action corrispondenti (`timeline_actions.py`, `edit_actions.py`)
- [x] Test: do → undo → stato identico (`tests/test_undo_redo.py`, il
      catalogo completo avanti e indietro); round-trip di serializzazione

**Fatto quando:** si crea un progetto via codice, lo si salva, lo si ricarica
identico, e ogni operazione e' annullabile. Ancora nessuna UI.

---

## Fase 2 — Media I/O e preview  ·  XL  ·  **IN CORSO**

Lo step tecnicamente piu' rischioso: farlo presto.

- [x] `media/probe.py` — metadata, rotazione, aspect anamorfico
- [x] `media/decoder.py` — **seek frame-accurate verificato** (18 posizioni,
      avanti/indietro/sequenziale, contro numero di frame impresso nel video)
- [x] `media/reader.py` — decodifica su worker thread con coalescing delle richieste
- [ ] `media/cache.py`
- [ ] `media/thumbnails.py`, `waveform.py` — asincroni
- [ ] Gestione colore fin da subito: spazio colore letto dai metadati,
      elaborazione in float lineare, range limited/full corretto,
      **tone mapping HDR→SDR** (vedi `MEDIA_FORMATS.md` §8)
- [ ] Rotazione dai metadati, frame rate variabile, primo frame non a zero
- [x] `video_engine/`: frame, graph, compositor, backend CPU (in `engine/`)
- [x] `audio_engine/`: mixer e resample in `engine/`, uscita in
      `playback/audio_output.py` (QAudioSink push-mode)
- [x] `playback/`: transport, clock, A/V sync, prefetch
- [x] `ui/preview_item.py` (QQuickPaintedItem; upload texture da fare)
- [x] `playback/transport.py` — play/pausa/seek/step; **il clock e' l'audio**
      (campioni processati dal device), timer solo come fallback senza device
- [x] Apertura file da tool rail e Ctrl+O; timeline legata al media aperto
- [x] Sfondo in loop per lo stato vuoto (720p, 15 fps, si ferma da solo)
- [x] **Audio e sincronizzazione A/V** — tono 440/880 Hz verificato DOPO il
      sink (`tests/test_audio_output.py`); conteggio campioni per frame
      drift-free ai rate frazionari (confini cumulativi, non round() costante)
- [ ] Proxy, cache di thumbnail e waveform
- [ ] Upload a texture nel PreviewItem (ora QQuickPaintedItem)
- [ ] Ambient backdrop alimentato dallo stesso frame decodificato, area
      libera e riscalatura animata del video (`UI_SHELL.md` §3)
- [ ] Transport HUD con auto-hide in riproduzione

**Fatto quando:** si apre un file, si riproduce con audio sincronizzato, si
fa seek preciso, e lo scrubbing e' fluido. Su tutte e tre le piattaforme.

> **Rischio principale del progetto.** A/V sync, seek frame-accurate e
> throughput del preview sono le tre cose che rendono difficile un editor
> video. Se qualcosa deve essere prototipato prima del resto, e' questo.

---

## Fase 3 — Timeline  ·  XL

- [ ] Media pool: import, metadata, thumbnail
- [ ] **Drag & drop di file e cartelle** dall'esterno, scansione ricorsiva,
      import asincrono con progresso, ordinamento per data di ripresa,
      rilevamento duplicati
- [ ] QML timeline: ruler, tracce, clip, playhead, zoom, scroll
- [ ] Drag & drop dal media pool alla timeline
- [ ] Trim, split, ripple delete, snap
- [ ] Selezione singola e multipla, copia/incolla
- [ ] Scorciatoie da tastiera mappate su action id
- [ ] Command palette (viene gratis dal registry)

**Fatto quando:** si monta un video reale: import, taglio, riordino, salvataggio,
riapertura. Il primo momento in cui l'app e' "usabile".

---

## Fase 4 — Export e preset  ·  M

Vedi `docs/EXPORT_PRESETS.md` e `docs/MEDIA_FORMATS.md`.

- [ ] Canvas preset (16:9, 9:16, 1:1, 4:5, 4:3, 21:9) + cambio rapporto con
      strategie fit/fill/blur, annullabile
- [ ] `export/presets.py` — preset dichiarativi JSON, codec **logici**
- [ ] `export/encoder.py` via PyAV
- [ ] `export/hwaccel.py` — rilevamento encoder hardware con test reale e
      fallback software
- [ ] `export/pipeline.py` — render → encode, progresso, cancellazione,
      scrittura su file temporaneo
- [ ] `JobService` + **coda di export** + status bar
- [ ] Dialog di export con validazione preventiva (alpha non supportata,
      aspect diverso, upscaling, HDR→SDR) e stima di dimensione
- [ ] Import/export di preset personalizzati come `.json` singolo
- [ ] Preset di sistema per YouTube / Shorts / Reels / Stories / TikTok /
      LinkedIn / Facebook / X / WhatsApp / archivio / ProRes

**Fatto quando:** il file esportato corrisponde al preview frame per frame,
lo stesso montaggio si esporta in coda per tre piattaforme diverse, e un
preset creato su una macchina funziona su un'altra con GPU differente.

---

## Fase 4-bis — Il motore  ·  L  ·  **PRIMA degli effetti**

Vedi `docs/ENGINE.md`. Senza questo, ogni effetto aggiunto e' debito.

- [x] `Frame` con stack immagine e audio pigri (`tests/test_engine.py`)
- [x] `Producer` / `Filter` / `Transition` / `Consumer`
- [x] `ClipProducer` (PyAV), `ColourProducer`, `Playlist`, `Multitrack`, `Tractor`
- [x] `PreviewConsumer` ed `ExportConsumer` sullo **stesso** grafo
- [x] Decodifica audio e mixer sullo stack audio (`tests/test_audio_graph.py`)
- [ ] Timebase della sequenza: il modello passa da secondi a frame
- [x] Traccia nera in fondo, come Kdenlive

**Fatto quando:** un effetto di prova applicato a una clip si vede identico in
anteprima e nel file esportato, senza che nessuno dei due percorso conosca
l'altro.

---

## Fase 5 — Effetti e testo  ·  L

- [ ] `effects/base.py` con parametri dichiarativi + registry
- [ ] Transform, crop, opacita', speed/time remap
- [ ] Correzione colore: lift/gamma/gain, curve, HSL, LUT `.cube`
- [ ] **Animazioni in/out** come keyframe dichiarativi (schema di
      `CONTENT_PACKS.md` §4.2), con preview nella libreria
- [ ] Transizioni: dissolve, wipe, slide, zoom, + supporto luma matte
- [ ] Titoli e testo, con font bundled e stili
- [x] Effetti audio: gain, EQ, compressore, normalizzazione loudness (2026-08-20, `docs/AUDIO.md`)
- [ ] Keyframe su qualunque parametro numerico + editor curve
- [ ] Pannello Inspector generato **dallo schema** dei parametri, non a mano

**Fatto quando:** un utente monta un video completo con color grading, testo e
transizioni. Aggiungere un effetto nuovo non richiede toccare la UI.

---

## Fase 6A — Content Pack  ·  L

Il sistema che permette alla comunita' di contribuire senza programmare.
Vedi `docs/CONTENT_PACKS.md`.

- [ ] `packs/`: manifest, installer `.ivepack`, library, indice cachato
- [ ] Installazione per drag & drop, con licenza mostrata prima della conferma
- [ ] Tipi di contenuto: audio (con loop e beat marker), animazioni in/out
      (keyframe JSON), transizioni (parametriche e luma matte), LUT `.cube`,
      font, overlay, template, export e canvas preset
- [ ] Librerie in UI con ricerca, filtri, preview e provenienza
- [ ] Tracking delle risorse mancanti all'apertura di un progetto altrui —
      il progetto si apre comunque
- [ ] "Raccogli risorse": progetto autonomo e trasferibile
- [ ] Validatore di pack (in-app e CLI)
- [ ] **"Esporta come content pack"** dall'app, senza editor di testo
- [ ] Pack starter `com.ive.starter` costruito con lo stesso formato pubblico
- [ ] Badge e generazione `credits.txt` per i contenuti con attribuzione

**Fatto quando:** un utente crea un pack di musiche dall'app, lo manda a un
altro utente che lo installa trascinandolo, e le tracce compaiono nella
libreria accanto a quelle di serie, indistinguibili.

---

## Fase 6B — Sistema di plugin  ·  M

- [ ] Manifest, host, discovery, isolamento degli errori
- [ ] API pubblica versionata (`api_version: 1`)
- [ ] Punti di estensione: effetti, transizioni, esportatori, action, task AI
- [ ] Un plugin di esempio + documentazione per sviluppatori
- [ ] UI di gestione plugin con licenze visibili

**Fatto quando:** un plugin esterno aggiunge un effetto senza modificare il
core, e un plugin rotto non fa cadere l'app.

---

## Fase 7 — Strumenti AI  ·  XL

Nell'ordine, per rapporto valore/rischio:

- [ ] Infrastruttura: `AITask`, model registry, downloader, runtime, backend
- [ ] **Sottotitoli automatici** — il valore piu' alto, il rischio piu' basso
- [ ] **Traduzione** dei sottotitoli
- [ ] **Rimozione sfondo** — attenzione alle licenze
- [ ] **Motion tracking** — prima i tracker OpenCV, poi il livello AI
- [ ] **Frame interpolation** — il piu' costoso, per ultimo

Ogni funzione segue la checklist di `docs/AI_FEATURES.md` §11.

**Fatto quando:** ogni funzione AI e' annullabile, correggibile a mano,
funziona su CPU, e degrada in modo pulito se il modello non e' installato.

---

## Fase 8 — Assistente in linguaggio naturale  ·  M

Arriva tardi non perche' sia meno importante, ma perche' il suo valore e'
proporzionale al numero di Action disponibili. Con l'architettura corretta,
e' uno step piccolo.

- [ ] `automation/tool_adapter.py`: registry → tool schema
- [ ] `automation/planner.py`: piano, dry-run, conferma
- [ ] `automation/assistant.py`: interfaccia provider (locale / remoto)
- [ ] Pannello assistente + transcript
- [ ] Controlli privacy espliciti e visibili

**Fatto quando:** "taglia i primi 3 secondi e aggiungi i sottotitoli in
italiano" funziona, e un solo Ctrl+Z annulla tutto.

---

## Fase 9 — Accelerazione hardware  ·  L

Deliberatamente tardi: il backend CPU e' la reference implementation, e serve
prima che ci sia qualcosa contro cui confrontarsi.

- [ ] `backends/detect.py` con capability detection reale
- [ ] Backend CUDA
- [ ] Backend OpenVINO
- [ ] Backend ROCm
- [ ] Encoding hardware in export
- [ ] Test di regressione visiva: ogni backend vs CPU

**Fatto quando:** su ogni macchina l'app sceglie il percorso migliore da sola,
e un backend rotto degrada a CPU senza che l'utente perda lavoro.

---

## Fase 10 — Rifinitura e distribuzione  ·  L

- [ ] Traduzioni complete IT / PT / ES
- [ ] `.spec` PyInstaller per Windows, Linux, macOS
- [ ] `THIRD_PARTY_LICENSES.md` generato automaticamente
- [ ] Schermata About / Licenze
- [ ] Onboarding, stati vuoti, scorciatoie documentate
- [ ] Passata di accessibilita' (contrasto, tastiera, screen reader)
- [ ] Profiling e ottimizzazione — con numeri, non a sensazione
- [ ] Documentazione utente

---

## Cosa e' fuori scope per la 1.0

Da non implementare, per non compromettere le fondamenta:

- **Editing ed export HDR nativo** (pipeline 10 bit, HDR10/HLG). La 1.0
  *gestisce correttamente* il materiale HDR con tone mapping verso SDR, che
  copre il caso reale piu' frequente (girato con smartphone, pubblicato in
  SDR). Vedi `MEDIA_FORMATS.md` §8.
- **Repository online di content pack.** La 1.0 supporta lo scambio diretto
  fra utenti via file, che non richiede infrastruttura ne' moderazione.
- Dolby Vision, Dolby Atmos (licenze proprietarie)
- Collaborazione multi-utente
- Editing su cloud / sincronizzazione
- Editing 3D o compositing nodale
- Cattura schermo e registrazione
- Streaming diretto verso piattaforme
- Editing multicam
- Formati di progetto di editor terzi (import/export)

Ognuno di questi e' un progetto a se'. Vanno valutati dopo la 1.0, e
l'architettura modulare deve permettere di aggiungerli senza riscritture.

---

## Regola per ogni step

1. Prima il modello, poi il command, poi l'action, poi il servizio, poi la UI
2. Test che coprono l'action **senza** UI
3. Documentazione aggiornata nello **stesso** step, non dopo
4. Nessuna regressione sugli step precedenti
5. Funziona su Windows, Linux e macOS prima di considerarlo chiuso
