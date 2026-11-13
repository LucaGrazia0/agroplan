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

Se il vecchio database contiene dati, viene creato un backup verificato **prima** della migrazione in `backend/backups/`. Nell’uso locale senza password i record precedenti vengono associati all’azienda locale; in modalità con account l’associazione viene scelta esplicitamente nel primo accesso. I confini delle particelle, che prima erano conservati solo nel browser, si importano con **Importa particelle precedenti**, usando lo stesso browser e l’origine del vecchio avvio. Le copie precedenti vengono conservate.

Il precedente `backend/start_mac.sh` ora avvia lo stesso percorso completo. Per cambiare porta:

```sh
bash 'Avvia AgroPlan.command' --port 8092
```

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

La configurazione propone un servizio **Starter con disco persistente da 1 GB**, montato in `/var/data`, e `AGROPLAN_DB_PATH=/var/data/agroplan.db`. **Richiede un piano a pagamento**: verificarne i costi prima di applicarla. Non viene attivato alcun piano dal codice. [Persistenza Render](https://render.com/docs/disks), [directory del servizio Render](https://render.com/docs/monorepo-support).

Per un servizio esistente: trasferire il vecchio database sul disco prima di cambiare percorso, impostare le due credenziali Copernicus nel dashboard e creare gli account dalla shell del servizio con `python backend/manage.py`. I dati precedenti restano riservati fino all’assegnazione esplicita. Il codice di primo avvio locale non viene trasferito alla produzione. Un eventuale primo avvio remoto richiede un `AGROPLAN_SETUP_TOKEN` casuale di almeno 32 caratteri, configurato esplicitamente dall’operatore e poi rimosso dopo l’attivazione.

Il frontend servito dalle API non richiede CORS aggiuntivo. Per un client web su un’origine diversa impostare `CORS_ORIGINS`; per client nativi compilare con l’URL HTTPS reale del backend tramite `--dart-define=AGROPLAN_API_URL=...`.

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
