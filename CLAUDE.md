# IVE — Guida per Claude Code

Documento di orientamento per qualunque sessione di lavoro su questo progetto.
**Leggilo per intero prima di scrivere codice.** I documenti in `docs/` sono la
fonte di verita' per i dettagli; questo file e' l'indice e contiene le regole
non negoziabili.

---

## 1. Cos'e' il progetto

**IVE — Individual Video Editor**: editor video open source, desktop,
multipiattaforma (Windows / Linux / macOS). Workflow ispirato a CapCut
(timeline-centric, operazioni rapide, strumenti AI integrati) ma
**implementazione originale**: nessun codice, asset, icona, font o stringa
copiati da prodotti proprietari.

Obiettivo dichiarato: dare alla comunita' uno strumento equivalente ai
prodotti commerciali ma **libero**, in cui chiunque possa aggiungere le
proprie musiche, animazioni e formati di export e scambiarli con gli altri
senza barriere.

Tre principi guidano tutto il resto:

1. **AI-first** — ogni funzione dell'applicazione e' esposta come *Action*
   invocabile in modo identico dalla UI, da un assistente in linguaggio
   naturale, da un plugin o da uno script. Non esiste funzionalita'
   raggiungibile solo cliccando. Vedi `docs/ARCHITECTURE.md` §4.
2. **Modularita' rigida** — aggiungere una feature significa aggiungere file
   in un modulo, mai gonfiare o riscrivere codice condiviso.
3. **Estendibile senza programmare** — musiche, animazioni, transizioni, LUT,
   font, template ed export preset sono **dati dichiarativi** (JSON + media),
   impacchettati in `.ivepack` e scambiabili come un file qualunque. Nessun
   codice eseguito, quindi installarli e' sicuro. Vedi `docs/CONTENT_PACKS.md`.

Stato attuale: **Fase 0 completata, Fase 2 in corso**. Lo shell immersivo si
avvia a schermo intero, con temi e lingua commutabili a runtime; ogni comando
passa dall'Action Registry. Si apre un file video e lo si riproduce, con seek
frame-accurate verificato. Mancano audio, A/V sync, proxy e il modello di
progetto (Fase 1). Vedi `docs/ROADMAP.md`.

---

## 2. Stack tecnologico (deciso, non rinegoziare senza chiedere)

| Area | Scelta | Nota |
|---|---|---|
| Linguaggio | Python 3.10 | venv condiviso, vedi §3 (verificato: 3.10.11) |
| UI | **PySide6 (Qt 6.11) + QML / Qt Quick** | scene graph GPU; backend D3D11 su Windows |
| Logica UI | Python `QObject` esposti a QML | niente business logic in JavaScript QML |
| Media I/O | FFmpeg via `PyAV` | vedi `docs/LICENSING.md` prima di scegliere la build |
| Motore di composizione | **modello MLT, implementazione nostra** | `docs/ENGINE.md`. I binding Python di MLT non esistono per Windows; il modello si adotta lo stesso, e un backend MLT resta sostituibile |
| Inferenza AI | ONNX Runtime (CPU/CUDA/DirectML) + OpenVINO | backend selezionati a runtime |
| Packaging | PyInstaller `--onedir` | layout "tre sorelle", §3 |
| Test | pytest + `pytest-qt` | |

**Attenzione:** la scelta QML implica che la style guide QSS degli altri
progetti (PICK, PALLET_*) **non si applica**. I design token vivono in un
singleton `Theme.qml`. Vedi `docs/UI_STYLE_GUIDE.md`.

---

## 3. Layout del progetto ("tre sorelle")

Standard gia' in uso negli altri progetti: tre cartelle sorelle con cicli di
vita diversi, cosi' un update e' uno scambio di cartelle.

```
IVE_V001/
├── ive/                    PROGRAMMA — sostituita ad ogni release
│   ├── src/ive/            package Python
│   ├── qml/                view QML + Theme singleton
│   ├── assets/             icone, font, splash
│   ├── config/defaults/    config "di fabbrica" (template bootstrap)
│   └── third_party/        binari/runtime esterni bundled
├── models/                 RISORSE PESANTI — pesi AI, sostituita raramente
├── user_data/              DATI UTENTE — mai toccata dagli update
├── build_scripts/          .spec PyInstaller, runtime hook
├── docs/                   documentazione tecnica
└── tests/
```

**L'app non scrive MAI dentro `ive/`.** Tutto cio' che e' scrivibile
(settings, log, cache, progetti, autosave) sta in `user_data/`.

Path sempre via gli helper in `ive/src/ive/utils/paths.py`:
`get_asset_path()`, `get_qml_path()`, `get_model_path()`, `get_data_path()`.
**Mai** ricalcolare `Path(__file__).parents[N]` altrove.

Struttura interna dei moduli: `docs/ARCHITECTURE.md`.

---

## 4. Regole non negoziabili

### 4.1 Lingua
- Identificatori, commenti, docstring, messaggi di log: **INGLESE**.
- Testi visibili all'utente: **mai hardcoded** → sempre via `tr("key")`.
- Documentazione in `docs/`: italiano (e' per te e per me).

### 4.2 Cross-platform
Il codice deve girare su Windows, Linux e macOS.
- `pathlib.Path` sempre, mai separatori o drive hardcoded.
- API OS-specifiche dietro `if sys.platform == ...` con fallback.
- Backend hardware scelti a runtime, mai assunti.
- `encoding="utf-8"` esplicito su ogni file di testo; attenzione al
  filesystem case-sensitive di Linux/macOS.

### 4.3 Modularita'
- Una feature nuova = file nuovi nel modulo di competenza, non righe in piu'
  in un file esistente gia' grande.
- Comunicazione fra moduli via **event bus / signal**, non chiamate dirette
  incrociate.
- Ogni modulo espone un'interfaccia pubblica esplicita in `__init__.py`;
  il resto e' dettaglio implementativo.
- **Nessun modulo importa `ui/` o `qml/`.** La UI dipende dal core, mai
  il contrario.

### 4.4 AI-first / Action Registry
Ogni operazione utente e' un'`Action` registrata con schema dei parametri.
Aggiungere una feature senza registrarne l'Action e' un bug, non una svista.
Vedi `docs/ARCHITECTURE.md` §4.

### 4.5 Motore di rendering
Il grafo e' **derivato dal modello di progetto, mai modificato per conto
proprio**: e' l'errore che ha destabilizzato Kdenlive gen-1 (parametri degli
effetti desincronizzati fra UI e render). Anteprima ed export tirano lo stesso
grafo. Solo il producer conosce la posizione. Audio e video viaggiano sullo
stesso grafo, in stack pigri separati. Vedi `docs/ENGINE.md`.

### 4.6 Undo/redo
Ogni mutazione del modello di progetto passa da un `Command` reversibile.
Nessuna scrittura diretta sul modello dalla UI.

### 4.7 Logging
- `setup_logging()` chiamato in `__main__.py` **prima** degli import pesanti.
- `faulthandler` attivo per i crash nativi (FFmpeg, driver GPU, ONNX).
- `sys.excepthook` + `threading.excepthook` installati.
- **Non** abilitare `faulthandler.dump_traceback_later` (heap corruption
  osservata con librerie video native su Windows).
- Log in `user_data/log/`, rotating. Mai `print()` per diagnostica.
- Ai confini critici (apertura media, start/stop playback, export, load
  modello AI): log INFO in ingresso e uscita, `try/except` che logga
  `exc_info=True`. Mai swallow silenzioso.

### 4.8 Thread
- Niente operazioni bloccanti sul thread Qt/GUI. Decode, inferenza AI,
  export e I/O vanno su worker thread o processi separati.
- Il modello di progetto e' posseduto dal thread GUI; i worker comunicano
  risultati via signal, non mutano il modello direttamente.

### 4.9 Licenze — e ambito di responsabilita'
Prima di aggiungere **qualunque** dipendenza o modello AI, verifica la
compatibilita' in `docs/LICENSING.md` e aggiorna la tabella.
Ricorda: **la licenza dei pesi di un modello e' diversa da quella del
codice** — molti modelli AI popolari sono non-commercial.

Il rigore vale su **cio' che spediamo noi**: dipendenze, build FFmpeg, asset e
pack ufficiali. **Non** sui contenuti dell'utente o di terzi.

IVE e' uno strumento, non un guardiano (`LICENSING.md` §0). Quindi, come
vincolo di progetto: **l'app non verifica, non giudica e non blocca** i media
importati, i pack di terzi o cio' che l'utente esporta. Niente controlli di
provenienza, niente fingerprinting, niente telemetria, niente filigrane,
niente funzioni a pagamento, niente avvisi moralistici. I campi di licenza
nei pack sono informativi; l'attribuzione e' una comodita' offerta, mai
imposta. Se ti trovi a scrivere un controllo che limita cio' che l'utente puo'
fare col proprio materiale, e' un errore: rileggi questo paragrafo.

---

## 5. Ambiente

Interprete Python (venv condiviso, un livello sopra i progetti):

```
D:\Progetti\DESENVOLVIMENTO\SOFTWARE SIMONE\.venv\Scripts\python.exe
```

Usare sempre questo per eseguire, testare e installare. Su Linux/macOS
l'equivalente `.venv/bin/python`.

---

## 6. Indice della documentazione

| File | Contenuto |
|---|---|
| `docs/ENGINE.md` | **Decisione sul motore**: modello MLT senza la libreria MLT, grafo pull, regole |
| `docs/ARCHITECTURE.md` | Moduli, confini, Action Registry, modello dati, flusso di rendering |
| `docs/UI_SHELL.md` | **Identita' visiva**: video a tutto schermo, vetro, timeline, tool rail, pannello fluttuante |
| `docs/UI_STYLE_GUIDE.md` | Design token, `Theme.qml`, componenti, regole QML |
| `docs/CODING_STANDARDS.md` | Convenzioni Python/QML, logging, errori, test, threading |
| `docs/CONTENT_PACKS.md` | `.ivepack`: musiche, animazioni, transizioni, LUT, font, template |
| `docs/COLOR_EFFECTS.md` | Effetti colore: ricette JSON, sezioni, corsia Color, thumbnail |
| `docs/MEDIA_FORMATS.md` | Codec e contenitori, motore FFmpeg/PyAV, hwaccel, colore e HDR, proxy |
| `docs/EXPORT_PRESETS.md` | Canvas preset (16:9, 9:16...) ed export preset JSON condivisibili |
| `docs/I18N.md` | Sistema traduzioni, chiavi, cosa tradurre e cosa no |
| `docs/LICENSING.md` | Licenza del progetto, tabella dipendenze, trappole GPL/non-commercial |
| `docs/AI_FEATURES.md` | Moduli AI: modelli, backend, contratti, fallback |
| `docs/ROADMAP.md` | Sequenza di implementazione a step |

---

## 7. Come lavorare su questo progetto

1. Prima di implementare, verifica che il modulo di destinazione esista in
   `docs/ARCHITECTURE.md`. Se non c'e', proponi dove va **prima** di scrivere.
2. Ogni feature nuova: modello → command → action → servizio → UI. In
   quest'ordine, mai partire dalla UI.
3. Dopo modifiche a QML/Theme, verifica visivamente (screenshot) prima di
   dichiarare fatto.
4. Non rompere quello che esiste: se una modifica tocca un'interfaccia
   pubblica, cerca prima tutti i chiamanti.
5. Se una decisione architetturale nuova viene presa in sessione,
   **aggiorna il .md corrispondente** nella stessa sessione.
