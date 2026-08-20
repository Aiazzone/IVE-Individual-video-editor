# IVE — Immersive Shell

Specifica del guscio dell'interfaccia: come sono disposti video, timeline,
toolbar e pannelli. E' il documento che definisce **l'identita' visiva del
progetto** e la sua differenza rispetto a ogni altro editor video.

Il design system (colori, componenti, tipografia) sta in
`docs/UI_STYLE_GUIDE.md`. Qui c'e' la struttura.

---

## 1. Il principio

**Il video occupa tutto. Tutto il resto galleggia sopra, in vetro.**

Gli editor video tradizionali — Premiere, DaVinci, Kdenlive, Shotcut —
dividono la finestra in riquadri affiancati: browser a sinistra, preview al
centro, inspector a destra, timeline sotto. Il risultato e' che il video, cioe'
l'unica cosa che conta davvero, occupa spesso meno di un terzo dello schermo.

IVE ribalta questo rapporto:

- il video riempie la finestra, dal primo all'ultimo pixel;
- la timeline e' una lastra di vetro semitrasparente appoggiata in basso, larga
  quanto tutta la finestra;
- gli strumenti sono una barra di sole icone a sinistra, anch'essa in vetro;
- effetti, audio, colore e impostazioni appaiono in **un unico pannello
  fluttuante** a destra, che si ritira in un quadratino quando non serve;
- l'app parte a schermo intero.

Nessun riquadro. Nessun bordo. Nessuna cornice grigia. Solo il video e ciò che
serve in quel momento.

---

## 2. Anatomia — ordine dei livelli

Dal fondo alla superficie:

```
┌─────────────────────────────────────────────────────────────────┐
│ 6  Dialog modali                          (sopra tutto)          │
│ 5  Pannello fluttuante                    lato, tinta piena      │
│ 4  Tool rail                              lato, vetro icone      │
│ 3  Timeline                               basso, vetro testo     │
│ 2  Comandi riproduzione                   centro video, a hover  │
│ 2  Tempo e volume                         angolo, senza lastra   │
│ 1  Video + maniglie di trasformazione     centrato, intero       │
│ 0  Ambient backdrop                       fotogramma sfocato     │
└─────────────────────────────────────────────────────────────────┘
```

```
╔═════════════════════════════════════════════════════════════════╗
║▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ ambient backdrop (sfocato) ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒║
║┌──┐▒▒┌───────────────────────────────────────┐▒▒▒▒▒▒▒▒▒┌──────┐║
║│▣ │▒▒│                                       │▒▒▒▒▒▒▒▒▒│ VIDEO│║
║│▣ │▒▒│                                       │▒▒▒▒▒▒▒▒▒│ AUDIO│║
║│▣ │▒▒│          VIDEO — INTERO               │▒▒▒▒▒▒▒▒▒│ ───○ │║
║│▣ │▒▒│                                       │▒▒▒▒▒▒▒▒▒│ [EQ] │║
║│▣ │▒▒│                                       │▒▒▒▒▒▒▒▒▒│      │║
║│⚙ │▒▒└───────────────────────────────────────┘▒▒▒▒▒▒▒▒▒└──────┘║
║└──┘▒▒▒▒▒▒▒▒  ◁ ▷ ‖ ▶ ▷▷   00:03:15:22  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒║
╟─────────────────────────────────────────────────────────────────╢
║ ░ 00:00    00:05    00:10    00:15    00:20    00:25    00:30 ░ ║
║ ░ ▪▪ ┃ ▐███████▌   ▐████▌         ▐██████████████▌          ░ ║
║ ░ ▪▪ ┃    ▐████████████▌  ▐█████▌      ▐███████████████▌     ░ ║
║ ░ ▪▪ ┃  ▐∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿▌         ░ ║
╚═════════════════════════════════════════════════════════════════╝
   ↑ tool rail        ↑ timeline in vetro, larga quanto la finestra
```

---

## 3. Ambient backdrop

Il fotogramma corrente viene disegnato **due volte**:

1. **Sotto**, ingrandito fino a coprire tutta la finestra, sfocato e scurito.
   E' lo sfondo.
2. **Sopra**, scalato per stare **interamente** nell'area libera, nitido. E' il
   video che l'utente sta montando.

**Perche'.** Senza questo, la timeline coprirebbe la parte bassa del
fotogramma — esattamente dove vivono sottotitoli, loghi e watermark. Montare
sottotitoli senza vederli e' inaccettabile. L'ambient backdrop da' l'effetto
immersivo a tutto schermo **e** garantisce che il fotogramma sia sempre
visibile per intero.

Specifica:
- La sorgente e' lo **stesso frame gia' decodificato**: nessun decode
  aggiuntivo, nessun costo di I/O.
- Ingrandimento: `cover` sull'intera finestra, poi sfocatura ampia
  (`backdropBlurRadius`) e scurimento (`backdropDim`, default 45%).
- Aggiornamento a bassa frequenza (vedi §8): lo sfondo e' sfocato, nessuno
  nota che non e' sincronizzato al fotogramma.
- Se la clip ha zone trasparenti, sotto c'e' il colore del canvas del
  progetto, non il backdrop.
- **Disattivabile** dai settings: chi preferisce lo sfondo nero pieno lo
  sceglie, e su hardware debole e' anche piu' veloce.

### Area libera

Il video nitido viene inscritto nel rettangolo **non coperto** da timeline,
tool rail e pannello fluttuante, meno un margine di respiro (`space5`).

**Forma dell'item video** (`Playback.viewAspect`, deciso 2026-08-09):
- **Canvas esplicito** (16:9, 9:16, ...): l'item ha la forma del canvas,
  bande comprese — l'utente ha scelto l'inquadratura e nasconderla
  mentirebbe sull'export.
- **Canvas "auto"**: l'item ha la forma del **clip corrente** al playhead.
  Il compositore produce comunque il canvas della sequenza (bande nere
  cotte); il `PreviewItem` con `fillMode: "cover"` lo centro-ritaglia alla
  forma del clip, eliminando **esattamente** le bande cotte e mai un pixel
  di immagine (il clip e' inscritto e centrato nel canvas). Cosi' un clip
  9:16 in una timeline 16:9 sta in verticale con l'ambient ai lati, invece
  del "muro nero alto quanto il video" (bug segnalato su progetto reale).
  Al passaggio di confine la forma cambia con l'animazione `durNormal`.
- Con canvas esplicito le due forme coincidono e `cover` equivale a `fit`:
  niente viene mai ritagliato.

Quando il pannello fluttuante si espande o la timeline si allarga, l'area
libera si restringe e il video si riscala con un'animazione `durNormal`.
Il video non salta mai bruscamente.

### Sfondo quando non c'e' un progetto — onde shader (riscritte 2026-08-09)

Le onde della schermata di riposo sono un **fragment shader**
(`shell/shaders/waves.frag`, compilato in `.qsb` accanto con
`pyside6-qsb --glsl "300 es,330" --hlsl 50 --msl 12`): niente geometria,
ogni pixel valuta pochi seni stratificati sulla GPU — lisce quanto lo
schermo, nessun segmento possibile (la PathPolyline a 48 punti si vedeva
a spezzoni). Cresta = esponenziale stretto attorno alla curva, corpo =
esponenziale unilaterale che sfuma in giu'; il `time` cresce per sempre e
i seni lo avvolgono: **animazione infinita, mai un riavvio** (tecnica del
wave_widget HMI). La CPU tocca un solo float a tick (Timer 30fps, fermo
con riduci-animazioni o quando non in vista). **Colori FISSI, non a tema
(2026-08-11)**: le onde sono l'immagine d'apertura dell'app — la sua
identita', come quelle della PS4 — e il tema chiaro non deve ridipingerle
(riportato dall'utente: col tema chiaro cambiavano onde e sfondo). I
pannelli di vetro sopra seguono il tema; il palcoscenico no. Uniform
hardcoded in IdleBackdrop.qml: #232b3a → #12161f, nastri #31435f.
ATTENZIONE test: `grabWindow()` mentre lo shader sta ancora compilando si
e' bloccato una volta — il primo screenshot aspetta 2.5s.

### Sfondo in loop quando non c'e' un progetto (storico)

A progetto chiuso l'ambient backdrop non ha niente da sfocare, quindi al suo
posto va un breve clip in loop (`assets/backgrounds/idle_loop.mp4`), a tutta
finestra, ritagliato e velato pesantemente.

E' **decorazione, e va trattata come tale**: non deve costare nulla
all'editor.

- Si ferma nell'istante in cui si apre un file: da quel momento lo sfondo e' il
  fotogramma dell'utente.
- Si ferma a finestra non visibile.
- Il clip e' distribuito a **720p** e decodificato a **15 fps**: e' lento e
  velato, nessuno distingue la differenza, e il costo scende di conseguenza.
- Velatura `idleBackdropDim` = **0.82**. Sembra molto, ma un clip chiaro a
  velatura leggera prosciuga il contrasto di tutta l'interfaccia: lo sfondo si
  deve **sentire, non vedere**.
- Disattivabile (`appearance.idle_background`). Se il file manca o non si apre,
  lo sfondo e' semplicemente pieno: **niente dipende da questo clip**.
- Il loop e' un ritorno secco a zero. Se il clip non e' costruito per ripetersi
  senza stacco, lo stacco si vede a ogni ciclo: e' una proprieta' del clip da
  scegliere bene, non un difetto da correggere nel codice.

Cio' che spediamo noi deve avere provenienza tracciata:
`assets/backgrounds/SOURCES.md`.

### Modalita' alternativa

Un comando (`view.toggle_ambient`) commuta in **Full-bleed**: il video riempie
la finestra e la timeline lo copre. Piu' spettacolare, adatto alla revisione
finale piu' che al montaggio. **Ambient e' il default.**

---

## 4. Superfici in vetro

Timeline, tool rail e transport HUD sono **superfici in vetro**: sfocatura di
ciò che sta sotto, piu' una velatura scura.

```
GlassSurface = blur(contenuto sottostante) + scrim + bordo sottile
```

### Due livelli di scrim, non uno

Il testo bianco su un video puo' finire su un fotogramma bianco. La sfocatura
da sola **non garantisce** il contrasto: serve la velatura. Ma la soglia
dipende da **cosa contiene** la superficie, e usare ovunque il valore del
testo rende inutilmente opache le barre di sole icone.

| Contenuto della superficie | Soglia richiesta | Scrim minimo | Operativo |
|---|---|---|---|
| Testo secondario (`textMuted`) | 4.5:1 | 0.68 | **0.72** |
| Testo primario bianco | 4.5:1 | 0.55 | **0.62** |
| **Solo icone** (tratto ≥1.5px) | 3:1 | 0.42 | **0.45** |

I numeri sono calcolati sul caso peggiore, cioe' un fotogramma completamente
bianco:

- **0.55** → superficie di luminanza ≈0.17 → contro il bianco **4.7:1**,
  sopra la soglia di 4.5:1 fissata in `UI_STYLE_GUIDE.md` §8.
- **0.42** → superficie di luminanza ≈0.30 → contro il bianco **3.0:1**,
  la soglia per elementi grafici non testuali.

Applicazione:

| Superficie | Livello |
|---|---|
| Timeline (righello, nomi traccia, timecode) | `scrimText` |
| Tool rail | `scrimIcons` |
| Comandi di riproduzione | `scrimIcons` |
| Lettura tempo/volume | pillola `scrimIcons` — vedi §8-bis |

Le icone su vetro portano inoltre un'ombra proiettata
(`drop-shadow(0 1px 3px rgba(0,0,0,.85))`): non sostituisce lo scrim, ma
irrobustisce il bordo dell'icona sui contenuti chiari.

**Nessuna superficie puo' scendere sotto la propria soglia.** Se un'idea
grafica lo richiede, si cambia l'idea, non la soglia.

### Ripiego quando il vetro non e' disponibile

Tre livelli, nell'ordine:

1. **Supporto assente** — la piattaforma o il backend grafico non offre la
   sfocatura: le superfici passano a tinta piena (scrim 0.88-0.93), rilevato
   in automatico, senza che l'utente debba fare nulla.
2. **Prestazioni insufficienti** — se il preview perde fotogrammi con il
   vetro attivo, il degrado a tinta piena e' automatico, con una nota nel log.
3. **Scelta dell'utente** — impostazione `Effetti vetro: Auto | Sempre | Mai`,
   piu' `Riduci trasparenza` fra le opzioni di accessibilita'.

In tutti e tre i casi **cambia solo l'estetica: il layout resta identico**.
Nessuna posizione, dimensione o funzione dipende dalla disponibilita' del
vetro.

### Token (aggiunti a `Theme.qml`)

```qml
readonly property real  scrimText:           0.62   // superfici con testo
readonly property real  scrimTextSecondary:  0.72   // con testo muted
readonly property real  scrimIcons:          0.45   // superfici di sole icone
readonly property real  scrimSolidFallback:  0.92   // senza sfocatura
readonly property color glassTint:           "#0A0A0C"
readonly property int   glassBlurMax:        64   // portata del kernel, FISSA
readonly property int   glassBlurIntensity:  66   // 0-100, e' il valore utente
readonly property color glassBorder:         "#2EFFFFFF"  // 18% bianco
readonly property real  backdropDim:         0.45
readonly property int   backdropBlurRadius:  96
```

Il bordo e' un filo di bianco al 18% sul lato rivolto al video: separa la
lastra dallo sfondo senza disegnare una cornice.

### `autoPaddingEnabled: false` — obbligatorio su ogni `MultiEffect`

`MultiEffect.autoPaddingEnabled` vale **true** di default: Qt allarga da solo
l'item di `blurMax * blurMultiplier` per lato, per dare spazio alla sfocatura.
La documentazione avverte esplicitamente che applicandolo a uno sfondo intero
«the effect grows outside the window / screen».

E' la ragione per cui la sfocatura usciva dalle toolbar e dalla finestra. Una
maschera non basta a rimediare: la maschera copre l'item, il padding
automatico viene aggiunto dopo.

Regola: **ogni `MultiEffect` del progetto imposta `autoPaddingEnabled: false`**,
sorgente esattamente grande quanto la superficie, maschera per gli angoli
arrotondati (`maskThresholdMin: 0.5`, `maskSpreadAtMin: 1.0`, altrimenti il
bordo della maschera scaletta). Senza margine campionato i bordi sfocano un
filo meno; il contenimento vale piu' di quel filo.

Corollario sul token: `blurMax` e' la **portata** in pixel e resta costante;
cio' che l'utente regola e' `blur` (0-1), cioe' l'**intensita'**. Pilotare la
portata dallo slider faceva crescere anche l'ingombro dell'effetto, quindi la
fuoriuscita aumentava con il valore impostato.

Verifica: `tests/visual/test_blur_containment.py`. Il confronto a pixel da
solo **non basta** — attorno alle toolbar la scena e' un gradiente lieve e
sfocare un gradiente non cambia nulla di misurabile, quindi una fuga reale
passava inosservata. Il test controlla percio' anche la proprieta' direttamente
su tutti i `MultiEffect` dell'albero.

Fonte: [Qt Quick and Blurred Panels](https://www.qt.io/blog/qt-quick-and-blurred-panels),
[MultiEffect](https://doc.qt.io/qt-6/qml-qtquick-effects-multieffect.html).

---

## 5. Timeline

La lastra principale. Occupa **tutta la larghezza della finestra**, appoggiata
al bordo inferiore, senza margini laterali: e' un ripiano, non un riquadro
fluttuante.

```
┌───────────────────────────────────────────────────────────────┐
│ ⧉ ✂ ⟲ ⟳                                    ⊙ ▭ ─○─── ⤢ ✕     │  toolbar 32
├───────────────────────────────────────────────────────────────┤
│ 00:00      00:05      00:10   ┃   00:15      00:20      00:25 │  ruler 28
├───────────────────────────────┃───────────────────────────────┤
│ ▪ 👁 🔒 │  ▐████▌      ▐██████┃█▌                             │  V2
│ ▪ 👁 🔒 │      ▐███████████▌  ┃   ▐██████████████████▌        │  V1
│ ▪ 🔇 🔒 │   ▐∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿┃∿∿∿∿∿∿∿∿∿∿∿∿▌                  │  A1
└───────────────────────────────┃───────────────────────────────┘
  header 180                    ┃ playhead
```

### Struttura

| Elemento | Altezza | Nota |
|---|---|---|
| Toolbar della timeline | 32 | taglia, undo/redo, zoom, altezza tracce, chiudi |
| Righello | 28 | timecode in **bianco pieno**, tacche bianche al 35% |
| Traccia video | 64 | riducibile a 44 e 88 |
| Traccia audio | 48 | |
| Header di traccia | larghezza 180 | nome, mute, solo, blocco, visibilita' |

Altezza totale ridimensionabile trascinando il bordo superiore; persistita nei
settings. Comprimibile a sola toolbar + righello con un tasto.

### Padding attorno alle clip — richiesta esplicita

Le clip **non toccano** i bordi della loro corsia. Attorno a ogni clip resta
vetro visibile: e' quello che fa "respirare" la timeline e che la distingue
dal blocco nero compatto di tutti gli altri editor.

| Token | Valore | Cosa fa |
|---|---|---|
| `trackLanePadding` | 6 | vetro sopra e sotto la clip dentro la corsia |
| `clipGap` | 3 | spazio fra clip adiacenti |
| `clipRadius` | 6 | angoli arrotondati |
| `clipBorderWidth` | 1 | bordo bianco al 15% |
| `laneSeparator` | 1 | filo bianco all'8% fra le corsie |

### Colore delle clip

I colori di `Theme` (`clipVideo`, `clipAudio`, `clipText`, `clipImage`) sono
usati **pieni, non trasparenti**: su vetro devono staccare nettamente. La
trasparenza e' della lastra, non delle clip.

- Miniature e forme d'onda dentro la clip, con il colore che resta visibile ai
  bordi come cornice di identificazione del tipo.
- **Forme d'onda vere (2026-08-11)**: `WaveformService` (singleton QML
  `Waves`, `ui/waveforms.py`) genera UNA striscia PNG per file — picchi
  bianchi simmetrici su trasparenza, ~100 colonne/s con cap 8192, curva
  percettiva 0.7, filo centrale di 1px sul silenzio — su worker thread e
  cache `user_data/cache/waveforms` (stesso pattern anti-deadlock di
  Thumbs: mai Python sui thread immagine di Qt). La corsia A1 mostra la
  fetta della clip stirando la striscia intera a `mediaDuration` e
  facendola scorrere di `-sourceIn`: trim, split e zoom non ridecodificano
  mai. L'estrazione picchi e' pura (`media/waveform.py`, PyAV + numpy
  `maximum.reduceat`). Le barre finte restano solo come segnaposto mentre
  la striscia viene generata la prima volta.
- Selezione: bordo bianco 2px + leggero bagliore. Mai cambiare il riempimento,
  altrimenti si perde il tipo.
- Clip disattivata: opacita' 0.4.

### Playhead e righello (rivisti 2026-08-09)

Il **righello sta in BASSO**, sotto le tracce: tacche che crescono dal
bordo inferiore, etichette in basso. Le tracce partono dal bordo alto delle
corsie. Alto solo `rulerHeight` = **16px** (il testo del timecode + 5px di
aria): la testina del playhead puo' SOVRAPPORSI alle scritte, quindi non
paga altezza propria.

Playhead: linea rossa (`playhead`) 2px che si ferma al righello e termina
in una **goccia vuota** (solo contorno, stile CapCut) nella striscia del
righello: punta assottigliata in alto che continua nella linea, corpo
arrotondato chiuso in basso (Shape 12x16, stroke 1.6, fill trasparente).
La linea NON attraversa la goccia: dentro e' vuota di proposito.

Le **intestazioni tracce** (colonna sinistra, `trackHeaderWidth` = 64)
portano solo il NOME (V1, A1). I bottoni occhio/lucchetto/muto che c'erano
erano segnaposto senza comportamento e sono stati tolti: torneranno uno a
uno INSIEME alla loro logica (nascondi/blocca/silenzia traccia), che e' il
mestiere di quella colonna in ogni editor.

### Scroll verticale delle tracce (2026-08-18)

Con cinque corsie possibili (V1, A1, Color, Sticker, Text) le tracce
superano i 232px del pannello, e la corsia Text nasceva TAGLIATA fuori
vista. Regola: **il righello del tempo resta sempre visibile; a scorrere
sono le tracce.**

- Il righello sta FUORI dal Flickable, ancorato al fondo del pannello;
  la striscia delle tacche segue `contentX` (i numeri restano sotto i
  loro clip) e il tap sul righello muove ancora il playhead.
- Il Flickable delle tracce scorre in entrambe le direzioni
  (`contentHeight` = somma delle corsie). Scrollbar verticale fatta a
  mano (niente Quick Controls): la maniglia e' un puro binding da
  `contentY`, il MouseArea della striscia scrive `contentY` — nessun
  `drag.target`, quindi nessun binding da rompere.
- Le **intestazioni scorrono in sincrono** (`y: -contentY`, ritagliate
  sopra la striscia del righello): un nome fermo mentre la sua traccia
  scivola via etichetterebbe la corsia sbagliata.
- Rotella sui NOMI = scroll verticale; rotella sulle corsie = zoom
  (com'era), Shift+rotella = scroll verticale anche li'.
- Il playhead e' fratello del Flickable, non figlio del contenuto: linea
  che copre la parte di tracce in vista (segue solo `contentX`), goccia
  nella striscia fissa del righello.

Test: `tests/visual/test_timeline_scroll.py` (overflow reale a 4 corsie,
Text fuori vista, drag della scrollbar col mouse, righello immobile,
rotella sulle intestazioni).

### Toolbox contestuale (deciso 2026-08-09)

La toolbar della timeline non ha piu' bottoni fissi a sinistra: quel lato
appartiene alla **selezione**. La selezione e' per **id di clip** (mai per
nome: due tagli dello stesso file condividono il nome) piu' il **tipo di
corsia** toccata (`selectedKind`: "video" | "audio") — stesso clip,
strumenti diversi.

I bottoni si dichiarano in `TimelinePanel.contextActions`: un elenco di
`{ icon, label, kinds, can?, run }`. La toolbar si costruisce da sola con
un Repeater; **aggiungere uno strumento = aggiungere una voce**, per un
nuovo tipo di selezione basta un nuovo valore in `kinds`.

Strumenti attuali:
- selezione **video**: Dividi (al playhead; `can` lo spegne se il playhead
  e' fuori dal clip), Ripristina audio (solo se il clip ha audio rimosso,
  via `show`), Elimina (il clip intero);
- selezione **audio**: Dividi, Silenzia/riattiva, **slider del volume**
  (0–200%, commit al rilascio: ogni commit ricostruisce il grafo, quindi
  niente live-update in drag; il valore live si legge nell'etichetta %
  accanto), Rimuovi audio.

I toggle di stato dichiarano `active(clip)` nel modello: il bottone si
accende in accent finche' lo stato e' attivo (es. Silenzia col clip muto) —
un toggle senza feedback non dice da che parte sta. `muted` e' un campo del
modello SEPARATO dal volume: smutare riporta il volume impostato, che
volume=0 avrebbe distrutto.

**Clip solo-audio (musica)**: un file senza traccia video (mp3, wav...)
vive SOLO sulla corsia A1 (`hasVideo` in timelineClips filtra la V1); nel
grafo la sua immagine e' un buco che la traccia nera riempie, il suono
suona come quello di ogni clip (il transport accetta segmenti audio-only).
Su un clip musica, Canc dalla corsia audio rimuove il CLIP intero —
togliergli solo il suono lascerebbe uno zombie invisibile.

**Eliminare dalla corsia audio toglie SOLO il suono** (deciso 2026-08-09):
V1 e A1 mostrano lo stesso clip, e Canc sulla selezione audio imposta
`TimelineClip.audio_enabled = false` (azione `timeline.set_clip_audio`) —
il video resta, la pillola A1 sparisce, e il volume memorizzato torna
intatto col Ripristina. Nel grafo l'audio rimosso e' un `Gain(0)`, che
restituisce silenzio SENZA decodificare il suono.

Tap su un clip = seleziona (e il tap-to-seek sottostante porta il playhead
li', dove il Dividi lo vuole); doppio tap = apri il file nell'anteprima
(vecchio comportamento); tap sul vuoto = deseleziona (deciso dai DATI, non
dall'ordine dei handler).

**Trim dai bordi** (2026-08-09): 8px su ciascun bordo del clip mostrano il
cursore di ridimensionamento; il drag rimodella la pillola dal vivo e al
rilascio `timeline.trim_clip` applica il taglio — bordo sinistro =
`source_in` + durata, bordo destro = durata. Il MODELLO blinda i limiti:
mai oltre il materiale del sorgente, mai sotto 0.1s, e la timeline
rifluisce. **Calamita** (`snapTime` sul TimelinePanel): ogni bordo
trascinato scatta sul bordo di un ALTRO clip entro ~8px — e' cosi' che il
bordo di un clip video aggancia la fine di un clip audio e viceversa.
Durante il trim il DragHandler di spostamento e' disabilitato: un drag
nato su una maniglia e' un resize, mai un move.

**Trascinare un clip lo riordina** (2026-08-09): DragHandler sul clip
(asse X, `CanTakeOverFromAnything` o il pan del Flickable ruba il gesto);
il clip segue il puntatore, al rilascio decide il MODELLO e il reflow fa
scattare tutto al posto. Regole di inserzione in project.py:
- **drop dal pool** (`add_clip(at)`): il punto del mouse contro i punti
  medi dei clip esistenti — prima della meta' va davanti, oltre va dopo
  (chiude il bug "il play parte sempre dall'ultimo video caricato": il
  vecchio sort per start metteva OGNI drop sopra il primo clip davanti);
- **drag di riordino** (`move_clip`): il bordo sinistro trascinato contro
  i punti medi degli ALTRI gia' compattati — col centro del clip un clip
  lungo non riusciva mai a scavalcarne uno corto. **Canc/Backspace** eliminano il clip selezionato
via `Shortcut` applicativo — stessa regola e stessa eccezione dello Spazio:
un campo di testo consuma il tasto prima.

Il volume per-clip e' un `Gain` (engine/filters.py) applicato alla ENTRY
della playlist, non al producer: due tagli dello stesso file condividono il
producer ma ciascuno tiene il suo volume. Persiste nel progetto
(`TimelineClip.volume`), come `source_in` che il Dividi imposta.

### Zoom (deciso 2026-08-09)

`TimelinePanel.zoom`: 1 = tutta la durata nella corsia, fino a 64x. Le corsie
vivono in un `Flickable` orizzontale (`contentWidth = width * zoom`).
- **Rotellina** sulle corsie = zoom ancorato al cursore (il `WheelHandler`
  sta sul CONTENT, non sul contenitore: il Flickable interattivo
  ruberebbe la rotellina per il pan).
- I bottoni +/− della toolbar passano dalla stessa `zoomBy(factor, anchorX)`;
  il terzo bottone ("Adatta alla durata", `fitAll()`) torna a zoom 1 con la
  vista all'inizio — ha sostituito il vecchio "Comprimi la timeline".
- A zoom > 1 il trascinamento fa il pan e la vista **segue il playhead**
  che avanza (salta a ~20% dal bordo sinistro quando esce dal campo).
- Sotto 1 si torna esattamente al "fit" con `contentX = 0`.

### Barra spaziatrice (deciso 2026-08-09)

Play/pausa e' uno `Shortcut` `Qt.ApplicationShortcut` in Main.qml, non solo
un `Keys.onPressed`: dopo un click su un qualunque controllo l'item col
focus cambia e la gestione per-item moriva. I campi di testo mantengono la
priorita' (shortcut-override degli editor Qt Quick): digitare uno spazio nel
nome file non avvia mai la riproduzione. I controlli focalizzati si
attivano con Invio.

---

## 6. Tool rail

Barra verticale a sinistra, **sole icone**, in vetro.

| Token | Valore |
|---|---|
| `toolRailWidth` | 56 |
| `toolRailButton` | 40 |
| `toolRailIcon` | 20 |
| `toolRailRadius` | 16 (lastra staccata dal bordo di `space3`) |

- Icone **Lucide** (licenza ISC), tratto 1.5px, bianche.
- Ogni pulsante ha un tooltip che compare a destra dopo 500 ms, con nome e
  scorciatoia. **Un'interfaccia di sole icone senza tooltip e' inutilizzabile**:
  il tooltip non e' un extra, e' parte del pulsante.
- Attivo: riempimento `accent`, icona bianca.
- Ordine: Media · Testo · Effetti · Audio · Colore · AI · (spazio flessibile) ·
  Assistente · **Impostazioni**.
- Ogni pulsante apre la sezione corrispondente **nel pannello fluttuante**;
  premerlo di nuovo lo chiude.

---

## 7. Pannello fluttuante

Un solo pannello, a destra. **Tutte** le opzioni, gli effetti, l'audio, il
colore e le impostazioni compaiono qui: non esistono altri pannelli laterali.

Diversamente dal resto, ha **tinta piena** (`bgPanel`), non vetro: contiene
slider, curve ed EQ, cioe' controlli di precisione che hanno bisogno di uno
sfondo stabile per essere letti.

| Token | Valore |
|---|---|
| `floatPanelWidth` | 320 |
| `floatPanelMaxHeight` | 70% dell'altezza finestra |
| `floatPanelRadius` | 14 |
| `floatPanelCollapsed` | 48 x 48 |
| `floatPanelMargin` | `space3` dai bordi |

Ombra netta sotto: e' l'unico elemento dell'interfaccia che proietta ombra, ed
e' cio' che lo fa leggere come "sopra" tutto il resto.

### Comportamento a scomparsa

Fuori dal puntatore si ritira in un quadratino 48x48 con l'icona della sezione
attiva. Al passaggio del mouse si riapre. Animazione `durNormal`, con
opacita' e larghezza animate insieme.

**Le regole di sicurezza sono parte della funzione, non una rifinitura.** Un
pannello che si chiude mentre lo stai usando e' peggio di un pannello fisso.
Il pannello **non si ritira mai** se:

1. si sta trascinando uno slider, una maniglia o un punto di una curva;
2. un campo di testo o un controllo ha il **focus da tastiera**;
3. un menu a tendina o un selettore colore aperto ne e' figlio;
4. e' **spillato** (icona 📌 nell'intestazione, stato persistito);
5. sono passati meno di **600 ms** da quando il puntatore e' uscito.

Il puntatore che rientra entro i 600 ms annulla il ritiro senza animazione
inversa visibile.

Il pannello e' anche **trascinabile** dalla sua intestazione e la posizione si
ricorda per sezione: chi vuole l'EQ in basso a sinistra lo mette li'.

### Contenuto

L'intestazione ha le schede della sezione (es. `VIDEO · AUDIO · COLOR ·
EFFECTS`), un pulsante spilla e uno di chiusura. Il corpo e' costruito
**dallo schema dei parametri** dell'effetto selezionato
(`UI_STYLE_GUIDE.md` §4, `ARCHITECTURE.md`): aggiungere un effetto non
richiede scrivere QML.

Le opzioni on/off usano `SwitchRow` (componente): **interruttore per primo,
etichetta accanto**, tutta la riga cliccabile (deciso 2026-08-09). Il
`SettingRow` impilato (etichetta sopra, controllo sotto) resta per i
controlli larghi — slider e segmented.

**Thumbnail del pool media** (deciso 2026-08-09): un image provider QML
(`image://thumb/<path percent-encoded>`, `ive/src/ive/ui/thumbnails.py`)
decodifica UN fotogramma per file — al 10% della durata, max 3 s, mai il
frame 0 che di solito e' nero — ridotto a 160 px via swscale e cacheato in
memoria per sessione. `Image { asynchronous: true }` fa girare la decodifica
sul thread dell'image loader di Qt: niente jank sul GUI thread e niente
worker nostro da mantenere.

---

## 8. Comandi di riproduzione

Pillola in vetro (`scrimIcons`) **al centro del video**, contenente **solo**
i comandi di trasporto: inizio, fotogramma indietro, play/pausa, fotogramma
avanti, fine.

- **Invisibile a riposo.** Compare quando il puntatore entra nella zona
  centrale del video (60% della larghezza × 64% dell'altezza del fotogramma),
  con dissolvenza `durNormal` e una lieve crescita di scala.
- Resta visibile finche' il puntatore e' sulla pillola stessa o un suo
  pulsante ha il focus da tastiera.
- Visibile anche a progetto appena aperto e fermo a inizio timeline:
  altrimenti chi apre l'app per la prima volta non sa dove sia il play.
- **Niente timecode, niente volume qui**: la lettura dei valori sta altrove
  (§8-bis). La pillola contiene solo azioni, e resta piccola.
- `Spazio` fa play/pausa sempre, anche a pillola nascosta. I comandi non
  dipendono dalla loro visibilita'.

**Perche' al centro.** Il puntatore, mentre si guarda l'anteprima, sta gia'
li'. Mettere il comando piu' usato dove la mano si trova gia' evita il
viaggio verso il bordo dello schermo, e a riposo non c'e' nulla che copra il
video.

---

## 8-bis. Lettura di tempo e volume

Timecode corrente, controlli di sessione (spegni, fullscreen, annulla,
ripeti) e volume, in un'unica **pillola di vetro** (rivisto 2026-08-11).

- **Lastra di vetro a pillola** (`GlassSurface`, raggio = meta' altezza,
  `scrimIcons`): stessa superficie del tool rail, quindi i contenuti
  seguono il TEMA (scuri su lastra chiara e viceversa). Prima gli
  elementi poggiavano nudi sul video con glifi bianchi: finche' erano
  solo timecode e volume bastava, ma coi bottoni veri (undo/redo ecc.)
  le icone si perdevano sul filmato in movimento.
- **Sempre visibile, ma discreta**: opacita' a riposo **0.55**, piena al
  passaggio del puntatore o quando riceve il focus.
- Il cursore del volume e' nascosto a riposo e si estende al passaggio del
  mouse sul gruppo.
- Il timecode usa il font monospace (`fontFamilyMono`) e
  `font-variant-numeric: tabular-nums`: con un font proporzionale le cifre
  ballano e in riproduzione diventa illeggibile.
- Posizione predefinita: **in alto a sinistra**, accanto alla tool rail.

**Perche' senza lastra.** Sono valori che si consultano di sfuggita, non
comandi da colpire. Una lastra li trasformerebbe in un elemento di
interfaccia permanente che ruba spazio al video; l'ombra costa nulla e li
rende leggibili su qualunque contenuto.

---

## 8-ter. Posizione degli strumenti — configurabile

Le posizioni non sono cablate: stanno nelle impostazioni, sezione
**Posizione degli strumenti**, e sono persistite.

| Elemento | Opzioni | Predefinito |
|---|---|---|
| Tool rail | Sinistra · Destra | Sinistra |
| Pannello fluttuante | segue la rail, sul lato opposto | Destra |
| Comandi di riproduzione | Centro video · Sopra la timeline | Centro video |
| Tempo e volume | Alto sx · Alto dx · Basso sx | Alto sx |
| Altezza timeline | Bassa 180 · Media 232 · Alta 300 | Media |
| Ritiro automatico del pannello | on/off | on |
| Ritardo di ritiro | 0-2000 ms | 600 ms |

Regole:
- Le **Impostazioni si aprono gia' spillate**: ci si va per configurare, non
  di passaggio. Un pannello che si ritira mentre l'utente sta scegliendo
  un'opzione sarebbe assurdo.
- Chi trova fastidioso il ritiro automatico lo disattiva del tutto qui, senza
  dover spillare il pannello ogni volta.
- Rail e pannello sono **sempre su lati opposti**: una sola impostazione li
  governa entrambi, cosi' non e' possibile sovrapporli.
- In modalita' "Sopra la timeline" i comandi tornano al comportamento
  classico: sempre visibili in pausa, nascosti dopo 2,5 s di inattivita'
  durante la riproduzione.
- Ogni cambio di posizione **ricalcola l'area libera** e riscala il video con
  l'animazione di §3: il fotogramma resta sempre interamente visibile.
- I tooltip della rail si aprono verso l'interno dello schermo, quindi il
  lato cambia insieme alla rail.

---

## 9. Avvio a schermo intero

- L'app parte **a schermo intero** sul monitor dell'ultima sessione.
- `F11` commuta schermo intero / finestra. `Esc` esce dallo schermo intero
  **solo** se non c'e' un dialog aperto e nessun trascinamento in corso.
- Lo stato (schermo intero, monitor, geometria della finestra, altezza
  timeline, posizione e spillatura del pannello) e' persistito e ripristinato.
- Su macOS lo schermo intero crea uno Space dedicato: i dialog devono essere
  figli transienti della finestra, altrimenti finiscono dietro o su un altro
  Space.
- Se il monitor memorizzato non esiste piu' (portatile scollegato dal dock),
  fallback al monitor primario senza errori.
- Una **modalita' Presentazione** (`view.presentation`) nasconde tutto tranne
  il video: consegna al cliente, revisione, controllo qualita'.

---

## 10. Prestazioni

Il rischio concreto di questo design e' che la grafica rubi risorse alla
riproduzione. Vincoli, non consigli:

| Elemento | Strategia |
|---|---|
| Ambient backdrop | sorgente ridotta a 1/8, sfocatura su quella, aggiornamento **10 Hz** |
| Vetro di timeline e rail | sfocatura su sorgente a 1/8, aggiornamento **10 Hz** |
| Durante il trascinamento della timeline | aggiornamento sfocatura sospeso, ultimo fotogramma congelato |
| Hardware debole | degrado automatico a tinta piena senza sfocatura |
| Ombre | solo sul pannello fluttuante, mai su elementi ripetuti |
| Miniature delle clip | asincrone, riciclate, mai una texture per fotogramma |

**Perche' 10 Hz basta.** Il contenuto e' sfocato di 48-96 px: la differenza fra
un aggiornamento e il successivo e' invisibile. Aggiornare a 60 Hz costerebbe
sei volte tanto per un risultato che nessuno distingue.

Tre impostazioni utente: `Effetti vetro: Automatico | Sempre | Mai`,
`Ambient backdrop: on/off`, `Riduci animazioni`.

**Regola di verifica.** Se il preview perde fotogrammi con gli effetti vetro
attivi e li recupera disattivandoli, e' un bug di questo modulo, non un limite
della macchina. Va misurato, non discusso.

### Realizzazione in Qt

Approccio previsto: `ShaderEffectSource` sull'elemento video con
`textureSize` ridotta e `live: false` pilotato da un timer a 10 Hz, piu'
`MultiEffect` (Qt 6.5+) per sfocatura e regolazione. **Da verificare
sperimentalmente prima di darlo per acquisito**, in particolare il costo del
`ShaderEffectSource` su un elemento che riceve texture dal decoder e la resa
su ciascuna piattaforma. Se il costo risultasse proibitivo, il ripiego e' la
tinta piena: il layout non cambia, cambia solo l'estetica.

---

## 11. Accessibilita'

Un'interfaccia in vetro e sole icone e' esposta a due difetti tipici. Entrambi
sono risolti per specifica, non a discrezione:

1. **Contrasto** — garantito dalle soglie di scrim del §4, calcolate sul caso
   peggiore. Non si abbassano per motivi estetici.
2. **Icone senza testo** — ogni pulsante della rail ha tooltip con nome e
   scorciatoia, `Accessible.name` e `Accessible.description`. Esiste inoltre
   una palette comandi ricercabile per nome (deriva dall'Action Registry).

In piu':
- opzione **"Riduci trasparenza"**: tutte le superfici diventano tinta piena.
  E' un requisito di accessibilita' standard, non una curiosita';
- ogni elemento raggiungibile da tastiera, focus sempre visibile anche sul
  vetro (anello `accent` con alone scuro sotto);
- il pannello fluttuante **non si ritira mai** durante la navigazione da
  tastiera: e' la regola 2 del §7.

---

## 12. Cosa non fare

| Errore | Perche' e' un errore |
|---|---|
| Scrim sotto le soglie del §4 | testo illeggibile su video chiari — difetto funzionale, non estetico |
| Usare `scrimText` su una barra di sole icone | inutilmente opaca: sembra una lastra, non vetro. Le icone stanno a 3:1, non a 4.5:1 |
| Mettere timecode o volume nei comandi di riproduzione | la pillola cresce, copre il video e mescola letture e azioni |
| Posizioni cablate nel codice | devono stare nelle impostazioni ed essere persistite (§8-ter) |
| Rendere semitrasparenti anche le clip | non si distinguono piu' i tipi, e le miniature diventano fango |
| Vetro sul pannello fluttuante | slider, curve ed EQ hanno bisogno di sfondo stabile |
| Aggiornare le sfocature a ogni fotogramma | ruba GPU alla riproduzione senza guadagno percepibile |
| Ritiro del pannello senza le regole di sicurezza | si chiude mentre lo usi: la funzione diventa un difetto |
| Icone senza tooltip | interfaccia indovinabile solo per chi l'ha scritta |
| Un secondo pannello laterale | il vincolo "un solo pannello" e' l'idea stessa del progetto |
| Cornici, bordi in rilievo, gradienti decorativi | il vetro funziona solo se resta pulito |
| Ombre su elementi ripetuti (clip, pulsanti) | costo per elemento, e sporca la lastra |

---

## 13. Checklist per un elemento nuovo dello shell

1. [ ] Sta in uno dei livelli del §2, senza inventarne altri
2. [ ] Se e' in vetro: rispetta le soglie di scrim del §4
3. [ ] Se ha testo: verificato su fotogramma bianco **e** nero
4. [ ] Le sfocature seguono il budget del §10
5. [ ] Ha una resa in "Riduci trasparenza"
6. [ ] Raggiungibile da tastiera, focus visibile
7. [ ] Se e' un'icona: tooltip con nome e scorciatoia
8. [ ] Non riduce l'area libera senza riscalare il video
9. [ ] Il suo stato (dimensione, posizione, apertura) e' persistito
10. [ ] Testato a schermo intero su 1080p e su 4K

## Tap sulla timeline → pannello (2026-08-20)

Toccare un clip sulla timeline seleziona E apre la sezione del pannello
fluttuante che lo modifica (`TimelinePanel.panelForKind`, segnale
`panelRequested` → `Main.openSection`): video → `project` (media),
audio → `audio`, color → `color`, sticker → `stickers`, text → `text`,
transizione → `transitions`. Solo il TAP lo fa: l'inizio di un drag o
di un trim seleziona senza cambiare pannello. Test:
`tests/visual/test_timeline_autopanel.py`.
