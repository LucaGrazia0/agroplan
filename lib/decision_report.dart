import 'package:flutter/material.dart';

class DecisionReport extends StatelessWidget {
  const DecisionReport({super.key, required this.data});
  final Map data;

  @override
  Widget build(BuildContext context) {
    final urgent = data['status'] == 'priority_check';
    final conclusions = data['conclusions'] as List? ?? [];
    final steps = data['next_steps'] as List? ?? [];
    final gaps = data['missing_inputs'] as List? ?? [];
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
