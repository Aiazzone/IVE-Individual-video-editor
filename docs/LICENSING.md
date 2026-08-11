# IVE — Licenze e conformita'

> **Documento vivo.** Prima di aggiungere qualunque dipendenza, modello AI,
> font o set di icone: verifica qui, e se non c'e', aggiungilo.
>
> **Le informazioni in questa tabella vanno riverificate alla data di
> adozione.** Le licenze dei progetti — soprattutto dei modelli AI — cambiano
> nel tempo. Le note qui sotto sono un punto di partenza, non un parere
> legale.

---

## 0. Ambito di responsabilita' — leggere prima di tutto il resto

Questo documento riguarda **il software che scriviamo e i contenuti che
distribuiamo noi**. Nient'altro.

| Di cosa rispondiamo | Di cosa non rispondiamo |
|---|---|
| La licenza di IVE | I video che l'utente monta |
| Le licenze delle dipendenze che spediamo | I file che l'utente importa |
| I content pack ufficiali (musiche, LUT, font, template) | I content pack di terzi |
| La build FFmpeg che distribuiamo | L'uso che l'utente fa dell'export |

**IVE e' uno strumento.** Come Kdenlive, Shotcut, GIMP, Audacity o VLC:
fornisce il motore e la liberta' di usarlo. Cosa l'utente importa, monta ed
esporta e' affare suo e sotto la sua responsabilita'.

Conseguenze pratiche sul codice — sono vincoli di progetto, non opinioni:

- **L'app non verifica, non giudica e non blocca** i contenuti dell'utente.
  Nessun controllo di provenienza, nessun fingerprinting, nessuna telemetria,
  nessun avviso moralistico.
- **Nessun campo di licenza e' bloccante** per i contenuti di terzi. Se un
  pack non dichiara una licenza, si installa lo stesso: il campo e'
  informativo, serve a chi vuole essere ordinato, non a fare da guardiano.
- **Nessuna filigrana, nessun limite, nessuna funzione a pagamento.**
- Gli strumenti di attribuzione (badge, `credits.txt`) sono **comodita'
  offerte**, mai imposizioni: chi vuole dare credito lo fa in un click, chi
  non vuole non viene infastidito.

L'unico posto dove siamo rigorosi e' **cio' che spediamo noi**: le musiche,
i font, le icone e i LUT dei pack ufficiali sono CC0, CC-BY o equivalenti,
con provenienza verificata. Quello e' materiale nostro, ed e' giusto che sia
pulito.

---

## 1. Licenza del progetto — decisione da prendere

La scelta dipende quasi interamente da **come distribuiamo FFmpeg**.

### Opzione A — GPL-3.0-or-later  *(consigliata)*

- Permette di usare build FFmpeg con `--enable-gpl` (x264, x265, e altri
  encoder GPL): la massima copertura di codec in export.
- Permette di usare modelli e librerie AI sotto GPL (es. alcuni modelli di
  matting).
- Compatibile con PySide6 sotto LGPLv3.
- E' la strada di **Kdenlive** e **Shotcut**, cioe' dei due editor video
  open source desktop piu' maturi. Terreno conosciuto.
- Costo: chi crea un derivato deve rilasciare le modifiche sotto GPL. I
  plugin di terze parti in-process sono in un'area grigia; va chiarito
  esplicitamente nel documento dei plugin (vedi §5).

### Opzione B — LGPL-3.0 / MPL-2.0

- Piu' permissiva, ma obbliga a distribuire una build FFmpeg **LGPL** (niente
  x264/x265): l'export H.264/H.265 dovrebbe appoggiarsi a encoder hardware
  o a OpenH264, e la qualita'/compatibilita' ne risente.
- Esclude ogni dipendenza GPL, quindi taglia fuori diversi modelli AI.

**Raccomandazione: Opzione A (GPL-3.0-or-later).** Per un editor video la
copertura codec vale piu' della permissivita'. Decisione da confermare prima
della prima release pubblica.

**Stato: DA CONFERMARE.**

---

## 2. Dipendenze principali

| Componente | Licenza (da verificare) | Nota |
|---|---|---|
| **PySide6 / Qt 6** | LGPL-3.0 (o GPL / commerciale) | Compatibile con GPLv3. Con LGPL serve il **linking dinamico** e la possibilita' di sostituire le librerie Qt — PyInstaller `--onedir` lo soddisfa, `--onefile` e' piu' delicato. **Usare `--onedir`.** |
| **FFmpeg** | LGPL-2.1+ core; **GPL-2.0+** se `--enable-gpl` | Il punto critico: vedi §1 e §3. |
| **PyAV** | BSD-3-Clause | Binding Python su FFmpeg; la licenza di FFmpeg resta quella che conta. |
| **NumPy** | BSD-3-Clause | |
| **opencv-python** | Apache-2.0 | Applicazione veloce dei filtri colore (LUT/transform/multiply). Il wheel standard NON include codec brevettati; usiamo solo primitive di elaborazione, mai il suo I/O video. |
| **rlottie-python** | LGPL (bundla rlottie: MIT + parti FTL/BSD-3/MPL-1.1) | Rendering degli sticker animati Lottie. Aggiunto 2026-08-11; LGPL compatibile col nostro GPL-3. |
| **Pillow** | MIT-CMU (HPND) | |
| **ONNX Runtime** | MIT | Provider CPU/CUDA/DirectML. |
| **OpenVINO** | Apache-2.0 | |
| **PyInstaller** | GPL-2.0 con **bootloader exception** | L'exception permette di distribuire app con qualunque licenza. |
| **pytest / pytest-qt** | MIT | Solo sviluppo. |
| **ruff** | MIT | Solo sviluppo. |

### Runtime di accelerazione

| Componente | Licenza | Nota |
|---|---|---|
| CUDA / cuDNN | Proprietaria NVIDIA, redistribuibile con vincoli | **Non bundlare.** Dipendenza opzionale a carico dell'utente: rilevata a runtime. |
| ROCm | MIT / Apache-2.0 | Linux. Dipendenza opzionale. |
| OpenVINO runtime | Apache-2.0 | Bundlabile. |
| DirectML | Proprietaria Microsoft, redistribuibile | Windows. Verificare i termini prima di bundlare. |

**Regola:** nessun runtime di accelerazione e' un requisito di installazione.
Tutti sono extra opzionali, rilevati a runtime, con fallback CPU.

---

## 3. La trappola FFmpeg

FFmpeg ha **due licenze possibili a seconda di come e' compilato**:

| Build | Licenza | Cosa include |
|---|---|---|
| default | LGPL-2.1+ | decoder nativi, VP8/VP9 (libvpx BSD), AV1, OpenH264 |
| `--enable-gpl` | GPL-2.0+ | + libx264, libx265, libxvid, alcuni filtri |
| `--enable-nonfree` | **non ridistribuibile** | **MAI usare.** |

Conseguenze pratiche:
1. Se distribuiamo una build GPL, **tutto IVE deve essere GPL**.
2. `--enable-nonfree` produce un binario che non puo' essere ridistribuito
   in nessun caso. Vietato, senza eccezioni.
3. La build FFmpeg che spediamo va documentata: versione, flag di configure,
   licenza risultante. Il file `ive/third_party/ffmpeg/BUILD_INFO.md` deve
   contenere l'output di `ffmpeg -version` e la configurazione completa.
4. Bisogna includere il testo delle licenze di FFmpeg e delle librerie
   incorporate in `ive/third_party/ffmpeg/LICENSES/`.

Su Linux, la strada piu' pulita e' **non bundlare FFmpeg** e usare quello di
sistema. Su Windows e macOS il bundling e' necessario.

---

## 4. Modelli AI — codice e pesi hanno licenze diverse

> **Questo e' l'errore piu' facile da commettere.** Un progetto puo' avere il
> codice MIT e i pesi CC BY-NC (non-commercial). Distribuire i pesi in
> quel caso limita l'uso dell'applicazione.

Regole ferree:

1. Per ogni modello si verificano **due** licenze: codice **e** pesi.
2. `ai/model_registry.py` registra per ogni modello: id, URL, checksum,
   **licenza del codice**, **licenza dei pesi**, e un flag
   `commercial_use_allowed`.
3. I pesi **non vengono bundlati** nell'installer. Vengono scaricati su
   richiesta esplicita dell'utente, che vede la licenza prima del download.
4. Un modello con pesi non-commercial e' **utilizzabile ma marcato**: la UI
   lo dichiara, e l'export che lo ha usato lo annota nei metadati del
   progetto.
5. Se esiste un'alternativa permissiva di qualita' comparabile, quella e' il
   default.

### Candidati da valutare (licenze da riverificare)

| Funzione | Candidato | Codice | Pesi | Nota |
|---|---|---|---|---|
| Sottotitoli | faster-whisper + CTranslate2 | MIT | MIT (pesi Whisper OpenAI) | Prima scelta: tutto permissivo. |
| Sottotitoli | whisper.cpp | MIT | MIT | Alternativa leggera, ottima su CPU. |
| Traduzione | Argos Translate | MIT | varia per coppia linguistica | Verificare modello per modello. |
| Traduzione | OPUS-MT (Helsinki-NLP) | MIT | tipicamente CC-BY-4.0 | Permissivo, buona copertura. |
| Traduzione | NLLB-200 | MIT | **CC-BY-NC-4.0** | **Non-commercial.** Solo come opzione dichiarata. |
| Rimozione sfondo | BiRefNet | MIT (verificare) | verificare | Buona qualita', licenza promettente. |
| Rimozione sfondo | MODNet | Apache-2.0 | **spesso non-commercial** | Verificare i pesi specifici. |
| Rimozione sfondo | Robust Video Matting | **GPL-3.0** | GPL-3.0 | Ottimo per il video, ma impone GPL. Coerente con l'Opzione A. |
| Segmentazione | SAM / SAM 2 (Meta) | Apache-2.0 | verificare per versione | Utile per masking assistito. |
| Tracking | trackers classici OpenCV | Apache-2.0 | n/a | Baseline sempre disponibile, nessun modello da scaricare. |
| Tracking | CoTracker | verificare, spesso **CC-BY-NC** | verificare | Solo come opzione dichiarata. |
| Frame interpolation | RIFE | MIT | **alcune versioni non-commercial** | Verificare la release esatta dei pesi. |
| Frame interpolation | FILM (Google) | Apache-2.0 | Apache-2.0 | Alternativa permissiva. |
| Sticker animati (Lottie) | rlottie (Samsung) | MIT (v0.2+; parti FTL/BSD-3/MPL-1.1) | n/a | Il renderer di Telegram. Repo poco attivo: rivalutare al momento. |
| Sticker animati (Lottie) | rlottie-python (binding pip) | **LGPL** (bundla rlottie) | n/a | LGPL compatibile col nostro GPL-3. Verificato 2026-08-11 (docs/STICKERS.md §3). |
| Sticker animati (Lottie) | ThorVG | MIT | n/a | Alternativa mantenuta a rlottie, supporto Lottie integrato. |

**Nessuna riga di questa tabella e' da considerare verificata finche' non
viene controllata alla fonte al momento dell'integrazione.**

---

## 5. Plugin di terze parti

- Il `manifest.json` di ogni plugin **deve** dichiarare `license`.
- Il plugin host mostra la licenza all'utente prima dell'installazione.
- Se IVE e' GPL, va chiarito nel documento dei plugin quale sia la posizione
  del progetto sui plugin proprietari in-process. La posizione consigliata,
  e la piu' difendibile, e' **richiedere che i plugin siano sotto licenza
  compatibile GPL** e dichiararlo esplicitamente nell'API.
- L'API dei plugin va documentata come **interfaccia stabile e versionata**,
  cosi' la posizione legale e' esplicita e non ambigua.

---

## 6. Asset

Vale per **gli asset che spediamo noi** dentro l'applicazione e nei pack
ufficiali. Non per i contenuti dell'utente o di terzi (§0).

| Asset | Vincolo |
|---|---|
| Icone | Solo set con licenza libera: Lucide (ISC), Feather (MIT), Material Symbols (Apache-2.0). Registrare la fonte. |
| Font | Solo SIL OFL o simili. Inter e' OFL-1.1 → OK. Verificare prima di bundlare qualunque font. |
| Suoni, LUT, template, preset | Solo materiale creato da noi o CC0/CC-BY con attribuzione registrata. |
| Sticker di fabbrica | Creati da noi (GPL col progetto). Le animazioni gratuite di LottieFiles ("Lottie Simple License": uso anche commerciale, no attribuzione, ridistribuzione con stessa licenza) sono libere per L'UTENTE; bundlarle NOI richiede il testo della licenza accanto ai file. |
| Screenshot nella documentazione | Solo di IVE stesso, mai di prodotti terzi. |

**Vietato senza eccezioni:** copiare, ridisegnare o "ispirarsi da vicino" a
icone, font, LUT, template, transizioni preconfezionate o stringhe di
prodotti proprietari. Il layout e i paradigmi di interazione sono liberi
(non sono protetti da copyright); l'espressione grafica concreta no.

---

## 7. Obblighi di distribuzione

Ogni release deve includere:

1. `LICENSE` — licenza del progetto.
2. `THIRD_PARTY_LICENSES.md` — elenco completo delle dipendenze con licenza e
   testo integrale dove richiesto. **Generato automaticamente** da uno script
   in `build_scripts/`, non mantenuto a mano.
3. `ive/third_party/ffmpeg/BUILD_INFO.md` — versione e flag di configure.
4. Per LGPL (Qt, FFmpeg LGPL): linking dinamico e istruzioni su come
   sostituire le librerie. Da cui l'uso di PyInstaller **`--onedir`**.
5. Una schermata "About / Licenze" nell'app che elenca le dipendenze e
   permette di leggere le licenze.

---

## 8. Checklist per una nuova dipendenza

1. [ ] Licenza identificata alla fonte (repo ufficiale, non un blog)
2. [ ] Compatibile con la licenza scelta al §1
3. [ ] Se e' un modello AI: licenza dei **pesi** verificata separatamente
4. [ ] Non richiede attribuzione runtime che non stiamo dando
5. [ ] Non e' `--enable-nonfree` o equivalente
6. [ ] Funziona su Windows, Linux e macOS (o e' opzionale con fallback)
7. [ ] Aggiunta alla tabella di questo documento
8. [ ] Aggiunta a `requirements.txt` (o a un extra opzionale)
9. [ ] `THIRD_PARTY_LICENSES.md` si rigenera correttamente
