# IVE — Formati, codec e motori di conversione

Cosa l'applicazione sa leggere, cosa sa scrivere, e con quale motore.

> Nota terminologica, utile se non hai mai lavorato con il video:
> un **contenitore** (MP4, MOV, MKV) e' la scatola; un **codec** (H.264,
> AAC) e' il modo in cui il contenuto e' compresso dentro la scatola. Lo
> stesso `.mp4` puo' contenere codec diversi. Quasi tutti i problemi di
> compatibilita' nascono dal confondere le due cose.

---

## 1. Un solo motore: FFmpeg

Tutto l'I/O media passa da **FFmpeg**, usato via **PyAV** (binding Python).
Niente secondo motore, niente percorsi alternativi.

**Perche' FFmpeg.** Legge e scrive praticamente tutto, e' libero, e' lo
standard di fatto: e' il motore dentro VLC, Kdenlive, Shotcut, HandBrake,
OBS, Blender e la maggior parte dei servizi di streaming. Qualunque
alternativa sarebbe un sottoinsieme con piu' bug.

**Perche' PyAV e non chiamare `ffmpeg.exe`.** Invocare il binario da riga di
comando significa: passare da file temporanei, ri-encodare a ogni passaggio
perdendo qualita', non avere controllo frame-accurate, e non poter riportare
il progresso in modo preciso. PyAV lavora con i frame in memoria, che e'
quello che serve a un editor.

Trappole note (documentate qui perche' costano ore):
- La **licenza di FFmpeg dipende da come e' compilato**. Vedi
  `docs/LICENSING.md` §3. E' la decisione piu' vincolante del progetto.
- I timestamp (`pts`/`dts`) sono in `time_base` del flusso, non in secondi.
  Le conversioni passano **solo** da `utils/timecode.py`.
- Il seek "veloce" arriva al keyframe precedente, non al frame richiesto: per
  un editor serve seek al keyframe + decode in avanti fino al frame esatto.
  E' l'unico modo di essere frame-accurate.
- La rotazione dei video da smartphone e' nei metadati, non nei pixel:
  ignorarla significa mostrare i video verticali coricati.
- Il primo frame non e' sempre a timestamp 0.

---

## 2. Import — video

L'import e' **permissivo**: se FFmpeg lo apre, l'app lo accetta.

| Contenitore | Nota |
|---|---|
| MP4 / M4V | il piu' comune |
| MOV | Apple, ProRes, alpha |
| MKV | flessibile |
| WebM | web, VP8/VP9/AV1 |
| AVI | vecchio ma frequente |
| MTS / M2TS | videocamere AVCHD |
| MPEG-TS | registrazioni, broadcast |
| GIF | trattata come video senza audio |

| Codec video | Nota |
|---|---|
| H.264 / AVC | lo standard, decode hardware ovunque |
| H.265 / HEVC | 4K e HDR, decode hardware su hardware recente |
| VP9 | web, alpha supportato |
| AV1 | recente, decode molto pesante su hardware vecchio → **usare i proxy** |
| ProRes | intermedio professionale, leggero da decodificare |
| DNxHD / DNxHR | equivalente Avid |
| MJPEG | vecchie fotocamere e webcam |
| MPEG-2 / MPEG-4 ASP | materiale d'archivio, DVD |

**Immagini:** PNG, JPEG, WebP, BMP, TIFF, HEIC (verificare la disponibilita'
del decoder nella build), e le **sequenze di immagini** (`frame_0001.png` …)
riconosciute automaticamente e trattate come una clip video.

### Import da cartella / drag & drop

Requisito esplicito. Comportamento:
- Trascinando **file** nella finestra: importati nel media pool.
- Trascinando una **cartella**: scansione ricorsiva (profondita' limitata e
  configurabile), import di tutti i media riconosciuti.
- Il rilascio **sulla timeline** inserisce direttamente al punto di rilascio;
  il rilascio sul media pool importa soltanto.
- Ordinamento all'import: per nome, per data di creazione, o per data di
  ripresa dai metadati. Impostazione persistita — chi monta filmati di
  vacanza vuole l'ordine cronologico, non alfabetico.
- **Import asincrono con progresso.** Trascinare 300 clip non deve congelare
  l'app: prima si popola la lista con i nomi, poi arrivano metadati e
  thumbnail via via.
- File non riconosciuti: elencati in un riepilogo finale, non con 40 popup
  di errore.
- File gia' presenti: rilevati per path + dimensione + mtime, non duplicati.

---

## 3. Export — video

L'export e' **restrittivo**: pochi formati, scelti bene, tutti affidabili.
Un editor che espone 200 codec confonde. Le combinazioni sono nei preset
(`docs/EXPORT_PRESETS.md`).

| Codec | Contenitore | Uso | Nota licenza |
|---|---|---|---|
| **H.264** | MP4 | default per tutto | encoder x264 e' GPL → vedi `LICENSING.md` §3 |
| **H.265 / HEVC** | MP4, MOV | 4K, HDR, file piu' piccoli | encoder x265 e' GPL |
| **VP9** | WebM | web, alpha | libvpx BSD → utilizzabile anche in build LGPL |
| **AV1** | MP4, WebM | archiviazione efficiente | SVT-AV1 BSD; encoding lento su CPU |
| **ProRes** | MOV | consegna a un altro editor, qualita' massima | encoder FFmpeg nativo |
| **GIF** | — | anteprime brevi | palette ottimizzata, non per contenuti lunghi |
| **PNG/JPEG sequence** | — | passaggio ad altri tool | |
| **Frame singolo** | PNG, JPEG | esportare un fotogramma | |

**Nota sull'audio nei preset:** AAC per MP4/MOV (l'encoder AAC nativo di
FFmpeg e' libero e sufficiente), Opus per WebM, PCM per ProRes.

**Alpha (trasparenza) in export:** solo VP9/WebM, ProRes 4444 e le sequenze
PNG la supportano. MP4/H.264 **non ha alpha** — se l'utente ha una clip con
sfondo rimosso e sceglie MP4, va avvisato prima dell'export, non dopo.

---

## 4. Encoding hardware

Encodare con la GPU e' molto piu' veloce; la qualita' a parita' di bitrate e'
leggermente inferiore rispetto a un buon encoder software. Quindi:
**hardware di default per la velocita', software selezionabile per la
qualita' massima.**

| Piattaforma | Encoder |
|---|---|
| NVIDIA | NVENC (H.264, HEVC, AV1 su schede recenti) |
| Intel | Quick Sync / QSV |
| AMD | AMF (Windows), VAAPI (Linux) |
| macOS | VideoToolbox |
| Software | x264, x265, SVT-AV1, libvpx |

Regole:
- Rilevamento a runtime (`export/hwaccel.py`): la presenza del codec in
  FFmpeg non basta, va **testato aprendo un encoder di prova**. Molte
  configurazioni dichiarano supporto e poi falliscono.
- Fallback automatico a software se l'encoder hardware fallisce
  all'inizializzazione **o a meta' export** — con WARNING e notifica, senza
  perdere il lavoro.
- L'encoder effettivamente usato e' mostrato nel dialog di export e
  registrato nel log.
- I preset dichiarano un codec logico (`h264`), non un encoder specifico:
  la scelta di `h264_nvenc` vs `libx264` la fa l'app in base all'hardware.
  Cosi' lo stesso preset condiviso funziona sulla macchina di chiunque.

**Decoding hardware:** attivo di default (DXVA2/D3D11VA, VAAPI, VideoToolbox)
con fallback software. Alcuni decoder hardware sono meno precisi nel seek:
se si rileva imprecisione, si passa a software per quella clip.

---

## 5. Audio

**Import:** WAV, FLAC, MP3, AAC/M4A, OGG Vorbis, Opus, AIFF, WMA, e le tracce
audio contenute nei video.

**Export e content pack:**

| Formato | Uso | Licenza |
|---|---|---|
| **OGG Vorbis** | musica nei content pack | libero, nessun brevetto |
| **Opus** | musica e voce, il piu' efficiente | libero, nessun brevetto |
| **FLAC** | qualita' senza perdita, pack di alta qualita' | libero |
| **WAV** | effetti brevi, lavorazione | nessuna compressione |
| **MP3** | massima compatibilita' | brevetti scaduti nel 2017 → utilizzabile |
| **AAC** | audio dentro MP4/MOV | encoder nativo FFmpeg |

**Consigliato per i content pack: OGG Vorbis o Opus.** Peso contenuto,
nessun problema di brevetti, ottima qualita'. FLAC dove la qualita' conta
piu' della dimensione.

**Elaborazione interna:** tutto convertito a **float32, 48 kHz, stereo**
all'ingresso del grafo audio. Un solo formato interno significa nessuna
conversione sparsa nel codice e nessun errore di sample rate.

**Loudness:** normalizzazione secondo EBU R128 (LUFS). I preset per
piattaforma dichiarano il target (tipicamente da -16 a -14 LUFS): e' la
differenza fra un video che suona come gli altri e uno troppo basso o
distorto.

---

## 6. Formati per le animazioni

| Formato | Uso | Perche' |
|---|---|---|
| **Keyframe JSON** (formato nostro) | animazioni in/out, movimenti | pochi kB, indipendente da risoluzione e durata, editabile |
| **Lottie JSON** | grafica animata vettoriale | scala senza perdita, molto leggero, esportabile da tool di animazione |
| **WebM / VP9 con alpha** | overlay animati raster | codec libero, alpha reale, buona compressione |
| **APNG** | animazioni brevi con alpha | supporto semplice, file grandi |
| **Sequenza PNG** | qualita' massima | molto pesante, per casi specifici |
| **SVG** | grafica statica vettoriale | scalabile |
| **Luma matte** (video grayscale) | transizioni wipe | permette wipe arbitrari senza shader |

Dettaglio degli schemi in `docs/CONTENT_PACKS.md` §4.

**Su Lottie:** Qt ha un modulo Lottie; **va verificata la disponibilita' e la
maturita' in Qt 6.7** prima di considerarlo acquisito. Alternativa: la
libreria `rlottie`. Se nessuna delle due risulta praticabile, Lottie si
rimanda e si parte con keyframe JSON + WebM alpha, che coprono la gran parte
dei casi. **Non e' un blocco per la 1.0.**

**Sconsigliati:** GIF animata come formato di overlay (256 colori, alpha a
1 bit, bordi frastagliati) e i formati Flash/SWF (morti). GIF resta
supportata in import e in export come comodita', non come formato di lavoro.

---

## 7. Sottotitoli

**Import/export:** SRT (semplice, universale), WebVTT (web), ASS/SSA
(stili e posizionamento).

- Internamente i sottotitoli sono **clip di testo su una traccia**, non un
  formato separato: cosi' si animano, si stilizzano e si spostano come
  qualunque altro elemento.
- All'export, due modalita': **burn-in** (impressi nei pixel, visibili
  ovunque) o **traccia separata** in MP4/MKV (disattivabile dallo
  spettatore). La scelta e' nel preset.
- ASS e' il piu' espressivo ma anche il piu' facile da rendere in modo
  incoerente fra player diversi: usarlo solo quando servono davvero stili
  complessi.

---

## 8. Colore e HDR

L'area piu' facile da sbagliare in modo invisibile. Serve un approccio
graduale e onesto.

### Fondamenta (obbligatorie fin dall'inizio)

Anche restando solo in SDR, il pipeline deve essere **color-managed**:

- Ogni clip in ingresso porta con se' il proprio spazio colore, letto dai
  metadati (primaries, transfer, matrix) — non assunto.
- Elaborazione interna in **float lineare** o in uno spazio di lavoro
  dichiarato, mai "i pixel come vengono".
- Conversione esplicita in uscita verso lo spazio di destinazione.
- Il range (limited 16-235 vs full 0-255) va gestito: sbagliarlo produce neri
  slavati o schiacciati, ed e' l'errore piu' comune in assoluto.

**Perche' farlo subito:** aggiungere la gestione colore dopo significa
riscrivere il compositor. Farla dal primo giorno costa poco.

### HDR — approccio in due tempi

L'HDR non e' una casella da spuntare: richiede pipeline a 10 bit,
gestione dei metadati, encoder adeguati e — problema serio — un modo di
mostrarlo su un monitor SDR.

**Fase A — Import HDR corretto (realistico per la 1.0)**
- Riconoscere il materiale HDR (PQ/HLG, BT.2020, 10 bit) dai metadati.
- **Tone mapping verso SDR per il preview e per l'export SDR.** Senza,
  un video HDR appare slavato e desaturato, e l'utente non capisce perche'.
- Preservare i metadati in passthrough se non si tocca il colore.
- Avvisare chiaramente quando si sta lavorando su materiale HDR in un
  progetto SDR.

Questo copre il caso reale piu' frequente: **girato con un iPhone o un
Android recente (che registrano in HDR di default) e pubblicato in SDR.**
Oggi la maggior parte degli editor gratuiti sbaglia proprio questo.

**Fase B — Editing e export HDR nativo (dopo la 1.0)**
- Pipeline a 10 bit end-to-end.
- HDR10: PQ + BT.2020 + metadati statici (MaxCLL, MaxFALL, mastering display).
- HLG: piu' semplice, retrocompatibile con SDR, usato in broadcast.
- Export: HEVC 10-bit o AV1 10-bit con i metadati corretti.
- Preview su monitor SDR **sempre** tone-mapped, con indicazione esplicita
  che quello che si vede non e' il risultato finale.
- Dolby Vision: **fuori scope**, richiede licenza proprietaria.

**Da dichiarare all'utente senza ambiguita':** in Fase A l'app *gestisce
correttamente* il materiale HDR, non *produce* HDR. Promettere HDR e
consegnare un tone mapping e' peggio che non prometterlo.

---

## 9. Proxy

Il 4K e l'AV1 non si montano fluidi su una macchina normale. Il proxy e' la
soluzione standard: si lavora su una copia leggera, si esporta
dall'originale.

- Generazione su richiesta o automatica sopra una soglia di risoluzione.
- Formato: ProRes Proxy o H.264 a bassa risoluzione (540p o 720p), da
  valutare per velocita' di decode.
- Salvati in `user_data/cache/proxies/`, chiave = hash di path + dimensione +
  mtime del sorgente.
- Toggle globale proxy on/off, con indicazione visibile dello stato.
- **L'export usa sempre i file originali**, mai i proxy. Questa e' la regola
  che non si viola mai: un export fatto dai proxy e' lavoro perso.

---

## 10. Cosa NON supportiamo

Deciso esplicitamente, per non finire in paludi:

- **Dolby Vision, Dolby Atmos** — licenze proprietarie
- **Blu-ray / DVD authoring** — progetto a se'
- **RED R3D, ARRIRAW, BRAW e altri raw cinema** — SDK proprietari
- **Progetti di editor terzi** (.prproj, .fcpxml, .drp) — formati non
  documentati e instabili
- **DRM di qualunque tipo**
- **Streaming diretto** verso piattaforme
- **Multicam** — dopo la 1.0

---

## 11. Checklist per un nuovo formato

1. [ ] FFmpeg lo supporta nella build che distribuiamo su **tutte e tre** le
       piattaforme?
2. [ ] La licenza dell'encoder/decoder e' compatibile (`LICENSING.md`)?
3. [ ] E' import, export, o entrambi?
4. [ ] Se export: c'e' un preset che lo usa, o resta irraggiungibile?
5. [ ] Alpha, HDR, frame rate variabile: gestiti o esplicitamente rifiutati?
6. [ ] Testato con file reali, inclusi casi degeneri (0 frame, audio assente,
       frame rate variabile, rotazione nei metadati, durata dichiarata errata)
7. [ ] Aggiunto alle tabelle di questo documento
