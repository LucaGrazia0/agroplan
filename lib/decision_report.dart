import 'package:flutter/material.dart';

class DecisionReport extends StatelessWidget {
  const DecisionReport({
    super.key,
    required this.data,
    this.onSectionRequested,
  });
  final Map data;
  final ValueChanged<int>? onSectionRequested;

  @override
  Widget build(BuildContext context) {
    final urgent = data['status'] == 'priority_check';
    final conclusions = data['conclusions'] as List? ?? [];
    final steps = data['next_steps'] as List? ?? [];
    final gaps = data['missing_inputs'] as List? ?? [];
    final trend = data['observation_trend'] as Map?;
    final candidates = data['differential'] as List? ?? [];
    final questions = data['questions'] as List? ?? [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: urgent ? Colors.orange.shade50 : const Color(0xFFE5F0E4),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${data['headline']}',
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              Text('${data['summary']}'),
            ],
          ),
        ),
        const SizedBox(height: 20),
        const Text(
          'Cosa emerge dagli input',
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
        ),
        if (conclusions.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Text(
              'Non ci sono ancora dati sufficienti per formulare una conclusione. Inizia dai dati richiesti qui sotto.',
            ),
          ),
        for (final item in conclusions)
          Card(
            margin: const EdgeInsets.only(top: 10),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${item['title']}',
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  Text('${item['explanation']}'),
                  ExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: const Text(
                      'Dati su cui si basa',
                      style: TextStyle(fontSize: 13),
                    ),
                    children: [
                      for (final input in data['inputs'] as List? ?? [])
                        if ((item['input_ids'] as List? ?? []).contains(
                          input['id'],
                        ))
                          ListTile(
                            dense: true,
                            contentPadding: EdgeInsets.zero,
                            title: Text('${input['label']}'),
                            subtitle: Text('${input['detail']}'),
                          ),
                      for (final ref in data['references'] as List? ?? [])
                        if ((item['source_ids'] as List? ?? []).contains(
                          ref['id'],
                        ))
                          Padding(
                            padding: const EdgeInsets.only(bottom: 10),
                            child: Text(
                              '${ref['title']} · ${ref['section']}',
                              style: const TextStyle(fontSize: 12),
                            ),
                          ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        const SizedBox(height: 20),
        const Text(
          'Cosa fare adesso',
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
        ),
        for (var i = 0; i < steps.take(3).length; i++)
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: CircleAvatar(
              radius: 14,
              child: Text('${i + 1}', style: const TextStyle(fontSize: 12)),
            ),
            title: Text('${steps[i]}'),
          ),
        if (steps.length > 3)
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: const Text('Altre verifiche utili'),
            children: [
              for (final step in steps.skip(3))
                ListTile(contentPadding: EdgeInsets.zero, title: Text('$step')),
            ],
          ),
        for (final note in data['quality_notes'] as List? ?? [])
          Card(
            color: Colors.orange.shade50,
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text('$note'),
            ),
          ),
        if (trend != null)
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: const Text('Come cambiano i rilievi'),
            subtitle: Text('${trend['summary']}'),
            children: [
              for (final point in trend['points'] as List? ?? [])
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text('${point['observed_at']}'),
                  subtitle: Text(
                    'Piante interessate: ${point['affected_percent'] ?? '—'}% · intensità ${const {'mild': 'lieve', 'moderate': 'moderata', 'high': 'elevata'}[point['severity']] ?? 'non indicata'}',
                  ),
                ),
              if (trend['severity_change'] != null)
                Text(
                  'Intensità segnalata: ${const {'increased': 'aumentata', 'decreased': 'diminuita', 'unchanged': 'uguale'}[trend['severity_change']]}.',
                ),
              for (final limit in trend['limitations'] as List? ?? [])
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text('$limit', style: const TextStyle(fontSize: 12)),
                ),
            ],
          ),
        if (candidates.isNotEmpty) ...[
          const Text(
            'Piste da verificare',
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
          ),
          Text(
            '${data['evidence_note']}',
            style: const TextStyle(fontSize: 12),
          ),
          for (final candidate in candidates)
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: Text('${candidate['title']}'),
              subtitle: Text(
                (const {
                      'consistent_inputs': 'Ci sono riscontri compatibili',
                      'to_verify': 'Servono ulteriori verifiche',
                      'less_supported': 'Un dato non sostiene questa pista',
                      'conflicting_inputs':
                          'Prima chiarisci i dati discordanti',
                    })[candidate['status']] ??
                    'Da verificare',
              ),
              children: [
                for (final entry in {
                  'supporting': 'Elementi a favore',
                  'contradicting': 'Elementi che non concordano',
                  'missing': 'Cosa manca',
                }.entries)
                  if ((candidate[entry.key] as List? ?? []).isNotEmpty) ...[
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        entry.value,
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                    ),
                    for (final reason in candidate[entry.key] as List)
                      ListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        title: Text('$reason'),
                      ),
                  ],
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Text('${candidate['next_check']}'),
                ),
              ],
            ),
        ],
        if (questions.isNotEmpty)
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            initiallyExpanded: false,
            title: const Text('Domande per affinare l’analisi'),
            subtitle: Text('${questions.length} domande mirate'),
            children: [
              for (final q in questions)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text('${q['text']}'),
                  subtitle: Text('${q['reason']}'),
                ),
              if (onSectionRequested != null)
                Wrap(
                  spacing: 8,
                  children: [
                    for (final section in [3, 1, 4])
                      if (questions.any((q) => q['section'] == section))
                        TextButton.icon(
                          onPressed: () => onSectionRequested!(section),
                          icon: const Icon(Icons.edit_outlined),
                          label: Text(
                            '${const {3: 'Completa il rilievo', 1: 'Completa le misure del suolo', 4: 'Completa la coltura'}[section]}',
                          ),
                        ),
                  ],
                ),
            ],
          ),
        const SizedBox(height: 20),
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: const Text('Input analizzati'),
          children: [
            for (final input in data['inputs'] as List? ?? [])
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(
                  input['status'] == 'available'
                      ? Icons.check_circle_outline
                      : Icons.info_outline,
                  color: input['status'] == 'available'
                      ? Colors.teal
                      : Colors.orange.shade800,
                ),
                title: Text('${input['label']}'),
                subtitle: Text('${input['detail']}'),
              ),
          ],
        ),
        if (gaps.isNotEmpty)
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: const Text('Cosa manca per una risposta più precisa'),
            children: [
              for (final gap in gaps)
                ListTile(contentPadding: EdgeInsets.zero, title: Text('$gap')),
            ],
          ),
        const SizedBox(height: 10),
        Text('${data['limits']}', style: const TextStyle(fontSize: 12)),
      ],
    );
  }
}
