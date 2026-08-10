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

---

## 5. Traduzione

Due usi distinti:
1. **Traduzione dei sottotitoli** generati o importati.
2. **Traduzione dei testi** (titoli, caption) presenti nel progetto.

> Da non confondere con l'i18n dell'interfaccia (`docs/I18N.md`): moduli
> separati, nessun codice in comune.

Punti importanti:
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

---

## 7. Motion tracking

**Pipeline:** selezione della regione → tracking → traiettoria di keyframe →
applicazione a un altro elemento (testo, effetto, maschera, mosaico).

Punti importanti:
- Baseline **senza modelli AI**: tracker classici di OpenCV (CSRT, KCF).
  Devono essere sempre disponibili, senza download.
- Livello AI opzionale per point tracking robusto a occlusioni.
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
