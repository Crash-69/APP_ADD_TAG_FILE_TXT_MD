# TxtToObsidian

Webapp locale Python per convertire indici Markdown in wikilink Obsidian. Include una modalità standard e un'opzione di arricchimento AI locale tramite Ollama.

## Requisiti

- Windows e Python 3.10 o successivo.
- Per la modalità standard: nessuna dipendenza Python esterna.
- Per la modalità AI: Ollama avviato in locale e pacchetto Python `ollama` installato nell'ambiente che esegue l'app.
- Un modello Ollama installato. L'app seleziona `gemma3:4b` quando disponibile; è possibile scegliere un altro modello dalla UI.

Installazione dello SDK, se necessario:

```powershell
python -m pip install ollama
```

Verifica dei modelli disponibili:

```powershell
ollama list
```

Esempio per installare il modello predefinito:

```powershell
ollama pull gemma3:4b
```

L'app comunica con Ollama all'indirizzo locale `http://127.0.0.1:11434`. Se Ollama è configurato per ascoltare su un altro indirizzo, aggiornare `OLLAMA_HOST` in `app.py`.

## Avvio

Dalla root del workspace:

```powershell
python C:\Progetto_AI\APP_TxtToObsidian\app.py
```

La webapp si apre normalmente su `http://127.0.0.1:8035/`. Se la porta è occupata, l'app prova le porte successive. Per specificare una porta o non aprire automaticamente il browser:

```powershell
python C:\Progetto_AI\APP_TxtToObsidian\app.py --port 8035 --no-browser
```

La dashboard del workspace include TxtToObsidian come applicazione `txt-to-obsidian` sulla porta `8035`.

Dopo modifiche a `app.py`, arrestare e riavviare TxtToObsidian dalla dashboard, quindi ricaricare la pagina. Il solo aggiornamento del browser ricarica HTML e JavaScript, ma non il codice Python del server: una vecchia istanza puo continuare a richiedere l'indice anche con l'interfaccia aggiornata.

## Flusso di utilizzo

1. Selezionare facoltativamente `indice.md`, oppure selezionare direttamente la cartella dei `.txt`: senza un indice caricato, l'elenco dei file appare anche lasciando attiva **Usa file indice, se selezionato**. Disattivare la casella solo per ignorare un indice gia caricato.
2. Selezionare la cartella che contiene i `.txt` oppure inserire il percorso completo della cartella. Le righe numerate, per esempio `01. Titolo`, vengono associate ai file che iniziano con lo stesso numero, per esempio `01_Titolo.txt`.
3. Controllare l'anteprima. Gli indici senza un file corrispondente sono segnalati e non producono un wikilink inesistente.
4. Impostare la directory di output. Per default è la cartella dell'app; la directory deve già esistere.
5. Scegliere se includere `.txt` nei wikilink e se sovrascrivere file esistenti.
6. Avviare la generazione.

Il selettore di cartella del browser serve a individuare i `.txt`; in alternativa si può inserire il percorso Windows, che consente al processo Python di leggere direttamente i file.

Senza indice, vengono elencati tutti i `.txt` direttamente presenti nella cartella, in ordine alfabetico e senza richiedere prefissi numerici. Le sottocartelle sono escluse. Il selettore e il percorso sono alternativi: l'ultima sorgente scelta sostituisce la precedente. Una cartella senza `.txt` viene segnalata e non consente la generazione. Per inserire i tag, attivare **Analisi AI locale** e selezionare nell'elenco i file da analizzare, come nella modalità con indice. L'indice generato include tutti i file elencati; le note con tag vengono create solo per quelli selezionati per AI.

## Modalità standard

Con **Attiva Analisi AI** disattivata, l'app crea nella directory di output `lista_obsidian.md`, con un wikilink per ogni riferimento risolto. Per default l'estensione `.txt` viene rimossa dal link:

```markdown
- [[01_Nome_Documento]]
```

Le sorgenti possono contenere il nome `.txt` esplicito oppure un numero di indice da associare al prefisso del file. Prefissi duplicati o ambigui sono segnalati.

## Modalità AI

Attivando **Analisi AI locale**:

- L'app analizza solo i file selezionati nell'elenco AI; inizialmente sono selezionati tutti.
- Ogni file viene letto per intero; se è lungo, viene suddiviso in blocchi inviati a Ollama uno alla volta. La barra mostra l'avanzamento sequenziale per file.
- Ollama estrae le persone citate e, quando il testo lo dichiara, le classifica come magistrati, mafiosi, appartenenti all'estrema destra, giornalisti, avvocati o politici; estrae inoltre terroristi/organizzazioni terroristiche, partiti, date rilevanti e luoghi nominati.
- I tag sono normalizzati senza spazi, per esempio `#persona/nome`, `#magistrato/nome`, `#mafioso/nome`, `#estrema_destra/nome`, `#giornalista/nome`, `#avvocato/nome`, `#data/1992-05-23`, `#luogo/Palermo`, `#terrorismo/nome`, `#politico/nome` e `#partito/nome`.
- Oltre a `lista_obsidian.md`, viene creato un file `.md` per ogni file selezionato. Ogni nota contiene il nome come titolo, tutto il testo originale e i tag restituiti dall'AI, se presenti.
- I `.txt` originali non vengono modificati.

Esempio di nota generata:

```markdown
# Nome_Documento

Testo originale completo della trascrizione...

Tags: #politico/Mario_Rossi #partito/Partito_Alfa #data/1992-05-23 #luogo/Palermo
```

### Elaborazione su CPU

Le chiamate sono serializzate, senza batch paralleli. Per contenere memoria e migliorare il riconoscimento delle entità nei testi densi, i testi lunghi sono divisi in blocchi sequenziali di massimo 4.500 caratteri con sovrapposizione di 400 caratteri; il contesto è impostato a 4096 token e ogni risposta a 1.024 token. Se Ollama tronca il JSON o va in timeout, il blocco viene riprovato una volta dividendolo in due. Il modello resta caricato per cinque minuti tra richieste. La nota generata conserva comunque il testo originale completo.

L'estrazione è probabilistica: controllare i tag prima dell'uso. Se Ollama non è disponibile, verificare che il servizio locale sia avviato e che il modello selezionato sia installato.

### Soluzioni per completezza e accuratezza

Nei test locali, i modelli con i risultati migliori sono, in ordine:
1. `qwen2.5:14b`
2. `Gemma4:e4b`

L'analisi non scarta più la parte centrale delle trascrizioni lunghe: divide il testo in blocchi consecutivi di massimo 4.500 caratteri, con 400 caratteri di sovrapposizione per conservare entità vicine ai confini. I blocchi e i file sono elaborati in sequenza, mai in parallelo. Per ridurre il carico su CPU/RAM, ogni chiamata usa contesto 4096, massimo 1.024 token in risposta, temperatura zero, modello mantenuto caldo per cinque minuti e thinking disattivato; quest'ultima opzione evita che modelli come Gemma 4 consumino il budget nel ragionamento lasciando vuoto il JSON. Un JSON troncato o un timeout attivano un singolo tentativo con due sotto-blocchi.

Lo schema JSON richiede liste separate per persone, magistrati, mafiosi, appartenenti all'estrema destra, giornalisti, avvocati, politici, partiti, organizzazioni terroristiche, date e luoghi. Il prompt considera possibili errori ASR e nomi propri in minuscolo; la normalizzazione pulisce i nomi, deduplica i tag e converte date italiane complete come `23 maggio 1992` in `#data/1992-05-23`. Accetta date complete e anni isolati, ma scarta valori non validi come `92` o il numero iniziale di un titolo. Mafia e Cosa nostra non vengono classificate come organizzazioni terroristiche senza una qualifica esplicita nel testo.

Per ridurre i falsi positivi, un nome viene classificato come politico solo se il testo vicino dichiara un incarico o ruolo politico esplicito. La sola presenza in un contesto politico non basta; magistrati, giornalisti, avvocati e altre professioni non vengono automaticamente convertiti in politici. Anche con queste regole il modello può omettere o attribuire ruoli in modo errato: controllare sempre i tag generati prima della pubblicazione.

Per compensare omissioni del modello su trascrizioni ASR, l'app integra alcuni ruoli solo in presenza di indizi testuali locali: magistrato se un titolo giudiziario precede il nome o se la persona è soggetto di attività investigative collegate a una Procura; mafioso se è indicata come pentito in un contesto di mafia, oppure come collaboratore di giustizia nell'elenco dei nomi associati al papello. Le altre menzioni di collaboratori non vengono automaticamente classificate come mafiose.

## Output e sovrascrittura

- L'indice standard si chiama `lista_obsidian.md`.
- Le note AI si chiamano come i rispettivi `.txt`, con estensione `.md`.
- Indice e note sono salvati tutti nella directory di output scelta.
- Se uno dei file di destinazione esiste già, la generazione si interrompe senza sovrascriverlo. Attivare **Sovrascrivi i file esistenti** per sostituire i file in conflitto.
- La cache temporanea usata per conservare i testi originali durante il flusso AI è locale e viene eliminata dopo il salvataggio riuscito o alla chiusura dell'app.

## Test

Dalla root del workspace:

```powershell
python -m unittest discover -s APP_TxtToObsidian -p test_app.py -v
node --test APP_TxtToObsidian\test_app_js.cjs
```

I test coprono estrazione dei riferimenti, risoluzione per numero, caricamento senza indice da cartella o selettore, generazione delle note selezionate, formattazione dei tag, note con testo completo e script CLI.

I test JavaScript richiedono Node.js 20 o successivo e verificano che la selezione della cartella senza indice mostri l'elenco anche con le impostazioni predefinite, oltre alla selezione AI e al mantenimento del filtro tramite indice.
