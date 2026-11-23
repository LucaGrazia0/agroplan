import 'dart:convert';

import 'package:flutter/material.dart';

import 'api.dart' as http;
import 'analysis_report.dart';

class AgronomyPanel extends StatefulWidget {
  const AgronomyPanel({
    super.key,
    required this.parcelId,
    required this.latitude,
    required this.longitude,
    required this.baseUrl,
    this.revision = 0,
    this.onResultSaved,
    this.section = 0,
  });

  final int section;
  final String parcelId;
  final double? latitude;
  final double? longitude;
  final String baseUrl;
  final int revision;
  final VoidCallback? onResultSaved;

  @override
  State<AgronomyPanel> createState() => _AgronomyPanelState();
}

class _AgronomyPanelState extends State<AgronomyPanel> {
  Map<String, dynamic>? result;
  bool loading = false;
  String? error;
  int requestVersion = 0;
  bool includeSatellite = false;

  @override
  void initState() {
    super.initState();
    load();
  }

  @override
  void didUpdateWidget(covariant AgronomyPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.parcelId != widget.parcelId ||
        oldWidget.latitude != widget.latitude ||
        oldWidget.longitude != widget.longitude ||
        oldWidget.baseUrl != widget.baseUrl ||
        oldWidget.revision != widget.revision) {
      load();
    }
  }

  @override
  void dispose() {
    requestVersion++;
    super.dispose();
  }

  Future<void> load() async {
    final version = ++requestVersion;

    setState(() {
      loading = true;
      error = null;
      result = null;
    });

    try {
      final response = await http
          .post(
            Uri.parse('${widget.baseUrl}/agronomy/analyze'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'parcel_id': widget.parcelId,
              'latitude': widget.latitude,
              'longitude': widget.longitude,
              'history_days': 60,
              'include_satellite': includeSatellite,
            }),
          )
          .timeout(const Duration(seconds: 100));

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('Errore HTTP ${response.statusCode}: ${response.body}');
      }

      final data = jsonDecode(response.body);
      if (data is! Map<String, dynamic>) {
        throw const FormatException('Risposta agronomica non valida');
      }

      if (!mounted || version != requestVersion) return;

      setState(() {
        result = data;
      });
      widget.onResultSaved?.call();
    } catch (e) {
      if (!mounted || version != requestVersion) return;
      setState(() {
        error = e.toString();
      });
    } finally {
      if (mounted && version == requestVersion) {
        setState(() {
          loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final title = switch (widget.section) {
      1 => 'Analisi del suolo',
      2 => 'Analisi meteo',
      3 => 'Analisi delle problematiche',
      _ => 'Analisi integrata',
    };
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                if (widget.section != 0)
                  IconButton(
                    tooltip: 'Aggiorna analisi',
                    onPressed: loading ? null : load,
                    icon: const Icon(Icons.refresh),
                  ),
              ],
            ),
            if (widget.section == 0) ...[
              const Text(
                'Il motore legge coltura, suolo, meteo, rilievi e satellite disponibili e restituisce una valutazione con le prossime verifiche.',
              ),
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: loading ? null : load,
                icon: const Icon(Icons.auto_graph),
                label: const Text('Analizza tutti gli input'),
              ),
              ExpansionTile(
                tilePadding: EdgeInsets.zero,
                title: const Text('Opzioni di aggiornamento'),
                children: [
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Aggiorna anche i dati satellitari'),
                    subtitle: const Text(
                      'Richiede nuove acquisizioni al server Copernicus.',
                    ),
                    value: includeSatellite,
                    onChanged: loading
                        ? null
                        : (value) =>
                              setState(() => includeSatellite = value ?? false),
                  ),
                ],
              ),
            ],
            if (loading) ...[
              const LinearProgressIndicator(),
              const SizedBox(height: 8),
              const Text('Analisi dei dati disponibili…'),
            ],
            if (error != null) ...[
              const Text(
                'Analisi non disponibile. I dati salvati restano nello storico.',
              ),
              TextButton(onPressed: load, child: const Text('Riprova')),
            ],
            if (result != null)
              AnalysisReport(data: result!, section: widget.section),
          ],
        ),
      ),
    );
  }
}
