# IVE — Content Pack

Il sistema con cui la comunita' aggiunge e si scambia **musiche, animazioni,
transizioni, LUT, font, sticker, template ed export preset** senza scrivere
una riga di codice.

---

## 0. Stato: v1 implementata (2026-08-19)

La prima versione e' viva e copre le tre categorie che oggi hanno un
catalogo JSON: **effetti colore, transizioni (mappe luma comprese) e
sticker (SVG e Lottie)**. Il resto di questo documento e' la specifica
completa verso cui si cresce; le sezioni sotto valgono come scritte,
con queste scelte concrete della v1:

- **Struttura interna**: le stesse cartelle che i cataloghi gia'
  scansionano — `pack.json` in cima, `color_effects/effects.json`,
  `transitions/transitions.json` + `transitions/luma/`,
  `stickers/pack_stickers.json` + `stickers/files/`.
- **Installazione**: `user_data/packs/<pack_id>/`; ogni catalogo
  scansiona anche quelle cartelle (`ive/packs/pack.py`,
  `pack_content_dirs`). Id duplicati saltati con warning, mai
  sovrascritto nulla. Percorsi dei membri sanificati (zip-slip).
- **Disinstallazione**: si cancella la cartella (tab «Installati» del
  pannello, o a mano). I progetti che usavano quei contenuti si aprono
  lo stesso: quei tratti tornano neutri.
- **UI** (layout «Opzione A», scelto su mockup): pannello **Pacchetti**
  nella tool rail con due tab — «Crea» (dettagli, contenuti spuntabili
  per categoria con contatori, scorciatoia «Aggiungi i preferiti»,
  export) e «Installati» (unita' rimovibili + installa da file).
  L'installazione passa SEMPRE dalla carta di conferma
  (`PackInstallOverlay.qml`): nome, autore, contenuti, avviso sui
  duplicati — mostrare, mai far approvare. Il drop di un `.ivepack`
  sulla finestra arriva alla stessa carta.
- **Azioni**: `pack.create`, `pack.install`, `pack.remove`.
- Moduli: `ive/packs/` (core, senza Qt), `ive/ui/pack_service.py`
  (bridge QML, singleton `Packs`).

Test: `tests/test_packs.py` (build coi file dentro, preview coi
duplicati, install/remove con i cataloghi che guadagnano e perdono,
zip-slip, servizio), `tests/visual/test_packs_panel.py` (pannello
reale: spunte, contatori, preferiti, export, carta di conferma
cliccata, cestino).

---

## 1. Due sistemi diversi, non confonderli

| | **Content Pack** | **Plugin di codice** |
|---|---|---|
| Cosa contiene | JSON + file media | Python |
| Chi lo puo' fare | chiunque, anche senza programmare | sviluppatori |
| Sicurezza | **nessun codice eseguito** → installazione sicura | richiede fiducia |
| Installazione | trascina il file nella finestra | conferma esplicita + avviso |
| Distribuzione | un singolo file `.ivepack` | vedi `ARCHITECTURE.md` §7 |
| Documento | questo | `ARCHITECTURE.md` §7 |

**Perche' separarli.** Se musiche e animazioni passassero dal sistema di
plugin, ogni pacchetto di musica sarebbe potenzialmente codice eseguibile: la
comunita' non potrebbe scambiarseli con leggerezza. Tenendoli dichiarativi,
un content pack e' un archivio di dati inerti — al massimo puo' essere brutto,
non pericoloso. E' questo che rende praticabile lo scambio informale fra
utenti.

Il 90% di quello che un utente vuole condividere e' un content pack.

---

## 2. Formato del pacchetto

Un content pack e' una cartella; distribuito e' uno **zip rinominato
`.ivepack`**.

```
my_pack.ivepack                        (zip)
└── musica_lofi/
    ├── pack.json                      manifest — obbligatorio
    ├── LICENSE.txt                    obbligatorio se il contenuto ha una licenza
    ├── cover.png                      opzionale, 512x512, per la libreria
    ├── audio/
    │   ├── chill_01.ogg
    │   └── chill_02.ogg
    └── metadata/
        └── chill_01.json              bpm, mood, loop points, ...
```

**Installazione.** L'utente trascina il `.ivepack` nella finestra di IVE.
L'app mostra nome, autore, licenza e contenuto, chiede conferma, e scompatta
in `user_data/packs/<pack_id>/`.

**Disinstallazione.** Si cancella la cartella. Nient'altro. Nessun registro,
nessun residuo.

**Perche' uno zip e non una cartella nuda:** un file singolo si manda per
email, si carica ovunque, non si "sfilaccia" copiandolo, e ha un checksum
verificabile.

---

## 3. Manifest — `pack.json`

```json
{
  "schema_version": 1,
  "id": "com.mariorossi.lofi-vol1",
  "name": "Lo-Fi Beats Vol. 1",
  "version": "1.2.0",
  "author": "Mario Rossi",
  "url": "https://example.org/packs/lofi",
  "description_key": null,
  "description": {
    "en": "12 royalty-free lo-fi loops.",
    "it": "12 loop lo-fi royalty free."
  },
  "license": "CC-BY-4.0",
  "license_file": "LICENSE.txt",
  "attribution_required": true,
  "attribution_text": "Music by Mario Rossi (CC BY 4.0)",
  "cover": "cover.png",
  "tags": ["music", "lofi", "chill"],
  "min_app_version": "1.0.0",
  "contents": {
    "audio":             ["audio/*.ogg"],
    "animations":        [],
    "transitions":       [],
    "luts":              [],
    "fonts":             [],
    "overlays":          [],
    "templates":         [],
    "export_presets":    [],
    "canvas_presets":    []
  }
}
```

Regole:
- `id` in reverse-DNS, univoco, immutabile. E' la chiave di installazione.
- `license` **consigliata ma non obbligatoria**: identificatore SPDX
  (`CC-BY-4.0`, `CC0-1.0`, `MIT`, ...) o testo libero. Se assente vale
  `"Unspecified"` e il pack si installa comunque. E' un'informazione per chi
  usa il pack, **non un controllo**: l'app non fa da guardiano sui contenuti
  altrui (vedi `LICENSING.md` §0). I pack **ufficiali** che spediamo noi la
  dichiarano sempre.
- `description` e' un dizionario per lingua, non una stringa: i pack sono
  scritti dagli utenti, non passano dall'i18n dell'app.
- `min_app_version` evita che un pack che usa feature nuove venga installato
  su una versione vecchia.
- Un pack puo' contenere **piu' tipi** di contenuto insieme (es. un pack
  "Vlog Estate" con musiche + LUT + animazioni + template).

---

## 4. Tipi di contenuto

### 4.1 Audio (musica ed effetti sonori)

```
audio/traccia.ogg
metadata/traccia.json
```

```json
{
  "title": "Chill Sunrise",
  "artist": "Mario Rossi",
  "duration_ms": 138000,
  "bpm": 85,
  "key": "Am",
  "mood": ["calm", "warm"],
  "category": "music",
  "loop": { "enabled": true, "start_ms": 4000, "end_ms": 132000 },
  "beat_markers_ms": [0, 706, 1412, 2118]
}
```

- `category`: `music` | `sfx` | `ambience`.
- **`loop`**: se l'utente ha bisogno di 3 minuti e la traccia ne dura 2, l'app
  ripete l'intervallo di loop invece di tagliare bruscamente.
- **`beat_markers_ms`**: abilita lo snap dei tagli sul beat, che e' una delle
  cose che rende piacevole montare. Se assenti, l'app puo' calcolarli e
  cachearli.
- Formati: vedi `docs/MEDIA_FORMATS.md` §5. In sintesi: **OGG Vorbis o Opus**
  consigliati, FLAC per la qualita' massima, WAV per gli effetti brevi.

### 4.2 Animazioni in/out

Sono la funzione "animazione di ingresso e uscita" tipica degli editor
moderni. **Non sono video**: sono keyframe dichiarativi applicati ai
parametri della clip. Pesano pochi kB e funzionano su qualunque clip, di
qualunque durata e risoluzione.

```json
{
  "schema_version": 1,
  "id": "slide_in_left",
  "name": { "en": "Slide In Left", "it": "Entrata da sinistra" },
  "kind": "in",
  "default_duration_ms": 500,
  "min_duration_ms": 100,
  "max_duration_ms": 3000,
  "preview": "preview/slide_in_left.webp",
  "tracks": [
    {
      "parameter": "transform.position.x",
      "unit": "percent_of_width",
      "keyframes": [
        { "t": 0.0, "value": -100, "easing": "out_cubic" },
        { "t": 1.0, "value": 0 }
      ]
    },
    {
      "parameter": "opacity",
      "keyframes": [
        { "t": 0.0, "value": 0, "easing": "out_quad" },
        { "t": 0.6, "value": 100 }
      ]
    }
  ]
}
```

Regole:
- `t` e' **normalizzato 0→1** sulla durata dell'animazione, non in
  millisecondi: cosi' la stessa animazione funziona a 300 ms o a 2 s.
- `kind`: `in` (ancorata all'inizio della clip) | `out` (alla fine) |
  `loop` (per tutta la durata, es. pulsazione).
- Le unita' relative (`percent_of_width`, `percent_of_height`) rendono
  l'animazione indipendente dalla risoluzione: la stessa entrata funziona su
  un 4K orizzontale e su un verticale 9:16.
- `parameter` deve esistere nello schema dei parametri degli effetti
  (`effects/base.py`). Un parametro sconosciuto → animazione scartata con un
  WARNING chiaro, non un crash.
- Easing ammessi: `linear`, `in/out/in_out` × `quad`/`cubic`/`quart`/
  `expo`/`back`/`elastic`/`bounce`. Set chiuso e documentato.
- `preview` e' una clip WebP/APNG breve mostrata nella libreria — perche' un
  nome non basta a capire cosa fa un'animazione.

**Perche' cosi'.** Un'animazione fatta come file video sarebbe legata a una
risoluzione, a un frame rate e a una durata. Fatta come keyframe e'
riutilizzabile ovunque, editabile dall'utente e pesa 2 kB.

### 4.3 Transizioni

Due sottotipi:

**a) Transizioni parametriche** — usano un effetto di transizione gia'
presente nell'app con parametri predefiniti:
```json
{
  "id": "soft_zoom_blur",
  "base": "builtin.zoom_blur",
  "parameters": { "strength": 70, "direction": "in" },
  "default_duration_ms": 400
}
```

**b) Transizioni a matte (luma wipe)** — una sequenza in scala di grigi che
guida la dissolvenza: il nero passa prima, il bianco dopo. E' il modo classico
di creare wipe arbitrari senza scrivere shader.
```json
{
  "id": "ink_spread",
  "type": "luma_matte",
  "matte": "mattes/ink_spread.webm",
  "softness": 0.15,
  "default_duration_ms": 600
}
```

La matte va autorata a risoluzione contenuta (es. 1280 di lato lungo) e viene
scalata: e' una maschera, non contenuto visibile.

### 4.4 LUT (correzione colore)

```
luts/teal_orange.cube
luts/teal_orange.json
```
```json
{
  "id": "teal_orange",
  "name": { "en": "Teal & Orange" },
  "format": "cube_3d",
  "input_space":  "rec709",
  "output_space": "rec709",
  "intensity_default": 100,
  "preview": "preview/teal_orange.jpg"
}
```

- Formato: `.cube` (Adobe Cube), standard de-facto, testuale, supportato
  ovunque. Size 33x33x33 tipico.
- **`input_space` e `output_space` sono obbligatori.** Una LUT pensata per
  log applicata a materiale rec709 produce risultati sbagliati: dichiararli
  permette all'app di avvisare l'utente invece di fargli sballare i colori
  senza capire perche'.
- L'intensita' e' sempre regolabile 0-100%.

### 4.5 Font

```
fonts/MyFont-Regular.ttf
```
- I font dei pack **ufficiali** sono solo SIL OFL, Apache o equivalenti.
  Per i pack di terzi vale la regola generale: il campo `license` e'
  informativo, l'app non blocca nulla.
- I font di un pack sono caricati a runtime e disponibili nell'editor di
  testo, senza installarli nel sistema operativo.

### 4.6 Overlay e sticker

Elementi grafici sovrapposti, con trasparenza.

| Tipo | Formato | Uso |
|---|---|---|
| Statico | PNG, WebP | loghi, cornici, badge |
| Animato vettoriale | Lottie JSON | grafica animata leggera, scalabile |
| Animato raster | WebM/VP9 con alpha, APNG | effetti complessi, particellari |
| Sequenza | PNG sequence in cartella | massima qualita', molto pesante |

Consigliato: **Lottie** dove possibile (kB invece di MB, scala senza perdita),
**WebM/VP9 con alpha** per il resto (codec libero, alpha reale).

### 4.7 Template

Un progetto parziale riutilizzabile: struttura di tracce, testi segnaposto,
musica, animazioni e timing gia' impostati. L'utente sostituisce le proprie
clip nei segnaposto.

```json
{
  "id": "vlog_intro_15s",
  "name": { "en": "Vlog Intro 15s" },
  "canvas": "9x16_1080",
  "duration_ms": 15000,
  "slots": [
    { "id": "clip1", "type": "video", "start_ms": 0,    "duration_ms": 3000,
      "label": { "en": "Opening shot" } },
    { "id": "clip2", "type": "video", "start_ms": 3000, "duration_ms": 4000 },
    { "id": "title", "type": "text",  "default": { "en": "Your title here" } }
  ],
  "project": "template.iveproj"
}
```

Gli **slot** sono la parte importante: dicono all'utente cosa mettere e dove,
e permettono all'app di adattare la durata se la clip inserita e' piu' lunga
o piu' corta.

### 4.8 Export preset e canvas preset

Vedi `docs/EXPORT_PRESETS.md`. Sono content a tutti gli effetti: si
distribuiscono, si condividono e si mettono nei pack come tutto il resto.

---

## 5. Come l'app usa i pack

```
user_data/packs/
├── com.mariorossi.lofi-vol1/
├── com.tizio.transizioni-glitch/
└── com.ive.starter/              ← pack di base, installato al bootstrap
```

- All'avvio l'app scansiona la cartella e costruisce un indice in cache.
  Il tempo di avvio non deve dipendere dal numero di pack installati.
- Ogni tipo di contenuto confluisce nella libreria corrispondente
  (Musica / Animazioni / Transizioni / LUT / Testo / Template), con un filtro
  per pack di provenienza.
- **Contenuti built-in e contenuti da pack sono indistinguibili nell'uso.**
  Quello che spediamo di default e' semplicemente il pack `com.ive.starter`,
  costruito con lo stesso formato pubblico. Se il formato e' abbastanza buono
  per noi, e' abbastanza buono per la comunita' — e non puo' marcire, perche'
  lo usiamo per primi.

---

## 6. Progetti e pack mancanti

Problema reale: apro un progetto di un amico che usa una musica che non ho.

Regole:
- Il progetto salva `pack_id`, `version` e il path relativo di ogni risorsa
  usata da un pack.
- All'apertura, i contenuti mancanti sono elencati in un pannello **"Contenuti
  mancanti"** con nome, pack di origine e URL se dichiarato nel manifest.
- Il progetto **si apre lo stesso**: le clip che usano risorse mancanti sono
  marcate visivamente, tutto il resto e' editabile. Mai bloccare l'apertura.
- Opzione **"Raccogli risorse"** in export/salvataggio: copia tutte le
  risorse usate dentro la cartella del progetto, producendo un progetto
  autonomo e trasferibile. E' il modo consigliato per mandare un progetto a
  qualcun altro. La funzione copia e basta: non ispeziona le licenze e non
  chiede permessi (`LICENSING.md` §0).

---

## 7. Creare un pack

Deve essere possibile **senza saper programmare**. Due strade, entrambe
supportate:

1. **A mano.** Crea una cartella, scrivi `pack.json`, metti i file, zippa,
   rinomina in `.ivepack`. Il formato e' documentato e leggibile.
2. **Dall'app.** "Esporta come content pack": l'utente seleziona nella
   libreria le proprie animazioni, LUT, musiche o preset e l'app genera il
   `.ivepack` compilando il manifest da un form.

La seconda strada e' quella che fa crescere una comunita': la maggior parte
delle persone non aprira' mai un editor di testo. Va prevista in `ROADMAP.md`
come parte della fase, non come extra.

**Validazione.** Uno strumento (in-app e a riga di comando) verifica il pack
prima della distribuzione: manifest valido, file referenziati esistenti,
parametri delle animazioni riconosciuti, formati media supportati, preview
presenti. Serve a evitare pack rotti, **non a controllare i contenuti**.

Distinzione fra i due esiti:
- **Errore** (blocca l'esportazione del pack): il pack non funzionerebbe —
  JSON malformato, file mancanti, parametri inesistenti.
- **Avviso** (non blocca): licenza non dichiarata, preview assenti, metadati
  incompleti. Suggerimenti di qualita', ignorabili.

---

## 8. Licenze del contenuto

Distinzione netta, da tenere presente ogni volta che si tocca questo modulo
(quadro generale in `LICENSING.md` §0):

### I pack che spediamo noi — rigorosi

Musiche, LUT, font e template dei pack ufficiali sono **CC0, CC-BY o
equivalenti**, con provenienza verificata e licenza dichiarata. E' materiale
nostro ed e' giusto che sia pulito: chi scarica IVE deve poter usare quello
che trova dentro senza pensarci.

### I pack di terzi e i contenuti dell'utente — nessun controllo

**IVE e' uno strumento, non un guardiano.**

- Un pack senza `license` **si installa lo stesso**. Il campo e'
  informativo.
- L'app **non verifica** la provenienza di nulla: ne' dei pack, ne' dei media
  importati, ne' di quello che l'utente esporta.
- Nessuna telemetria, nessun fingerprinting, nessun avviso moralistico.
- La schermata di installazione **mostra** autore, licenza e contenuto perche'
  e' utile saperlo, non per far approvare qualcosa.

### Attribuzione — una comodita', mai un obbligo

Se un pack dichiara `attribution_required`, l'app:
- mostra un piccolo badge nella libreria sulle risorse di quel pack;
- **offre** in export la generazione di un `credits.txt` con le attribuzioni
  delle risorse effettivamente usate.

Entrambe sono facilitazioni per chi vuole dare credito volentieri. Non sono
bloccanti, non sono invadenti, e non si ripetono a ogni export. L'utente puo'
disattivarle.

### Repository online

Un repository ufficiale di pack richiederebbe moderazione e dichiarazioni di
titolarita' da parte di chi carica: e' un impegno continuativo, non un
componente software. **Fuori scope per la 1.0**, che supporta lo scambio
diretto fra utenti — un file mandato a mano — e non richiede alcuna
infrastruttura.

---

## 9. Compatibilita' nel tempo

- Ogni formato di questo documento ha `schema_version`.
- Un pack con `schema_version` piu' recente dell'app: si installa lo stesso,
  gli elementi non comprensibili vengono ignorati con un avviso. **Mai
  rifiutare in blocco.**
- Non rimuoviamo mai un campo: si deprecano, restano leggibili.
- Le regole di migrazione stanno accanto a quelle dei progetti
  (`project_io/migrations.py`).

**Perche' e' importante.** I contenuti della comunita' sopravvivranno alle
versioni dell'app. Un pack fatto oggi deve funzionare fra cinque anni,
altrimenti la comunita' smette di produrne.

---

## 10. Checklist per un nuovo tipo di contenuto

1. [ ] E' davvero dichiarativo? Se serve codice, e' un plugin, non un pack
2. [ ] Ha uno schema JSON documentato in questo file, con `schema_version`
3. [ ] Le grandezze sono relative (percentuali, tempo normalizzato), non in
       pixel o millisecondi assoluti
4. [ ] Ha una preview visiva
5. [ ] Il validatore lo verifica
6. [ ] La libreria in UI ha una sezione con ricerca e filtri
7. [ ] Il pack starter che spediamo lo usa
8. [ ] Il tracking delle risorse mancanti (§6) lo copre
9. [ ] Degrada in modo pulito se la versione dello schema e' piu' nuova
