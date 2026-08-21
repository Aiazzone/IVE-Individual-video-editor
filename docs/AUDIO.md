# IVE — Audio: effetti, dissolvenze, pannello, musiche

Implementato il 2026-08-20 (passo «1 + 2» deciso con l'utente: pannello
Audio + effetti come ricette JSON). Segue la stessa strada di colori,
motion e transizioni: **dati dichiarativi, mai codice**, condivisibili
nei pack.

## 1. Cosa fa l'audio oggi

- Riproduzione con A/V sync guidato dal clock audio; export con lo
  stesso mix del preview (`docs/ENGINE.md` §2.3: audio e video sullo
  stesso grafo, stack pigri separati).
- Per clip: **volume**, **mute** (stato, non volume zero), rimuovi/
  ripristina l'audio di un video, clip musicali (solo audio).
- **Dissolvenze** in entrata/uscita per clip (`fade_in`/`fade_out` in
  secondi sul `TimelineClip`, max meta' clip): nel grafo sono
  `AudioRamp` equal-power, le stesse delle transizioni. Lo split lascia
  la fade-in alla testa e la fade-out alla coda.
- **Effetti audio** per clip (`audio_effect_id`): una ricetta di ops.

## 2. La ricetta

```json
{
  "schema_version": 1,
  "id": "voice_clear",
  "name": {"en": "Clear voice", "it": "Voce chiara"},
  "section": "voice",
  "ops": [
    {"op": "highpass", "hz": 90},
    {"op": "peak", "hz": 3000, "q": 1.0, "db": 3},
    {"op": "compressor", "threshold_db": -20, "ratio": 3, "makeup_db": 3},
    {"op": "limiter", "ceiling_db": -1}
  ]
}
```

Vocabolario (`ive/audio/dsp.py`, tutti i parametri opzionali):

| op | parametri | a cosa serve |
|---|---|---|
| `gain` | `db` | livello |
| `highpass` / `lowpass` | `hz`, `q` | rimbombi / fruscio, effetto telefono |
| `low_shelf` / `high_shelf` | `hz`, `db` | calore / aria |
| `peak` | `hz`, `q`, `db` | presenza, una risonanza |
| `compressor` | `threshold_db`, `ratio`, `attack_ms`, `release_ms`, `makeup_db` | uniforma il livello |
| `loudness` | `target_db`, `max_gain_db` | porta l'RMS a un target, lentamente (normalizzazione) |
| `limiter` | `ceiling_db` | niente sopra il tetto |

I filtri sono biquad RBJ (`scipy.signal.lfilter` con `zi`), la dinamica
un inviluppo a un polo per sotto-blocchi di 1 ms. **Lo stato vive tra i
frame**: la `AudioChain` si azzera solo quando le posizioni smettono di
essere consecutive (seek), cosi' nessun click ai confini di frame e
nessun "pompaggio" a freddo a meta' clip. `loudness` e' un'AGC lenta
sull'RMS degli ultimi ~3 s, NON un LUFS integrato (servirebbe tutto il
programma in anticipo): onesta come «normalizza», non come «misura EBU
R128». Op sconosciuta → saltata con un warning, mai un crash.

Cataloghi: fabbrica `ive/config/defaults/audio_effects/` (15 ricette in
4 sezioni: voice, music, clean, fx), utente `user_data/audio_effects/`,
pack `audio_effects/effects.json`. Sezioni sconosciute portate da un
pack vanno in coda in ordine alfabetico.

## 3. Nel motore

Il transport risolve `audio_effect_id` in **ops pure** nel `_Segment`
(`audio_ops`), insieme a `fade_in`/`fade_out`; `sequence_clips()` le
passa all'export, cosi' il grafo e il worker non conoscono il catalogo
(stesso principio degli effetti colore). Il builder attacca per ENTRY,
dopo il `Gain` del volume: `AudioEffect(ops)` e poi le `AudioRamp`
delle dissolvenze — la ricetta modella il suono, le dissolvenze scalano
quello che ne esce. Anteprima ed export identici per costruzione.

## 4. UI

- **Pannello Audio** (`AudioContent.qml`, singleton `AudioFx`): si apre
  toccando sulla timeline la corsia audio (o video) di un clip con
  suono. Sopra: nome del clip, volume + mute, dissolvenza in entrata e
  in uscita (slider con commit al rilascio: ogni commit ricostruisce il
  grafo). Sotto: «Come registrato» + card degli effetti per famiglia,
  Preferiti in cima (stella sulla card, `audio.favorites`). Un tocco
  applica = un passo di undo.
- **Dissolvenze sulla timeline** (2026-08-20, su richiesta utente): con
  un clip audio o musica selezionato il toolbox della timeline mostra
  due slider «Dissolvenza in entrata / in uscita» (0 → meta' clip, max
  10 s, commit al rilascio); il clip disegna un'**ombra scura** sulla
  forma d'onda che sale alla testa e scende alla coda (`Shape` con
  curva quadratica ≈ la rampa equal-power del motore), larga quanto la
  dissolvenza allo zoom corrente — il tempo si legge a occhio.
  Trappola test: ogni delegate di clip possiede un waveBox (nascosto
  senza onda) → cercare `fade_in_shade` DENTRO il delegate A1, non in
  tutta la timeline. Test: `tests/visual/test_fade_ui.py`.
- Azioni: `timeline.set_clip_audio_effect`, `timeline.set_clip_fades`,
  `audio.toggle_favorite`. I comandi del toolbox (volume/mute) restano.
- Pack: categoria «Effetti audio» nella creazione, contata nella carta
  di conferma e negli installati.

Test: `tests/test_audio_effects.py` (numeri su toni noti per ogni op,
stato tra frame e reset al seek, catalogo, modello+undo+split,
transport → ops pure, grafo: -12 dB a meta' clip e code silenziose con
le dissolvenze), `tests/visual/test_audio_panel.py` (tap sulla corsia
A1 → pannello, card che applica con un undo, stella, slider che
committa la dissolvenza, «Come registrato»).

## 5. Musiche — libreria e corsia Music (implementato il 2026-08-20)

**Corsia Music = track 4 del modello** (`Project.MUSIC_TRACK`): clip
solo-audio posati LIBERAMENTE sotto il montaggio (si sovrappongono alla
V1 per costruzione, mai riflow). Nel transport NON sono segmenti ma
`music_spans`; il builder li mette su playlist `M1, M2...` (video=False,
audio=True — una playlist in piu' per ogni sovrapposizione), con Gain,
`AudioEffect`, `AudioRamp` per entry, e **clampa la durata alla
sequenza**: la musica non allunga mai il montaggio. Il tractor somma
l'audio di tutte le tracce.

- **Libreria** (`ive/music/library.py`): i pack portano
  `music/tracks.json` + `music/files/`; `user_data/music/` e' la cartella
  personale (ogni file audio = un brano, categoria `mine`, sidecar
  `.json` opzionale). Campi del brano: titolo per lingua, artista,
  categoria, tag, bpm, `vocals`, durata, licenza SPDX + URL + riga di
  attribuzione (informativi, mai bloccanti).
- **Servizio `Music`** (`ui/music_service.py`): categorie, brani,
  preferiti (`music.favorites`), **anteprima** con QMediaPlayer
  indipendente dal transport (lo mette in pausa; piazzare ferma
  l'anteprima).
- **UI**: tab «Musica» nel pannello Audio — chip per categoria, switch
  «Ripeti fino alla fine del montaggio», righe con play/stella/+.
  `+` = `timeline.place_music` al cursore: il file entra nel pool se
  manca (una sola probe) e con `cover` si ripete back-to-back fino alla
  fine della V1 — un solo passo di undo per tutto. Tap su un clip della
  corsia Music apre il pannello Audio (tab Clip: volume, dissolvenze,
  effetti valgono anche qui).
- **Pack**: categoria «Musiche» (file copiati dentro), contata ovunque.
  **Limite noto (Windows)**: rimuovere un pack musicale mentre un suo
  brano e' sulla timeline aperta (decoder del transport) o in anteprima
  fallisce per file bloccato: `remove_pack` ora lo dice nel log e
  ritorna False invece di lasciare residui; un residuo senza
  `pack.json` viene comunque ripulito al tentativo successivo.
  `Music.refresh()` ferma l'anteprima e rilascia il file.
- **Pack ufficiale «Business music»**: `build_scripts/make_music_pack.py`
  scarica 9 brani strumentali di Kevin MacLeod (incompetech.com,
  **CC BY 4.0**), compila licenza/attribuzione per brano e produce
  `packs_out/ive-music-business.ivepack` (~61 MB, NON in git: lo script
  e' la sorgente). Installato nell'user_data dell'utente il 2026-08-20.

Test: `tests/test_music.py` (libreria da pack sandbox + cartella utente,
piazzamento singolo e a copertura con undo che toglie anche il pool,
transport → span, grafo che mixa la musica solo sul suo tratto senza
allungare la sequenza), `tests/visual/test_music_panel.py` (tab, chip,
anteprima, + con copertura → corsia Music con due pezzi).

### 5.1 Le regole decise per le musiche (valgono per i prossimi pack)

Rispettando `CLAUDE.md` §4.9 (rigore su cio' che spediamo NOI, nessun
controllo su cio' che l'utente importa):

1. **Formato = content pack** (`CONTENT_PACKS.md` §4.1): `audio/*.ogg` +
   `metadata/<brano>.json` con titolo, autore, **licenza SPDX**, URL
   della fonte, testo di attribuzione, BPM, durata, tag/categoria
   (`business`, `ambient`, `upbeat`, `cinematic`, ...), `vocals: false`.
   Un pack per categoria, installabile/rimovibile come gli altri.
2. **Fonti lecite per i pack ufficiali** (solo licenze che permettono
   redistribuzione e uso commerciale): CC0 e CC-BY 4.0 (Free Music
   Archive con filtro licenza, Incompetech / Kevin MacLeod CC-BY,
   ccMixter CC-BY). **Non** impacchettabili da noi: Pixabay Music (la
   licenza vieta la ridistribuzione del file fuori da un'opera → si puo'
   solo linkare), YouTube Audio Library (uso solo su YouTube), Bensound /
   Mixkit (licenze proprie con limiti: verificare brano per brano). Ogni
   brano CC-BY porta l'attribuzione nel metadata e l'app **offre** il
   `credits.txt` all'export (mai imposto).
3. **Pannello Musica** (tab nel pannello Audio): categorie → lista brani
   con durata/BPM, **anteprima** (solo audio via il grafo, senza toccare
   la timeline), preferiti, drag sulla corsia A1 (diventa una clip
   solo-audio, gia' supportata) con **loop** opzionale per coprire la
   durata del montaggio.
4. **Libreria personale**: `user_data/music/` scansionata come il resto;
   l'utente ci mette i suoi mp3/ogg/wav e li vede nel pannello senza
   passare da un pack.
5. Dopo: **ducking** automatico (abbassa la musica quando c'e' parlato:
   compressore + VAD) e beat marker per tagliare a tempo.
