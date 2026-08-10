# Sfondi — provenienza e licenze

Questi file **vengono distribuiti con l'applicazione**, quindi ricadono nella
parte rigorosa di `docs/LICENSING.md` §0: di ciò che spediamo noi rispondiamo
noi. Ogni file elencato qui deve avere fonte e licenza verificate **alla
fonte**, non dedotte.

---

## `idle_loop.mp4`

Sfondo in loop mostrato quando non c'è nessun progetto aperto.

| | |
|---|---|
| File originale | `14683997_3840_2160_30fps.mp4` |
| Risoluzione originale | 3840×2160, 29.97 fps, 20.0 s, 15.7 MB |
| Distribuito come | 1280×720, 29.97 fps, 20.0 s, **1.0 MB**, senza traccia audio |
| Transcodifica | H.264 `crf 26 preset slow`, nessun audio |
| Fonte | **DA COMPLETARE** — URL della pagina di download |
| Autore | **DA COMPLETARE** |
| Licenza | **DA VERIFICARE** |

### Perché è ridotto a 720p

Lo sfondo viene mostrato sfocato e scurito dietro l'interfaccia. Alla
risoluzione originale la decodifica continua consumerebbe la stessa CPU che
serve all'anteprima — cioè il budget che `UI_SHELL.md` §10 protegge. A 720p i
pixel da decodificare sono nove volte meno e sullo schermo non si distingue
alcuna differenza.

### Da completare prima di una distribuzione pubblica

Lo schema del nome originale (`14683997_3840_2160_30fps.mp4`) corrisponde a
quello dei download di Pexels. **Va confermato**, e vanno registrati sopra URL,
autore e licenza esatta.

Se la provenienza non si riesce a stabilire con certezza, il file va sostituito
prima di pubblicare: uno sfondo decorativo non vale il rischio di spedire agli
utenti materiale di origine incerta. In alternativa lo sfondo si disattiva dai
settings (`appearance.idle_background`) e l'app resta pienamente funzionale —
non è una dipendenza di nulla.

---

## Aggiungere un nuovo sfondo

1. Transcodificare a 1280×720 senza audio (`crf 26`).
2. Aggiungere una riga in questa tabella con fonte, autore e licenza.
3. File senza licenza dichiarata non si spediscono.
