# IVE — Roadmap

Sequenza di implementazione. Ogni step si chiude con codice **funzionante,
testato e documentato**, e non rompe gli step precedenti.

Le stime sono relative fra loro (S/M/L/XL), non calendarizzate.

> **Audit sul codice del 2026-09-19.** Ogni casella di questo file e' stata
> riconfrontata con il sorgente (moduli, azioni registrate, cataloghi di
> fabbrica, test). Le voci che il codice aveva superato sono state spuntate,
> quelle fatte in modo diverso dal piano lo dicono, e cio' che resta e'
> scritto accanto a ogni voce. Il riepilogo e' in fondo: «Cosa manca alla 1.0».
> Numeri al momento dell'audit: ~23 000 righe Python, oltre 100 azioni registrate,
> 53 suite di test + 55 test visivi, 449 chiavi di traduzione in 4 lingue.

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
- [ ] `ruff`, `pytest`, CI su Win/Linux/macOS — audit 2026-09-19: nessuna
      configurazione di lint, nessun `pyproject.toml`/`conftest.py`, nessuna
      CI. Le 53 suite in `tests/` sono **script** (`__main__`, guidano l'app
      vera); solo 5 hanno anche funzioni `test_*`. Decidere: o un runner che
      le raccoglie tutte, o la migrazione a pytest. **2026-11-02: scelto il
      runner** (`tests/run_all.py`, uno solo per Windows e Linux: uscita 2
      = prerequisito mancante, mostrato come SALTATO; fallimenti noti e
      instabili elencati a parte) e uno script di preparazione per Linux.
      La cartella `tests/` resta locale per scelta, quindi niente CI per
      ora; macOS non e' verificabile a mano. Restano lint e CI
- [x] `.gitignore`
- [x] `LICENSE` — **GPL-3.0-or-later** (file alla radice dal primo commit,
      dichiarata nel README; `LICENSING.md` §1 aggiornato il 2026-09-19)

**Fatto quando:** l'app si avvia, mostra una finestra vuota tematizzata, ha
log funzionanti su tutte e tre le piattaforme, e un'Action di prova e'
invocabile dai test senza UI.

**Verificato su Windows** (Python 3.10.11, PySide6 6.11, backend Direct3D11):
avvio a schermo intero, zero warning QML, cambio lingua e tema a runtime,
impostazioni persistite. **Da verificare su Linux e macOS.** Tre trappole
PySide6/QML incontrate qui sono documentate in `CODING_STANDARDS.md` §3-bis.

---

## Fase 1 — Modello di progetto e persistenza  ·  M  ·  **FATTA in forma diversa dal piano**

- [x] `core/model/project.py` — fatto, ma **piu' piatto del piano**:
      `Project`, `MediaItem`, `TimelineClip` (niente classi Sequence/Track/
      EffectInstance/Keyframe). Le tracce sono numeri fissi con un ruolo
      (0 video+musica, 1 Colore, 2 Sticker, 3 Testo, 5 Effetti); effetti,
      grade, motion e keyframe sono campi del clip. Una sola sequenza per
      progetto. Tracce video multiple / picture-in-picture: **da fare**, ed
      e' il punto in cui il modello piatto andra' ripensato
- [x] `utils/timecode.py` con test esaustivi (incluso drop-frame) —
      fatto il 2026-11-02 (`tests/test_timebase.py`): rate esatte come
      `Fraction` (29.97 = 30000/1001), frame ↔ secondi, timecode SMPTE
      drop-frame a 29.97/59.94 in entrambe le direzioni (round-trip su un
      giorno intero). Il transport formatta da qui
- [x] Persistenza — dentro `Project.to_dict/from_dict` e
      `ProjectService.open/save`, non in un `project_io/` separato: JSON con
      `schema_version` (=1), lettura tollerante (campi ignoti ignorati, file
      di versione piu' nuova aperto con avviso), scrittura atomica
      (`.tmp` + rename), **autosave a ogni edit**, media mancanti marcati
      all'apertura senza bloccarla. Schema 2 (2026-11-02): tempi in frame;
      la migrazione da 1 e' in `Project.from_dict` (adotta la frequenza,
      aggancia i tempi alla griglia). **Resta:** un modulo di *migrations*
      separato quando ne servira' una seconda, e un autosave su file
      separato con recupero dopo crash
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
*(Criterio soddisfatto: `tests/test_undo_redo.py`,
`tests/test_project_service_safety.py`.)*

---

## Fase 2 — Media I/O e preview  ·  XL  ·  **COMPLETATA su Windows**
   (resta la verifica Linux/macOS della regola d'oro, e il float
   lineare/HDR nativo dichiarato post-1.0)

Lo step tecnicamente piu' rischioso: farlo presto.

- [x] `media/probe.py` — metadata, rotazione, aspect anamorfico
- [x] `media/decoder.py` — **seek frame-accurate verificato** (18 posizioni,
      avanti/indietro/sequenziale, contro numero di frame impresso nel video)
- [x] `media/reader.py` — decodifica su worker thread con coalescing delle richieste
- [x] Cache dei media: ASSORBITA da decoder (cursor+frame cache),
      read-ahead (30 frame) e proxy — un `media/cache.py` separato non
      e' mai servito; se un giorno serve, questa riga e' il promemoria
- [x] Thumbnail e waveform asincroni (`ui/thumbnails.py`,
      `ui/waveforms.py`: worker thread, PNG cache in user_data)
- [x] **Matrice colore corretta** (2026-08-24): un file taggato e'
      onorato da swscale; un file SENZA tag usa la convenzione per
      dimensione (HD = BT.709, non piu' il default 601); l'export
      converte con la matrice dell'uscita E la dichiara nel file
- [x] **HDR gestito e range chiuso** (2026-08-26, MEDIA_FORMATS.md §8):
      la probe riconosce PQ/HLG/10-bit; la decodifica fa **tone mapping
      verso SDR** (203 nit → bianco SDR, ginocchio sui soli highlight,
      gamut 2020→709; 67 ms/frame a 1080p via LUT); il proxy di una
      sorgente HDR esce SDR 709 taggato (tempo reale via proxy, mai
      doppia mappatura); l'export dichiara matrice+transfer+primaries+
      **range**; pool e preflight avvisano. Resta (dopo la 1.0):
      pipeline float lineare/10 bit ed export HDR nativo
- [x] Rotazione dai metadati (2026-08-24: la display matrix dei telefoni
      si legge SOLO dal frame decodificato in questo PyAV — la probe ne
      decodifica uno; pixel-verificata fino al motore), frame rate
      variabile (fps = average_rate, campionamento per TEMPO), primo
      frame non a zero (video gia' ok; l'ancora AUDIO ora sottrae lo
      start_time — un MPEG-TS non suona piu' 1,4 s in ritardo)
- [x] `video_engine/`: frame, graph, compositor, backend CPU (in `engine/`)
- [x] `audio_engine/`: mixer e resample in `engine/`, uscita in
      `playback/audio_output.py` (QAudioSink push-mode)
- [x] `playback/`: transport, clock, A/V sync, prefetch
- [x] `ui/preview_item.py` — **a texture dal 2026-08-27**: il frame va
      dritto sullo scene graph (QSGSimpleTextureNode via
      updatePaintNode, upload sul render thread), niente piu' passaggio
      QPainter+FBO per frame; API QML invariata, pixel-verificato dai
      test visivi (HDR, canvas fit, riquadro)
- [x] `playback/transport.py` — play/pausa/seek/step; **il clock e' l'audio**
      (campioni processati dal device), timer solo come fallback senza device
- [x] Apertura file da tool rail e Ctrl+O; timeline legata al media aperto
- [x] Sfondo in loop per lo stato vuoto (720p, 15 fps, si ferma da solo)
- [x] **Audio e sincronizzazione A/V** — tono 440/880 Hz verificato DOPO il
      sink (`tests/test_audio_output.py`); conteggio campioni per frame
      drift-free ai rate frazionari (confini cumulativi, non round() costante)
- [x] Proxy (con tone-map HDR incorporato) e cache di thumbnail e
      waveform in user_data/cache
- [x] Ambient backdrop alimentato dallo stesso frame decodificato:
      `AmbientBackdrop.qml` campiona il PreviewItem via
      ShaderEffectSource a 10 Hz — zero decodifiche extra
- [x] Transport HUD con auto-hide in riproduzione (2026-08-27: durante
      il play la pillola sfuma anche in modalita' centro; il puntatore
      nella zona la riporta)

**Fatto quando:** si apre un file, si riproduce con audio sincronizzato, si
fa seek preciso, e lo scrubbing e' fluido. Su tutte e tre le piattaforme.

> **Rischio principale del progetto.** A/V sync, seek frame-accurate e
> throughput del preview sono le tre cose che rendono difficile un editor
> video. Se qualcosa deve essere prototipato prima del resto, e' questo.

---

## Fase 3 — Timeline  ·  XL  ·  **COMPLETATA** (due code aperte sotto)

- [x] Media pool: import, metadata, thumbnail (pannello Progetto)
- [x] **Drag & drop di file e cartelle** dall'esterno (2026-08-23 il
      completamento): rilasciati sulla TIMELINE diventano clip nel punto
      del rilascio — pool e montaggio in un solo undo
      (`timeline.drop_media` / `import_and_place`); altrove entrano nel
      pool. Cartelle ricorsive e duplicati riusati. **Import asincrono
      con progresso** (stesso giorno): le probe girano su un worker
      (`_ImportWorker`), la UI non si congela mai, riga di progresso con
      annulla nel pannello Progetto, il lotto atterra intero in un solo
      undo (mai mezzi atterraggi; un lotto che atterra dopo la chiusura
      del suo progetto viene scartato). Resta: ordinamento per data di
      ripresa
- [x] QML timeline: ruler, tracce, clip, playhead, zoom, scroll
- [x] Drag & drop dal media pool alla timeline
- [x] Trim con maniglie (con snap tra corsie), split, delete con reflow
      (2026-08-23: il trim di testa sulle corsie libere ora muove il
      bordo SINISTRO — param `start` di trim_clip; un clip senza
      sorgente si allunga a sinistra liberamente). Ripple delete
      esplicito: da fare
- [x] Selezione singola e multipla, copia/incolla (2026-08-24):
      Ctrl+click aggiunge alla selezione (primaria + extra nello
      ShellState), Delete toglie tutto in un undo
      (`timeline.remove_clips`), Ctrl+C/Ctrl+V copiano e incollano dal
      playhead con spaziatura e proprieta' intatte, id nuovi, clipboard
      per progetto (mai link a media inesistenti)
- [x] Scorciatoie da tastiera mappate su action id (2026-08-24): ogni
      azione che dichiara `shortcut` e gira senza argomenti viene
      cablata da un Instantiator in Main.qml — registrare l'azione
      basta. Ctrl+B = split al playhead, Ctrl+C/V, Ctrl+S, F11,
      Home/End; Space resta a mano (fallback senza media)
- [x] Command palette (2026-08-24, `CommandPalette.qml`, Ctrl+K):
      filtra il catalogo del registry sulle azioni invocabili senza
      parametri; frecce + Invio eseguono. Il registry reso visibile:
      zero manutenzione UI quando le azioni cambiano

- [x] Corsie dedicate oltre al video (audit 2026-09-19): Musica, Colore,
      Sticker, Testo, **Effetti** (2026-08-28, con la regola «l'ultima mano
      vince» dove Colore ed Effetti si sovrappongono), `timeline.clear_lane`
- [ ] Code aperte: **ripple delete** esplicito; ordinamento del pool per
      data di ripresa; **marker di battuta e snap-to-beat** sulla corsia
      Musica (nessun codice ancora)

**Fatto quando:** si monta un video reale: import, taglio, riordino, salvataggio,
riapertura. Il primo momento in cui l'app e' "usabile".

---

## Fase 4 — Export e preset  ·  M  ·  **COMPLETATA**

Vedi `docs/EXPORT_PRESETS.md` e `docs/MEDIA_FORMATS.md`.

- [x] Canvas di progetto (auto/16:9/9:16/4:3/1:1/21:9, gia' dal 2026-08) +
      **strategie fit/fill/blur** (2026-08-23): scelta globale in
      Impostazioni → Layout, ricompone la sequenza aperta all'istante,
      anteprima ed export identici. **Varianti per clip fatte il
      2026-08-27**: un clip A/V selezionato mostra le stesse maniglie
      degli sticker e si pizzica sul canvas (centro/scala/rotazione,
      campo `placed` nel modello, filtro `Placement` per entry con
      contratto live sul dict, sfondo nero o blur del clip stesso,
      bottone ↺ per tornare al fit); azioni
      timeline.set_clip_transform (estesa) e reset_clip_transform
- [x] `export/presets.py` — preset dichiarativi JSON, codec **logici**
      (2026-08, factory + user + pack)
- [x] Encoder via PyAV, dentro `export/service.py` (muxer per contenitore,
      audio dal grafo)
- [x] Rilevamento encoder hardware con **test reale** (apre un contesto
      alle impostazioni dell'export: h264_qsv/nvenc/amf prima, software
      come fallback) — in `export/service.py`, non in un hwaccel.py separato
- [x] Pipeline render → encode: progresso, cancellazione, scrittura su
      `.part` e rename solo al successo
- [x] **Coda di export** (2026-08-23): ogni Esporta congela la timeline in
      un job, un worker li rende in ordine, card con stato/progresso per
      riga, cancel del singolo o di tutto
- [x] **Preflight** nel pannello (2026-08-23): avvisi su upscaling, aspect
      diverso dal canvas, durata oltre il limite del preset; blocco SOLO
      per encoder mancante; stima dimensione/durata + encoder reale.
      Alpha e HDR→SDR arriveranno con quei percorsi nel motore
- [x] Import/export di preset personalizzati come `.json` singolo
      (2026-08-23: salva dal tab Custom, condividi/elimina/importa)
- [x] Preset di sistema YouTube / Shorts / Reels / Stories / TikTok /
      LinkedIn / Facebook / WhatsApp (X, archivio e ProRes: quando serviranno)

**Fatto quando:** il file esportato corrisponde al preview frame per frame,
lo stesso montaggio si esporta in coda per tre piattaforme diverse, e un
preset creato su una macchina funziona su un'altra con GPU differente.

---

## Fase 4-bis — Il motore  ·  L  ·  **COMPLETATO tranne la timebase**

Vedi `docs/ENGINE.md`. Senza questo, ogni effetto aggiunto e' debito.

- [x] `Frame` con stack immagine e audio pigri (`tests/test_engine.py`)
- [x] `Producer` / `Filter` / `Transition` / `Consumer`
- [x] `ClipProducer` (PyAV), `ColourProducer`, `Playlist`, `Multitrack`, `Tractor`
- [x] `PreviewConsumer` ed `ExportConsumer` sullo **stesso** grafo
- [x] Decodifica audio e mixer sullo stack audio (`tests/test_audio_graph.py`)
- [x] Timebase della sequenza (2026-11-02): il progetto ha la SUA
      frequenza (`Project.frame_rate`, adottata dal primo video e poi
      ferma, o scelta dall'utente in Impostazioni > Layout, annullabile);
      ogni modifica finisce sulla griglia dei frame (`Project.conform` in
      `ProjectService._edit`, un solo punto); su disco i tempi sono
      **conteggi di frame** (schema 2). In memoria restano secondi, ma
      sempre multipli esatti di un frame. Corretti quattro errori reali:
      inizio e durata arrotondati separatamente (buco/sovrapposizione di
      un frame fra clip che si toccano), sequenza alla frequenza del
      primo clip (cancellarlo cambiava la griglia), export a
      `round(29.97)` = 30 fps (immagine 3,6 s/ora avanti al suono), e il
      playhead fermo fra due frame (mostrava un frame, il taglio cadeva
      sul successivo: ora si parcheggia all'inizio del frame mostrato).
      In piu' il timecode a 29.97/59.94 e' drop-frame. Vedi `ENGINE.md`
      §6 regola 7
- [x] Traccia nera in fondo, come Kdenlive

**Fatto quando:** un effetto di prova applicato a una clip si vede identico in
anteprima e nel file esportato, senza che nessuno dei due percorso conosca
l'altro.

---

## Fase 5 — Effetti e testo  ·  L  ·  **in gran parte fatta; manca lo strato «generato dallo schema»**

- [ ] `effects/base.py` con parametri dichiarativi + registry — **non
      fatto cosi'**: gli effetti sono *ricette JSON* su un vocabolario di op
      (`engine/filters.py`, `apply_colour_ops`), con i cataloghi in
      `color/`, `audio/`, `transitions/`, `motion/`. Funziona ed e'
      condivisibile, ma le op **non dichiarano uno schema dei parametri**:
      e' il prerequisito dell'Inspector generato e dei keyframe generici
      (ultime due voci di questa fase)
- [x] Transform e **speed** (2026-08-27): riquadro sul canvas per i
      clip A/V (vedi Fase 4) e velocita' 0.1-8x con semantica CapCut
      (`SpeedProducer` per entry: video mappato per tempo, audio
      ricampionato — il pitch segue il passo; pitch-preserve in seguito)
- [x] **Crop, opacita' e keyframe per clip** (2026-08-27): quattro
      maniglie di bordo ritagliano la sorgente (frazioni, live sul
      preview), slider di opacita' verso cio' che sta sotto, e
      fotogrammi chiave su x/y/scala/rotazione/opacita' — bottone rombo
      al playhead, rombi sulla pillola, interpolazione lineare in tempo
      CLIP-locale (`utils/keyframes.py`, condiviso da modello e motore
      via `clip_keyframe_values`); su un clip animato il drag delle
      maniglie pianta un rombo invece di muovere la trasformazione
      statica. **Easing fatto** (2026-08-28): ogni rombo porta la curva
      di ARRIVO (lineare/morbida/entrata/uscita/**molla** — oscillatore
      smorzato, ~12% di overshoot, si assesta nel segmento; chip
      accanto al bottone rombo, azione timeline.set_keyframe_easing).
      Restano: editor curve visuale, time remap a curve
- [x] **Correzione colore manuale** (2026-08-27): nove manopole
      (luminosita', contrasto, saturazione, gamma, temperatura, tinta,
      ombre, luci, vignettatura) su qualunque clip della corsia Colore
      — sopra una ricetta o su un clip «Regolazione» nudo
      (`ive/color/grade.py` compila nello stesso vocabolario di op
      delle ricette; azioni timeline.place_grade / set_clip_grade).
      Restano: curve, HSL per gamma, LUT `.cube`
- [x] **Animazioni in/out/loop** come keyframe dichiarativi (2026-08-20,
      `docs/MOTION.md`): 12 ricette di fabbrica (4 in, 3 out, 5 loop) in
      `config/defaults/motion/`, evaluatore in `motion/runtime.py`, preview
      viva sulle card (`MotionPicker.qml`), su sticker e titoli, categoria
      di pack; azione `timeline.set_clip_motion`
- [x] **Transizioni** (2026-08-25, `docs/TRANSITIONS.md`): 16 di fabbrica in
      3 famiglie (dissolvenze, wipe a **mappa luma** PNG, movimento), A/B
      roll con semantica CapCut, intro/outro da/verso il nero, crossfade
      audio a potenza costante, pillola in timeline, 1,2-6 ms/frame a 720p;
      azione `timeline.set_transition`. Resta: altre mappe luma di fabbrica
      (stella, cuore, pennellata)
- [x] **Titoli e testo** (2026-08-18, `docs/TEXT_TITLES.md`): corsia Testo,
      renderer QPainterPath (`text/raster.py`), colore/contorno/grassetto/
      corsivo/font, maniglie sul video condivise con gli sticker, motion
      preset, karaoke per parola. **Restano:** *font bundled* (`assets/fonts/`
      non esiste: si usano i font di sistema, quindi un progetto puo'
      cambiare aspetto da una macchina all'altra) e *stili di testo come
      preset JSON* condivisibili
- [x] **Sticker** (2026-08-11 → 09-14, `docs/STICKERS.md`; non era nel
      piano originale): manifest + SVG, 15 statici e 6 animati Lottie via
      rlottie (ultimo: indicatore di tap `shape_tap`), corsia dedicata,
      maniglie nel preview, motion preset
- [x] **Look artistici ed effetti sul soggetto** (2026-08-28): matita,
      cartoon, pittura; aura, sfondo sfocato / grigio / parallasse 2.5D
      (`bg_zoom`) guidati dalla maschera AI; pannello **Effetti** con corsia
      propria (un catalogo, due porte: `COLOR_EFFECTS.md` §3-bis,
      `AI_FEATURES.md` §6-bis). 42 ricette colore/fx di fabbrica in 10 file
- [x] Effetti audio: gain, EQ, compressore, normalizzazione loudness (2026-08-20, `docs/AUDIO.md`)
- [ ] Keyframe su qualunque parametro numerico + editor curve — oggi i
      keyframe coprono x/y/scala/rotazione/opacita' dei clip A/V; i
      parametri di effetti, grade e audio non sono animabili
- [ ] Pannello Inspector generato **dallo schema** dei parametri, non a mano
      — oggi ogni pannello (`ColorContent`, `AudioContent`, `TextContent`...)
      e' QML scritto a mano: il criterio «aggiungere un effetto non richiede
      toccare la UI» vale per le *ricette*, non per una *op* nuova

**Fatto quando:** un utente monta un video completo con color grading, testo e
transizioni. Aggiungere un effetto nuovo non richiede toccare la UI.

---

## Fase 6A — Content Pack  ·  L  ·  **v1 FATTA (2026-08-19/20), resta il secondo giro**

Il sistema che permette alla comunita' di contribuire senza programmare.
Vedi `docs/CONTENT_PACKS.md` §0 per lo stato di dettaglio.

- [x] `packs/pack.py`: manifest, `build_pack` / `preview_pack` /
      `install_pack` / `remove_pack`, pack installati come unita' rimovibili,
      mai sovrascritture. (Nessun indice cachato: non e' servito.)
- [x] Installazione da file o **per drag & drop sulla finestra**, sempre con
      card di conferma (contenuti + avviso duplicati). **Resta:** la card
      non mostra ancora la *licenza* del pack prima della conferma
- [~] Tipi di contenuto — **fatti:** effetti colore/fx, transizioni (mappe
      luma incluse), sticker, motion preset, effetti audio, export preset,
      musica (con licenza e URL per traccia). **Mancano:** LUT `.cube`,
      font, overlay, template di progetto, canvas preset, loop e beat
      marker sulle tracce audio
- [~] Librerie in UI: pannelli per famiglia con preview viva e preferiti
      (stelle) per colore, effetti, sticker, transizioni, motion, audio,
      musica. **Mancano:** ricerca testuale, filtri, provenienza visibile
      (da quale pack arriva un contenuto)
- [~] Risorse mancanti: i *media* mancanti sono marcati e il progetto si
      apre comunque (`_check_missing`). **Manca** lo stesso per i
      *contenuti di pack* non installati (effetto/sticker/transizione ignoti)
- [ ] "Raccogli risorse": progetto autonomo e trasferibile
- [ ] Validatore di pack (in-app e CLI)
- [x] **"Esporta come content pack"** dall'app: pannello Pack → Crea, con
      spunte sui contenuti e i preferiti come scorciatoia (`pack.create`)
- [x] Pack ufficiali scaricabili (al posto di `com.ive.starter`): catalogo
      `config/defaults/packs/catalog.json` con 7 pack musicali (Kevin
      MacLeod, CC BY 4.0) costruiti da `build_scripts/make_music_pack.py`
      nello stesso formato pubblico; `pack.download`, overlay di offerta
- [ ] Badge e generazione `credits.txt` per i contenuti con attribuzione
      (i dati ci sono: licenza e URL per traccia; manca l'uscita)

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

- [x] Infrastruttura (2026-08-25, la parte che serviva): model registry
      con URL ancorati a revisione + SHA-256, downloader con verifica
      hash/ripresa/cancel (`ive/ai/`), pesi in `models/<task>/`; inferenza
      in PROCESSO separato (crash isolation + conflitto OpenMP del venv,
      vedi `AI_FEATURES.md` §4). Restano: `AITask.estimate` e la selezione
      del backend GPU dalla UI (la schermata "Modelli AI" e' fatta, vedi
      sotto; la segmentazione sceglie gia' DirectML/CPU da sola). (Primo modello
      ONNX gia' in campo il 2026-08-23: Silero VAD in `models/vad/` per
      il ducking «Intelligente».)
- [x] **Sottotitoli automatici** (2026-08-25): faster-whisper con
      timestamp per parola, trascrizione per sorgente (trim rispettati,
      corsia Musica esclusa), segmentazione in righe leggibili, titoli
      modificabili sulla corsia Testo in UN undo; card nel pannello
      Testo con download esplicito del modello (tiny/small, MIT),
      progresso e annulla; azioni `timeline.auto_subtitles` e
      `subtitles.*`. Secondo passaggio (2026-08-26): export/import
      SRT e VTT, karaoke per parola (timestamp nel modello, switch per
      clip, pixel-verificato), lingua dalla UI, schermata "Modelli AI"
      nelle impostazioni (download/rimozione per modello). Resta: ASS
- [x] **Traduzione** dei sottotitoli (2026-08-26): coppie OPUS-MT di
      Argos caricate direttamente con ctranslate2+sentencepiece (niente
      argostranslate/stanza), it/pt/es↔en a catalogo con pivot per
      l'inglese, sorgente = lingua fissata o rilevata, timing intatti,
      un undo, righe troppo veloci segnalate; worker in processo
      separato; UI nella card sottotitoli e coppie nella schermata
      Modelli AI. Vedi `AI_FEATURES.md` §5
- [x] **Segmentazione del soggetto** (2026-08-28, Fasi A-D,
      `AI_FEATURES.md` §6-bis): U²-Net small (`u2netp`, 4,6 MB, Apache-2.0)
      su ONNX Runtime, provider scelto a runtime (DirectML 34 ms/frame vs
      446 su CPU sulla macchina di sviluppo), una maschera condivisa da
      tutte le op mascherate del motore, sessione scaldata all'avvio
- [x] **Rimozione sfondo** (2026-11-02) — Fase A: sfondo di una clip
      sostituito da un colore o un'immagine (`engine/cutout.py`, scheda
      nel pannello Effetti, `timeline.set_clip_cutout`), bordo
      regolabile, sfarfallio attenuato fra frame consecutivi. Fase B:
      modalita' **Trasparente** ed **export con alpha** (ProRes 4444 MOV,
      VP9 WebM/MKV), alpha come terza pila pigra del frame. Restano
      migliorie: sfondo video, pennello di correzione, scacchiera
      nell'anteprima. `AI_FEATURES.md` §6
- [x] **Ducking «intelligente»** (2026-08-23): Silero VAD in `audio/vad.py`,
      modalita' globale semplice/intelligente, ombra sul letto musicale dove
      il ducking lo abbassa (`ui/duck_shades.py`)
- [ ] **Motion tracking** — prima i tracker OpenCV, poi il livello AI.
      Fasi A+B fatte (2026-11-01): motore ViT/MIL, mappatura, keyframe sulle
      overlay, Action, scheda + riquadro sulla preview, drag del percorso.
      Tracking all'indietro fatto (direzione avanti/indietro/entrambe) e
      re-tracking di un tratto dalla UI con relazione salvata. Resta il
      point tracking AI.
      `AI_FEATURES.md` §7
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

- [ ] `backends/detect.py` con capability detection reale — oggi la scelta
      e' locale a chi ne ha bisogno (segmentazione: provider ONNX; export:
      test reale dell'encoder), non c'e' un modulo unico
- [ ] Backend CUDA
- [ ] Backend OpenVINO
- [ ] Backend ROCm
- [ ] Decodifica hardware (hwaccel) — nessun codice in `media/`
- [x] Encoding hardware in export — fatto in Fase 4 (`export/service.py`:
      h264_qsv / nvenc / amf con test reale, software come fallback)
- [ ] Test di regressione visiva: ogni backend vs CPU

**Fatto quando:** su ogni macchina l'app sceglie il percorso migliore da sola,
e un backend rotto degrada a CPU senza che l'utente perda lavoro.

---

## Fase 10 — Rifinitura e distribuzione  ·  L

- [x] Traduzioni IT / PT / ES — audit 2026-09-19: 449 chiavi in `en.json`,
      **zero mancanti** nelle altre tre lingue (una ventina di valori
      identici all'inglese per lingua: nomi propri e sigle, da rileggere).
      Resta la verifica che nessuna stringa QML sia sfuggita a `tr()`
- [ ] `.spec` PyInstaller per Windows, Linux, macOS — `build_scripts/`
      contiene solo `make_music_pack.py`; nessun packaging ancora
- [ ] `THIRD_PARTY_LICENSES.md` generato automaticamente
- [ ] Schermata About / Licenze
- [ ] Onboarding, stati vuoti, scorciatoie documentate
- [ ] Passata di accessibilita' (contrasto, tastiera, screen reader)
- [ ] Profiling e ottimizzazione — con numeri, non a sensazione
- [ ] Documentazione utente

---

## Cosa manca alla 1.0 — riepilogo dell'audit 2026-09-19

In ordine di rischio, non di comodita':

1. ~~**Timebase in frame + `utils/timecode.py`**~~ — fatto il
   2026-11-02 (Fase 4-bis / 1).
2. **Verifica su Linux e macOS.** Tutto e' verificato solo su Windows; la
   regola 5 qui sotto non e' soddisfatta per nessuna fase. Serve insieme a
   **CI + lint + un runner unico** per le 53 suite a script (Fase 0).
3. **Schema dei parametri delle op** → Inspector generato e keyframe su
   qualunque parametro (Fase 5). Senza, ogni op nuova costa QML a mano.
4. **Tracce video multiple / picture-in-picture**: il modello a corsie
   fisse non le prevede.
5. **Secondo giro dei pack** (Fase 6A): LUT `.cube`, font, template,
   validatore, "Raccogli risorse", contenuti di pack mancanti, licenza
   nella card di installazione, `credits.txt`, ricerca nelle librerie.
6. **Font bundled** e stili di testo come preset (Fase 5).
7. **Colore avanzato**: curve, HSL per gamma, LUT; editor curve dei
   keyframe; time remap; speed con pitch preservato.
8. **AI**: point tracking AI, frame interpolation, `AITask.estimate`,
   sottotitoli ASS (la rimozione sfondo, export con alpha compreso, e'
   fatta dal 2026-11-02).
9. **Fase 6B (plugin)**, **Fase 8 (assistente)**, **Fase 9 (backend GPU,
   hwaccel in decodifica)**: intere, nessun codice. Per la Fase 8 la base
   c'e': oltre 100 azioni con schema e la command palette che gia' le elenca.
10. **Distribuzione** (Fase 10): `.spec` PyInstaller, licenze di terze
    parti generate, schermata About, onboarding, accessibilita', profiling
    con numeri, documentazione utente.
11. Code piccole: ripple delete, ordinamento per data di ripresa, marker
    di battuta e snap-to-beat, recupero autosave dopo crash, migrations
    del formato progetto, refresh dell'albero moduli in `ARCHITECTURE.md`
    (cita ancora `video_engine/`/`audio_engine/`; il codice ha `engine/`,
    e mancano `color/`, `stickers/`, `text/`, `motion/`, `music/`,
    `transitions/`, `audio/`).

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
