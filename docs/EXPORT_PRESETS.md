# IVE — Canvas ed Export Preset

Due cose distinte che vengono spesso confuse:

| | **Canvas preset** | **Export preset** |
|---|---|---|
| Cosa definisce | la forma del progetto: 16:9, 9:16, 1:1... | come si scrive il file finale |
| Quando si sceglie | alla creazione del progetto | al momento dell'export |
| Cambia il montaggio? | si', tutte le inquadrature | no, mai |
| Esempio | "Verticale 1080x1920" | "YouTube 1080p" |

Entrambi sono **file JSON**, condivisibili, e possono stare in un content
pack (`docs/CONTENT_PACKS.md`).

---

## 1. Canvas preset

```json
{
  "schema_version": 1,
  "id": "9x16_1080",
  "name": { "en": "Vertical 1080x1920", "it": "Verticale 1080x1920" },
  "width": 1080,
  "height": 1920,
  "aspect": "9:16",
  "fps": 30,
  "sample_rate": 48000,
  "background": "#000000",
  "tags": ["social", "vertical", "reels", "shorts", "tiktok"]
}
```

Set di base incluso:

| id | Risoluzione | Rapporto | Uso tipico |
|---|---|---|---|
| `16x9_1080` | 1920x1080 | 16:9 | standard, YouTube, TV |
| `16x9_4k` | 3840x2160 | 16:9 | 4K |
| `9x16_1080` | 1080x1920 | 9:16 | Reels, Shorts, TikTok, Stories |
| `1x1_1080` | 1080x1080 | 1:1 | feed quadrato |
| `4x5_1080` | 1080x1350 | 4:5 | feed verticale Instagram |
| `4x3_1080` | 1440x1080 | 4:3 | materiale d'archivio |
| `21x9_1080` | 2560x1080 | 21:9 | cinematografico |

### Cambiare rapporto a montaggio iniziato

Caso frequentissimo: montato in 16:9, serve anche la versione verticale.
Va gestito bene, perche' e' uno dei momenti in cui un editor sembra
intelligente o stupido.

Al cambio di canvas, per ogni clip si applica una strategia scelta
dall'utente:

| Strategia | Comportamento |
|---|---|
| **Fit** | l'inquadratura intera entra, con bande |
| **Fill** | riempie il fotogramma, tagliando i bordi (default) |
| **Fill + riquadro** | come Fill, ma con inquadratura riposizionabile per clip |
| **Sfondo sfocato** | Fit, con l'immagine sfocata e ingrandita a riempire le bande |
| **Nessuna** | mantiene la trasformazione esistente |

Regole ferree:
- **L'operazione e' annullabile con un solo Ctrl+Z.**
- Le trasformazioni originali sono conservate: tornare a 16:9 ripristina lo
  stato precedente, non ricalcola.
- Testi e overlay usano posizioni relative (percentuali), quindi non escono
  dal fotogramma cambiando rapporto. E' il motivo per cui in
  `CONTENT_PACKS.md` le unita' sono relative.
- Le clip che diventano molto tagliate sono **segnalate** all'utente, che
  puo' riposizionarle una per una.

---

## 2. Export preset

**Stato (2026-08-20): catalogo JSON implementato.** I preset di
fabbrica stanno in `ive/config/defaults/export_presets/social.json`,
quelli dell'utente in `user_data/export_presets/*.json`, e i pack li
portano in `export_presets/presets.json` (`ive/export/presets.py`:
`list_presets`, `preset_by_id`, `reload`; il servizio `Export` espone
`presets`/`platforms` con notify e `refresh()`, chiamato dal servizio
pack dopo install/remove). La forma implementata e' il sottoinsieme
qui sotto effettivamente usato dall'export di oggi — `container`,
`video.{codec,width,height,fps,bitrate_kbps}`,
`audio.{codec,bitrate_kbps}`, `constraints`, `platform`, `note`; i
campi aggiuntivi dello schema completo (rate control, loudness,
faststart...) sono accettati e ignorati finche' l'export non li
implementa. Regole del loader: container o codec sconosciuti → preset
saltato con warning (meglio una card in meno di un export che non
parte); `platform` sconosciuta → raccolto sotto «Other» nella riga
delle piattaforme, che appare solo se serve; id duplicato → ignorato,
mai sovrascritto (fabbrica > utente > pack).

```json
{
  "schema_version": 1,
  "id": "youtube_1080p",
  "name": { "en": "YouTube 1080p", "it": "YouTube 1080p" },
  "description": {
    "en": "Recommended settings for YouTube uploads at 1080p."
  },
  "icon": "youtube",
  "tags": ["youtube", "web", "1080p"],

  "video": {
    "codec": "h264",
    "profile": "high",
    "width": 1920,
    "height": 1080,
    "fps": "source",
    "rate_control": "vbr",
    "bitrate_kbps": 12000,
    "max_bitrate_kbps": 16000,
    "quality": null,
    "keyframe_interval_sec": 2,
    "bit_depth": 8,
    "color": { "primaries": "bt709", "transfer": "bt709", "matrix": "bt709",
               "range": "limited" },
    "scaling": "lanczos",
    "prefer_hardware": true
  },

  "audio": {
    "codec": "aac",
    "bitrate_kbps": 384,
    "sample_rate": 48000,
    "channels": 2,
    "loudness_target_lufs": -14,
    "true_peak_db": -1.0
  },

  "container": "mp4",
  "faststart": true,

  "subtitles": { "mode": "burn_in" },

  "constraints": {
    "max_duration_sec": null,
    "max_filesize_mb": null,
    "recommended_aspect": ["16:9"]
  },

  "metadata": { "write_credits_file": true }
}
```

### Campi che meritano una spiegazione

- **`codec: "h264"` e' logico, non un encoder.** L'app sceglie
  `h264_nvenc`, `h264_qsv`, `h264_videotoolbox` o `libx264` in base
  all'hardware. E' cio' che rende un preset condiviso funzionante sulla
  macchina di chiunque, anche con GPU diversa.
- **`fps: "source"`** eredita dal progetto; oppure un numero fisso.
- **`rate_control`**: `vbr` (bitrate variabile, default per il web), `cbr`
  (costante, per lo streaming), `crf` (qualita' costante — in quel caso si
  usa `quality` invece di `bitrate_kbps`; e' il modo migliore per
  l'archiviazione, perche' il peso si adatta alla complessita').
- **`keyframe_interval_sec: 2`**: le piattaforme web lo richiedono per
  permettere il seek fluido allo spettatore.
- **`faststart`**: sposta l'indice all'inizio del file, cosi' la
  riproduzione web parte senza scaricare tutto. Sempre `true` per i preset
  web; e' un dettaglio che quasi nessun editor gratuito imposta.
- **`loudness_target_lufs`**: le piattaforme normalizzano l'audio in
  automatico. Consegnare gia' al target giusto evita che il video suoni
  compresso o troppo basso rispetto agli altri.
- **`constraints`**: puramente informativo, serve a **avvisare** l'utente
  (es. durata massima di una Storia), non a bloccarlo.

### Preset inclusi (set di partenza)

| id | Target |
|---|---|
| `youtube_1080p`, `youtube_4k` | YouTube orizzontale |
| `youtube_shorts` | 9:16, ≤60s |
| `instagram_feed`, `instagram_reels`, `instagram_stories` | 1:1 / 4:5 / 9:16 |
| `tiktok` | 9:16 |
| `linkedin` | 16:9, bitrate contenuto |
| `facebook`, `x_twitter` | 16:9 |
| `whatsapp` | file leggero, alta compatibilita' |
| `web_small` | H.264 leggero per sito |
| `web_vp9` | WebM/VP9, alpha disponibile |
| `archive_master` | H.265 CRF alta qualita', per conservare |
| `prores_master` | ProRes 422 HQ, per passare a un altro editor |
| `gif_short` | GIF ottimizzata |
| `audio_only` | estrazione traccia audio |

### Presentazione nel dialog di export (deciso 2026-08-09)

La tab **Social** non elenca i preset in piatto: mostra **una riga di icone
di piattaforma** (YouTube, Instagram, TikTok, LinkedIn, Facebook, WhatsApp)
e toccarne una rivela i preset di quella piattaforma. Ogni preset dichiara
il campo `platform`, che punta a una voce di `PLATFORMS`
(`ive/src/ive/export/presets.py`); l'icona e' **monocromatica in stile
outline Lucide**, disegnata in `Icons.qml` come path 24x24 — mai asset di
brand a colori, cosi' segue il tema come ogni altro glifo.

Entrambe le tab hanno il campo **Nome del file** (vuoto = nome automatico
`<sorgente>_<preset>`); il nome digitato viene ripulito da caratteri
illegali e da un'eventuale estensione, e non sovrascrive mai un file
esistente (suffisso `_N`).

La tab **Personalizzato** ha un selettore di **proporzioni**
(16:9, 9:16, 4:3, 1:1, 21:9) con una scala di risoluzioni per proporzione
(720p / 1080p / 4K); cambiare proporzione conserva il livello e rimodella
solo il fotogramma. Nota: le risoluzioni "21:9" sono lo standard ultrawide
reale 64:27 (2560x1080, 5120x2160), non il 2.33 letterale dell'etichetta.

> **Attenzione a un rischio reale:** i requisiti delle piattaforme cambiano.
> Un preset "Instagram" del 2024 puo' essere sbagliato nel 2027. Per questo
> ogni preset ha `schema_version` e i preset di piattaforma vengono
> aggiornati con l'app. **Non sono cablati nel codice**: sono file JSON in
> `ive/config/defaults/export_presets/`, aggiornabili anche via content pack
> senza attendere una release.

---

## 3. Preset personalizzati e condivisione

Requisito esplicito: i preset devono passare facilmente da un utente
all'altro.

- Un preset creato dall'utente si salva in
  `user_data/settings/export_presets/<id>.json`.
- **"Esporta preset"** produce un `.json` singolo, leggibile e modificabile
  con un editor di testo.
- **Importare** = trascinare il `.json` nella finestra, oppure metterlo nella
  cartella. Nessun installer, nessun formato binario.
- Piu' preset insieme possono essere raccolti in un `.ivepack`
  (`CONTENT_PACKS.md`) con nome, autore e descrizione.
- Un preset utente non sovrascrive mai uno di sistema: se l'id coincide, si
  crea una variante (`youtube_1080p_custom`) e si avvisa.
- Il dialog di export distingue visivamente i preset di sistema, quelli
  dell'utente e quelli provenienti da pack.

**Perche' JSON semplice e non un formato proprietario.** Un preset deve
poter essere aperto, letto, capito e corretto da chiunque, anche a distanza
di anni e anche senza l'applicazione. E' esattamente cio' che manca negli
editor commerciali.

---

## 4. Comportamento all'export

1. L'utente sceglie un preset (o parte da uno e modifica alcuni campi).
2. L'app **valida** contro il progetto e avvisa se qualcosa non torna:
   - rapporto del canvas diverso da `recommended_aspect`
   - durata oltre `max_duration_sec`
   - **alpha richiesta ma il codec non la supporta** (H.264 non ha alpha)
   - progetto HDR con preset SDR → verra' applicato tone mapping
   - upscaling rispetto alla risoluzione del canvas (di solito non voluto)
3. Mostra **una stima** di dimensione e durata prima di partire.
4. L'export gira come Job: progresso, tempo residuo, cancellazione pulita.
   Si continua a montare mentre esporta.
5. A fine export: dimensione reale, percorso, encoder effettivamente usato,
   e — se ci sono risorse con attribuzione richiesta — l'offerta di generare
   `credits.txt`.
6. Un export fallito **non lascia un file parziale** spacciato per buono:
   si scrive su file temporaneo e si rinomina solo al termine.

**Coda di export.** Piu' export in fila (es. lo stesso montaggio per YouTube,
Reels e LinkedIn) con preset diversi, eseguiti in sequenza. E' il caso d'uso
piu' frequente per chi pubblica su piu' piattaforme, e va previsto dal
principio, non aggiunto dopo.

---

## 5. Checklist per un nuovo preset

1. [ ] Ha `schema_version`, `id` univoco e nome tradotto
2. [ ] Usa un codec **logico**, non un encoder specifico
3. [ ] Il contenitore supporta i codec scelti (e l'alpha, se richiesta)
4. [ ] Target di loudness dichiarato
5. [ ] `faststart` attivo per i preset web
6. [ ] `constraints` compilati se la piattaforma ha limiti
7. [ ] Testato: file prodotto, riprodotto, e caricato davvero sulla
       piattaforma di destinazione
8. [ ] Aggiunto alla tabella di §2 se e' un preset di sistema
