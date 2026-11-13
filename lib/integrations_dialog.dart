import 'dart:convert';

import 'package:flutter/material.dart';

import 'api.dart' as api;

class IntegrationsDialog extends StatefulWidget {
  const IntegrationsDialog({
    super.key,
    this.latitude = 44.65,
    this.longitude = 11.18,
  });
  final double latitude;
  final double longitude;
  @override
  State<IntegrationsDialog> createState() => _IntegrationsDialogState();
}

class _IntegrationsDialogState extends State<IntegrationsDialog> {
  bool loading = true;
  String? error;
  Map<String, dynamic>? result;
  static const labels = {
    'copernicus': 'Satelliti Copernicus',
    'open_meteo': 'Storico meteo e ET0',
    'nasa_power': 'Storico di riserva NASA',
    'met_norway': 'Previsioni MET Norway',
    'soil_rer': 'Suolo Emilia-Romagna',
    'osm': 'Mappa stradale',
    'imagery': 'Mappa satellitare',
  };
  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final response = await api
          .post(
            Uri.parse('${api.apiBaseUrl}/integrations/status'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'latitude': widget.latitude,
              'longitude': widget.longitude,
            }),
          )
          .timeout(const Duration(seconds: 75));
      if (response.statusCode != 200) {
        throw Exception('Verifica non disponibile');
      }
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      if (mounted) setState(() => result = data);
    } catch (_) {
      if (mounted) {
        setState(
          () => error = 'Verifica non riuscita. Controlla che il server sia raggiungibile e riprova.',
        );
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Collegamenti e servizi'),
    content: SizedBox(
      width: 500,
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (loading) const LinearProgressIndicator(),
            if (loading)
              const Padding(
                padding: EdgeInsets.only(top: 12),
                child: Text('Verifica dei servizi in corso…'),
              ),
            if (error != null)
              Text(error!, style: const TextStyle(color: Colors.red)),
            if (result != null) ...[
              const SizedBox(height: 8),
              for (final item in result!['services'] as List)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(
                    item['status'] == 'ok'
                        ? Icons.check_circle
                        : item['status'] == 'not_covered'
                        ? Icons.info_outline
                        : Icons.cloud_off,
                    color: item['status'] == 'ok'
                        ? Colors.green
                        : item['status'] == 'not_covered'
                        ? Colors.orange
                        : Colors.red,
                  ),
                  title: Text(labels[item['id']] ?? item['id'].toString()),
                  subtitle: Text(
                    item['message']?.toString() ?? 'Esito non disponibile',
                  ),
                ),
              Text(
                'Verifica: ${DateTime.tryParse(result!['checked_at']?.toString() ?? '')?.toLocal().toString().substring(0, 16) ?? 'ora'}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: loading ? null : load,
        child: const Text('Riprova'),
      ),
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Chiudi'),
      ),
    ],
  );
}
