# AgroPlan

App Flutter per particelle agricole, monitoraggio Sentinel-2, meteo, analisi del suolo, cicli colturali e osservazioni BBCH. Backend FastAPI con account per azienda, sessioni revocabili e SQLite persistente. Le versioni runtime verificate sono fissate in `backend/requirements-lock.txt`; `requirements.txt` descrive gli intervalli per gli aggiornamenti futuri. Stato: alpha, con test automatici; i suggerimenti agronomici sono esplorativi e non modelli diagnostici validati.

## Avvio locale

Requisiti: Python 3.12 e Flutter 3.47.6 / Dart 3.13.5 (versioni usate dalla CI).

```sh
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
cp backend/.env.example backend/.env
```

Inserire le credenziali Copernicus in `backend/.env` per le funzioni satellitari. Meteo, particelle, colture e analisi manuali non richiedono credenziali Copernicus.

Creare un account: la password viene richiesta in modo interattivo, non va inserita negli argomenti del comando. Ogni azienda ha un identificativo; account con lo stesso `--farm` condividono intenzionalmente le particelle.

```sh
backend/.venv/bin/python backend/manage.py create-user luca --farm azienda-luca
backend/.venv/bin/python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In un secondo terminale:

```sh
flutter pub get
flutter run -d chrome --web-port 8091 --dart-define=AGROPLAN_API_URL=http://127.0.0.1:8000
```

Aprire l’app, accedere, disegnare una particella e attendere il salvataggio sul server. Registrare il ciclo colturale e una osservazione BBCH. Il pannello agronomico si aggiorna dopo ogni salvataggio. Per Android emulator usare `http://10.0.2.2:8000`; per dispositivi fisici impostare un backend raggiungibile. Su internet usare HTTPS e configurare `CORS_ORIGINS` con le origini esatte dell’app.

## Dati precedenti e sincronizzazione

La migrazione aggiunge le tabelle di accesso e proprietà senza eliminare i record esistenti. I dati agronomici precedenti sono riservati fino all’assegnazione esplicita da parte dell’amministratore:

```sh
backend/.venv/bin/python backend/manage.py claim-legacy --farm azienda-luca
```

Eseguire questa operazione solo per l’azienda proprietaria dei dati del vecchio database. Nell’app usare **Importa particelle precedenti** per copiare i confini dalle preferenze locali nell’azienda selezionata. La vecchia copia rimane intatta; l’importazione non sovrascrive particelle già presenti. La cache nuova è separata per azienda.

Il server conserva le particelle, le analisi e i cicli. Le modifiche alle particelle vengono salvate anche sul dispositivo e ritentate premendo **Sincronizza**. Le revisioni impediscono di sovrascrivere silenziosamente modifiche fatte su un altro dispositivo: in caso di conflitto l’app chiede quale versione conservare. Le cancellazioni hanno una tombstone per impedire che un dispositivo offline ricrei un campo eliminato. Le analisi di laboratorio salvate durante un’interruzione di rete restano in una coda locale e vengono inviate alla sincronizzazione successiva; un identificativo impedisce duplicati se una risposta va persa.

Le sessioni durano 8 ore e il token rimane solo in memoria; al riavvio si accede nuovamente. Uscire revoca la sessione sul server quando è raggiungibile. I dati locali rimangono sul dispositivo per il recupero offline: usare un profilo dispositivo riservato alle persone autorizzate all’azienda.

```sh
backend/.venv/bin/python backend/manage.py set-password luca
backend/.venv/bin/python backend/manage.py disable-user luca
```

Entrambi revocano le sessioni dell’account. La registrazione pubblica non è prevista: gli account vengono creati dal responsabile tramite CLI.

## Persistenza e backup

`AGROPLAN_DB_PATH` sceglie il database; in assenza di configurazione si usa `backend/agroplan.db`. Le connessioni vengono chiuse dopo ogni operazione. SQLite usa WAL e le query di modifica delle particelle verificano atomicamente proprietà e revisione.

`render.yaml` prepara un servizio **Starter con disco persistente da 1 GB**, montato in `/var/data`, e imposta `AGROPLAN_DB_PATH=/var/data/agroplan.db`. **Richiede un piano a pagamento**: verificare i costi prima di applicarlo. Non è stato attivato alcun servizio. Impostare le credenziali Copernicus e `CORS_ORIGINS` nel dashboard; creare poi gli utenti dalla shell del servizio. Se si migra un servizio esistente, esportare e trasferire il vecchio database prima di cambiare percorso. Il filesystem del piano gratuito Render non conserva le modifiche tra riavvii/deploy; non usarlo per dati reali. [Documentazione Render sui dischi](https://render.com/docs/disks).

Creare backup SQLite coerenti anche mentre il servizio è attivo (usa `sqlite3.backup`, non una copia del solo file `.db`):

```sh
backend/.venv/bin/python backend/manage.py backup /percorso-riservato/agroplan-2026-11-12.sqlite
```

La destinazione deve essere nuova; il comando verifica l’integrità e imposta permessi di lettura/scrittura al solo proprietario. Conservare copie anche fuori dal volume del servizio. Per ripristinare: fermare il backend, conservare database e relativi file WAL/SHM correnti, verificare il backup con `PRAGMA integrity_check`, sostituire il database sul volume con il backup verificato e riavviare. Il ripristino torna allo stato del backup, incluse le sessioni allora esistenti: revocarle prima di riaprire il servizio.

## Fonti e limiti

- Sentinel-2 L2A tramite Copernicus: NDVI/DVI, maschera SCL, statistiche sul poligono e acquisizioni temporali. Nessun dato satellitare simulato quando il fornitore fallisce.
- Open-Meteo è la prima fonte per lo storico completo, inclusa ET0. La mancata disponibilità delle previsioni non scarta uno storico valido. NASA POWER è il fallback: non fornisce ET0 nell’integrazione attuale; in questo caso il bilancio P − ET0 resta esplicitamente assente. MET Norway integra le previsioni quando disponibile.
- Le finestre agronomiche richiedono giorni distinti e consecutivi fino alla data dichiarata dello storico; duplicati e lacune non diventano uno storico completo.
- La ricerca automatica del suolo interroga la cartografia dell’Emilia-Romagna su punti rappresentativi. Non sostituisce analisi di laboratorio né calcola una media pesata sull’intero appezzamento.
- Gli avvisi non diagnosticano malattie, infestanti o carenze e non prescrivono irrigazioni, trattamenti o concimazioni.

## Verifiche

```sh
backend/.venv/bin/python -m pytest -q
flutter analyze
flutter test
flutter build web --release --dart-define=AGROPLAN_API_URL=https://backend.example.com
```

La CI esegue test backend offline (accessi, isolamento aziende, revisioni, cancellazioni, percorso particella → ciclo → BBCH → analisi → indicatori, fallback meteo e serie storiche), analisi Flutter, widget test e compilazione web. Non usa credenziali Copernicus e non dimostra la disponibilità corrente dei servizi esterni.

La sorgente attiva è in `lib/`; `flutter/` e `backup_*` sono copie storiche locali escluse dal repository, insieme ad ambienti virtuali, database, credenziali e file generati.
