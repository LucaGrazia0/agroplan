import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart' as api;

const symptomLabels = {
  'yellowing': 'Ingiallimento',
  'wilting': 'Appassimento',
  'spots': 'Macchie',
  'insects': 'Insetti',
  'uneven_growth': 'Crescita irregolare',
  'no_symptoms': 'Nessun sintomo evidente',
};

class FieldObservations extends StatefulWidget {
  const FieldObservations({
    super.key,
    required this.parcelId,
    required this.onChanged,
  });
  final String parcelId;
  final VoidCallback onChanged;
  @override
  State<FieldObservations> createState() => _FieldObservationsState();
}

class _FieldObservationsState extends State<FieldObservations> {
  final notes = TextEditingController(), percent = TextEditingController();
  Set<String> symptoms = {};
  String severity = 'mild', part = 'leaves';
  DateTime date = DateTime.now();
  List<dynamic> rows = [];
  bool busy = false, ready = false;
  String? message, id;
  String get draftKey =>
      'field_draft_${api.apiBaseUrl}_${api.ApiSession.instance.farmId}_${widget.parcelId}';
  Future<void> writes = Future.value();
  Map<String, dynamic> get payload => {
    'parcel_id': widget.parcelId,
    'observed_at': date.toIso8601String().substring(0, 10),
    'symptoms': symptoms.toList()..sort(),
    'severity': severity,
    'affected_percent': percent.text.trim().isEmpty
        ? null
        : double.tryParse(percent.text.replaceAll(',', '.')),
    'plant_part': part,
    'notes': notes.text.trim(),
  };
  @override
  void initState() {
    super.initState();
    restore();
  }

  Future<void> restore() async {
    try {
      final saved = (await SharedPreferences.getInstance()).getString(draftKey);
      if (saved != null && mounted) {
        final d = jsonDecode(saved) as Map<String, dynamic>;
        final p = d['payload'] as Map;
        setState(() {
          id = d['id'];
          notes.text = p['notes'];
          percent.text = p['affected_percent']?.toString() ?? '';
          symptoms = Set<String>.from(p['symptoms']);
          severity = p['severity'];
          part = p['plant_part'];
          date = DateTime.parse(p['observed_at']);
          message = 'Bozza recuperata sul dispositivo.';
        });
      }
    } catch (_) {
      if (mounted) {
        setState(
          () => message = 'Bozza non leggibile: nessun dato precedente è stato sovrascritto.',
        );
      }
    }
    if (mounted) setState(() => ready = true);
    await load();
  }

  Future<void> load() async {
    try {
      final r = await api
          .get(
            Uri.parse(
              '${api.apiBaseUrl}/observations?parcel_id=${Uri.encodeQueryComponent(widget.parcelId)}',
            ),
          )
          .timeout(const Duration(seconds: 75));
      if (r.statusCode != 200) throw Exception();
      final data = jsonDecode(r.body) as List;
      if (mounted) setState(() => rows = data);
    } catch (_) {
      if (mounted) {
        setState(
          () => message = 'Storico non disponibile. Puoi conservare una bozza sul dispositivo.',
        );
      }
    }
  }

  void draft() {
    if (!ready) return;
    final text = jsonEncode({'id': id, 'payload': payload});
    writes = writes.catchError((_) {}).then((_) async {
      final ok = await (await SharedPreferences.getInstance()).setString(
        draftKey,
        text,
      );
      if (!ok) throw Exception();
    });
    writes.catchError((_) {
      if (mounted) {
        setState(
          () =>
              message = 'Bozza non salvata: mantieni aperta questa schermata.',
        );
      }
    });
  }

  Future<void> save() async {
    final value = payload;
    final n = value['affected_percent'];
    if (symptoms.isEmpty && notes.text.trim().isEmpty) {
      setState(
        () => message = 'Descrivi ciò che hai visto o seleziona un sintomo.',
      );
      return;
    }
    if (percent.text.trim().isNotEmpty && (n == null || n < 0 || n > 100)) {
      setState(() => message = 'Inserisci una percentuale tra 0 e 100.');
      return;
    }
    var draftSaved = false;
    id ??= newId();
    setState(() {
      busy = true;
      message = null;
    });
    try {
      draft();
      await writes;
      draftSaved = true;
      final r = await api
          .put(
            Uri.parse('${api.apiBaseUrl}/observations/$id'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(value),
          )
          .timeout(const Duration(seconds: 75));
      if (r.statusCode != 200) throw Exception('server');
      await (await SharedPreferences.getInstance()).remove(draftKey);
      if (!mounted) return;
      setState(() {
        id = null;
        notes.clear();
        percent.clear();
        symptoms = {};
        message = 'Rilievo salvato. Lo ritrovi nello storico e nella prossima analisi.';
      });
      widget.onChanged();
      await load();
    } catch (_) {
      if (mounted) {
        setState(
          () => message = draftSaved
              ? 'Invio non riuscito. La bozza resta sul dispositivo: riprova con la rete disponibile.'
              : 'Salvataggio locale non riuscito. Mantieni aperta questa schermata e riprova.',
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  static String newId() {
    final random = Random.secure();
    final bytes = List.generate(16, (_) => random.nextInt(256));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    final h = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return '${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
  }

  @override
  void dispose() {
    notes.dispose();
    percent.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      const Text(
        'Cosa vedi sulle piante?',
        style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
      ),
      const Text(
        'Registra ciò che osservi, anche quando non noti sintomi. Il rilievo non è una diagnosi.',
      ),
      TextButton.icon(
        onPressed: busy || !ready
            ? null
            : () async {
                final picked = await showDatePicker(
                  context: context,
                  initialDate: date,
                  firstDate: DateTime(2000),
                  lastDate: DateTime.now(),
                );
                if (picked != null) {
                  setState(() {
                    id = null;
                    date = picked;
                  });
                  draft();
                }
              },
        icon: const Icon(Icons.calendar_today),
        label: Text('Data: ${date.day}/${date.month}/${date.year}'),
      ),
      Wrap(
        spacing: 6,
        runSpacing: 4,
        children: [
          for (final item in symptomLabels.entries)
            FilterChip(
              label: Text(item.value),
              selected: symptoms.contains(item.key),
              onSelected: busy || !ready
                  ? null
                  : (selected) {
                      setState(() {
                        id = null;
                        if (selected) {
                          if (item.key == 'no_symptoms') {
                            symptoms.clear();
                          } else {
                            symptoms.remove('no_symptoms');
                          }
                          symptoms.add(item.key);
                        } else {
                          symptoms.remove(item.key);
                        }
                      });
                      draft();
                    },
            ),
        ],
      ),
      const SizedBox(height: 12),
      DropdownButtonFormField<String>(
        key: ValueKey('severity-$severity'),
        initialValue: severity,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Intensità osservata'),
        items: const [
          DropdownMenuItem(value: 'mild', child: Text('Lieve')),
          DropdownMenuItem(value: 'moderate', child: Text('Moderata')),
          DropdownMenuItem(value: 'high', child: Text('Elevata')),
        ],
        onChanged: busy || !ready
            ? null
            : (v) {
                setState(() {
                  id = null;
                  severity = v!;
                });
                draft();
              },
      ),
      DropdownButtonFormField<String>(
        key: ValueKey('part-$part'),
        initialValue: part,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Parte della pianta'),
        items: const [
          DropdownMenuItem(value: 'leaves', child: Text('Foglie')),
          DropdownMenuItem(value: 'stem', child: Text('Fusto')),
          DropdownMenuItem(value: 'roots', child: Text('Radici')),
          DropdownMenuItem(value: 'whole', child: Text('Pianta intera')),
        ],
        onChanged: busy || !ready
            ? null
            : (v) {
                setState(() {
                  id = null;
                  part = v!;
                });
                draft();
              },
      ),
      TextField(
        controller: percent,
        enabled: !busy && ready,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: const InputDecoration(
          labelText: 'Piante interessate (%)',
          hintText: 'Facoltativo, da 0 a 100',
        ),
        onChanged: (_) {
          id = null;
          draft();
        },
      ),
      TextField(
        controller: notes,
        enabled: !busy && ready,
        minLines: 3,
        maxLines: 6,
        maxLength: 3000,
        decoration: const InputDecoration(
          labelText: 'Descrivi quello che vedi',
          hintText:
              'Dove compaiono i sintomi? Da quando? Sono diffusi o a chiazze?',
        ),
        onChanged: (_) {
          id = null;
          draft();
        },
      ),
      if (message != null)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Text(message!),
        ),
      FilledButton.icon(
        onPressed: busy || !ready ? null : save,
        icon: const Icon(Icons.save_outlined),
        label: Text(busy ? 'Salvataggio…' : 'Salva rilievo'),
      ),
      const SizedBox(height: 24),
      const Text(
        'Storico dei rilievi',
        style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
      ),
      if (rows.isEmpty) const Text('Non ci sono ancora rilievi salvati.'),
      for (final row in rows)
        Card(
          child: ListTile(
            title: Text(
              '${row['observed_at']} · ${(row['symptoms'] as List).map((s) => symptomLabels[s] ?? s).join(', ')}',
            ),
            subtitle: Text(
              '${row['notes']}\n${row['affected_percent'] ?? '—'}% di piante interessate',
            ),
          ),
        ),
    ],
  );
}
