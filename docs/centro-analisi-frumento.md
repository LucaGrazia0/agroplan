# Centro analisi e riconoscimento fotografico del frumento

Il Centro analisi è una sezione separata della scheda particella. Legge gli stessi input dell’analisi integrata, conserva i calcoli idrici e il contesto meteorologico dei 14 giorni precedenti e aggiunge un percorso di indagine. Distingue osservazioni generali, segni più specifici, elementi che indeboliscono una pista e verifiche ancora da fare. Non elimina una causa perché manca un dato e permette più cause concomitanti.

Le risposte di approfondimento vengono salvate come un nuovo rilievo immutabile con la stessa data reale e tutti i dettagli precedenti. Le bozze sono separate per server, azienda, particella e rilievo; un errore di rete mantiene le risposte. Ogni nuova analisi conserva il Centro analisi nel risultato storico.

## Fonti e regole

- [American Phytopathological Society, Plant Disease Diagnosis](https://www.apsnet.org/edcenter/Pages/PlantDiseaseDiagnosis.aspx): metodo per distinguere sintomi, segni e possibili cause. Cronologia e confronto tra campioni orientano le verifiche; le forme visibili possono avere spiegazioni diverse.
- [Nebraska Extension, Broderick e Jackson-Ziems (2019)](https://cropwatch.unl.edu/2019/using-symptom-distribution/): distribuzione nel campo, avvallamenti e tracce possono suggerire controlli del suolo o delle attività. Sono indizi con eccezioni, non criteri per escludere malattie.
- [AHDB, Yellow rust](https://ahdb.org.uk/knowledge-library/yellow-rust-in-wheat): disposizione delle pustole da osservare nel frumento. Un segno dichiarato rende la pista più mirata, senza confermare il patogeno.
- [AHDB, Septoria tritici](https://ahdb.org.uk/knowledge-library/septoria-tritici-in-winter-wheat): lesioni e picnidi da controllare; quelli non ancora osservati non sono considerati assenti. La latenza impedisce di trasformare il solo contesto meteo in una ricostruzione dell’infezione.
- [UC IPM, Powdery mildew](https://ipm.ucanr.edu/agriculture/small-grains/powdery-mildew/): crescita superficiale bianca da distinguere da polvere e residui.
- [UC IPM, Barley yellow dwarf](https://ipm.ucanr.edu/agriculture/small-grains/barley-yellow-dwarf/): alterazioni di colore e vettori come elementi da approfondire, senza dedurre infezione dalla presenza di afidi.

La cronologia dell’evento rispetto all’esordio può indebolire una pista di fitotossicità o danno fisico. Un evento successivo non spiega la comparsa iniziale. L’ordine delle piste dipende dal tipo di riscontro disponibile, non da una probabilità agronomica calcolata. Il catalogo specifico parte dal frumento; per altre colture restano i controlli generali.

## Foto già classificate

La raccolta scelta è [Long, Hartley, Morris e Brown (2023), Wheat disease images (small dataset)](https://doi.org/10.5281/zenodo.7573133), John Innes Centre, licenza **CC BY 4.0**, verificata nei metadati ufficiali Zenodo. L’archivio originale ha checksum MD5 `1f8a7c660c2da137b957fb4edee3dd7d`.

| Etichetta originale | Foto |
|---|---:|
| Septoria | 349 |
| Yellow rust | 239 |
| Mildew | 161 |
| Brown rust | 128 |
| Healthy | 122 |
| Totale | 999 |

Le etichette non sono state modificate. Le immagini di lavoro sono convertite in RGB JPEG, orientate, private dei metadati e ridotte a un massimo di 640 pixel. Il corpus completo resta in `.local/vision-research/`, escluso dal repository e dai pacchetti mobili.

La preparazione usa gruppi di immagini con pixel identici o dHash a 64 bit distante al massimo quattro bit. Un gruppo resta in una sola partizione; gruppi con etichette discordanti sarebbero messi in quarantena. Nessun gruppo discordante è stato rilevato in questa preparazione. Le partizioni risultano di 696 immagini di addestramento, 152 di validazione e 151 di test. Non sono disponibili identificatori affidabili di azienda, pianta o sessione: questo controllo riduce il rischio di duplicati ma non dimostra indipendenza biologica o geografica.

## Primo modello locale, sperimentale

Il prototipo usa caratteristiche di [MobileNetV3 Small di torchvision](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.mobilenet_v3_small.html), con pesi iniziali ufficiali ImageNet1K V1 congelati, e una testa lineare addestrata sulle cinque etichette. Media, scala e pesi della testa usano solo il training. L’epoca è scelta con la balanced accuracy della validazione: 37. Il test non è usato per scegliere epoca o soglie. È un’applicazione di [transfer learning](https://docs.pytorch.org/tutorials/beginner/transfer_learning_tutorial.html), non un nuovo modello di diagnosi validato in campo.

| Partizione | Foto | Accuratezza | Balanced accuracy |
|---|---:|---:|---:|
| Addestramento | 696 | 95,98% | 97,34% |
| Validazione | 152 | 78,95% | 77,67% |
| Test interno | 151 | 84,11% (127/151) | 85,27% |

Queste metriche descrivono soltanto il test interno a questa raccolta. Non misurano prestazioni su aziende italiane, malattie non rappresentate o foto generiche. I punteggi del modello non sono probabilità diagnostiche calibrate. Una soglia applicativa di 0,85 e un margine di 0,25 segnalano il confronto come incerto quando non sono raggiunti; non sono un rilevatore validato di classi sconosciute. Foto di malattie assenti dal catalogo possono comunque ottenere punteggi alti. Non si modifica questa politica in base al test già osservato.

Il modello propone tre corrispondenze e riferimenti fotografici selezionati **esclusivamente dal training** (12 per categoria). Le foto di test non entrano nella banca di confronto. “Healthy” significa somiglianza ai riferimenti etichettati sani; non certifica salute. Le osservazioni del modello non diventano automaticamente segni confermati: l’operatore li controlla e li registra nel percorso guidato.

## Esecuzione e privacy

In questa versione il modello gira sulla CPU del server **AgroPlan**, senza API AI di altri fornitori. Serve la connessione al proprio server: non è ancora inferenza offline sul telefono. Il pacchetto statico `backend/vision_bundle/bundle.zip` contiene rete ONNX, banca di caratteristiche, 60 piccoli riferimenti e attribuzioni. Versione, checksum e metriche sono nel file adiacente `metadata.json`.

L’app ridimensiona e ricodifica l’immagine prima dell’invio, eliminando i metadati originali. Il server applica ulteriori limiti di dimensione e controlli tecnici orientativi di luce, contrasto e dettaglio. La foto completa non viene conservata né usata automaticamente per addestrare il modello. Il confronto foto è temporaneo; le osservazioni confermate vengono salvate nell’approfondimento. Accesso alla foto e ai riferimenti richiede la sessione; l’analisi richiede proprietà della particella, ciclo di frumento e conferma che si tratti di una foglia.

La [telemetria ONNX Runtime](https://github.com/microsoft/onnxruntime/blob/main/docs/Privacy.md) è disabilitata prima dell’inizializzazione nativa tramite `ORT_DISABLE_TELEMETRY=1` e anche tramite API. Il server non scarica pesi durante l’uso. Verifica i checksum del pacchetto e del modello prima di caricarli.

## Riproducibilità e prossime colture

```sh
python scripts/prepare_wheat_photos.py --archive /percorso/archivio-originale.zip --output .local/vision-research/wheat-jic-2023
# In un ambiente separato con scripts/requirements-vision-research.txt:
TORCH_HOME=.local/vision-research/torch-cache python scripts/train_wheat_vision.py --dataset .local/vision-research/wheat-jic-2023 --output .local/vision-research/wheat-model-v1
```

Prima dell’estensione occorrono foto indipendenti del frumento con diagnosi verificata, controlli di malattie fuori catalogo, stress abiotici, sfondi e casi misti. Le foto dell’utente non sono etichettate automaticamente. Per ogni nuova coltura servono una raccolta dedicata con licenza e provenienza, un catalogo di cause specifiche e nuove verifiche. Le percentuali ottenute sul frumento non si trasferiscono a orzo o mais.
