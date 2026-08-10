# IVE — Il motore: decisione e architettura

Documento di decisione architetturale. Risponde a una domanda sola:
**su quali fondamenta si costruisce, perche' fra sei mesi aggiungere effetti,
transizioni e audio non sia una riscrittura?**

Scritto dopo aver studiato MLT e Kdenlive alla fonte. Le fonti sono in fondo.

---

## 1. La domanda vera non e' "quale libreria"

La tentazione e' impostare la scelta come *FFmpeg contro MLT*. E' l'inquadratura
sbagliata, e ci ha fatto perdere un giro.

MLT **usa** FFmpeg per decodificare. Non sono alternative sullo stesso livello:
FFmpeg legge e scrive file, MLT e' il **modello di composizione** che sta sopra.
La domanda giusta e':

> Qual e' il modello che rende possibile aggiungere effetti dopo, senza
> toccare quello che c'e' gia'?

E la risposta a quella domanda **non dipende da quale libreria si linka**.

---

## 2. Cosa fa davvero MLT, e perche' e' il modello giusto

MLT esiste dal 2004 ed e' il motore di **Kdenlive** e **Shotcut**. Il suo
modello e' stato validato da vent'anni di editor veri. Vale la pena capirlo
prima di inventarne uno.

### 2.1 Si tira, non si spinge

Il **consumer** chiede un fotogramma. La richiesta risale all'indietro nel
grafo fino ai producer, che generano; poi filtri e transizioni modificano i
dati mentre risalgono verso il consumer.

Niente viene calcolato se nessuno lo ha chiesto. E' questo che rende
economico lo scrubbing: si tira un fotogramma solo, non si "riproduce" niente.

### 2.2 Solo il producer sa che ora e'

Questa e' la parte piu' sottile e piu' preziosa. Citando la documentazione MLT:

> "neither the filter nor the consumer have any conception of 'position'
> until they receive a frame"

Il producer scrive la posizione **dentro il fotogramma**. Da quel momento un
filtro e' una **funzione pura del fotogramma**: non sa dove si trova nella
timeline, non sa chi lo ha chiamato, non ha stato.

Le conseguenze pratiche sono enormi:
- un filtro si testa da solo, senza timeline e senza interfaccia;
- lo stesso filtro funziona identico in anteprima e in export;
- l'ordine dei filtri e' l'unica cosa che conta, e si legge dal modello.

### 2.3 Un fotogramma porta due pile pigre: immagine e audio

Audio e video **percorrono lo stesso grafo**, in due stack separati dentro
l'oggetto frame, valutati pigramente. Un consumer puo' chiedere solo l'audio,
o solo l'immagine.

E' cosi' che si ottengono gratis cose che altrimenti sono lavoro:
lo scrub audio, l'anteprima video senza decodificare l'audio, l'export
audio-only, la forma d'onda.

**Questa e' la ragione per cui il nostro audio non deve essere un sottosistema
separato.** Se lo fosse, la sincronizzazione A/V diventerebbe un problema
permanente invece di una proprieta' del modello.

### 2.4 La composizione e' ricorsiva

| Elemento | Cos'e' |
|---|---|
| **Producer** | zero ingressi, una uscita; genera fotogrammi |
| **Playlist** | **e' un producer**: sequenza di clip e spazi vuoti = una traccia |
| **Multitrack** | piu' producer in parallelo |
| **Field** | dove vivono filtri e transizioni fra le tracce |
| **Tractor** | avvolge il multitrack, tira le tracce **in modo sincrono**, produce un fotogramma solo — **ed e' a sua volta un producer** |
| **Filter** | trasforma un fotogramma |
| **Transition** | combina esattamente due fotogrammi |
| **Consumer** | tira i fotogrammi e li porta fuori: schermo o file |

Il punto che fa la differenza: **playlist e tractor sono producer**. Quindi una
traccia e' un producer, una sequenza e' un producer, e una sequenza annidata
dentro un'altra non e' un caso speciale — e' la stessa cosa. Gratis.

### 2.5 Come lo usa Kdenlive

- un **tractor principale** (`maintractor`) contiene le tracce;
- ogni traccia e' una **playlist**;
- la traccia piu' in basso e' una **traccia nera**, un producer `colour`,
  nascosta all'utente: garantisce che ci sia sempre qualcosa su cui comporre;
- il formato di progetto **e' MLT XML** con un namespace `kdenlive:` per i
  propri metadati, scelto apposta perche' *MLT sappia renderizzare
  direttamente un file Kdenlive*.

---

## 3. La lezione piu' importante viene da un errore di Kdenlive

Nella prima generazione di Kdenlive i parametri degli effetti potevano
**desincronizzarsi fra il livello dell'interfaccia e quello di rendering**: la
UI mostrava un valore, il render ne usava un altro. La documentazione lo
definisce un problema di instabilita' critico, risolto nella migrazione a KF5
tenendo **un'unica fonte di verita'**.

Per noi diventa una regola non negoziabile:

> **Il grafo di rendering e' sempre DERIVATO dal modello di progetto,
> mai modificato per conto proprio.**

Nessun percorso in cui la UI scrive un parametro "nel render" e un altro "nel
progetto". Se un valore vive in due posti, prima o poi divergono, e il bug che
ne esce e' fra i piu' difficili da trovare: l'anteprima e' giusta, l'export no.

Vale anche al contrario: `docs/ARCHITECTURE.md` §5 promette che anteprima ed
export usino lo stesso grafo. Per un periodo il codice ha violato quella
promessa — `PlaybackService` chiedeva fotogrammi al decoder ed `ExportService`
riapriva il file per conto suo. **Sanato il 2026-08-09**, prima di iniziare gli
effetti: entrambi passano ora dal `GraphBuilder`.

---

## 4. La decisione

> **Adottiamo il modello di MLT. Non adottiamo, per ora, la libreria MLT.**
>
> Il codice viene strutturato in modo che un backend MLT sia sostituibile
> dietro le stesse interfacce, senza toccare modello di progetto, azioni o
> interfaccia.

### Perche' non la libreria, adesso

Verificato su questa macchina, non dedotto:

```
pip install mlt / mlt7   ->  No matching distribution found
import mlt               ->  ModuleNotFoundError
MLT nel sistema          ->  assente
```

I binding Python di MLT **non sono distribuiti per Windows**. Su Linux le
distribuzioni pacchettizzano `python3-mlt`; su Windows si ottengono solo
compilando MLT dai sorgenti con SWIG contro Python 3.10, e poi impacchettando
l'intero albero dei plugin dentro PyInstaller.

E il dato decisivo: **Kdenlive e Shotcut usano MLT dal C++**, linkano
`libmlt` direttamente. Non esiste un percorso Python collaudato da seguire.

### Perche' il modello si', subito

Il modello e' l'80% del valore e costa qualche centinaio di righe. La libreria
e' il restante 20% (i ~200 filtri gia' pronti) e costa un cantiere di build.

Adottare il modello ora significa che il giorno in cui la libreria diventa
conveniente, il cambio e' **un backend nuovo**, non una riscrittura.

### Le tre strade tenute aperte

| | Quando conviene | Costo del passaggio, se il modello e' questo |
|---|---|---|
| **A. Producer nostri (PyAV)** | ora | — |
| **B. `melt.exe` + MLT XML per l'export** | quando servono transizioni in export prima che nell'anteprima | scrivere un serializzatore XML: giorni |
| **C. `libmlt` vero** | se il progetto passasse a C++, o se apparissero binding Python affidabili | implementare `Producer` con un tractor MLT: settimane, non mesi |

**Raccomandazione operativa sul formato di progetto:** `.iveproj` deve restare
**mappabile su MLT XML** — producer, playlist, tractor, transizioni,
filtri con i loro parametri. Non e' un vincolo costoso oggi e tiene aperte
sia la strada B sia la C. E' esattamente la scelta che ha fatto Kdenlive.

---

## 5. L'architettura che costruiamo

```
                          ┌───────────────┐
                          │   Consumer    │  tira i fotogrammi
                          │ preview/export│
                          └───────┬───────┘
                                  │ frame_at(n)
                          ┌───────▼───────┐
                          │    Tractor    │  tira le tracce in sincrono
                          │  (e' Producer)│
                          └───────┬───────┘
                    ┌─────────────┼─────────────┐
              ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐
              │ Playlist  │ │ Playlist  │ │  Colour   │
              │  traccia  │ │  traccia  │ │  (nero)   │
              │   V1      │ │    A1     │ │  sempre   │
              └─────┬─────┘ └───────────┘ └───────────┘
              ┌─────▼─────┐
              │   Clip    │  ← foglia: PyAV
              │ + Filter  │
              └───────────┘
```

### I contratti

```python
class Frame:
    position: int              # scritta dal producer, mai da altri
    fps: Fraction
    _image: Callable | None    # pigro: valutato solo se richiesto
    _audio: Callable | None    # pigro, indipendente dall'immagine

class Producer(Protocol):
    length: int
    def frame_at(self, position: int) -> Frame | None: ...

class Filter(Protocol):
    def process(self, frame: Frame) -> Frame: ...      # funzione pura

class Transition(Protocol):
    def process(self, a: Frame, b: Frame, t: float) -> Frame: ...

class Consumer(Protocol):
    def start(self, producer: Producer) -> None: ...
    def stop(self) -> None: ...
```

### Cosa diventa cosa

| Funzione futura | Dove entra |
|---|---|
| Effetto video | `Filter` sullo stack immagine |
| Effetto audio | `Filter` sullo stack audio |
| Transizione | `Transition` fra due entry della playlist |
| Traccia in piu' | una `Playlist` in piu' nel `Multitrack` |
| Audio esterno | `Playlist` su una traccia audio: **stesso meccanismo** dei video |
| Traccia audio di un video | lo stack audio del `Clip`, gia' presente |
| Sequenza annidata | un `Tractor` usato come producer |
| Anteprima | `PreviewConsumer` (tira a orologio) |
| Export | `ExportConsumer` (tira il piu' veloce possibile) |
| Forma d'onda | si tira solo lo stack audio, senza decodificare immagini |
| Backend MLT | una classe che implementa `Producer` |

Le due colonne dicono la cosa importante: **nessuna riga di quella tabella
richiede di cambiare il modello di progetto, le azioni o l'interfaccia.**

---

## 6. Regole del motore

1. **Il grafo e' derivato dal modello, mai modificato a parte.**
   Fonte unica di verita'. E' l'errore che ha destabilizzato Kdenlive gen-1.
2. **Anteprima ed export tirano lo stesso grafo.** Cambiano solo risoluzione,
   uso dei proxy e velocita' di tiraggio. Se differiscono, il file esportato
   non corrispondera' a quello che l'utente ha visto.
3. **Solo il producer conosce la posizione.** Un filtro che chiede "dove sono"
   e' un filtro progettato male.
4. **Audio e video sullo stesso grafo**, in stack separati e pigri.
   L'audio non e' un sottosistema parallelo.
5. **Sempre una traccia nera in fondo**, come Kdenlive: componendo, c'e'
   sempre qualcosa sotto.
6. **Ogni producer e' sostituibile.** Il tipo che sta sopra non deve sapere se
   sotto c'e' PyAV, un generatore di colore o un tractor MLT.
7. **Tutto in frame, mai in secondi**, dentro il motore. I secondi restano
   all'interfaccia. Il modello di progetto oggi usa i secondi: e' un debito
   da chiudere quando arriva il timebase della sequenza.

---

## 6-bis. Il riproduttore: read-ahead, non richiesta a tempo

Il consumer di MLT — quello che Kdenlive pilota — non chiede il fotogramma
quando serve. Ha un **thread di read-ahead** che riempie una coda, e il lato
uscita prende quello che e' pronto. La proprieta' `real_time` dice quanti
thread preparano i fotogrammi: `0` nessun parallelismo, `> 0` con scarto di
fotogrammi, `< 0` senza scarto (usata per il rendering).

Noi facevamo l'opposto: il QTimer chiedeva il fotogramma dovuto e aspettava.
Misurato su un 1080p: **2,1 fps invece di 30, con il 100% dei fotogrammi che
passava da un seek** (`tests/test_playback_pacing.py`).

Il motivo per cui degenera cosi': `VideoDecoder.frame_at` ha la via veloce
**solo** per `cursor + 1`. Un fotogramma in ritardo fa avanzare l'orologio, la
richiesta successiva salta un indice, il salto costa un seek, il seek e' piu'
lento di una decodifica, e la richiesta dopo salta ancora. **La scattosita' si
autoalimenta.**

Regole, tutte con la misura che le motiva:

1. **Riprodurre e scrubbare sono due percorsi diversi.** Lo scrub chiede un
   fotogramma e aspetta; la riproduzione prende dal buffer.
2. **Il produttore ha thread e decoder propri.** Con i decoder condivisi, uno
   scrub durante la riproduzione sposta il cursore e rimette tutto sulla via
   del seek. Un produttore guidato da segnali in coda gira solo quando viene
   sollecitato, e la frequenza delle sollecitazioni e' quella di consumo:
   non puo' costruire riserva (33 fps contro i 58 di cui era capace).
3. **Restare indietro deve costare fotogrammi, mai tempo.** Se il buffer non
   ha nulla di pronto resta a schermo il fotogramma precedente e l'orologio
   prosegue; e' il `real_time` positivo di MLT.
4. **Gli indici si troncano, non si arrotondano.** `_tick` decide che il
   fotogramma e' cambiato confrontando numeri troncati: un indice calcolato
   con `round()` va alla deriva di mezzo fotogramma rispetto a quella
   decisione, e allora certi tick chiedono due volte lo stesso indice e altri
   ne saltano uno. Uscivano 30 fotogrammi al secondo dal buffer e ne arrivavano
   20 a schermo.
5. **L'orologio parte solo col primo fotogramma pronto.** Avviarlo subito
   significa riempire il buffer mentre il tempo scorre gia': quei fotogrammi
   nascono in ritardo.
6. **Quando l'audio suona, l'audio E' l'orologio.** La scheda consuma campioni
   al ritmo del proprio quarzo, che non e' il secondo di `QElapsedTimer`: due
   orologi in disaccordo divergono, e il labiale se ne va in pochi minuti. Il
   playhead segue `processedUSecs()` del sink (quanto suono il device ha
   davvero processato); il timer resta solo come fallback per macchine senza
   device audio, e come paracadute se il device smette di consumare a meta'
   riproduzione (`playback/audio_output.py`, `_elapsed_since_anchor` nel
   transport).
7. **L'audio viaggia sullo stesso buffer del read-ahead.** Un solo thread puo'
   tirare sul grafo, quindi il produttore valuta ENTRAMBI gli stack; il tick
   raccoglie il suono con `take_audio` prima e indipendentemente dalle
   immagini (il sink bufferizza avanti, lo schermo no). Un fotogramma
   scartato perche' in ritardo costa un'immagine, **mai i suoi campioni**:
   perderli lascerebbe un click e accorcerebbe la traccia.

Risultato oggi (`tests/test_transport_playback.py`): 1080p **35 fotogrammi su
34 attesi**. 4K **24,8 su 30** — il player decodifica ancora a piena
risoluzione e non usa i proxy, vedi il debito qui sotto.

Il tono di prova (440 Hz a sinistra, 880 a destra) e' verificato **dopo il
sink**: `tests/test_audio_output.py` intercetta i blocchi che il device
accetta e ne recupera il pitch esatto, con playhead e suono d'accordo entro
il buffer del device (0,2 s). Il costo one-shot del backend WASAPI (~0,5 s
alla prima query di formato) e' pagato in background alla costruzione del
transport (`AudioOutput.warm_up`), non dentro il primo play().

---

## 7. Stato attuale e debito

**Cosa c'e' oggi:** decodifica frame-accurate, un sequencer che riproduce
clip in fila, export che ricodifica un file.

**Cosa non c'e' e va costruito prima degli effetti:**

- [x] `Frame` con stack immagine/audio pigri
- [x] `Producer` / `Filter` / `Transition` / `Consumer`
- [x] `ClipProducer` (PyAV), `ColourProducer`, `Playlist`, `Multitrack`, `Tractor`
- [x] `PreviewConsumer` ed `ExportConsumer` **sullo stesso grafo** —
      chiude la violazione di `ARCHITECTURE.md` §5
- [x] decodifica audio e mixer sullo stack audio
- [ ] timebase della sequenza: modello in frame, non in secondi

**Chiuso il 2026-08-09:** anteprima ed export tirano lo **stesso grafo**,
derivato dallo stesso modello. `PlaybackService` non apre piu' decoder per
conto suo; `ExportService` cammina il grafo con `SequenceWalker` e rende la
sequenza intera invece del solo clip sotto il playhead — con
`use_proxies=False`, perche' una consegna renderizzata da file sostitutivi e'
lavoro sprecato che l'utente scopre dopo. Verificato da
`tests/test_export_sequence.py` (il file reso dura quanto la timeline) e da
`tests/test_transport_playback.py`.

**Debito noto, dichiarato:**
- Il canvas della sequenza e' il rapporto del **primo clip**. Un clip con
  proporzioni diverse ci entra con le bande nere, e l'ambient backdrop —
  che sfoca il fotogramma del canvas — si scurisce di conseguenza. Corretto
  come modello (il canvas appartiene al progetto), ma va reso una **scelta
  esplicita**: canvas di progetto come da `EXPORT_PRESETS.md`.
- Il modello di progetto misura in secondi.
- L'export non porta ancora l'audio nel file (il grafo lo produce; manca il
  muxing in `export/service.py`, insieme al fix dei rate frazionari
  `rate=round(fps)`).
- La forma d'onda sulle clip e' ancora generata, non i picchi reali
  (`media/waveform.py`).

**Chiuso il 2026-08-09 (sera): uscita audio e sincronia A/V.** Il grafo viene
suonato da `playback/audio_output.py` (QAudioSink, push mode) e il playhead
segue il clock del device (§6-bis, regole 6-7). Nella stessa area: conteggio
campioni per frame dai **confini cumulativi interi** (un `round()` costante
derivava ~0,9 s/ora a 29.97), e il buffer audio del producer si ancora al pts
di **atterraggio reale** del seek, non al tempo richiesto. Verificato da
`tests/test_audio_output.py` (12 check, misurati dopo il sink).

---

## Fonti

- [MLT Framework — architettura](https://www.mltframework.org/docs/framework/)
- [Kdenlive — introduzione a MLT (dev-docs)](https://github.com/KDE/kdenlive/blob/master/dev-docs/mlt-intro.md)
- [Kdenlive — formato di progetto (dev-docs)](https://github.com/KDE/kdenlive/blob/master/dev-docs/fileformat.md)
- [Inside Kdenlive Projects: MLT Concepts](https://thediveo-e.blogspot.com/2016/07/inside-kdenlive-projects-mlt-concepts.html)
- [Inside Kdenlive Projects: Main Tractor and Multitrack](https://thediveo-e.blogspot.com/2016/07/inside-kdenlive-projects-main-tractor.html)
