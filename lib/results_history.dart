import 'dart:convert';

import 'package:flutter/material.dart';

import 'api.dart' as api;
import 'analysis_report.dart';

class AssessmentView extends StatelessWidget {
  const AssessmentView({super.key, required this.data});
  final Map data;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const Text(
        'Evidenze e verifiche',
        style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
      ),
      for (final item in data['evidence'] as List? ?? [])
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.fact_check_outlined),
          title: Text('${item['label']}'),
          subtitle: Text('${item['source']} · ${item['date']}'),
        ),
      for (final item in data['hypotheses'] as List? ?? [])
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Ipotesi da verificare',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
                Text('${item['hypothesis']}'),
                Text('${item['evidence']}'),
                const SizedBox(height: 8),
                Text('${item['next_check']}'),
              ],
            ),
          ),
        ),
      for (final question in data['questions'] as List? ?? [])
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text('• $question'),
        ),
      const SizedBox(height: 8),
      Text('${data['method'] ?? ''}', style: const TextStyle(fontSize: 12)),
    ],
  );
}

class ResultsHistory extends StatefulWidget {
  const ResultsHistory({super.key, required this.parcelId, this.revision = 0});
  final String parcelId;
  final int revision;
  @override
  State<ResultsHistory> createState() => _ResultsHistoryState();
}

class _ResultsHistoryState extends State<ResultsHistory> {
  List<dynamic> rows = [];
  String? error;
  @override
  void initState() {
    super.initState();
    load();
  }

  @override
  void didUpdateWidget(covariant ResultsHistory old) {
    super.didUpdateWidget(old);
    if (old.revision != widget.revision || old.parcelId != widget.parcelId) {
      load();
    }
  }

  Future<void> load() async {
    try {
      final r = await api
          .get(
            Uri.parse(
              '${api.apiBaseUrl}/agronomy/results?parcel_id=${Uri.encodeQueryComponent(widget.parcelId)}',
            ),
          )
          .timeout(const Duration(seconds: 75));
      if (r.statusCode != 200) throw Exception();
      final data = jsonDecode(r.body) as List;
      if (mounted) {
        setState(() {
          rows = data;
          error = null;
        });
      }
    } catch (_) {
      if (mounted) setState(() => error = 'Storico risultati non disponibile.');
    }
  }

  @override
  Widget build(BuildContext context) => ExpansionTile(
    title: const Text('Risultati precedenti'),
    subtitle: Text('${rows.length} analisi salvate'),
    children: [
      if (error != null) TextButton(onPressed: load, child: Text(error!)),
      if (rows.isEmpty && error == null)
        const Padding(
          padding: EdgeInsets.all(12),
          child: Text('La prima analisi verrà conservata qui.'),
        ),
      for (final row in rows)
        ExpansionTile(
          title: Text(
            '${row['saved_at']}'.replaceFirst('T', ' ').substring(0, 16),
          ),
          subtitle: Text(
            '${row['crop_review']?['summary'] ?? 'Analisi colturale'}',
          ),
          children: [
            if (row['crop_review']?['manual_assessment'] is Map)
              SavedAnalysisView(data: row),
            if (row['crop_review']?['manual_assessment'] == null &&
                row['crop_review']?['integrated_assessment'] is Map)
              Padding(
                padding: const EdgeInsets.all(12),
                child: AssessmentView(
                  data: row['crop_review']['integrated_assessment'],
                ),
              ),
          ],
        ),
    ],
  );
}

class SavedAnalysisView extends StatefulWidget {
  const SavedAnalysisView({super.key, required this.data});
  final Map data;
  @override
  State<SavedAnalysisView> createState() => _SavedAnalysisViewState();
}

class _SavedAnalysisViewState extends State<SavedAnalysisView> {
  int section = 0;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(12),
    child: Column(
      children: [
        DropdownButtonFormField<int>(
          initialValue: section,
          decoration: const InputDecoration(
            labelText: 'Sezione del risultato salvato',
          ),
          items: const [
            DropdownMenuItem(value: 0, child: Text('Analisi integrata')),
            DropdownMenuItem(value: 1, child: Text('Suolo')),
            DropdownMenuItem(value: 2, child: Text('Meteo')),
            DropdownMenuItem(value: 3, child: Text('Problematiche')),
          ],
          onChanged: (v) => setState(() => section = v ?? 0),
        ),
        const SizedBox(height: 12),
        AnalysisReport(data: widget.data, section: section),
      ],
    ),
  );
}
