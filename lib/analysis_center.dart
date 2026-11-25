import 'dart:convert';
import 'dart:math';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart' as api;
import 'observation_weather_card.dart';

class AnalysisCenter extends StatefulWidget {
  const AnalysisCenter({
    super.key,
    required this.parcelId,
    required this.onSectionRequested,
    this.onSaved,
  });
  final String parcelId;
  final ValueChanged<int> onSectionRequested;
  final VoidCallback? onSaved;
  @override
  State<AnalysisCenter> createState() => _AnalysisCenterState();
}

class _AnalysisCenterState extends State<AnalysisCenter> {
  Map? report, schema, photo;
  Map<String, dynamic> details = {};
  bool busy = false, saving = false, photoBusy = false, wheatLeaf = false;
  Uint8List? pixels;
  String? message, pendingId, pendingJson;
  int generation = 0;
  int tab = 0;
  Future<void> draftWrites = Future.value();
  Map? get review => report?['crop_review'] as Map?;
  Map? get latest => review?['visual_context']?['latest'] as Map?;
  Map get center => review?['analysis_center'] as Map? ?? {};
  String? get draftKey => latest?['id'] == null
      ? null
      : 'analysis_center_${api.apiBaseUrl}_${api.ApiSession.instance.farmId}_${widget.parcelId}_${latest!['id']}';

  @override
  void initState() {
    super.initState();
    load();
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      recoverPhoto();
    }
  }

  @override
  void dispose() {
    generation++;
    super.dispose();
  }

  Future<void> load() async {
    final current = ++generation;
    setState(() {
      busy = true;
      message = null;
    });
    try {
      final responses = await Future.wait([
        api.get(Uri.parse('${api.apiBaseUrl}/analysis-center/schema')),
        api.post(
          Uri.parse('${api.apiBaseUrl}/agronomy/analyze'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'parcel_id': widget.parcelId}),
        ),
      ]).timeout(const Duration(seconds: 110));
      if (responses.any((r) => r.statusCode != 200)) throw Exception();
      if (!mounted || current != generation) return;
      setState(() {
        schema = jsonDecode(responses[0].body) as Map;
        report = jsonDecode(responses[1].body) as Map;
        details = Map<String, dynamic>.from(
          latest?['diagnostic_details'] as Map? ?? {},
        );
      });
      final key = draftKey;
      if (key != null) {
        final saved = (await SharedPreferences.getInstance()).getString(key);
        if (saved != null && mounted && current == generation) {
          final draft = jsonDecode(saved) as Map;
          setState(() {
            details = Map<String, dynamic>.from(draft['details'] as Map);
            pendingId = draft['pending_id'];
            pendingJson = draft['pending_json'];
            message = 'Approfondimento non ancora salvato recuperato sul dispositivo.';
          });
        }
      }
    } catch (_) {
      if (mounted && current == generation) {
        setState(
          () => message = 'Centro analisi non disponibile. I dati già mostrati restano consultabili; riprova.',
        );
      }
    } finally {
      if (mounted && current == generation) setState(() => busy = false);
    }
  }

  void change(String key, dynamic value) {
    setState(() {
      details[key] = value;
      if (key == 'recent_event') details.remove('event_date');
    });
    saveDraft();
  }

  void saveDraft() {
    final key = draftKey;
    if (key == null) return;
    final content = jsonEncode({
      'details': details,
      'pending_id': pendingId,
      'pending_json': pendingJson,
    });
    draftWrites = draftWrites.catchError((_) {}).then((_) async {
      if (!await (await SharedPreferences.getInstance()).setString(
        key,
        content,
      )) {
        throw Exception();
      }
    });
    draftWrites.catchError((_) {
      if (mounted) {
        setState(
          () => message = 'Bozza ancora in memoria: il dispositivo non riesce a conservarla.',
        );
      }
    });
  }

  String uuid() {
    final random = Random.secure();
    final bytes = List.generate(16, (_) => random.nextInt(256));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    final h = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return '${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
  }

  Future<void> save() async {
    if (latest == null || busy || saving) return;
    final originalKey = draftKey;
    final payload = Map<String, dynamic>.from(latest!);
    payload.remove('id');
    payload.remove('created_at');
    payload['diagnostic_details'] = details;
    final encoded = jsonEncode(payload);
    if (pendingJson != encoded) {
      pendingId = uuid();
      pendingJson = encoded;
    }
    saveDraft();
    setState(() {
      saving = true;
      message = null;
    });
    try {
      await draftWrites;
      final r = await api
          .put(
            Uri.parse('${api.apiBaseUrl}/observations/$pendingId'),
            headers: {'Content-Type': 'application/json'},
            body: pendingJson,
          )
          .timeout(const Duration(seconds: 75));
      if (r.statusCode != 200) throw Exception();
      if (originalKey != null) {
        await (await SharedPreferences.getInstance()).remove(originalKey);
      }
      pendingId = null;
      pendingJson = null;
      if (mounted) setState(() => tab = 0);
      widget.onSaved?.call();
      if (mounted) await load();
    } catch (_) {
      if (mounted) {
        setState(
          () => message = 'Salvataggio non completato: la bozza resta sul dispositivo. Riprova senza perdere le risposte.',
        );
      }
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Future<void> recoverPhoto() async {
    try {
      final lost = await ImagePicker().retrieveLostData();
      if (lost.files?.isNotEmpty ?? false) {
        await preparePhoto(lost.files!.first);
      }
    } catch (_) {
      /* No upload, even when recovery fails. */
    }
  }

  Future<void> choosePhoto(ImageSource source) async {
    try {
      final file = await ImagePicker().pickImage(
        source: source,
        maxWidth: 1280,
        maxHeight: 1280,
        imageQuality: 85,
        requestFullMetadata: false,
      );
      if (file != null) await preparePhoto(file);
    } catch (_) {
      if (mounted) {
        setState(
          () => message = 'Foto non disponibile. Controlla i permessi o scegli un’immagine dalla galleria.',
        );
      }
    }
  }

  Future<void> preparePhoto(XFile file) async {
    if (await file.length() > 20_000_000) {
      throw const FormatException('Foto troppo grande');
    }
    final bytes = await file.readAsBytes();
    final codec = await ui.instantiateImageCodec(
      bytes,
      targetWidth: 768,
      allowUpscaling: false,
    );
    final frame = await codec.getNextFrame();
    final encoded = await frame.image.toByteData(
      format: ui.ImageByteFormat.png,
    );
    frame.image.dispose();
    codec.dispose();
    if (encoded == null || encoded.lengthInBytes > 4_000_000) {
      throw const FormatException('Scegli un dettaglio più piccolo');
    }
    if (mounted) {
      setState(() {
        pixels = encoded.buffer.asUint8List();
        photo = null;
        wheatLeaf = false;
      });
    }
  }

  Future<void> comparePhoto() async {
    if (pixels == null || photoBusy) return;
    setState(() {
      photoBusy = true;
      message = null;
    });
    try {
      final r = await api
          .post(
            Uri.parse('${api.apiBaseUrl}/analysis-center/photo'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'parcel_id': widget.parcelId,
              'image_base64': base64Encode(pixels!),
              'wheat_leaf_confirmed': wheatLeaf,
            }),
          )
          .timeout(const Duration(seconds: 75));
      if (r.statusCode != 200) throw Exception();
      if (mounted) setState(() => photo = jsonDecode(r.body) as Map);
    } catch (_) {
      if (mounted) {
        setState(
          () => message = 'Confronto foto non riuscito. La foto resta qui; puoi riprovare o proseguire con i segni osservati.',
        );
      }
    } finally {
      if (mounted) setState(() => photoBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final candidates = center['candidates'] as List? ?? [];
    final questions = center['questions'] as List? ?? [];
    final signs = Set<String>.from(details['signs'] as List? ?? []);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Centro analisi',
          style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        const Text(
          'Confronta gli input, restringi le piste e scegli il prossimo controllo utile.',
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 6,
          children: [
            for (final entry in const {
              0: 'Quadro',
              1: 'Rilievo',
              2: 'Foto',
            }.entries)
              ChoiceChip(
                label: Text(entry.value),
                selected: tab == entry.key,
                onSelected: busy || saving
                    ? null
                    : (_) => setState(() => tab = entry.key),
              ),
          ],
        ),
        FilledButton.icon(
          onPressed: busy || saving ? null : load,
          icon: const Icon(Icons.manage_search),
          label: Text(busy ? 'Analisi degli input…' : 'Aggiorna il quadro'),
        ),
        if (busy) const LinearProgressIndicator(),
        if (message != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: Text(message!),
          ),
        if (report != null) ...[
          const SizedBox(height: 12),
          Text(
            '${center['headline'] ?? 'Completa un nuovo rilievo'}',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          if (latest == null)
            TextButton(
              onPressed: () => widget.onSectionRequested(3),
              child: const Text('Aggiungi il rilievo delle piante'),
            ),
          if (latest != null)
            Text(
              'Rilievo del ${ObservationWeatherCard.dateLabel(latest!['observed_at'])} · data reale mantenuta',
            ),
          if (tab == 0) ...[
            if (review?['observation_weather'] is Map)
              ObservationWeatherCard(data: review!['observation_weather']),
            for (final note in center['quality_notes'] as List? ?? [])
              Text('Da chiarire: $note'),
            if (questions.isNotEmpty)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Per avere più focus',
                        style: TextStyle(fontWeight: FontWeight.bold),
                      ),
                      for (final q in questions.take(3))
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text('${q['text']}'),
                          subtitle: Text('${q['reason']}'),
                        ),
                      TextButton(
                        onPressed: () => setState(() => tab = 1),
                        child: const Text('Approfondisci il rilievo'),
                      ),
                    ],
                  ),
                ),
              ),
            if (candidates.isNotEmpty)
              const Text(
                'Piste da distinguere',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
            for (final c in candidates)
              ExpansionTile(
                tilePadding: EdgeInsets.zero,
                title: Text('${c['title']}'),
                subtitle: Text(
                  const {
                        'focused': 'Segni o misure più mirati, da confermare',
                        'to_verify': 'Da approfondire',
                        'less_supported': 'Un dato indebolisce questa pista',
                        'conflicting_inputs': 'Prima chiarisci i dati',
                      }[c['status']] ??
                      'Da verificare',
                ),
                children: [
                  for (final e in const {
                    'supporting': 'A favore',
                    'contradicting': 'Non concorda',
                    'missing': 'Da verificare',
                  }.entries)
                    for (final text in c[e.key] as List? ?? [])
                      ListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        title: Text('${e.value}: $text'),
                      ),
                  Text('${c['next_check']}'),
                ],
              ),
            if (center['temporal_note'] != null)
              Text('${center['temporal_note']}'),
          ],
          if (tab == 1 && latest != null && schema != null) ...[
            const SizedBox(height: 18),
            const Text(
              'Approfondisci il rilievo',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const Text(
              'Seleziona solo i segni che riesci a confermare. Lascia “Non so” per ciò che non hai controllato.',
            ),
            for (final e in (schema!['signs'] as Map).entries)
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                dense: true,
                title: Text('${e.value}'),
                value: signs.contains(e.key),
                onChanged: saving
                    ? null
                    : (value) {
                        final updated = Set<String>.from(signs);
                        if (value == true) {
                          updated.add('${e.key}');
                        } else {
                          updated.remove(e.key);
                        }
                        change('signs', updated.toList()..sort());
                      },
              ),
            for (final e in const {
              'field_pattern': 'Distribuzione nel campo',
              'progression': 'Andamento',
              'recent_event': 'Evento da confrontare',
            }.entries)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: DropdownButtonFormField<String>(
                  key: ValueKey('${latest!['id']}-${e.key}-${details[e.key]}'),
                  isExpanded: true,
                  initialValue: '${details[e.key] ?? 'unknown'}',
                  decoration: InputDecoration(labelText: e.value),
                  items: [
                    for (final option
                        in (schema!['choices'][e.key] as Map).entries)
                      DropdownMenuItem(
                        value: '${option.key}',
                        child: Text(
                          '${option.value}',
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                  ],
                  onChanged: saving
                      ? null
                      : (value) {
                          if (value != null) change(e.key, value);
                        },
                ),
              ),
            if (!['unknown', 'none', null].contains(details['recent_event']))
              TextButton.icon(
                icon: const Icon(Icons.calendar_today),
                label: Text(
                  details['event_date'] == null
                      ? 'Data dell’evento, se nota'
                      : ObservationWeatherCard.dateLabel(details['event_date']),
                ),
                onPressed: saving
                    ? null
                    : () async {
                        final end = DateTime.parse(latest!['observed_at']);
                        final selected = await showDatePicker(
                          context: context,
                          initialDate:
                              DateTime.tryParse('${details['event_date']}') ??
                              end,
                          firstDate: DateTime(2000),
                          lastDate: end,
                        );
                        if (selected != null) {
                          change(
                            'event_date',
                            selected.toIso8601String().substring(0, 10),
                          );
                        }
                      },
              ),
            FilledButton(
              onPressed: busy || saving ? null : save,
              child: Text(
                saving ? 'Salvataggio…' : 'Salva approfondimento e rianalizza',
              ),
            ),
            const Text(
              'Salva un nuovo approfondimento con la stessa data del rilievo; conserva le osservazioni precedenti.',
            ),
            TextButton(
              onPressed: () => widget.onSectionRequested(3),
              child: const Text(
                'Registra un nuovo rilievo o completa i dettagli delle piante',
              ),
            ),
          ],
          if (tab == 2) ...[
            const SizedBox(height: 18),
            const Text(
              'Confronto dalle foto',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            Text(
              '${schema?['vision']?['message'] ?? 'Caricamento del modello interno…'}',
            ),
            const Text(
              'Fotografa una foglia intera e un dettaglio nitido; confronta piante sane e interessate. Centra la foglia, evita riflessi e sfondi predominanti.',
            ),
            Wrap(
              spacing: 8,
              children: [
                OutlinedButton.icon(
                  onPressed: photoBusy
                      ? null
                      : () => choosePhoto(ImageSource.gallery),
                  icon: const Icon(Icons.photo_library_outlined),
                  label: const Text('Scegli foto'),
                ),
                if (!kIsWeb &&
                    [
                      TargetPlatform.android,
                      TargetPlatform.iOS,
                    ].contains(defaultTargetPlatform))
                  OutlinedButton.icon(
                    onPressed: photoBusy
                        ? null
                        : () => choosePhoto(ImageSource.camera),
                    icon: const Icon(Icons.camera_alt_outlined),
                    label: const Text('Scatta foto'),
                  ),
              ],
            ),
            if (pixels != null) ...[
              Image.memory(pixels!, height: 190, fit: BoxFit.contain),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Confermo: è una foglia di frumento'),
                value: wheatLeaf,
                onChanged: photoBusy
                    ? null
                    : (value) => setState(() => wheatLeaf = value ?? false),
              ),
              FilledButton.tonal(
                onPressed: photoBusy || !wheatLeaf ? null : comparePhoto,
                child: Text(
                  photoBusy
                      ? 'Confronto locale…'
                      : 'Confronta nel server AgroPlan',
                ),
              ),
              const Text(
                'La foto va solo al tuo server AgroPlan; nessun servizio AI esterno. Il confronto resta temporaneo: salva nel rilievo i segni che confermi.',
              ),
            ],
            if (photo != null) ...[
              Text('${photo!['recognition']['message']}'),
              if (photo!['recognition']['status'] == 'experimental_match') ...[
                Text(
                  const {
                        'brown_rust': 'Per verificare la prima corrispondenza, cerca piccole pustole brune sparse.',
                        'yellow_rust': 'Per verificarla, osserva le pustole gialle e la loro disposizione; sulle foglie giovani le strisce possono essere poco evidenti.',
                        'septoria': 'Per verificarla, cerca puntini neri nelle lesioni mature e confronta foglie inferiori e superiori.',
                        'powdery_mildew': 'Per verificarla, controlla se la patina bianca è crescita superficiale e distinguila da polvere o residui.',
                        'healthy': 'Se osservi sintomi, prosegui con il percorso guidato: la somiglianza a riferimenti sani non esclude altre cause.',
                      }[photo!['recognition']['candidates'][0]['label']] ??
                      'Confronta i segni visibili nel rilievo.',
                ),
                TextButton(
                  onPressed: () => setState(() => tab = 1),
                  child: const Text('Conferma solo i segni che osservi'),
                ),
              ],
              for (final issue in photo!['quality']['issues'] as List)
                Text('$issue'),
              for (final c in photo!['recognition']['candidates'] as List)
                ExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  title: Text('${c['title']}'),
                  subtitle: const Text(
                    'Proposta sperimentale da confrontare con i segni osservati.',
                  ),
                  children: [
                    PhotoReference(
                      key: ValueKey(c['reference_id']),
                      id: '${c['reference_id']}',
                    ),
                  ],
                ),
              for (final limit
                  in photo!['recognition']['limitations'] as List? ?? [])
                Text('$limit', style: const TextStyle(fontSize: 12)),
            ],
          ],
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: const Text('Input letti e fonti'),
            children: [
              for (final input in center['coverage'] as List? ?? [])
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text('${input['label']}'),
                  subtitle: Text('${input['detail']}'),
                ),
              for (final source in center['sources'] as List? ?? [])
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text('${source['title']}'),
                  subtitle: Text('${source['section']}'),
                  trailing: IconButton(
                    icon: const Icon(Icons.copy),
                    tooltip: 'Copia fonte',
                    onPressed: () => Clipboard.setData(
                      ClipboardData(text: '${source['url']}'),
                    ),
                  ),
                ),
              for (final limit in center['limitations'] as List? ?? [])
                Text('$limit', style: const TextStyle(fontSize: 12)),
            ],
          ),
        ],
      ],
    );
  }
}

class PhotoReference extends StatefulWidget {
  const PhotoReference({super.key, required this.id});
  final String id;
  @override
  State<PhotoReference> createState() => _PhotoReferenceState();
}

class _PhotoReferenceState extends State<PhotoReference> {
  late Future<api.Response> response;
  @override
  void initState() {
    super.initState();
    response = api.get(
      Uri.parse(
        '${api.apiBaseUrl}/analysis-center/references/${Uri.encodeComponent(widget.id)}',
      ),
    );
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<api.Response>(
    future: response,
    builder: (context, snapshot) {
      final result = snapshot.data;
      if (snapshot.hasError) {
        return const Text('Immagine di riferimento non disponibile.');
      }
      if (result == null) return const Text('Caricamento del riferimento…');
      if (result.statusCode != 200) {
        return const Text('Immagine di riferimento non disponibile.');
      }
      return Column(
        children: [
          Image.memory(result.bodyBytes, height: 180, fit: BoxFit.contain),
          Text(
            'Riferimento ${widget.id} · Long et al. 2023, John Innes Centre · CC BY 4.0',
            style: const TextStyle(fontSize: 11),
          ),
          const SelectableText(
            'https://doi.org/10.5281/zenodo.7573133',
            style: TextStyle(fontSize: 11),
          ),
          const Text(
            'Foto etichettata della raccolta: la somiglianza non conferma la stessa causa.',
          ),
        ],
      );
    },
  );
}
