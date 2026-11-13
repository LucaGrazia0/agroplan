import 'dart:convert';

import 'package:flutter/material.dart';

import 'api.dart' as api;

class CropOverview extends StatefulWidget {
  const CropOverview({super.key});
  @override
  State<CropOverview> createState() => _CropOverviewState();
}

class _CropOverviewState extends State<CropOverview> {
  late final Future<Map<String, dynamic>> report = load();
  Future<Map<String, dynamic>> load() async {
    final response = await api
        .get(Uri.parse('${api.apiBaseUrl}/agronomy/overview'))
        .timeout(const Duration(seconds: 75));
    if (response.statusCode != 200) {
      throw Exception(
        'Analisi aziendale non disponibile. Riprova dal pulsante nella barra.',
      );
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Analisi colturale aziendale'),
    content: SizedBox(
      width: 650,
      child: FutureBuilder<Map<String, dynamic>>(
        future: report,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return Text('${snapshot.error}'.replaceFirst('Exception: ', ''));
          }
          if (!snapshot.hasData) {
            return const SizedBox(
              height: 100,
              child: Center(child: CircularProgressIndicator()),
            );
          }
          final data = snapshot.data!;
          final parcels = data['parcels'] as List;
          return SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${data['parcel_count']} particelle con dati salvati'),
                const SizedBox(height: 12),
                if (parcels.isEmpty)
                  const Text(
                    'Registra una particella e i relativi dati colturali per iniziare.',
                  ),
                for (final parcel in parcels)
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${parcel['name']}',
                            style: const TextStyle(fontWeight: FontWeight.bold),
                          ),
                          Text('${parcel['review']['summary']}'),
                          for (final check
                              in parcel['review']['checks'] as List)
                            Padding(
                              padding: const EdgeInsets.only(top: 8),
                              child: Text(
                                '${check['title']}: ${check['evidence']}\n${check['action']}',
                              ),
                            ),
                          for (final gap
                              in parcel['review']['missing_data'] as List)
                            Padding(
                              padding: const EdgeInsets.only(top: 6),
                              child: Text('• $gap'),
                            ),
                        ],
                      ),
                    ),
                  ),
                Text('${data['note']}', style: const TextStyle(fontSize: 12)),
              ],
            ),
          );
        },
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Chiudi'),
      ),
    ],
  );
}
