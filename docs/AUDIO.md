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

## 5. Musiche (prossimo passo, deciso in discussione)

L'utente vuole una libreria di brani come CapCut, divisa per categoria,
con musiche **senza voce** per video tecnici / "business".

Come si fa, rispettando `CLAUDE.md` §4.9 (rigore su cio' che spediamo
NOI, nessun controllo su cio' che l'utente importa):

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
