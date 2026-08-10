# IVE — Convenzioni di codice

---

## 1. Lingua

| Cosa | Lingua |
|---|---|
| Nomi di classi, funzioni, variabili, moduli | Inglese |
| Commenti e docstring | Inglese |
| Messaggi di `logging.*` | Inglese |
| Nomi di file e cartelle | Inglese, `snake_case` |
| Chiavi di traduzione | Inglese |
| Testo mostrato all'utente | **mai hardcoded** → `tr()` / `qsTr()` |
| Documentazione in `docs/` | Italiano |

Motivo: il codice deve restare leggibile da chiunque contribuisca a un
progetto open source, e i log devono essere comprensibili a chi fa supporto.

---

## 2. Python

- **Python 3.12.** Type hint su tutte le funzioni pubbliche.
- Formattazione: `ruff format` (line length 100). Lint: `ruff`.
- `snake_case` per funzioni e variabili, `PascalCase` per classi,
  `UPPER_SNAKE` per costanti di modulo.
- Un modulo privato o un simbolo interno inizia con `_`.
- `__init__.py` di ogni package dichiara `__all__` con l'interfaccia pubblica.
  Cio' che non e' in `__all__` e' dettaglio implementativo e puo' cambiare.
- Import assoluti (`from ive.core.model import Clip`), mai relativi profondi.
- Import pesanti (torch, onnxruntime, av) **lazy**, dentro la funzione che
  li usa: l'avvio dell'app non deve pagarli.
- `dataclass` (o `attrs`) per le strutture del modello, con `slots=True` dove
  se ne creano molte istanze.
- Nessuna variabile globale mutabile. Lo stato vive nei servizi, iniettati.

### Docstring

```python
def split_clip(clip: Clip, frame: int) -> tuple[Clip, Clip]:
    """Split a clip at the given timeline frame.

    Args:
        clip: The clip to split. Must contain ``frame``.
        frame: Absolute timeline frame where the cut happens.

    Returns:
        The left and right parts, in timeline order.

    Raises:
        ValueError: If ``frame`` is outside the clip bounds.
    """
```

---

## 3. QML

- Un componente per file, nome file `PascalCase.qml`.
- `id` in camelCase, `root` per l'elemento radice del file.
- Ordine dentro un componente: `id` → proprieta' pubbliche → signal →
  proprieta' private (`_`) → funzioni → figli → stati/transizioni.
- Niente valori letterali di colore o dimensione: sempre `Theme.*`.
- Niente business logic: solo presentazione e binding.
- Warning QML = bug.
- Dentro `Repeater` annidati **non usare `parent.parent`**: dare un `id` al
  delegato e riferirsi a quello. `parent` cambia significato in modo sottile e
  gli errori che ne derivano sono silenziosi.

Dettagli in `docs/UI_STYLE_GUIDE.md` §9.

### 3-bis. Trappole PySide6/QML gia' incontrate

Tutte e tre hanno **fallito in silenzio o con un messaggio fuorviante**.
Sono costate ore: leggerle prima di perderci tempo di nuovo.

**1. Registrare i singleton PRIMA di creare l'engine.**
`qmlRegisterSingletonInstance()` chiamato *dopo* che esiste un
`QQmlApplicationEngine` corrompe la risoluzione dei tipi per tutti i
componenti caricati in seguito. Il sintomo indica il figlio sbagliato:

```
Cannot assign object of type "QQuickRectangle"
to list property "data"; expected "QObject"
```

Il file QML e' corretto: e' sbagliato l'ordine. Vedi
`ui/bridge.py:register_singletons()`.

**Corollario diagnostico:** la cache dei tipi QML maschera il problema. Una
volta che un componente e' stato caricato con successo resta in cache, quindi
un secondo caricamento nello stesso processo riesce anche dopo che il registro
si e' corrotto. **Questo tipo di guasto si indaga con un processo nuovo per
ogni ipotesi**, altrimenti il bisect da' risultati falsi.

**2. Un layout dentro un layout ha `fillWidth`/`fillHeight` a `true` di
default.** Questo sovrascrive `Layout.preferredWidth` senza alcun avviso. In
`TimelinePanel` gli header presero 1432 px invece di 180 e alle corsie ne
restarono 7: la timeline era vuota, senza un solo warning. Su un layout
annidato con larghezza fissa scrivere sempre in modo esplicito:

```qml
Layout.fillWidth: false
Layout.preferredWidth: N
Layout.minimumWidth: N
Layout.maximumWidth: N
```

**3. `Theme.c` contiene stringhe, non colori.** Funziona per
`color: Theme.c.bgPanel` (QML converte), ma leggere `.r`/`.g`/`.b` su una
stringa da' `undefined`. `Qt.rgba(undefined, ...)` produce **nero**, il che in
tema scuro sembra corretto ed e' evidente solo in tema chiaro. Per fare
aritmetica su un colore, dichiararlo prima come `color`:

```qml
readonly property color _tint: Theme.c.glassTint   // forza la conversione
color: Qt.rgba(_tint.r, _tint.g, _tint.b, scrim)
```

Vale anche per `Qt.alpha()`, `Qt.darker()`, `Qt.lighter()`.

**Verifica dei colori: campionare i pixel, non fidarsi dell'occhio.** Su uno
screenshot di un editor video il contenuto domina la percezione: durante lo
sviluppo di questa fase ho letto come "scuro" un pannello che era `#ffffff`.
Le regressioni di tema si verificano con `img.getpixel()`, non guardando.

---

## 4. Cross-platform

Il codice deve girare su Windows, Linux e macOS.

- Path: sempre `pathlib.Path`. Mai separatori, drive o `~` hardcoded.
- Path del progetto: solo via `utils/paths.py`. Mai
  `Path(__file__).parents[N]` sparso nel codice.
- API OS-specifiche dietro `if sys.platform == "win32" / "linux" / "darwin"`,
  con ramo alternativo o degradazione esplicita.
- File di testo: sempre `encoding="utf-8"`.
- Attenzione al filesystem case-sensitive di Linux: `Icon.svg` != `icon.svg`.
- Estensioni degli eseguibili e delle librerie mai assunte (`.exe`, `.dll`,
  `.so`, `.dylib`) — risolvere a runtime.
- Backend hardware **rilevati**, mai assunti. Vedi §7.
- Su macOS il thread GUI ha vincoli piu' rigidi: nessuna operazione grafica
  fuori dal main thread.

---

## 5. Logging

Setup in `utils/logging_setup.py`, chiamato in `__main__.py` **prima** di
qualunque import pesante e di qualunque scrittura su disco.

Produce in `user_data/log/`:

| File | Contenuto |
|---|---|
| `ive.log` | log applicativo, `RotatingFileHandler` 5 x 2 MB |
| `faulthandler.log` | crash nativi (FFmpeg, driver GPU, ONNX Runtime) |
| `events.log` | eventi di business (progetti aperti, export), rotazione giornaliera |
| `stall.log` | stack di **tutti** i thread quando il thread GUI si pianta |

### Il guardiano del thread GUI

Un blocco e' il bug peggiore da diagnosticare da un log, perche' un programma
piantato non scrive nulla: la finestra smette di ridisegnare, l'utente dice
"si e' bloccato", e il log finisce e basta. E' successo uscendo da fullscreen
con le animazioni disattivate — l'azione loggata, il cambio di visibilita' che
la segue mai, e nessun dump di crash perche' il processo non era crashato.

`utils/watchdog.py`: il thread GUI marca un battito a 4 Hz, un thread daemon
lo sorveglia, e quando il battito invecchia oltre 2 s scrive lo stack di ogni
thread in `stall.log`. Un blocco produce **un** dump, non uno per controllo.

Usa `faulthandler.dump_traceback()` chiamato dal thread di guardia, **non**
`dump_traceback_later()`: quest'ultimo farebbe lo stesso lavoro con meno
codice, ma e' vietato dalla regola qui sotto.

Verificato in `tests/test_watchdog.py`, che pianta apposta il thread GUI e
pretende che il dump nomini la funzione colpevole — un diagnostico che
funziona solo in teoria e' peggio di nessun diagnostico, perche' al blocco
successivo il silenzio ci farebbe cercare altrove.

Installa inoltre `sys.excepthook`, `threading.excepthook`, un handler
`atexit` che dumpa lo stack di tutti i thread, e — dopo la creazione della
`QGuiApplication` — un message handler Qt che convoglia i warning QML nel log.

Regole:
- **Mai** `faulthandler.dump_traceback_later()` / heartbeat: con librerie
  video native su Windows ha causato heap corruption in altri progetti.
- Mai `print()` per diagnostica: in modalita' frozen senza console sparisce.
- Livelli: `DEBUG` dettaglio interno · `INFO` confini e transizioni di stato ·
  `WARNING` degradazioni (fallback a CPU, modello mancante) · `ERROR`
  operazione fallita · `CRITICAL` app non piu' utilizzabile.
- Log INFO in ingresso e uscita ai confini critici: apertura media, start/stop
  playback, inizio/fine export, load/unload modello AI, load plugin,
  selezione backend.
- Messaggi con contesto: `logger.info("Opened media: path=%s codec=%s fps=%s")`,
  non `"ok"`.
- **Mai loggare percorsi personali o contenuti utente** oltre il nome file:
  e' un progetto open source, i log finiscono nelle issue.
- Lazy formatting (`logger.info("x=%s", x)`), non f-string.

---

## 6. Gestione errori

- **Vietato `except Exception: pass`.** Se un errore va ignorato, si logga
  perche'.
- `except Exception` generico solo al confine piu' esterno di un job o di un
  plugin, sempre con `exc_info=True`.
- Ogni modulo definisce le proprie eccezioni tipizzate
  (`MediaOpenError`, `UnsupportedCodecError`, `ModelNotFoundError`, ...)
  derivate da una base `IveError`.
- La UI traduce l'eccezione in un messaggio comprensibile via `tr()`. Mai
  mostrare un traceback all'utente: quello va nel log.
- Errori attesi non devono mai far cadere l'app.

---

## 7. Rilevamento hardware e fallback

- Il backend di rendering e quello di inferenza sono **rilevati a runtime**
  (`video_engine/backends/detect.py`, `ai/runtime/`).
- Ordine di preferenza configurabile dai settings; default automatico.
- Se un backend accelerato fallisce all'inizializzazione **o durante l'uso**,
  fallback a CPU con un WARNING e una notifica non bloccante.
- L'app deve essere **pienamente funzionale su CPU**, senza GPU e senza
  modelli AI installati. Le funzioni non disponibili si mostrano disabilitate
  con una spiegazione, non nascoste.
- Nessuna dipendenza CUDA/ROCm/OpenVINO obbligatoria in `requirements.txt`:
  vanno in extra opzionali.

---

## 8. Threading

- Il modello di progetto e' letto e scritto **solo dal thread GUI**.
- Ogni operazione lunga passa da `JobService`: progresso, cancellazione,
  errori uniformi. Non scrivere thread ad-hoc.
- I worker restituiscono risultati via signal Qt; non mutano strutture
  condivise.
- Il callback audio non alloca, non prende lock lunghi, non fa I/O.
- Riferimenti a `QThread`: tenere viva la reference Python finche' il thread
  gira, e azzerarla nei callback di fine, altrimenti si ottiene
  `RuntimeError: wrapped C/C++ object has been deleted`.
- Librerie native non thread-safe (decoder, contesti GPU): accesso
  serializzato con un lock esplicito, documentato dove si crea l'oggetto.
- **Mai uno slot Python in `DirectConnection` su un segnale emesso dal
  render thread di Qt Quick** (`frameSwapped`, `beforeSynchronizing`,
  `afterRendering`, ...). Chiamare Python richiede il GIL; se il thread GUI
  e' bloccato dentro una chiamata Qt nativa col GIL in mano (es.
  `setVisibility` uscendo da fullscreen, che attende il sync del render
  thread), il processo va in deadlock circolare: GUI aspetta il render,
  il render aspetta il GIL, il GIL e' del GUI. E' stata la causa del blocco
  sistematico uscendo da fullscreen (deadlock in `watchdog.watch_window`,
  provato con py-spy `--native` sul processo piantato). Usare
  `QueuedConnection`: il post dell'evento dal render thread e' C++ puro e
  non tocca il GIL.
- **Seconda faccia della stessa malattia**: `PreviewItem` e' un
  `QQuickPaintedItem` Python, e il suo `paint()` viene eseguito **sul render
  thread** durante il sync dello scene graph (`QSGDefaultPainterNode::paint`
  → `PyGILState_Ensure`). Quindi **mai bloccarsi su una chiamata Qt nativa
  che attende il render thread da un frame Python** (che tiene il GIL):
  `setVisibility`/`setWindowStates` lo fanno. Ogni cambio di stato della
  finestra originato da Python va **differito nell'event loop C++** — in QML
  `Qt.callLater(...)` (vedi `Main.qml`, `onIsFullscreenChanged`), da Python
  un `QMetaObject.invokeMethod(..., QueuedConnection)` — dove PySide ha
  rilasciato il GIL. Provato con py-spy `--native` e riprodotto/verificato
  da `tests/visual/test_fullscreen_cycles.py`.

---

## 9. Performance

- **Misurare prima di ottimizzare.** Nessuna ottimizzazione senza un numero.
- Un solo resize lungo la pipeline video (vedi `ARCHITECTURE.md` §5).
- Niente copie di frame non necessarie: passare buffer, non duplicati.
- Cache su disco (thumbnail, waveform, proxy) in `user_data/cache/`, con
  chiave che include mtime e dimensione del sorgente, e un limite di
  dimensione configurabile.
- La UI non fa mai I/O sincrono su file media.
- Budget indicativo: preview 1080p in tempo reale su CPU desktop moderna con
  al piu' 2-3 effetti attivi; oltre, si usano i proxy.

---

## 10. Test

- `pytest`, con `pytest-qt` per la parte Qt.
- Struttura di `tests/` che rispecchia quella di `src/ive/`.
- **Le Action si testano senza UI**: e' il vantaggio principale del registry.
- Test obbligatori per: matematica del timecode, commands (do → undo →
  stato identico), serializzazione + migrazioni di progetto, compilazione del
  render graph.
- Test di regressione visiva: i backend accelerati confrontati contro il
  backend CPU su clip di riferimento, con tolleranza per-pixel dichiarata.
- I test non toccano mai `user_data/` reale: `tmp_path` sempre.
- Nessun test che richiede una GPU nella suite di default: marcarli
  `@pytest.mark.gpu` ed escluderli di default.

---

## 11. Settings

- Vivono in `user_data/settings/`, formato JSON, letti e scritti solo via
  `settings/service.py`.
- Ogni chiave e' dichiarata in `settings/schema.py` con tipo e default.
  Una chiave non dichiarata non esiste.
- Un file di settings mancante o corrotto → si ricrea dai default con un
  WARNING, l'app parte comunque. Il file corrotto viene rinominato, non
  cancellato.
- I default "di fabbrica" stanno in `ive/config/defaults/` e vengono copiati
  dal bootstrap solo se mancanti.

---

## 12. Dipendenze

- Prima di aggiungere una dipendenza: verificare licenza e piattaforme in
  `docs/LICENSING.md`, e aggiornare la tabella.
- Preferire una dipendenza matura e mantenuta a una micro-libreria.
- `requirements.txt` con versioni pinnate; le dipendenze opzionali
  (accelerazione, modelli AI) in extra separati.
- Nessuna dipendenza che scarica pesi a runtime senza il consenso esplicito
  dell'utente.

---

## 13. Git

- Commit atomici, messaggio in inglese, imperativo:
  `Add ripple delete action to timeline`.
- Un commit non lascia mai il progetto in stato non avviabile.
- `user_data/`, `models/`, `build/`, `dist/` mai versionati.
