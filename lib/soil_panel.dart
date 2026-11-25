import 'dart:convert';

import 'package:flutter/material.dart';

import 'api.dart' as http;

class SoilPanel extends StatefulWidget {
  const SoilPanel({
    super.key,
    required this.parcelId,
    required this.revision,
    required this.latitude,
    required this.longitude,
    required this.points,
  });

  final String parcelId;
  final String revision;
  final double latitude;
  final double longitude;
  final List<Map<String, double>> points;

  @override
  State<SoilPanel> createState() => _SoilPanelState();
}

class _SoilPanelState extends State<SoilPanel> {
  List<Map<String, dynamic>> analyses = [];
  String? error;
  bool busy = false;
  bool automaticBusy = false;
  Map<String, dynamic>? automatic;
  String? automaticError;

  static String get baseUrl => http.apiBaseUrl;

  @override
  void initState() {
    super.initState();
    refresh();
    searchAutomatic();
  }

  @override
  void didUpdateWidget(covariant SoilPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.parcelId != widget.parcelId ||
        oldWidget.revision != widget.revision) {
      refresh();
      searchAutomatic();
    }
  }

  Future<void> refresh() async {
    final parcelId = widget.parcelId;
    setState(() {
      busy = true;
      error = null;
      analyses = [];
    });
    try {
      final response = await http
          .get(
            Uri.parse(
              '$baseUrl/soil/analyses?parcel_id=${Uri.encodeQueryComponent(parcelId)}',
            ),
          )
          .timeout(const Duration(seconds: 15));
      if (response.statusCode != 200) {
        throw Exception('HTTP ${response.statusCode}');
      }
      final data = jsonDecode(response.body) as List;
      if (mounted && parcelId == widget.parcelId) {
        setState(
          () => analyses = data
              .map((e) => Map<String, dynamic>.from(e as Map))
              .toList(),
        );
      }
    } catch (e) {
      if (mounted && parcelId == widget.parcelId) {
        setState(() => error = e.toString());
      }
    } finally {
      if (mounted && parcelId == widget.parcelId) {
        setState(() => busy = false);
      }
    }
  }

  Future<void> searchAutomatic() async {
    final parcelId = widget.parcelId;
    setState(() {
      automaticBusy = true;
      automaticError = null;
      automatic = null;
    });
    try {
      final response = await http
          .post(
            Uri.parse('$baseUrl/soil/automatic-analysis'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'parcel_id': parcelId, 'points': widget.points}),
          )
          .timeout(const Duration(seconds: 75));
      if (response.statusCode != 200) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      final result = Map<String, dynamic>.from(
        jsonDecode(response.body) as Map,
      );
      if (mounted && parcelId == widget.parcelId) {
        setState(() => automatic = result);
      }
    } catch (e) {
      if (mounted && parcelId == widget.parcelId) {
        setState(() => automaticError = e.toString());
      }
    } finally {
      if (mounted && parcelId == widget.parcelId) {
        setState(() => automaticBusy = false);
      }
    }
  }

  // Il servizio restituisce testo separato da ';'. Conserviamo il testo
  // originale ed estraiamo solo descrizioni leggibili, senza inventare valori.
  static List<String> _descriptions(String raw) {
    final chunks = raw
        .split(';')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty);
    final descriptions = <String>[];
    final seen = <String>{};
    for (final chunk in chunks) {
      final normalized = chunk.replaceAll(RegExp(r'\s+'), ' ').trim();
      final lower = normalized.toLowerCase();
      if (normalized.length < 24 || normalized.length > 1100) continue;
      if (lower.startsWith('http') ||
          lower.startsWith('@') ||
          lower.startsWith('punto ') ||
          lower.startsWith('polygon') ||
          lower.startsWith('shape') ||
          lower.startsWith('objectid') ||
          lower.startsWith('fid_') ||
          lower.startsWith('id_') ||
          lower.startsWith('xid_') ||
          lower.contains('https://') ||
          RegExp(
                r'^[a-z0-9_]+(;|$)',
                caseSensitive: false,
              ).hasMatch(normalized) &&
              normalized == normalized.toUpperCase()) {
        continue;
      }
      // Un testo descrittivo contiene parole, non soltanto numeri/codici.
      if (!RegExp(r'[a-zA-ZÀ-ÿ]{4,}\s+[a-zA-ZÀ-ÿ]{3,}').hasMatch(normalized)) {
        continue;
      }
      if (seen.add(lower)) descriptions.add(normalized);
    }
    return descriptions;
  }

  static String _responseText(dynamic value) {
    if (value == null) return '';
    if (value is String) return value;
    if (value is Map || value is List) {
      return const JsonEncoder.withIndent('  ').convert(value);
    }
    return value.toString();
  }

  static String _resultKey(String raw) {
    // Deduplica le risposte identiche anche se cambiano le coordinate del punto.
    final cleaned = raw.replaceAll(
      RegExp(
        r'Punto\s+-?\d+(?:\.\d+)?,\s*-?\d+(?:\.\d+)?',
        caseSensitive: false,
      ),
      'Punto',
    );
    return cleaned.trim();
  }

  Widget _sectionTitle(String title, IconData icon) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Row(
      children: [
        Icon(icon, size: 19, color: Colors.green.shade800),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            title,
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
          ),
        ),
      ],
    ),
  );

  Widget _automaticCard() {
    final data = automatic;
    if (data == null) return const SizedBox.shrink();
    final results = (data['results'] as List? ?? [])
        .whereType<Map>()
        .map((r) => Map<String, dynamic>.from(r))
        .toList();
    final sources = (data['sources_checked'] as List? ?? [])
        .whereType<Map>()
        .map((s) => Map<String, dynamic>.from(s))
        .toList();
    final unique = <String, Map<String, dynamic>>{};
    for (final result in results) {
      final raw = _responseText(result['response']);
      if (raw.trim().isNotEmpty) {
        unique.putIfAbsent(_resultKey(raw), () => result);
      }
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (unique.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              children: [
                Icon(
                  Icons.check_circle_outline,
                  color: Colors.green.shade700,
                  size: 18,
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    '${results.length} punti consultati · ${unique.length} risposte distinte',
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ),
        if (unique.isEmpty)
          Text(
            data['message']?.toString() ??
                'Nessun dato pedologico disponibile.',
          ),
        for (final entry
            in unique.entries.take(5).toList().asMap().entries) ...[
          Builder(
            builder: (context) {
              final result = entry.value.value;
              final raw = _responseText(result['response']);
              final units = (result['soil_units'] as List? ?? [])
                  .whereType<Map>()
                  .toList();
              final descriptions = units.isEmpty
                  ? _descriptions(raw)
                  : <String>{
                      for (final unit in units)
                        for (final text
                            in (unit['descriptions'] as List? ?? []))
                          text.toString(),
                    }.toList();
              final title = units.isEmpty
                  ? 'Risultato cartografico ${entry.key + 1}'
                  : units.map((u) => '${u['code']} · ${u['name']}').join(' / ');
              return Container(
                width: double.infinity,
                margin: const EdgeInsets.only(bottom: 10),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surface,
                  border: Border.all(
                    color: Theme.of(context).dividerColor
                        .withValues(alpha: 0.45),
                  ),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 5),
                    if (descriptions.isEmpty)
                      const Text(
                        'Nessuna descrizione sintetica estratta. Consulta i dati originali.',
                        style: TextStyle(fontSize: 12),
                      )
                    else
                      for (final description in descriptions.take(8))
                        Padding(
                          padding: const EdgeInsets.only(bottom: 6),
                          child: Text(
                            description,
                            style: const TextStyle(fontSize: 13),
                          ),
                        ),
                    const SizedBox(height: 4),
                    ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      childrenPadding: EdgeInsets.zero,
                      title: const Text(
                        'Dati originali e dettagli tecnici',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      children: [
                        SelectableText(
                          raw,
                          style: const TextStyle(fontSize: 11),
                        ),
                      ],
                    ),
                  ],
                ),
              );
            },
          ),
        ],
        if (unique.length > 5)
          Text(
            'Altre ${unique.length - 5} risposte disponibili nel servizio.',
            style: const TextStyle(fontSize: 12),
          ),
        if (sources.isNotEmpty) ...[
          const SizedBox(height: 8),
          _sectionTitle('Fonti cartografiche', Icons.source_outlined),
          for (final source in sources)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text(
                '${source['name'] ?? 'Fonte non specificata'} · Scala ${source['scale'] ?? 'n.d.'}',
                style: const TextStyle(fontSize: 12),
              ),
            ),
        ],
        const SizedBox(height: 8),
        Text(
          'Le descrizioni riguardano unità cartografiche, non misure puntuali della particella. '
          'La ricerca campiona punti e non calcola ancora la superficie di intersezione. '
          'Questi dati non sostituiscono le analisi di laboratorio.',
          style: TextStyle(
            fontSize: 11,
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  'Analisi del suolo',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 17),
                ),
              ),
              IconButton(
                tooltip: 'Aggiorna analisi di laboratorio',
                onPressed: busy ? null : refresh,
                icon: const Icon(Icons.refresh),
              ),
            ],
          ),
          _sectionTitle('Analisi di laboratorio', Icons.science_outlined),
          if (busy) const LinearProgressIndicator(),
          if (error != null)
            Text(
              'Archivio suolo non raggiungibile: $error',
              style: const TextStyle(color: Colors.orange),
            ),
          if (analyses.isEmpty && !busy)
            const Text(
              'Nessuna analisi di laboratorio salvata.',
              style: TextStyle(fontSize: 13),
            ),
          for (final a in analyses.take(5))
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Text(
                '${a['sample_date'] ?? 'Data n.d.'} · '
                'pH ${a['ph'] ?? 'n.d.'} · '
                'N ${a['nitrogen_g_kg'] ?? 'n.d.'} g/kg · '
                'P ${a['phosphorus_mg_kg'] ?? 'n.d.'} mg/kg',
                style: const TextStyle(fontSize: 12),
              ),
            ),
          const Divider(height: 28),
          Row(
            children: [
              const Expanded(
                child: Text(
                  'Ricerca pedologica automatica',
                  style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                ),
              ),
              IconButton(
                tooltip: 'Ripeti ricerca pedologica',
                onPressed: automaticBusy ? null : searchAutomatic,
                icon: const Icon(Icons.travel_explore),
              ),
            ],
          ),
          if (automaticBusy) ...[
            const LinearProgressIndicator(),
            const SizedBox(height: 6),
            const Text(
              'Interrogazione delle banche dati territoriali…',
              style: TextStyle(fontSize: 12),
            ),
          ],
          if (automaticError != null)
            Text(
              'Ricerca non disponibile: $automaticError',
              style: const TextStyle(color: Colors.orange),
            ),
          _automaticCard(),
        ],
      ),
    ),
  );
}
