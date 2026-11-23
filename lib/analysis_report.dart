import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'decision_report.dart';

/// A saved report and a fresh report use the same category layout.
class AnalysisReport extends StatelessWidget {
  const AnalysisReport({
    super.key,
    required this.data,
    this.section = 0,
    this.onSectionRequested,
  });
  final Map data;
  final int section; // 0 summary, 1 soil, 2 weather, 3 problems
  final ValueChanged<int>? onSectionRequested;

  static const names = {
    'soil': 'Suolo',
    'weather': 'Meteo',
    'problems': 'Problematiche',
  };
  static const icons = {
    'soil': Icons.science_outlined,
    'weather': Icons.cloud_outlined,
    'problems': Icons.health_and_safety_outlined,
  };
  static String status(dynamic value) => switch (value) {
    'available' => 'Calcolo disponibile',
    'attention' => 'Dati da verificare',
    'partial' => 'Valutazione da completare',
    _ => 'Dati insufficienti',
  };

  @override
  Widget build(BuildContext context) {
    final review = data['crop_review'] as Map? ?? {};
    final manual = review['manual_assessment'] as Map?;
    final crop = data['crop_context'] as Map? ?? {};
    final bbch = crop['latest_bbch'] as Map?;
    final domains = manual?['domains'] as Map? ?? {};
    final references = manual?['references'] as List? ?? [];
    final domainKey = switch (section) {
      1 => 'soil',
      2 => 'weather',
      3 => 'problems',
      _ => '',
    };
    final selected = domains[domainKey] as Map? ?? {};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (manual == null)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Text(
              'Questo risultato usa il formato precedente. Aggiorna l’analisi per ottenere le sezioni e i riferimenti ai manuali.',
            ),
          ),
        if (section == 0 && review['decision_support'] is Map)
          DecisionReport(
            data: review['decision_support'],
            onSectionRequested: onSectionRequested,
          ),
        if (section == 0 && review['decision_support'] == null) ...[
          const Text(
            'Questo risultato contiene il riepilogo precedente. Per un nuovo ritorno, avvia l’analisi integrata della particella.',
          ),
          Text('${review['summary'] ?? 'Sintesi dei dati disponibili'}'),
          const SizedBox(height: 12),
          Text(
            'Coltura: ${const {'frumento_tenero': 'Frumento tenero', 'frumento_duro': 'Frumento duro', 'orzo': 'Orzo', 'mais': 'Mais', 'avena': 'Avena', 'segale': 'Segale', 'triticale': 'Triticale'}[crop['crop']] ?? crop['crop'] ?? 'Non registrata'}',
          ),
          Text('Stagione: ${crop['season'] ?? '—'}'),
          Text(
            bbch == null
                ? 'BBCH: non registrato'
                : 'BBCH ${bbch['bbch']} (osservato il ${bbch['observed_at']})',
          ),
          const SizedBox(height: 12),
          for (final key in names.keys)
            Card(
              child: ListTile(
                leading: Icon(icons[key]),
                title: Text(names[key]!),
                subtitle: Text(
                  '${domains[key]?['summary'] ?? 'Aggiorna l’analisi'}\n${status(domains[key]?['status'])}',
                ),
              ),
            ),
          if ((review['missing_data'] as List? ?? []).isNotEmpty)
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: const Text('Dati da completare'),
              children: [
                for (final gap in review['missing_data'] as List)
                  ListTile(title: Text('$gap')),
              ],
            ),
        ],
        if (section != 0) ...[
          for (final item in selected['findings'] as List? ?? [])
            findingCard(context, item as Map, references),
          if (section == 2) ...[
            Text(
              'Fonte meteo: ${data['source'] ?? '—'} · storico fino al ${data['historical_end'] ?? '—'}',
              style: const TextStyle(fontSize: 12),
            ),
            for (final period in ['7', '15', '30'])
              if (data['windows']?[period] is Map)
                weatherWindow(period, data['windows'][period]),
            for (final warning in data['warnings'] as List? ?? [])
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text('• $warning'),
              ),
          ],
          if (section == 3) ...[
            for (final evidence
                in review['integrated_assessment']?['evidence'] as List? ?? [])
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.visibility_outlined),
                title: Text('${evidence['label']}'),
                subtitle: Text('${evidence['source']} · ${evidence['date']}'),
              ),
            for (final question
                in review['integrated_assessment']?['questions'] as List? ?? [])
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text('• $question'),
              ),
            for (final check in review['checks'] as List? ?? [])
              if (check['title'] == 'Sopralluogo prioritario')
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Text(
                      '${check['title']}\n${check['evidence']}\n${check['action']}\nPriorità organizzativa dell’app: intensità elevata o almeno il 30% di piante segnalate, non soglia di trattamento.',
                    ),
                  ),
                ),
          ],
        ],
        if (manual != null)
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: const Text('Metodo e manuali'),
            subtitle: Text('Edizione del motore ${manual['engine_version']}'),
            children: [
              Text('${manual['method']}'),
              const SizedBox(height: 8),
              Text('${manual['scope']}', style: const TextStyle(fontSize: 12)),
              for (final ref in references) source(context, ref as Map),
            ],
          ),
      ],
    );
  }

  Widget findingCard(BuildContext context, Map item, List refs) => Card(
    margin: const EdgeInsets.only(bottom: 10),
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${item['title']}',
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
          const SizedBox(height: 5),
          Text(
            status(item['status']),
            style: TextStyle(
              color: item['status'] == 'attention'
                  ? Colors.orange.shade900
                  : Colors.teal.shade800,
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 10),
          Text('${item['interpretation']}'),
          const SizedBox(height: 10),
          Text('${item['next_check']}'),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: const Text(
              'Perché questo risultato?',
              style: TextStyle(fontSize: 13),
            ),
            children: [
              Text('${item['evidence']}'),
              if (item['equation'] != null)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Text(
                    '${item['equation']}',
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                ),
              for (final limit in item['limitations'] as List? ?? [])
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text('• $limit', style: const TextStyle(fontSize: 12)),
                ),
              for (final id in item['source_ids'] as List? ?? [])
                for (final ref in refs.where((r) => r['id'] == id))
                  source(context, ref as Map),
              if ((item['source_ids'] as List? ?? []).isEmpty)
                const Text(
                  'Controllo di qualità o limite applicativo; nessuna soglia agronomica attribuita a un manuale.',
                  style: TextStyle(fontSize: 12),
                ),
              const SizedBox(height: 8),
            ],
          ),
        ],
      ),
    ),
  );

  Widget source(BuildContext context, Map ref) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '${ref['title']}',
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12),
        ),
        Text('${ref['section']}', style: const TextStyle(fontSize: 12)),
        SelectableText('${ref['url']}', style: const TextStyle(fontSize: 11)),
        TextButton.icon(
          onPressed: () async {
            await Clipboard.setData(ClipboardData(text: '${ref['url']}'));
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Link al manuale copiato.')),
              );
            }
          },
          icon: const Icon(Icons.copy, size: 16),
          label: const Text('Copia link'),
        ),
      ],
    ),
  );

  Widget weatherWindow(String period, Map row) {
    String value(dynamic v) => v is num ? v.toStringAsFixed(1) : '—';
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      title: Text('Ultimi $period giorni disponibili'),
      subtitle: Text('${row['start_date'] ?? '—'} → ${row['end_date'] ?? '—'}'),
      children: [
        for (final entry in {
          'Pioggia (mm)': 'rain_mm',
          'ET₀ (mm)': 'et0_mm',
          'P − ET₀ (mm)': 'climatic_balance_mm',
          'Temperatura media (°C)': 'mean_temperature_c',
          'Minima (°C)': 'min_temperature_c',
          'Massima (°C)': 'max_temperature_c',
        }.entries)
          ListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            title: Text(entry.key),
            trailing: Text(value(row[entry.value])),
          ),
        if (row['data_complete'] != true)
          const Text('Serie incompleta: i valori assenti non sono zero.'),
      ],
    );
  }
}
