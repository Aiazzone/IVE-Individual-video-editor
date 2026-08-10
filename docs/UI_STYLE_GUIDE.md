# IVE — UI Style Guide

Regole obbligatorie per l'interfaccia. **Framework: PySide6 (Qt 6.7) + QML /
Qt Quick.**

> **Differenza rispetto agli altri progetti (PICK, PALLET_*, INSPECTOR):**
> quelli sono HMI industriali in Qt Widgets + QSS, con testi tutti MAIUSCOLI e
> palette grigia. IVE e' un prodotto creator: QML, palette near-black, testi in
> **case naturale**. La *struttura* di questa guida (token centralizzati,
> costanti single-source-of-truth, componenti riusabili) e' ereditata; i
> *valori* no. Non copiare QSS dagli altri progetti.

---

## 1. Design token — `Theme.qml`

**Un solo posto per colori e dimensioni.** Nessun valore letterale nei file
QML: ne' `"#4C8DFF"`, ne' `height: 32`.

`ive/qml/theme/qmldir`
```
singleton Theme 1.0 Theme.qml
```

`ive/qml/theme/Theme.qml`
```qml
pragma Singleton
import QtQuick

QtObject {
    id: theme

    // ── Modalita' ────────────────────────────────────────────────
    property bool dark: true

    // ── Colori: superfici ────────────────────────────────────────
    readonly property color bgRoot:      dark ? "#0E0E11" : "#F7F7F9"
    readonly property color bgPanel:     dark ? "#16161A" : "#FFFFFF"
    readonly property color bgElevated:  dark ? "#1E1E24" : "#FFFFFF"
    readonly property color bgSunken:    dark ? "#0A0A0C" : "#EDEDF0"
    readonly property color bgHover:     dark ? "#24242C" : "#E8E8EC"
    readonly property color bgPressed:   dark ? "#2C2C36" : "#DCDCE2"
    readonly property color border:      dark ? "#2A2A32" : "#D8D8DE"
    readonly property color borderStrong:dark ? "#3A3A46" : "#BFBFC8"

    // ── Colori: testo ────────────────────────────────────────────
    readonly property color text:        dark ? "#EDEDF2" : "#16161A"
    readonly property color textMuted:   dark ? "#8A8A96" : "#6A6A76"
    readonly property color textDisabled:dark ? "#54545E" : "#A8A8B2"

    // ── Colori: semantici ────────────────────────────────────────
    readonly property color accent:      "#4C8DFF"
    readonly property color accentHover: "#6BA1FF"
    readonly property color accentPress: "#3A78E6"
    readonly property color onAccent:    "#FFFFFF"
    readonly property color danger:      "#FF4D4F"
    readonly property color warning:     "#F5A623"
    readonly property color success:     "#22C55E"

    // ── Colori: timeline ─────────────────────────────────────────
    readonly property color clipVideo:      "#2D6BD4"
    readonly property color clipAudio:      "#1F8A5C"
    readonly property color clipText:       "#8B5CF6"
    readonly property color clipImage:      "#D97706"
    readonly property color clipAdjustment: "#6B7280"
    readonly property color clipSelected:   "#FFFFFF"   // bordo, non fill
    readonly property color playhead:       "#FF4D4F"
    readonly property color trackHeaderBg:  dark ? "#131318" : "#F0F0F3"
    readonly property color rulerBg:        dark ? "#101014" : "#EDEDF0"
    readonly property color gridLine:       dark ? "#22222A" : "#DEDEE4"

    // ── Tipografia ───────────────────────────────────────────────
    readonly property string fontFamily:     "Inter"       // fallback di sistema
    readonly property string fontFamilyMono: "JetBrains Mono"
    readonly property int fontSizeXs:  10
    readonly property int fontSizeSm:  11
    readonly property int fontSizeMd:  13   // default UI
    readonly property int fontSizeLg:  15
    readonly property int fontSizeXl:  20
    readonly property int fontWeightRegular: Font.Normal
    readonly property int fontWeightMedium:  Font.Medium
    readonly property int fontWeightBold:    Font.DemiBold

    // ── Spaziatura (scala 4px) ───────────────────────────────────
    readonly property int space1: 4
    readonly property int space2: 8
    readonly property int space3: 12
    readonly property int space4: 16
    readonly property int space5: 24
    readonly property int space6: 32

    // ── Raggi ────────────────────────────────────────────────────
    readonly property int radiusSm:   4
    readonly property int radiusMd:   6    // input, bottoni
    readonly property int radiusLg:   8    // card, pannelli
    readonly property int radiusFull: 999

    // ── Dimensioni componenti ────────────────────────────────────
    readonly property int controlHeight:      32   // bottoni, input, combo
    readonly property int controlHeightSm:    24
    readonly property int iconButtonSize:     32
    readonly property int iconSize:           18
    readonly property int toolbarHeight:      48
    readonly property int statusBarHeight:    24
    readonly property int sidePanelMinWidth:  260
    readonly property int sidePanelDefWidth:  320
    readonly property int inspectorDefWidth:  320
    readonly property int timelineMinHeight:  180
    readonly property int trackHeightVideo:   64
    readonly property int trackHeightAudio:   48
    readonly property int trackHeaderWidth:   180
    readonly property int rulerHeight:        28
    readonly property int splitterThickness:  4

    // ── Animazioni ───────────────────────────────────────────────
    readonly property int durFast:   120
    readonly property int durNormal: 180
    readonly property int durSlow:   280
    readonly property int easing:    Easing.OutCubic

    // ── Elevazione ───────────────────────────────────────────────
    readonly property color shadow: dark ? "#000000" : "#20000000"

    // ── Superfici in vetro (vedi UI_SHELL.md §4) ─────────────────
    // Soglie di leggibilita' calcolate sul caso peggiore (fotogramma
    // bianco). NON abbassarle. Il livello dipende da cosa contiene la
    // superficie: testo 4.5:1, sole icone 3:1.
    readonly property real  scrimText:          0.62
    readonly property real  scrimTextSecondary: 0.72
    readonly property real  scrimIcons:         0.45
    readonly property real  scrimSolidFallback: 0.92
    readonly property color glassTint:          "#0A0A0C"
    readonly property int   glassBlurRadius:    48
    readonly property color glassBorder:        "#2EFFFFFF"
    readonly property real  backdropDim:        0.45
    readonly property int   backdropBlurRadius: 96
    readonly property int   glassUpdateHz:      10
    readonly property bool  glassAvailable:     true   // rilevato a runtime

    // ── Shell: letture su video (senza lastra) ───────────────────
    readonly property real  readoutIdleOpacity: 0.55
    readonly property string readoutShadow:     "0 2px 6px rgba(0,0,0,.95)"

    // ── Shell: tool rail ─────────────────────────────────────────
    readonly property int toolRailWidth:   56
    readonly property int toolRailButton:  40
    readonly property int toolRailIcon:    20
    readonly property int toolRailRadius:  16

    // ── Shell: pannello fluttuante ───────────────────────────────
    readonly property int  floatPanelWidth:      320
    readonly property real floatPanelMaxHeightR: 0.70
    readonly property int  floatPanelRadius:     14
    readonly property int  floatPanelCollapsed:  48
    readonly property int  floatPanelHideDelay:  600   // ms, regola di sicurezza

    // ── Shell: timeline ──────────────────────────────────────────
    readonly property int timelineToolbarHeight: 32
    readonly property int trackLanePadding:      6
    readonly property int clipGap:               3
    readonly property int clipRadius:            6
    readonly property int clipBorderWidth:       1
    readonly property int laneSeparator:         1

    // ── Accessibilita' ───────────────────────────────────────────
    property bool reduceTransparency: false   // superfici a tinta piena
    property bool reduceMotion:       false
}
```

Uso:
```qml
import "../theme"

Rectangle {
    color: Theme.bgPanel
    radius: Theme.radiusLg
    border.color: Theme.border
}
```

Il cambio tema chiaro/scuro e' un solo `Theme.dark = false`: tutti i binding
si aggiornano. Per questo i colori sono `readonly property color` derivati e
**non vanno mai copiati in variabili locali**.

Il valore iniziale di `Theme.dark` arriva da `ui/theme_bridge.py`, che lo
legge dai settings. Default: **dark**.

---

## 2. Tipografia e testi

- Testi in **case naturale**: `"Export"`, non `"EXPORT"`. Solo le etichette
  di sezione molto piccole possono usare uppercase + letter-spacing come
  scelta grafica deliberata (`fontSizeXs`, `textMuted`).
- Font: preferenza `Inter`, con fallback di sistema. Il font va bundled in
  `ive/assets/fonts/` — verifica la licenza (Inter e' SIL OFL, OK).
- Numeri di timecode e valori numerici allineati: usare `fontFamilyMono` per
  evitare che le cifre "ballino" durante il playback.
- Mai stringhe hardcoded: sempre `qsTr()` lato QML → vedi `docs/I18N.md`.

---

## 3. Layout della finestra principale

**La specifica completa e' in `docs/UI_SHELL.md`.** Qui solo il riassunto.

IVE **non** usa il layout a riquadri affiancati degli editor tradizionali.
Il video occupa tutta la finestra; tutto il resto galleggia sopra in vetro
semitrasparente.

```
╔═════════════════════════════════════════════════════════╗
║▒▒▒▒▒▒▒▒▒ ambient backdrop (fotogramma sfocato) ▒▒▒▒▒▒▒▒▒║
║┌──┐▒▒┌─────────────────────────────┐▒▒▒▒▒▒▒▒▒┌────────┐║
║│▣ │▒▒│                             │▒▒▒▒▒▒▒▒▒│pannello│║
║│▣ │▒▒│      VIDEO — INTERO         │▒▒▒▒▒▒▒▒▒│fluttu- │║
║│⚙ │▒▒│                             │▒▒▒▒▒▒▒▒▒│ante    │║
║└──┘▒▒└─────────────────────────────┘▒▒▒▒▒▒▒▒▒└────────┘║
╟─────────────────────────────────────────────────────────╢
║ ░░ timeline in vetro, larga quanto tutta la finestra ░░ ║
╚═════════════════════════════════════════════════════════╝
```

- **Ambient backdrop**: il fotogramma corrente, ingrandito e sfocato, riempie
  la finestra. Il video nitido sta *tutto* nell'area libera.
- **Timeline**: lastra di vetro in basso, larghezza piena, con padding attorno
  alle clip.
- **Tool rail**: sole icone Lucide bianche a sinistra, in vetro.
- **Un solo pannello fluttuante** a destra, tinta piena, che si ritira in un
  quadratino quando il mouse esce. Tutte le opzioni, gli effetti e le
  impostazioni compaiono li'.
- L'app parte a **schermo intero**.

- I **comandi di riproduzione** stanno al centro del video e compaiono
  all'avvicinarsi del puntatore; **timecode e volume** stanno in un angolo,
  senza lastra, sempre un po' visibili grazie all'ombra proiettata.
- Le posizioni di rail, pannello, comandi e letture sono **configurabili
  nelle impostazioni** e persistite.

Vincolo di leggibilita' che condiziona ogni superficie in vetro, calcolato sul
caso peggiore di un fotogramma bianco: scrim minimo **0.55** per il testo
primario, **0.68** per il testo secondario, **0.42** per le superfici di sole
icone (che stanno a 3:1, non a 4.5:1). Vedi `UI_SHELL.md` §4.

---

## 4. Componenti

Tutti in `ive/qml/components/`. **Nessuna schermata istanzia controlli Qt
Quick Controls grezzi**: si usano i wrapper, cosi' un cambio di stile e' un
solo file.

| Componente | File | Note |
|---|---|---|
| `AppButton` | `AppButton.qml` | variant: `primary` / `secondary` / `ghost` / `danger` |
| `IconButton` | `IconButton.qml` | 32x32, icona 18px, tooltip obbligatorio |
| `AppTextField` | `AppTextField.qml` | placeholder, stato errore |
| `AppComboBox` | `AppComboBox.qml` | popup stilizzato, vedi §4.1 |
| `AppSlider` | `AppSlider.qml` | doppio click = reset al default |
| `NumberField` | `NumberField.qml` | drag orizzontale per variare il valore |
| `ToggleSwitch` | `ToggleSwitch.qml` | 44x24, animazione `durNormal` |
| `Card` | `Card.qml` | `bgElevated`, `radiusLg`, titolo opzionale |
| `Section` | `Section.qml` | gruppo collassabile nell'Inspector |
| `Tooltip` | `AppTooltip.qml` | delay 500ms |
| `ContextMenu` | `AppMenu.qml` | voci = Action id, non callback inline |
| `ProgressBar` | `AppProgressBar.qml` | usato dai job |
| `EmptyState` | `EmptyState.qml` | icona + testo + call to action |
| `GlassSurface` | `GlassSurface.qml` | blur + scrim + bordo. Proprieta' `tier: "text" \| "icons"` che sceglie la soglia (`UI_SHELL.md` §4); ripiego automatico a tinta piena |
| `Readout` | `Readout.qml` | valore su video senza lastra: ombra proiettata, opacita' 0.55 a riposo |
| `AmbientBackdrop` | `AmbientBackdrop.qml` | fotogramma ingrandito, sfocato, scurito, a 10 Hz |
| `ToolRail` | `ToolRail.qml` | barra icone sinistra; ogni voce = Action id |
| `FloatingPanel` | `FloatingPanel.qml` | pannello unico a destra, ritiro con regole di sicurezza |
| `TransportHUD` | `TransportHUD.qml` | pillola in vetro, auto-hide in riproduzione |

### 4.1 Stati obbligatori

Ogni controllo interattivo implementa **tutti** questi stati, altrimenti la UI
sembra rotta:

| Stato | Trattamento |
|---|---|
| normal | `bgElevated` + `border` |
| hover | `bgHover`, transizione `durFast` |
| pressed | `bgPressed` |
| focus | bordo `accent` 1px + alone `accent` al 20% |
| checked / active | fill `accent`, testo `onAccent` |
| disabled | opacita' 0.45, `textDisabled`, nessun hover |

### 4.2 `AppButton` — riferimento

| variant | background | border | testo | hover |
|---|---|---|---|---|
| `primary` | `accent` | nessuno | `onAccent` | `accentHover` |
| `secondary` | `bgElevated` | `border` | `text` | `bgHover` |
| `ghost` | trasparente | nessuno | `text` | `bgHover` |
| `danger` | `danger` | nessuno | `#FFFFFF` | `danger` +10% |

Sempre `height: Theme.controlHeight`, `radius: Theme.radiusMd`,
padding orizzontale `Theme.space3`.

---

## 5. Timeline — regole specifiche

La timeline e' la parte piu' delicata: e' l'unico punto dove le performance
di rendering contano davvero.

- Rendering delle clip con **`Repeater` su un modello + delegati riciclati**,
  oppure `QQuickPaintedItem` custom se il numero di clip supera qualche
  centinaio. Mai istanziare un `Item` per ogni frame o per ogni waveform peak.
- Colore della clip per tipo (`clipVideo`, `clipAudio`, `clipText`,
  `clipImage`, `clipAdjustment`), **non** per contenuto.
- Selezione = bordo `clipSelected` 2px, non cambio di fill: il tipo deve
  restare riconoscibile anche selezionato.
- Thumbnail e waveform vengono da `media/` in modo **asincrono**; finche' non
  ci sono, si mostra il colore pieno. Mai bloccare la UI per una thumbnail.
- Playhead: linea `playhead` 1px + handle in testa nel ruler.
- Snap: soglia in **pixel** (8px), non in frame, cosi' e' costante a ogni zoom.
- Zoom: la scala e' logaritmica; il punto sotto il cursore resta fermo.
- Ogni drag/trim produce **un solo `Command`** al rilascio (coalescing),
  non uno per movimento del mouse.

---

## 6. Iconografia

- Set di icone **outline**, tratto 1.5px, griglia 24px, esportate SVG.
- Devono essere monocromatiche e colorate via `Theme` (usare
  `MultiEffect`/`ColorOverlay` o SVG con `currentColor`), cosi' funzionano in
  tema chiaro e scuro senza duplicare i file.
- Licenza libera obbligatoria (Lucide ISC, Feather MIT, Material Symbols
  Apache-2.0). **Vietato** ridisegnare o riesportare icone di prodotti
  proprietari. Registrare la fonte in `docs/LICENSING.md`.
- Cartella: `ive/assets/icons/`.

---

## 7. Movimento

- Solo transizioni **funzionali**: feedback su hover/press, comparsa pannelli,
  cambio tab. Niente animazioni decorative.
- Durate: `durFast` per feedback, `durNormal` per pannelli, `durSlow` solo per
  onboarding.
- Easing: `Easing.OutCubic` di default.
- **Mai animare durante il playback**: qualunque animazione nella timeline o
  nel preview mentre si riproduce ruba frame. Disabilitarle quando
  `playback.isPlaying`.
- Rispettare l'eventuale preferenza di sistema "riduci animazioni".

---

## 8. Accessibilita'

- Contrasto minimo 4.5:1 per il testo normale, 3:1 per testo grande e per i
  bordi degli elementi interattivi. `textMuted` su `bgPanel` va verificato.
- Ogni controllo raggiungibile da tastiera, focus visibile sempre.
- `Accessible.name` e `Accessible.role` sui controlli custom.
- Target di click minimo 32x32 (24x24 solo per controlli densi della timeline).
- Il colore non e' mai l'unico veicolo di informazione: affiancare icona o
  testo.

---

## 9. Regole QML

1. **Niente business logic in QML.** JavaScript in QML si limita a
   presentazione e binding. Ogni operazione chiama un'Action:
   `Actions.invoke("timeline.split_clip", {})`.
2. **Niente valori letterali** di colore o dimensione: sempre `Theme.*`.
3. Un componente per file, `PascalCase.qml`, `id` in camelCase.
4. Le proprieta' pubbliche di un componente sono dichiarate in cima con
   `property`/`signal`, prima del resto.
5. Evitare binding costosi in `Repeater`/delegati (niente `JSON.parse`,
   niente chiamate Python nel binding). Precalcolare nel modello.
6. `Loader` + `asynchronous: true` per pannelli pesanti non ancora visibili.
7. `anchors` per il posizionamento, `Layout` dentro i layout — non mischiarli
   sullo stesso item.
8. Ogni componente nuovo deve funzionare in **entrambi** i temi: verificare
   prima di considerarlo finito.
9. Warning QML in console = bug. Vanno risolti, non ignorati.

---

## 10. Verifica visiva

Dopo ogni modifica a `Theme.qml` o a un componente:

1. Rendere il componente isolato in una scena di test
   (`tests/visual/<component>.qml`).
2. Catturare gli stati: normal, hover, focus, pressed, disabled, checked,
   e per i popup anche aperto.
3. Confrontare con le aspettative di §4.1 in **entrambi** i temi.
4. Leggere sempre stderr: un warning QML e' un difetto.

Massimo 3 iterazioni fix→verifica; oltre, chiedere invece di tentare a caso.

---

## 11. Checklist per una nuova schermata

1. [ ] Tutti i colori e le dimensioni da `Theme`
2. [ ] Tutti i testi via `qsTr()`
3. [ ] Componenti da `components/`, nessun controllo Qt Quick grezzo
4. [ ] Tutti gli stati di §4.1 implementati
5. [ ] Ogni azione passa dall'Action Registry
6. [ ] Funziona in tema chiaro e scuro
7. [ ] Navigabile da tastiera, focus visibile
8. [ ] Larghezze/altezze persistite nei settings se ridimensionabili
9. [ ] Stato vuoto gestito con `EmptyState`
10. [ ] Nessun warning QML in console
