# AgroPlan

App per particelle agricole, Sentinel-2, meteo, suolo, cicli colturali e BBCH. Interfaccia Flutter e API FastAPI vengono servite **dallo stesso indirizzo**: non occorre collegare manualmente due server. Gli account e i dati sono separati per azienda. Stato: alpha con test automatici e verifiche reali delle integrazioni; le segnalazioni agronomiche restano esplorative.

## Avvio completo sul Mac

Aprire **Avvia AgroPlan.command** con un doppio clic, oppure dal terminale nella cartella del progetto:

```sh
bash 'Avvia AgroPlan.command'
```

L’avvio prepara un ambiente Python isolato in `.local/runtime`, installa le versioni verificate e compila l’interfaccia solo se necessario. Quando la build è già aggiornata, non serve avviare Flutter. Alla prima compilazione occorrono Python 3.12 e Flutter 3.47.6 / Dart 3.13.5; `FLUTTER_BIN` permette di scegliere un’installazione Flutter specifica.

L’app si apre su **http://localhost:8091** direttamente, **senza nome utente o password**. Questa modalità è limitata al Mac: il servizio ascolta solo sull’interfaccia locale e rifiuta l’accesso senza credenziali da host o origini esterne. I dati locali precedenti vengono mantenuti nell’azienda locale; gli eventuali account già creati restano conservati.

Per ripristinare l’accesso con account, riavviare il servizio usando `bash 'Avvia AgroPlan.command' --require-password`. In questa modalità il primo account si crea con un collegamento locale riservato e una password scelta dal proprietario. Il deploy Render mantiene l’autenticazione.

Se il vecchio database contiene dati, viene creato un backup verificato **prima** della migrazione in `backend/backups/`. Nell’uso locale senza password i record precedenti vengono associati all’azienda locale; in modalità con account l’associazione viene scelta esplicitamente nel primo accesso. Le copie storiche conservate nel browser non vengono importate automaticamente nella nuova area di lavoro.

Il precedente `backend/start_mac.sh` ora avvia lo stesso percorso completo. Per cambiare porta:

```sh
bash 'Avvia AgroPlan.command' --port 8092
```

## Nuovo avvio e archivi (1.6.0)

Un’area vuota presenta i passaggi per creare la prima particella, senza dati dimostrativi precaricati. **Area di lavoro e archivi** permette di ripartire da zero: archivia le particelle dell’azienda e conserva i relativi cicli, analisi e osservazioni. **Ripristina** recupera l’archivio insieme alle eventuali nuove particelle. Il collegamento del dispositivo resta valido.

La versione dell’area di lavoro viene verificata prima di caricare la copia locale e prima di sincronizzare. Dopo un azzeramento le vecchie copie e modifiche in attesa vengono conservate in un backup locale riservato, poi escluse dalla nuova area. Server, abbinamento e altre aziende restano indipendenti. Serve una connessione al primo avvio; dopo una verifica riuscita resta disponibile la copia offline. Le copie storiche non vengono importate automaticamente.

Gli archivi sono aziendali, recuperabili e inclusi nell’esportazione del database: non costituiscono una cancellazione definitiva. Le richieste concorrenti con una versione precedente vengono rifiutate. Per il servizio Render, anche gli archivi dipendono dalla durata del database gratuito della prova.

## IPA per iPhone e iPad

Il workflow **AgroPlan IPA** compila su macOS con Xcode e produce l’artefatto **AgroPlan-IPA**, contenente `AgroPlan.ipa`, peso effettivo e checksum. È una build **Release arm64 non firmata** per SideStore/iLoader/AltStore: la firma e l’installazione avvengono con lo strumento scelto. Non è una distribuzione TestFlight. Il primo avvio permette di scegliere un server AgroPlan HTTPS; l’indirizzo viene conservato sul dispositivo e si può cambiare con **Configura server** nella schermata di accesso. Il launcher senza password del Mac resta limitato al Mac: `localhost` sull’iPhone indica il telefono.

Per ridurre il peso vengono usati tree shaking delle icone, simboli Dart separati e compressione ZIP massima. I simboli sono conservati nell’artefatto separato **AgroPlan-debug-symbols**; non vengono inclusi nell’IPA. L’app non contiene runtime Python, database del Mac o credenziali dei servizi. Il backend deve essere attivo e raggiungibile per usare le integrazioni.

Su un Mac con Xcode completo e Flutter installati:

```sh
python3 scripts/build_ios.py
# Facoltativo: preconfigurare un server reale, invece di sceglierlo nell’app.
python3 scripts/build_ios.py --api-url https://TUO-SERVER
```

Il risultato si trova in `build/ios/ipa/AgroPlan.ipa`. Il peso del file viene misurato dopo la compilazione; lo spazio occupato dopo l’installazione sarà maggiore.

## Credenziali e collegamenti

Le credenziali Copernicus vanno solo in `backend/.env`, copiando `backend/.env.example` se il file non esiste. Non copiarle nel frontend. Le altre fonti configurate non richiedono chiavi nel client.

Il pulsante **Verifica collegamenti** nella barra dell’app prova realmente:

- autenticazione Copernicus;
- storico Open-Meteo con ET0 e storico di riserva NASA POWER;
- previsioni MET Norway;
- cartografia del suolo Emilia-Romagna;
- mappe OpenStreetMap e immagini Esri.

Gli esiti vengono aggiornati al massimo una volta al minuto per la stessa zona. Fuori dalla copertura cartografica configurata, il suolo viene indicato come non coperto; le analisi manuali rimangono disponibili.

La diagnostica da terminale usa le credenziali del backend senza scriverle nei risultati:

```sh
.local/runtime/bin/python scripts/check_integrations.py --full --output .local/integrations.json
.local/runtime/bin/python scripts/smoke_live.py --output .local/live-smoke.json
```

Il secondo comando usa un database temporaneo e servizi esterni reali: verifica primo account, accesso, particelle, colture, BBCH, meteo, suolo, NDVI, DVI, immagini, statistiche, cancellazione e revoca della sessione. Non modifica i dati aziendali. Richiede rete e una piccola quantità della quota Copernicus dell’account configurato.

## Salvataggi e account

Le particelle sono conservate sul server e in una cache locale separata per **server e azienda**. Le modifiche offline vengono ritentate con **Sincronizza**. Le revisioni impediscono sovrascritture silenziose tra dispositivi: l’app chiede quale versione conservare. Le cancellazioni lasciano una tombstone; le analisi offline hanno identificativi che impediscono duplicati se una risposta va persa.

In modalità con account, le sessioni durano 8 ore; il token rimane solo in memoria. Al riavvio si accede nuovamente. Uscire revoca la sessione quando il server è raggiungibile. Le copie locali rimangono sul dispositivo per il recupero offline: usare un profilo dispositivo riservato alle persone autorizzate.

Gli altri account sono creati dal responsabile. Usare lo stesso identificativo azienda solo quando si vuole condividere intenzionalmente l’accesso ai dati:

```sh
.local/runtime/bin/python backend/manage.py create-user collega --farm azienda-locale
.local/runtime/bin/python backend/manage.py set-password collega
.local/runtime/bin/python backend/manage.py disable-user collega
.local/runtime/bin/python backend/manage.py claim-legacy --farm azienda-locale
```

L’ultimo comando assegna i record precedenti ancora privi di proprietario: usarlo solo per l’azienda a cui appartengono. Le operazioni sulle password avvengono in modo interattivo. La registrazione iniziale dal browser è disabilitata dopo la creazione del primo account e richiede un codice casuale generato dal launcher.

## Pubblicazione online

`render.yaml` ora compila **anche il frontend** tramite `scripts/render_build.sh`, avvia le API dalla radice del repository e serve l’app allo stesso URL. Le risorse grafiche Flutter vengono incluse nel bundle. La build web non contiene indirizzi localhost o URL segnaposto: usa l’origine da cui è stata aperta.

Il servizio esistente è **https://agroplan-backend.onrender.com**, piano **Free**. Il backend mobile si compila senza Flutter su Render. `render.yaml` usa un database PostgreSQL **Free** separato tramite `DATABASE_URL`: il filesystem del web service non conserva i dati ai riavvii. Il database gratuito di questa prova scade il **13 dicembre 2026**: esportare i dati prima della scadenza. Nessun piano a pagamento è configurato. Le credenziali Copernicus e del database restano solo nel backend.

Per iPhone è disponibile un abbinamento monouso, emesso dall’amministratore e valido per 7 giorni. Il codice viene scambiato con una sessione di 90 giorni, conservata nel Portachiavi e revocabile con Esci o disabilitando l’account. Il codice e la sessione non sono inclusi nell’IPA; non inviarli in chat. Il Mac mantiene l’accesso locale senza password.

Il frontend servito dalle API non richiede CORS aggiuntivo. Per un client web su un’origine diversa impostare `CORS_ORIGINS`; per client nativi scegliere il server HTTPS nell’app oppure preconfigurarlo durante la compilazione tramite `--dart-define=AGROPLAN_API_URL=...`.

## Backup e ripristino

`AGROPLAN_DB_PATH` sceglie il database; in locale il valore predefinito è `backend/agroplan.db`. SQLite usa WAL e le connessioni vengono chiuse dopo ogni operazione. Per un backup coerente anche a server attivo:

```sh
.local/runtime/bin/python backend/manage.py backup /percorso-riservato/agroplan-2026-11-12.sqlite
```

La destinazione deve essere nuova; il comando verifica l’integrità e imposta permessi al solo proprietario. Conservare copie anche fuori dal volume del servizio. Per ripristinare: fermare il backend, conservare database e relativi WAL/SHM correnti, verificare il backup con `PRAGMA integrity_check`, sostituire il database con il backup verificato e riavviare. Prima di riaprire il servizio revocare le sessioni presenti nel backup ripristinato.

## Sviluppo e test

Le versioni runtime verificate sono in `backend/requirements-lock.txt`; `requirements.txt` descrive gli intervalli per gli aggiornamenti futuri.

```sh
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
backend/.venv/bin/python -m pytest -q
flutter pub get
flutter analyze
flutter test
python3.12 scripts/build_web.py
```

Per lavorare con hot reload e API separate:

```sh
backend/.venv/bin/python -m uvicorn main:app --app-dir backend --port 8000
flutter run -d chrome --web-port 8091 --dart-define=AGROPLAN_API_URL=http://127.0.0.1:8000
```

La CI esegue test backend offline, analisi e test Flutter, e build web. Non usa credenziali esterne. Le verifiche live sono separate per non consumare quote durante ogni commit.

## Fonti e limiti

- Sentinel-2 L2A tramite Copernicus: NDVI/DVI, maschera SCL, immagini ritagliate sul poligono e serie temporali. I giorni del selettore sono unici e ordinati. La prima visualizzazione cerca un’acquisizione disponibile e carica anche le statistiche; i giorni mancanti non vengono simulati.
- Open-Meteo è la prima fonte per lo storico con ET0; l’assenza delle previsioni non scarta uno storico valido. NASA POWER è il fallback, senza ET0 nell’integrazione attuale. MET Norway integra le previsioni. Finestre con date duplicate o mancanti non risultano complete.
- La cartografia Emilia-Romagna è interrogata su punti rappresentativi. Codici e nomi delle unità vengono mostrati senza trasformarli in analisi di laboratorio; non viene calcolata una media pesata sull’intera superficie.
- Gli avvisi non diagnosticano malattie o carenze e non prescrivono irrigazioni, trattamenti o concimazioni.

La sorgente attiva è in `lib/`. Copie storiche, ambienti, build, database, collegamenti di attivazione e credenziali sono esclusi dal repository.

## Analisi colturale

Il pulsante **Analisi colturale aziendale** riepiloga i record di tutte le particelle dell’azienda, incluse quelle prive di confini da recuperare. La scheda della particella integra ciclo e BBCH, copertura dei dati, ultimo campione del suolo e indicatori meteo. L’opzione **Aggiorna anche i dati satellitari** richiede fino a tre acquisizioni recenti e conserva i risultati per dodici ore, invalidandoli se cambiano i confini. Il confronto NDVI richiede due date distinte, entro 45 giorni, con almeno il 50% di pixel validi. Le variazioni non sono diagnosi di malattie o stime di resa. Senza meteo il servizio mantiene la sintesi dei record salvati e segnala il dato mancante.

La sintesi non propone dosi irrigue o di fertilizzanti sulla base del solo NDVI o del bilancio pioggia–ET₀. [FAO 56](https://www.fao.org/4/x0490e/x0490e0a.htm). La compilazione IPA viene eseguita solo dopo il superamento dei test dell’analisi.

## Connessione iPhone e ripristino

La versione 1.1.1 verifica che `/auth/status` esista prima di proporre qualsiasi accesso. Se Render non è ancora aggiornato o è offline, mostra un messaggio specifico e permette di riprovare; non presenta un modulo password inutile. Sul client nativo la prima scelta è l’abbinamento monouso. L’accesso con account resta una scelta esplicita.

L’amministratore può migrare una copia SQLite in un database PostgreSQL vuoto e generare un codice locale riservato con `backend/transfer.py`. Il comando rifiuta una destinazione con dati o account esistenti, verifica il backup SQLite e conserva gli identificativi e le sequenze. `DATABASE_URL` deve essere configurato solo nell’ambiente backend, mai negli argomenti o nel client.

```sh
python backend/transfer.py migrate --source backend/agroplan.db --farm azienda-locale --owner proprietario --backup .local/backups/pre-cloud.sqlite
python backend/transfer.py pair-device --owner proprietario --output .local/abbinamento-iphone.txt
python backend/transfer.py backup --output .local/backups/cloud.json
```

Il codice va copiato dal file privato nel campo **Codice di abbinamento** dell’iPhone una sola volta. Non inserirlo in chat. Per PostgreSQL usare il backup JSON di `transfer.py`; il comando `manage.py backup` è riservato a SQLite.

## Analisi integrata e motore documentato (1.5.0)

La scheda della particella è divisa in **Analisi integrata, Suolo, Meteo, Problematiche, Coltura, Mappa e satellite**. Suolo contiene referti, parametri idrici e fonti cartografiche distinte; Meteo contiene storico, previsioni e calcoli; Problematiche raccoglie rilievi e indagine dei sintomi. Cambiare categoria di un risultato già caricato non avvia una nuova analisi. La mappa permette zoom e spostamento ma non rotazione.

**Analizza tutti gli input** aggiorna il ritorno della sezione Analisi integrata: valutazione complessiva, conclusioni motivate, tre prossime verifiche prioritarie, ulteriori controlli, input effettivamente letti e dati da completare. `backend/decision_engine.py` compone i risultati documentati del motore senza aggiungere soglie diagnostiche. Confronta sintomi e meteo solo quando le date sono compatibili; distingue osservazioni strutturate, indizi testuali e assenza di dati. La priorità del sopralluogo è un criterio organizzativo dell’app, non una soglia di trattamento. L’assenza di sintomi segnalati non diventa una certificazione sanitaria. Conclusioni e azioni sono salvate nel risultato immutabile e mostrate anche nel riepilogo aziendale.

L’endpoint `/agronomy/analyze` accetta entrambe le coordinate oppure nessuna. Se mancano anche i confini, analizza i soli record salvati senza attribuire meteo a una posizione presunta. I risultati precedenti conservano il loro formato e non vengono riscritti come nuove valutazioni.

La versione 1.5 aggiunge un confronto descrittivo tra rilievi di giorni distinti, entro 30 giorni, con lo stesso contesto (parte della pianta, foglie e distribuzione). La variazione percentuale è espressa in **punti percentuali**, non viene trasformata in una diagnosi di peggioramento o guarigione e non cambia automaticamente la priorità. Il campionamento deve essere confrontabile. Le osservazioni discordanti dello stesso giorno restano esplicite.

`backend/assessment_detail.py` espone piste concorrenti con elementi a favore, elementi che non concordano e informazioni mancanti. Una misura umida dello stesso giorno non sostiene la pista della scarsità d’acqua nel profilo; non esclude un problema radicale o di assorbimento. Piste diverse possono essere compatibili contemporaneamente e non ricevono percentuali di probabilità. Domande condizionali rimandano a Problematiche, Suolo o Coltura; lo storico mostra le stesse informazioni in sola lettura.

I rilievi accettano i dettagli facoltativi `leaf_age`, `distribution`, `root_condition`, `noticed_since`. La data di comparsa non può seguire il rilievo. I dettagli sono conservati nelle bozze locali e nel payload JSON; non servono nuove tabelle. Gli invii ripetuti di vecchi rilievi restano idempotenti: i default aggiunti non riscrivono i payload storici.

Ogni analisi conserva una fotografia dei risultati, consultabile nello storico. Il motore integra i rilievi degli ultimi 14 giorni con gli indicatori colturali e ambientali. I termini nelle note sono indizi da confermare: non sono una diagnosi automatica. Evidenze, ipotesi e domande per il sopralluogo sono separate. Nessun testo o dato viene inviato a un servizio AI esterno.

Le regole e i metodi sono implementati in `backend/manual_engine.py`; edizione e bibliografia verificata sono in `backend/agronomy_knowledge.py`. Ogni risultato include identificativo del metodo, prerequisiti, misure usate, interpretazione, verifiche successive, limiti e fonti. La bibliografia non viene eseguita né aggiornata automaticamente: una modifica richiede revisione, nuova edizione e test.

- **pH:** classi descrittive della tabella 3-15 del [USDA Soil Survey Manual 2017, capitolo 3](https://www.nrcs.usda.gov/sites/default/files/2022-09/SSM-ch3.pdf), arrotondamento a un decimale. Non sono raccomandazioni di correzione o diagnosi di carenze; va confrontato il metodo analitico.
- **Acqua disponibile:** `TAW = 1000 × (θFC − θWP) × Zr`, [FAO 56, capitolo 8, equazione 82](https://www.fao.org/4/x0490e/x0490e0e.htm). Gli input percentuali volumetrici vengono divisi per 100; la profondità radicale è in metri. Umidità opzionale: esaurimento limitato tra zero e TAW, con data della misura. Profilo assunto uniforme; non si calcolano RAW, Ks o dosi irrigue.
- **Meteo:** P − ET₀ soltanto su una finestra completa. `ETc = Kc × ET₀` secondo [FAO 56, capitolo 6, equazione 58](https://www.fao.org/4/x0490e/x0490e0b.htm) soltanto con Kc fornito/verificato dall’operatore e valido per tutti i sette giorni. Non viene dedotto dal BBCH: clima, bagnature e fase richiedono verifica locale. ETc standard non equivale al consumo effettivo sotto stress.
- **Problematiche:** il metodo di [CSU Extension, Diagnosing Plant Disorders](https://extension.colostate.edu/resource/diagnosing-plant-disorders/) guida raccolta dei dettagli, contesto e cause alternative. Il collegamento sintomi/meteo richiede sovrapposizione delle date. Nessun modello patogeno-specifico, soglia di trattamento o piano nutritivo regionale è implementato.

I parametri facoltativi si salvano con GET/PUT `/agronomy/parameters/{parcel_id}`, con autorizzazione della particella, validazione di date e unità e migrazione additiva SQLite/PostgreSQL. Copia dei parametri, metodi e fonti rimane nel risultato immutabile. Nuovi referti richiedono la data effettiva del campione; quelli precedenti conservano i dati già registrati. I rilievi includono sintomi, intensità, percentuale e note, con bozze locali e invii idempotenti.

## Approfondimenti del motore (1.7.0)

Edizione `2026.11.24.1`, riferimenti verificati il 24 novembre 2026. Le funzionalità di questa sezione ampliano i limiti dell’edizione 1.5 descritta sopra; i risultati storici conservano la propria edizione.

- **RAW e Ks alla data della misura:** FAO 56, capitolo 8, equazioni 82–84 e 86–87. Serve una frazione `depletion_fraction` (p effettivo, maggiore di 0 e minore di 1) già verificata dall’operatore per coltura e domanda evaporativa alla data del profilo. Nessun p viene dedotto dal nome della coltura o dal BBCH. `RAW = p × TAW`; Dr deriva dall’umidità media della zona radicale e viene limitato tra 0 e TAW; `Ks = 1` se `Dr ≤ RAW`, altrimenti `(TAW − Dr)/(TAW − RAW)`. Senza umidità si calcola solo RAW. La fotografia del profilo non viene proiettata in avanti né moltiplicata per l’ETc settimanale. Il modello presume un profilo uniforme e non salino e non rappresenta danni radicali o anossia. Il confronto con i sintomi richiede lo stesso giorno e misure entro 7 giorni (criterio applicativo di aggiornamento).
- **Acqua irrigua:** `water_sample_date`, `water_ec_ds_m` (ECw a 25 °C) e `water_sar` nello stesso referto, separati dall’analisi del suolo. [FAO 29 Rev. 1, tabella 1 e assunzioni](https://www.fao.org/4/t0234e/t0234e01.htm): confronto orientativo della salinità ed ECw–SAR per il possibile problema di infiltrazione. Le fasce con estremo SAR condiviso mantengono entrambe le letture quando differiscono; oltre SAR 40 non si estrapola. Un’ECw bassa può coincidere con restrizioni per infiltrazione: le due letture rimangono distinte. Non è una certificazione di idoneità, potabilità o danno alla coltura. Vanno verificate le assunzioni del manuale (soprattutto condizioni aride/semiaride e suoli drenati); fonte usata e date delle irrigazioni restano domande prima di collegare un referto ai sintomi.
- **Coerenza degli input:** misure storiche esplicitamente etichettate, confronto numerico prima dell’arrotondamento, note con più occorrenze dello stesso sintomo e negazioni locali, rimozione del saldo meteo dalle ipotesi quando non coincide con il periodo del rilievo. Le parole restano indizi da confermare, non classificazione libera del linguaggio.

I nuovi campi sono facoltativi, conservati nel payload esistente e inclusi nei backup. Salvare dalla sezione Suolo mantiene i parametri Meteo letti dal server e viceversa. Le valutazioni, le piste alternative, le domande e le fonti sono incluse nel risultato immutabile. Le prove con dati sintetici usano un database separato e non riattivano le particelle archiviate.

## Coltura e fase specifica (1.8.0)

Edizione `2026.11.24.2`. La lettura BBCH usa i codici esplicitamente verificati nella [BBCH Monograph, seconda edizione 2001, copia MASAF](https://www.masaf.gov.it/flex/AppData/WebLive/Agrometeo/MIEPFY800_ORI/BBCHengl2001.pdf), chiavi Cereals e Maize (pagine PDF 14–16 e 24–25), principi generali (pagine 6–8). Il catalogo distingue frumento, orzo, avena e segale dal mais. BBCH 39, ad esempio, descrive la foglia a bandiera nei cereali e almeno nove nodi nel mais; BBCH 87 distingue maturazione pastosa dura e strato nero del mais. Un nome generico di frumento non viene trasformato in tenero o duro. Triticale, altre specie e codici non presenti nel catalogo restano da verificare e non vengono assimilati automaticamente a una specie vicina.

La sezione Coltura mostra la descrizione dei rilievi; l’analisi integrata conserva fase, fonti e limiti nel risultato. Un BBCH futuro, storico oltre 21 giorni (criterio applicativo) o precedente alla semina non diventa una fase attuale. I nuovi rilievi futuri sono rifiutati; i codici non riconosciuti già dichiarati dall’operatore restano conservati. Seme asciutto, pianta morta e prodotto raccolto non vengono trattati come una coltura in vegetazione attiva. BBCH 00 può precedere la semina, coerentemente con la descrizione del seme.

L’ingiallimento viene confrontato con una maturazione registrata **nello stesso giorno**, mantenendo le altre possibili cause. Il BBCH non certifica la causa del sintomo e non diventa una dose, un Kc o una finestra di trattamento. Le macrofasi possono sovrapporsi: non vengono sottratti codici per stimare velocità di crescita e non si deduce una fase dal calendario o dalla temperatura.
