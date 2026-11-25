import 'dart:convert';

import 'package:flutter/material.dart';

import 'api.dart' as api;

class WorkspacePanel extends StatefulWidget {
  const WorkspacePanel({super.key, required this.onChanged});
  final Future<void> Function() onChanged;
  @override
  State<WorkspacePanel> createState() => _WorkspacePanelState();
}

class _WorkspacePanelState extends State<WorkspacePanel> {
  Map status = {};
  List archives = [];
  bool busy = true;
  String? message;
  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    if (mounted) setState(() => busy = true);
    try {
      final s = await api
          .get(Uri.parse('${api.apiBaseUrl}/workspace/status'))
          .timeout(const Duration(seconds: 75));
      final a = await api
          .get(Uri.parse('${api.apiBaseUrl}/workspace/archives'))
          .timeout(const Duration(seconds: 75));
      if (s.statusCode != 200 || a.statusCode != 200) throw Exception();
      if (mounted) {
        setState(() {
          status = jsonDecode(s.body) as Map;
          archives = jsonDecode(a.body) as List;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(
          () => message =
              'Area di lavoro non disponibile. Collegati al server e riprova.',
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> change({String? archiveId}) async {
    final restoring = archiveId != null;
    final yes = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(
          restoring
              ? 'Ripristinare le particelle archiviate?'
              : 'Ripartire da zero?',
        ),
        content: Text(
          restoring
              ? 'Le particelle archiviate e i loro dati torneranno disponibili insieme alle particelle attuali.'
              : 'Le ${status['active_parcels']} particelle attive e i dati collegati verranno archiviati. Potrai recuperarli da questa schermata. Il collegamento al server resta disponibile.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Annulla'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text(restoring ? 'Ripristina' : 'Archivia e inizia'),
          ),
        ],
      ),
    );
    if (yes != true || !mounted) return;
    setState(() {
      busy = true;
      message = null;
    });
    try {
      final path = restoring
          ? '/workspace/archives/$archiveId/restore'
          : '/workspace/reset';
      final r = await api
          .post(
            Uri.parse('${api.apiBaseUrl}$path'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'expected_generation': status['generation']}),
          )
          .timeout(const Duration(seconds: 75));
      if (r.statusCode != 200) throw Exception();
      await widget.onChanged();
      if (mounted) {
        setState(
          () => message = restoring
              ? 'Archivio ripristinato.'
              : 'Area vuota: puoi creare la prima particella.',
        );
      }
    } catch (_) {
      if (mounted) {
        setState(
          () => message = 'Operazione non completata. Ricarica l’area di lavoro prima di riprovare.',
        );
      }
    }
    if (mounted) await load();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Area di lavoro'),
    content: SizedBox(
      width: 460,
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('${status['active_parcels'] ?? '—'} particelle attive'),
            const SizedBox(height: 12),
            const Text(
              'Puoi iniziare un’area vuota o recuperare le particelle archiviate con i relativi dati.',
            ),
            if (busy) const LinearProgressIndicator(),
            if (message != null)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Text(message!),
              ),
            FilledButton.tonalIcon(
              onPressed: busy || (status['active_parcels'] as num? ?? 0) == 0
                  ? null
                  : () => change(),
              icon: const Icon(Icons.restart_alt),
              label: const Text('Riparti da zero'),
            ),
            const SizedBox(height: 20),
            const Text(
              'Archivi recuperabili',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            if (archives.isEmpty && !busy)
              const Text('Non ci sono archivi precedenti.'),
            for (final archive in archives)
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text('${archive['parcel_count']} particelle'),
                subtitle: Text(
                  '${archive['created_at']}'
                      .replaceFirst('T', ' ')
                      .substring(0, 16),
                ),
                trailing: archive['restored_at'] != null
                    ? const Text('Ripristinato')
                    : TextButton(
                        onPressed: busy
                            ? null
                            : () => change(archiveId: '${archive['id']}'),
                        child: const Text('Ripristina'),
                      ),
              ),
          ],
        ),
      ),
    ),
    actions: [
      TextButton(onPressed: busy ? null : load, child: const Text('Ricarica')),
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Chiudi'),
      ),
    ],
  );
}
