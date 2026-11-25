import 'package:flutter/material.dart';

class ObservationWeatherCard extends StatelessWidget {
  const ObservationWeatherCard({super.key, required this.data});
  final Map data;

  static String dateLabel(dynamic value) {
    final parsed = DateTime.tryParse('$value');
    if (parsed == null) return 'non disponibile';
    return '${parsed.day.toString().padLeft(2, '0')}/${parsed.month.toString().padLeft(2, '0')}/${parsed.year}';
  }

  static String dates(dynamic values) =>
      (values as List? ?? []).map(dateLabel).join(', ');

  @override
  Widget build(BuildContext context) {
    final missing = data['missing_dates'] as List? ?? [];
    final coverage = data['coverage'] as Map? ?? {};
    final paired = data['paired_days'] ?? 0;
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Meteo prima del rilievo',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text('Rilievo del ${dateLabel(data['observation_date'])}'),
            Text(
              '14 giorni precedenti: ${dateLabel(data['start_date'])} – ${dateLabel(data['end_date'])}',
            ),
            const SizedBox(height: 8),
            Text(
              '${data['available_days'] ?? 0} giorni con dati su 14',
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            Text(
              'Meteo disponibile fino al ${dateLabel(data['available_through'])}',
            ),
            Text(
              missing.isEmpty
                  ? 'Nessun giorno completamente mancante.'
                  : 'Giorni senza dati: ${dates(missing)}',
            ),
            if ((data['trailing_missing_dates'] as List? ?? []).isNotEmpty)
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text(
                  'Lo storico non include ancora gli ultimi giorni. Il ritardo non richiede di cambiare la data del rilievo.',
                ),
              ),
            const SizedBox(height: 8),
            Text(
              data['climatic_balance_mm'] == null
                  ? 'P − ET₀ non disponibile: mancano giorni con entrambi i dati.'
                  : 'P − ET₀: ${data['climatic_balance_mm']} mm sui $paired giorni confrontabili.',
            ),
            const Text(
              'I valori parziali non sono il totale di 14 giorni e non provano la causa dei sintomi.',
            ),
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: const Text('Copertura e valori disponibili'),
              children: [
                for (final entry in const {
                  'rain': ('Pioggia', 'rain_mm', 'mm'),
                  'et0': ('ET₀', 'et0_mm', 'mm'),
                  'tmax': ('Temperatura massima', 'max_temperature_c', '°C'),
                  'tmin': ('Temperatura minima', 'min_temperature_c', '°C'),
                }.entries)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(
                      '${entry.value.$1}: ${data[entry.value.$2] ?? '—'} ${entry.value.$3}',
                    ),
                    subtitle: Text(
                      '${coverage[entry.key]?['valid_days'] ?? 0}/14 giorni validi'
                      '${(coverage[entry.key]?['missing_dates'] as List? ?? []).isEmpty ? '' : '\nDate senza valore: ${dates(coverage[entry.key]?['missing_dates'])}'}',
                    ),
                  ),
                const Text(
                  'Pioggia ed ET₀: somme sui rispettivi giorni validi. Il saldo usa solo le stesse date con entrambi i valori. Temperature: estremi osservati nei dati disponibili.',
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
