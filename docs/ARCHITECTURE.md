# IVE — Architettura

Fonte di verita' per la struttura del codice. Se una feature non ha un posto
in questo documento, il posto va deciso e scritto **qui prima** di scrivere
il codice.

---

## 1. Regola dei livelli

Quattro livelli, dipendenze **solo verso il basso**:

```
┌───────────────────────────────────────────────────────────┐
│  PRESENTATION   qml/ , src/ive/ui/                        │  ← puo' importare tutto
├───────────────────────────────────────────────────────────┤
│  APPLICATION    actions/ , commands/ , services/          │  ← non importa la UI
├───────────────────────────────────────────────────────────┤
│  DOMAIN         core/model/                               │  ← non importa nulla di IVE
├───────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE media/, video_engine/, audio_engine/,     │  ← non importa il domain
│                 ai/, export/, plugins/, utils/               (parla per interfacce)
└───────────────────────────────────────────────────────────┘
```

Violazioni tipiche da evitare:
- un modulo di `core/model/` che importa `PySide6.QtWidgets` → **no**, il
  domain e' Python puro (`QObject` ammesso solo nei wrapper in `ui/`);
- `video_engine/` che importa `core/model/Clip` → **no**, riceve strutture
  di rendering neutre (`RenderNode`), non il modello di progetto;
- `ui/` che modifica direttamente un `Clip` → **no**, passa da un `Command`.

---

## 2. Albero dei moduli

```
ive/src/ive/
├── __main__.py                 entry point: bootstrap, logging, QApplication
├── app.py                      composition root: costruisce e collega tutto
│
├── core/                       DOMAIN + APPLICATION
│   ├── model/                  modello di progetto, Python puro, serializzabile
│   │   ├── project.py            Project, ProjectSettings
│   │   ├── sequence.py           Sequence (timebase, risoluzione, sample rate)
│   │   ├── track.py              Track (video/audio/text/adjustment)
│   │   ├── clip.py               Clip, ClipSource, in/out point, speed map
│   │   ├── effect.py             EffectInstance, ParameterSet
│   │   ├── transition.py         Transition
│   │   ├── keyframe.py           Keyframe, AnimatedParameter, interpolazione
│   │   ├── marker.py             Marker, Chapter
│   │   └── ids.py                generazione ID stabili
│   ├── commands/               ogni mutazione del modello, reversibile
│   │   ├── base.py               Command (do/undo), CompositeCommand
│   │   ├── history.py            UndoStack, coalescing, transazioni
│   │   ├── clip_commands.py      insert, remove, move, trim, split
│   │   ├── track_commands.py     add, remove, reorder, lock, mute
│   │   ├── effect_commands.py    add/remove effect, set parameter
│   │   └── keyframe_commands.py
│   ├── actions/                ACTION REGISTRY — vedi §4
│   │   ├── registry.py           ActionRegistry, decoratore @action
│   │   ├── schema.py             descrizione parametri + validazione
│   │   ├── context.py            ActionContext (selezione, playhead, progetto)
│   │   └── builtin/              action raggruppate per area
│   ├── services/               servizi applicativi con stato
│   │   ├── container.py          service locator, wiring esplicito
│   │   ├── project_service.py    apri/salva/nuovo, dirty state, autosave
│   │   ├── selection_service.py  selezione corrente
│   │   ├── playback_service.py   transport
│   │   └── job_service.py        coda di task lunghi (export, AI)
│   ├── events/
│   │   └── bus.py                event bus tipizzato, pub/sub
│   └── project_io/
│       ├── serializer.py         .iveproj (JSON), schema versionato
│       ├── migrations.py         upgrade fra versioni di schema
│       └── autosave.py
│
├── media/                      INFRASTRUCTURE — ingresso dei media
│   ├── probe.py                  metadata (durata, fps, codec, rotation)
│   ├── decoder.py                decode frame-accurate, seek, cache
│   ├── thumbnails.py             strip di thumbnail per la timeline
│   ├── waveform.py               peak file audio
│   ├── cache.py                  cache su disco in user_data/cache/
│   └── formats.py                estensioni e capability supportate
│
├── video_engine/               INFRASTRUCTURE — composizione e rendering
│   ├── graph.py                  RenderGraph, RenderNode (struttura neutra)
│   ├── compositor.py             blending, trasformazioni, mask
│   ├── frame.py                  VideoFrame (buffer + colorspace + timing)
│   ├── color.py                  gestione colorspace / transfer function
│   └── backends/
│       ├── base.py               interfaccia RenderBackend
│       ├── cpu.py                riferimento, sempre disponibile
│       ├── cuda.py               NVIDIA
│       ├── openvino.py           Intel
│       ├── rocm.py               AMD
│       └── detect.py             capability detection + selezione a runtime
│
├── audio_engine/
│   ├── graph.py                  grafo audio
│   ├── mixer.py                  somma tracce, pan, gain
│   ├── resample.py
│   ├── effects/                  eq, compressor, limiter, noise reduction
│   └── output.py                 device di riproduzione
│
├── playback/                   preview: unisce video_engine + audio_engine
│   ├── transport.py              play/pause/seek/loop, velocita'
│   ├── clock.py                  master clock, A/V sync
│   ├── prefetch.py               lettura anticipata, ring buffer
│   └── proxy.py                  proxy a bassa risoluzione per scrubbing
│
├── effects/                    effetti built-in dichiarati con schema
│   ├── base.py                   Effect, ParameterSpec
│   ├── registry.py
│   ├── video/                    blur, sharpen, crop, transform, LUT, chroma key
│   ├── color/                    lift/gamma/gain, curve, HSL
│   ├── text/                     titoli, sottotitoli renderizzati
│   └── transitions/              dissolve, wipe, slide, zoom
│
├── ai/                         strumenti AI — dettaglio in docs/AI_FEATURES.md
│   ├── base.py                   AITask, progresso, cancellazione
│   ├── runtime/                  onnxruntime / openvino, selezione device
│   ├── model_registry.py         quali pesi, dove, checksum, licenza
│   ├── subtitles/                speech-to-text + allineamento
│   ├── translate/                traduzione testi e sottotitoli
│   ├── matting/                  rimozione sfondo
│   ├── tracking/                 motion tracking
│   └── interpolation/            frame interpolation
│
├── export/
│   ├── presets.py                preset dichiarativi (JSON)
│   ├── encoder.py                muxing/encoding via PyAV
│   ├── hwaccel.py                encoder hardware disponibili
│   └── pipeline.py               render → encode, progresso, cancellazione
│
├── packs/                      CONTENT PACK — dati dichiarativi, nessun codice
│   ├── manifest.py               parsing e validazione di pack.json
│   ├── installer.py              install/uninstall .ivepack, verifica
│   ├── library.py                indice unificato dei contenuti disponibili
│   ├── validator.py              validazione pack (in-app e CLI)
│   ├── builder.py                "Esporta come content pack"
│   └── types/                    audio, animations, transitions, luts,
│                                 fonts, overlays, templates, presets
│
├── plugins/                    PLUGIN DI CODICE — richiedono fiducia
│   ├── host.py                   discovery, load, isolamento errori
│   ├── manifest.py               manifest.json: id, versione, permessi, licenza
│   ├── api.py                    superficie pubblica stabile per i plugin
│   └── errors.py
│
├── automation/                 LIVELLO AI-FIRST
│   ├── assistant.py              orchestratore linguaggio naturale
│   ├── tool_adapter.py           ActionRegistry → tool schema per un LLM
│   ├── planner.py                sequenze di action, dry-run, conferma
│   └── transcript.py             log delle azioni eseguite dall'assistente
│
├── i18n/
│   ├── translation_manager.py    tr(), fallback, cambio lingua a runtime
│   └── locales/                  en.json (sorgente), it.json, pt.json, es.json
│
├── settings/
│   ├── service.py                lettura/scrittura, default, validazione
│   └── schema.py                 chiavi tipizzate
│
├── utils/
│   ├── paths.py                  get_asset_path/get_qml_path/get_model_path/get_data_path
│   ├── logging_setup.py          rotating log + faulthandler + excepthook
│   ├── platform.py               rilevamento OS, GPU, encoder
│   └── timecode.py               conversioni frame ↔ timecode ↔ secondi
│
└── ui/                         PRESENTATION — lato Python
    ├── bridge.py                 registrazione dei tipi QML
    ├── models/                   QAbstractListModel per timeline, media pool, ...
    ├── controllers/              QObject esposti a QML, chiamano le Action
    ├── theme_bridge.py           espone i token a QML e gestisce il cambio tema
    └── preview_item.py           QQuickItem custom per il rendering del preview
```

```
ive/qml/
├── Main.qml
├── theme/
│   ├── Theme.qml                 SINGLETON — tutti i design token
│   └── qmldir
├── components/                   Button, Slider, ComboBox, Card, ToggleSwitch...
├── panels/                       MediaPool, Inspector, EffectsBrowser, Assistant
├── timeline/                     Timeline, Track, Clip, Ruler, Playhead
├── preview/                      PreviewArea, TransportBar
└── dialogs/                      Export, Settings, About
```

---

## 3. Modello dati

```
Project
 ├── settings (nome, cartella, versione schema)
 ├── media_pool: [MediaItem]         riferimenti ai file sorgente + metadata
 └── sequences: [Sequence]
      ├── timebase (fps, drop-frame), risoluzione, sample rate
      ├── tracks: [Track]            ordinate, tipo video/audio/text/adjustment
      │    └── clips: [Clip]
      │         ├── source_ref → MediaItem
      │         ├── source_in/out, timeline_start
      │         ├── speed_map (per time remap)
      │         ├── effects: [EffectInstance]
      │         │    └── parameters: {name: AnimatedParameter}
      │         └── transitions in/out
      └── markers: [Marker]
```

Regole:
- Tutti i tempi in **frame o rational**, mai float di secondi, per evitare
  drift. `utils/timecode.py` e' l'unico posto dove si converte.
- Ogni entita' ha un `id` stabile (UUID) — la serializzazione usa gli id,
  mai gli indici di lista.
- Il modello e' serializzabile senza dipendenze Qt.
- `.iveproj` = JSON con `schema_version`. Ogni modifica di schema aggiunge
  una migration in `project_io/migrations.py`. Mai rompere i progetti vecchi.

---

## 4. Action Registry — il cuore dell'architettura AI-first

**Nessuna funzionalita' e' raggiungibile solo dalla UI.** Ogni operazione
utente e' registrata come Action con nome, descrizione e schema dei
parametri. Da questo derivano gratis: menu, scorciatoie, command palette,
scripting, plugin e assistente in linguaggio naturale.

```python
# core/actions/builtin/timeline_actions.py

@action(
    id="timeline.split_clip",
    title_key="action.timeline.split_clip",
    description="Split the selected clip at the playhead position.",
    params={
        "clip_id":  Param(str, required=False, doc="Defaults to selection."),
        "position": Param(int, required=False, doc="Frame; defaults to playhead."),
    },
    undoable=True,
    category="timeline",
)
def split_clip(ctx: ActionContext, clip_id=None, position=None):
    clip_id = clip_id or ctx.selection.single_clip()
    position = position if position is not None else ctx.playhead
    return SplitClipCommand(clip_id, position)
```

Un'Action:
- riceve un `ActionContext` (progetto, selezione, playhead, sequenza attiva);
- **ritorna un `Command`** se e' `undoable`, altrimenti esegue direttamente;
- non tocca la UI e non sa chi l'ha invocata;
- ha parametri opzionali che si risolvono dal contesto — cosi' funziona sia
  con "spezza qui" (UI, tutto implicito) sia con una chiamata programmatica
  completamente esplicita.

Consumatori del registry:

| Consumatore | Come lo usa |
|---|---|
| UI QML | `ActionController.invoke("timeline.split_clip")` |
| Scorciatoie | mappa tasto → action id, in `user_data/settings/keymap.json` |
| Command palette | ricerca su titolo e descrizione tradotti |
| Assistente NL | `automation/tool_adapter.py` converte lo schema in tool per LLM |
| Plugin | possono invocare action esistenti e registrarne di nuove |
| Test | invocano le action direttamente, senza istanziare la UI |

**Regola operativa:** una feature nuova senza Action registrata e' incompleta.

### Assistente in linguaggio naturale

`automation/assistant.py` non ha logica di editing propria: traduce la
richiesta dell'utente in una sequenza di action id + parametri.

- Il piano e' **mostrato prima dell'esecuzione** quando contiene operazioni
  distruttive o non-undoable.
- L'esecuzione avviene in una singola transazione dell'`UndoStack`: un solo
  Ctrl+Z annulla l'intera richiesta.
- Ogni action eseguita finisce in `automation/transcript.py`.
- Il provider LLM e' dietro un'interfaccia: locale o remoto, configurabile,
  e l'app deve restare **pienamente funzionale senza** assistente.

---

## 5. Pipeline di rendering

> **La decisione sul motore e le sue regole stanno in `docs/ENGINE.md`.**
> Qui resta il quadro d'insieme. Nota che il codice attuale **viola**
> ancora la regola "anteprima ed export usano lo stesso grafo": e' un
> debito dichiarato, da chiudere prima degli effetti.


```
Sequence + playhead
   ↓  compilazione (pura, testabile, senza I/O)
RenderGraph — DAG di RenderNode: source → effect → transform → composite
   ↓  backend selezionato a runtime
RenderBackend.execute(graph, frame_number) → VideoFrame
   ↓
   ├── preview  → PreviewItem (QQuickItem, upload texture)
   └── export   → encoder PyAV
```

Punti fermi:
- **Preview ed export usano lo stesso grafo.** Differiscono solo per
  risoluzione, uso dei proxy e qualita' di scaling. Nessuna duplicazione di
  logica: quello che vedi e' quello che esporti.
- Il backend CPU e' la **reference implementation**. Ogni backend accelerato
  deve produrre output visivamente equivalente; i test di regressione
  confrontano contro il CPU.
- `backends/detect.py` sceglie a runtime e fa **fallback silenzioso a CPU**
  se il backend fallisce, loggando WARNING. Un'installazione senza GPU deve
  funzionare senza configurazione.
- Un solo resize lungo la pipeline. Niente scale intermedi ridondanti.
- Nessun assunto di aspect ratio: mai deformare, si usa fit + padding.

---

## 6. Threading

| Thread | Responsabilita' |
|---|---|
| GUI (Qt) | modello di progetto, UI, undo stack |
| Playback | decode + composizione preview, ring buffer |
| Audio | callback del device, **mai** bloccare (no allocazioni, no lock lunghi) |
| Job pool | export, task AI, generazione proxy/thumbnail/waveform |

- Il modello di progetto e' letto/scritto **solo dal thread GUI**.
- I job lunghi passano da `JobService`: progresso, cancellazione e reporting
  errori uniformi. Nessun task lungo scritto a mano fuori da li'.
- I risultati tornano via signal Qt, mai mutando strutture condivise.

---

## 7. Plugin

Un plugin e' una cartella in `user_data/plugins/<id>/` con `manifest.json`:

```json
{
  "id": "com.example.glitch",
  "name": "Glitch Effects",
  "version": "1.0.0",
  "api_version": 1,
  "license": "MIT",
  "entry": "plugin.py",
  "provides": ["effects", "actions"],
  "permissions": ["filesystem:read"]
}
```

- Estendibili: effetti, transizioni, esportatori, task AI, action, pannelli UI.
- `api_version` e' versionata e stabile: rompere l'API richiede bump.
- Un plugin che solleva un'eccezione al load viene **disabilitato e loggato**,
  non fa cadere l'app.
- Il manifest **deve** dichiarare la licenza (vedi `docs/LICENSING.md`).

---

## 8. Gestione errori

- Errori attesi (file non leggibile, codec mancante, modello assente) →
  eccezioni tipizzate del modulo, tradotte in messaggio utente dalla UI.
- Errori inattesi → loggati con `exc_info=True`, l'app resta viva.
- Un errore in un backend accelerato → fallback a CPU + WARNING.
- Un errore in un plugin → plugin disabilitato + notifica, mai crash.
- **Nessun `except Exception: pass`.** Se serve ignorare, si logga il motivo.

---

## 9. Estendere il progetto senza rompere nulla

Checklist per una feature nuova:

1. [ ] Il modello ha bisogno di campi nuovi? → aggiungi + `schema_version` + migration
2. [ ] La mutazione ha un `Command` reversibile?
3. [ ] C'e' un'`Action` registrata con schema e chiave di traduzione?
4. [ ] La logica sta nel modulo giusto secondo §2?
5. [ ] Niente import verso l'alto (§1)?
6. [ ] Testi UI via `tr()`?
7. [ ] Funziona senza GPU e senza modelli AI installati?
8. [ ] Ci sono test che invocano l'Action senza UI?
9. [ ] Log ai confini critici?
10. [ ] Nuove dipendenze verificate in `docs/LICENSING.md`?
