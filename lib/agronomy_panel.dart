import 'dart:convert';

import 'package:flutter/material.dart';

import 'api.dart' as http;

class AgronomyPanel extends StatefulWidget {
  const AgronomyPanel({
    super.key,
    required this.parcelId,
    required this.latitude,
    required this.longitude,
    required this.baseUrl,
    this.revision = 0,
  });

  final String parcelId;
  final double latitude;
  final double longitude;
  final String baseUrl;
  final int revision;

  @override
  State<AgronomyPanel> createState() => _AgronomyPanelState();
}

class _AgronomyPanelState extends State<AgronomyPanel> {
  Map<String, dynamic>? result;
  bool loading = false;
  String? error;
  int requestVersion = 0;
  bool includeSatellite = false;

  static const cropNames = {
    'frumento_tenero': 'Frumento tenero',
    'frumento_duro': 'Frumento duro',
    'orzo': 'Orzo',
    'mais': 'Mais',
  };

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

  String number(dynamic value, {String suffix = ''}) {
    if (value is! num) return 'Dati insufficienti';
    return '${value.toStringAsFixed(1)}$suffix';
  }

  Widget metric(String label, dynamic value, String unit) {
    return Container(
      width: 145,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        border: Border.all(color: Colors.grey.shade300),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontSize: 12)),
          const SizedBox(height: 5),
          Text(
            number(value, suffix: value is num ? ' $unit' : ''),
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
        ],
      ),
    );
  }

  Widget periodCard(String period, Map<String, dynamic> data) {
    final complete = data['data_complete'] == true;

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Ultimi $period giorni disponibili',
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
                Icon(
                  complete ? Icons.check_circle_outline : Icons.info_outline,
                  color: complete ? Colors.green : Colors.orange,
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              '${data['start_date'] ?? '—'} → ${data['end_date'] ?? '—'}',
              style: const TextStyle(fontSize: 12),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                metric('Precipitazioni', data['rain_mm'], 'mm'),
                metric('ET₀', data['et0_mm'], 'mm'),
                metric('Bilancio climatico', data['climatic_balance_mm'], 'mm'),
                metric('Temperatura media', data['mean_temperature_c'], '°C'),
                metric('Temperatura massima', data['max_temperature_c'], '°C'),
                metric('Temperatura minima', data['min_temperature_c'], '°C'),
              ],
            ),
            if (!complete) ...[
              const SizedBox(height: 10),
              const Text(
                'Serie incompleta: alcuni indicatori potrebbero '
                'non essere disponibili.',
                style: TextStyle(fontSize: 12, color: Colors.orange),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget monitoringCard(Map<String, dynamic> alert) {
    final category = (alert['category'] ?? 'general').toString();
    final status = (alert['status'] ?? 'da_verificare').toString();
    final title = (alert['title'] ?? 'Segnalazione').toString();
    final evidence = alert['evidence'] is List
        ? alert['evidence'] as List
        : const [];
    final color = status == 'attenzione'
        ? Colors.orange.shade800
        : status == 'dati_insufficienti'
        ? Colors.grey.shade700
        : Colors.teal.shade700;
    final icon = switch (category) {
      'malattie' => Icons.coronavirus_outlined,
      'infestanti' => Icons.grass_outlined,
      'nutrizione' => Icons.science_outlined,
      'meteo' => Icons.cloud_outlined,
      _ => Icons.info_outline,
    };
    final label = switch (status) {
      'attenzione' => 'Controllo consigliato',
      'monitoraggio' => 'Monitoraggio',
      'dati_insufficienti' => 'Dati insufficienti',
      _ => 'Da verificare',
    };
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              label,
              style: TextStyle(color: color, fontWeight: FontWeight.w600),
            ),
            if (evidence.isNotEmpty) ...[
              const SizedBox(height: 8),
              for (final item in evidence)
                Padding(
                  padding: const EdgeInsets.only(bottom: 3),
                  child: Text('• $item', style: const TextStyle(fontSize: 12)),
                ),
            ],
            if ((alert['recommended_check'] ?? '').toString().isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('Verifica consigliata: ${alert['recommended_check']}'),
            ],
            if ((alert['limitations'] ?? '').toString().isNotEmpty)
              ExpansionTile(
                tilePadding: EdgeInsets.zero,
                title: const Text(
                  'Limiti della valutazione',
                  style: TextStyle(fontSize: 12),
                ),
                children: [
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Text(
                      '${alert['limitations']}',
                      style: const TextStyle(fontSize: 12),
                    ),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final data = result;
    final crop = data?['crop_context'];
    final cropMap = crop is Map ? crop : null;
    final bbch = cropMap?['latest_bbch'];
    final bbchMap = bbch is Map ? bbch : null;
    final windows = data?['windows'];
    final windowMap = windows is Map ? windows : null;
    final warnings = data?['warnings'];
    final warningList = warnings is List ? warnings : [];
    final monitoring = data?['monitoring_alerts'];
    final monitoringList = monitoring is List ? monitoring : [];
    final review = data?['crop_review'];

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'Analisi colturale',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                ),
                IconButton(
                  tooltip: 'Aggiorna analisi',
                  onPressed: loading ? null : load,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
            const SizedBox(height: 6),
            const Text(
              'Coltura, BBCH, meteo, suolo e osservazioni satellitari disponibili',
              style: TextStyle(fontSize: 12),
            ),
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Aggiorna anche i dati satellitari'),
              subtitle: const Text(
                'Fino a 3 acquisizioni recenti; usa la quota Copernicus del server.',
              ),
              value: includeSatellite,
              onChanged: loading
                  ? null
                  : (value) =>
                        setState(() => includeSatellite = value ?? false),
            ),
            if (loading) ...[
              const SizedBox(height: 12),
              const LinearProgressIndicator(),
              const SizedBox(height: 8),
              const Text('Analisi dei dati disponibili…'),
            ],
            if (error != null) ...[
              const SizedBox(height: 10),
              Text(
                error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
              TextButton(onPressed: load, child: const Text('Riprova')),
            ],
            if (data != null) ...[
              if (review is Map) ...[
                const Divider(height: 24),
                Text('${review['summary']}'),
                for (final check in (review['checks'] as List? ?? []))
                  if (check is Map)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text('${check['title']}'),
                      subtitle: Text(
                        '${check['evidence']}\n${check['action']}',
                      ),
                    ),
                if ((review['missing_data'] as List? ?? []).isNotEmpty)
                  ExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: const Text('Dati da completare'),
                    children: [
                      for (final gap in review['missing_data'] as List)
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text('$gap'),
                        ),
                    ],
                  ),
              ],
              const Divider(height: 24),
              Text(
                'Coltura: ${cropNames[cropMap?['crop']] ?? 'Non registrata'}',
              ),
              Text('Stagione: ${cropMap?['season'] ?? '—'}'),
              Text(
                bbchMap == null
                    ? 'BBCH: non registrato'
                    : 'BBCH ${bbchMap['bbch']} '
                          '(osservato il ${bbchMap['observed_at']})',
              ),
              const SizedBox(height: 8),
              Text(
                'Fonte: ${data['source'] ?? '—'} | '
                'Storico fino al ${data['historical_end'] ?? '—'}',
                style: const TextStyle(fontSize: 12),
              ),
              const SizedBox(height: 14),
              const Text(
                'Monitoraggio agronomico',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 5),
              const Text(
                'Segnalazioni esplorative: non sono diagnosi né indicazioni di trattamento.',
                style: TextStyle(fontSize: 12),
              ),
              const SizedBox(height: 10),
              if (monitoringList.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(bottom: 12),
                  child: Text(
                    'Nessuna segnalazione disponibile. Verifica che il backend sia aggiornato.',
                  ),
                ),
              for (final item in monitoringList)
                if (item is Map)
                  monitoringCard(Map<String, dynamic>.from(item)),
              const Divider(height: 24),
              const Text(
                'Indicatori meteorologici',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 10),
              if (windowMap != null)
                for (final period in ['7', '15', '30'])
                  if (windowMap[period] is Map)
                    periodCard(
                      period,
                      Map<String, dynamic>.from(windowMap[period] as Map),
                    ),
              if (warningList.isNotEmpty) ...[
                const SizedBox(height: 8),
                const Text(
                  'Avvertenze',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
                for (final warning in warningList)
                  Padding(
                    padding: const EdgeInsets.only(top: 5),
                    child: Text('• $warning'),
                  ),
              ],
              const Divider(height: 24),
              const Text(
                'Interpretazione',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 5),
              const Text(
                'Il bilancio climatico è calcolato come '
                'precipitazioni meno ET₀ (P − ET₀). '
                'Non equivale al bilancio idrico del terreno e '
                'non dimostra da solo uno stress idrico.',
                style: TextStyle(fontSize: 12),
              ),
              const SizedBox(height: 8),
              const Text(
                'Le segnalazioni di monitoraggio non costituiscono una stima validata '
                'del rischio fitosanitario. Servono osservazioni in campo e, per '
                'stimare il rischio di infezione, modelli specifici per patogeno.',
                style: TextStyle(fontSize: 12),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
