import 'package:flutter/material.dart';

class AnalysisCenterSnapshot extends StatelessWidget {
  const AnalysisCenterSnapshot({super.key, required this.data});
  final Map data;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const Text(
        'Centro analisi · risultato salvato',
        style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
      ),
      Text('${data['headline']}'),
      Text(
        'Rilievo del ${data['observation_date'] ?? 'non disponibile'} · motore ${data['version']}',
      ),
      const Text(
        'Questo quadro conserva gli input e le verifiche del momento dell’analisi.',
      ),
      for (final note in data['quality_notes'] as List? ?? []) Text('$note'),
      for (final item in data['candidates'] as List? ?? [])
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: Text('${item['title']}'),
          children: [
            for (final entry in const {
              'supporting': 'A favore',
              'contradicting': 'Non concorda',
              'missing': 'Da verificare',
            }.entries)
              for (final text in item[entry.key] as List? ?? [])
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text('${entry.value}: $text'),
                ),
            Text('${item['next_check']}'),
          ],
        ),
      for (final question in data['questions'] as List? ?? [])
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text('${question['text']}'),
          subtitle: Text('${question['reason']}'),
        ),
      for (final limit in data['limitations'] as List? ?? [])
        Text('$limit', style: const TextStyle(fontSize: 12)),
    ],
  );
}
