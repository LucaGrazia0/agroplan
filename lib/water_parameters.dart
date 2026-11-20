import 'dart:convert';

import 'package:flutter/material.dart';

import 'api.dart' as api;

class WaterParametersPanel extends StatefulWidget {
  const WaterParametersPanel({
    super.key,
    required this.parcelId,
    required this.weather,
    required this.onSaved,
  });
  final String parcelId;
  final bool weather;
  final VoidCallback onSaved;
  @override
  State<WaterParametersPanel> createState() => _WaterParametersPanelState();
}

class _WaterParametersPanelState extends State<WaterParametersPanel> {
  final form = GlobalKey<FormState>();
  final controls = <String, TextEditingController>{};
  bool busy = true;
  bool saving = false;
  String? message;
  bool failed = false;
  Map<String, String> get labels => widget.weather
      ? {
          'kc': 'Coefficiente Kc verificato',
          'kc_from': 'Kc valido dal (AAAA-MM-GG)',
          'kc_to': 'Kc valido al (AAAA-MM-GG)',
        }
      : {
          'observed_at': 'Data delle misure (AAAA-MM-GG)',
          'field_capacity_percent': 'Capacità di campo (% volume)',
          'wilting_point_percent': 'Punto di appassimento (% volume)',
          'root_depth_m': 'Profondità radicale (m)',
          'moisture_percent': 'Umidità misurata (% volume)',
        };
  Uri get uri => Uri.parse(
    '${api.apiBaseUrl}/agronomy/parameters/${Uri.encodeComponent(widget.parcelId)}',
  );
  @override
  void initState() {
    super.initState();
    for (final key in labels.keys) {
      controls[key] = TextEditingController();
    }
    load();
  }

  @override
  void dispose() {
    for (final c in controls.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> load() async {
    setState(() {
      busy = true;
      message = null;
    });
    try {
      final r = await api.get(uri).timeout(const Duration(seconds: 75));
      if (r.statusCode != 200) throw Exception();
      final data = jsonDecode(r.body) as Map;
      if (!mounted) return;
      for (final key in labels.keys) {
        controls[key]!.text = '${data[key] ?? ''}';
      }
      if (controls['observed_at']?.text.isEmpty == true) {
        controls['observed_at']!.text = DateTime.now()
            .toIso8601String()
            .substring(0, 10);
      }
      failed = false;
    } catch (_) {
      failed = true;
      message = 'Parametri non disponibili. Riprova prima di modificarli.';
    }
    if (mounted) setState(() => busy = false);
  }

  Future<void> save() async {
    if (saving || !form.currentState!.validate()) return;
    setState(() {
      saving = true;
      message = null;
    });
    try {
      // Preserve parameters owned by the other section, including recent edits.
      final previous = await api.get(uri).timeout(const Duration(seconds: 75));
      if (previous.statusCode != 200) throw Exception();
      final data = Map<String, dynamic>.from(jsonDecode(previous.body) as Map);
      for (final key in labels.keys) {
        final text = controls[key]!.text.trim();
        data[key] = text.isEmpty
            ? null
            : (key.contains('_at') || key.startsWith('kc_')
                  ? text
                  : double.parse(text.replaceAll(',', '.')));
      }
      data['observed_at'] ??= DateTime.now().toIso8601String().substring(0, 10);
      if (data['kc'] == null) {
        data['kc_from'] = null;
        data['kc_to'] = null;
      }
      final r = await api
          .put(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(data),
          )
          .timeout(const Duration(seconds: 75));
      if (r.statusCode != 200) throw Exception();
      if (!mounted) return;
      setState(
        () => message = 'Parametri salvati. L’analisi è stata aggiornata.',
      );
      widget.onSaved();
    } catch (_) {
      if (mounted) {
        setState(
          () => message = 'Salvataggio non riuscito. Controlla date, intervallo Kc e capacità di campo maggiore del punto di appassimento; poi riprova.',
        );
      }
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => Card(
    child: ExpansionTile(
      title: Text(
        widget.weather ? 'Parametri per ETc' : 'Parametri idrici misurati',
      ),
      subtitle: const Text('Facoltativi · metodo FAO 56'),
      childrenPadding: const EdgeInsets.all(14),
      children: [
        Text(
          widget.weather
              ? 'Inserisci un Kc verificato per coltura e fase, valido per l’intero periodo meteo da analizzare. Non viene dedotto dal BBCH.'
              : 'Usa misure dello stesso profilo radicale. Percentuali in volume, non in peso; valori assenti restano vuoti. La riserva calcolata non è una dose irrigua.',
        ),
        if (busy) const LinearProgressIndicator(),
        if (failed)
          TextButton(
            onPressed: busy ? null : load,
            child: const Text('Ricarica parametri'),
          ),
        if (!busy && !failed)
          Form(
            key: form,
            child: Column(
              children: [
                for (final entry in labels.entries)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: TextFormField(
                      controller: controls[entry.key],
                      enabled: !saving,
                      decoration: InputDecoration(
                        labelText: entry.value,
                        border: const OutlineInputBorder(),
                      ),
                      keyboardType:
                          entry.key.contains('_at') ||
                              entry.key.startsWith('kc_')
                          ? TextInputType.datetime
                          : const TextInputType.numberWithOptions(
                              decimal: true,
                            ),
                      validator: (value) {
                        final text = (value ?? '').trim();
                        if (text.isEmpty) {
                          return entry.key == 'observed_at'
                              ? 'Indica la data delle misure'
                              : null;
                        }
                        if (entry.key.contains('_at') ||
                            entry.key.startsWith('kc_')) {
                          final d = DateTime.tryParse(text);
                          if (!RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(text) ||
                              d == null ||
                              d.toIso8601String().substring(0, 10) != text ||
                              d.isAfter(DateTime.now())) {
                            return 'Usa una data valida, non futura';
                          }
                        } else {
                          final v = double.tryParse(text.replaceAll(',', '.'));
                          if (v == null ||
                              !v.isFinite ||
                              v < 0 ||
                              (entry.key.endsWith('_percent') && v > 100) ||
                              (entry.key == 'root_depth_m' &&
                                  (v <= 0 || v > 5)) ||
                              (entry.key == 'kc' && (v <= 0 || v > 2.5))) {
                            return 'Valore fuori intervallo';
                          }
                        }
                        return null;
                      },
                    ),
                  ),
                const SizedBox(height: 12),
                FilledButton.icon(
                  onPressed: saving ? null : save,
                  icon: const Icon(Icons.save_outlined),
                  label: Text(saving ? 'Salvataggio…' : 'Salva parametri'),
                ),
              ],
            ),
          ),
        if (message != null)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(message!),
          ),
      ],
    ),
  );
}
