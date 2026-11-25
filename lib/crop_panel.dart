import 'dart:convert';

import 'package:flutter/material.dart';

import 'api.dart' as http;

class CropPanel extends StatefulWidget {
  const CropPanel({
    super.key,
    required this.parcelId,
    required this.baseUrl,
    this.onChanged,
    this.onCropChanged,
  });
  final String parcelId;
  final String baseUrl;
  final VoidCallback? onChanged;
  final ValueChanged<String>? onCropChanged;
  @override
  State<CropPanel> createState() => _CropPanelState();
}

class _CropPanelState extends State<CropPanel> {
  List<Map<String, dynamic>> cycles = [];
  List<Map<String, dynamic>> observations = [];
  bool busy = false;
  bool saving = false;
  String? error;
  int? selectedCycle;
  final season = TextEditingController(text: DateTime.now().year.toString());
  final variety = TextEditingController();
  final date = TextEditingController(
    text: DateTime.now().toIso8601String().substring(0, 10),
  );
  final sowing = TextEditingController();
  final bbch = TextEditingController();
  final notes = TextEditingController();
  String crop = 'frumento_tenero';
  static const crops = {
    'frumento_tenero': 'Frumento tenero',
    'frumento_duro': 'Frumento duro',
    'orzo': 'Orzo',
    'mais': 'Mais',
    'avena': 'Avena',
    'segale': 'Segale',
    'triticale': 'Triticale',
  };
  @override
  void initState() {
    super.initState();
    refresh();
  }

  @override
  void dispose() {
    season.dispose();
    variety.dispose();
    date.dispose();
    sowing.dispose();
    bbch.dispose();
    notes.dispose();
    super.dispose();
  }

  Future<dynamic> request(String path, {Map<String, dynamic>? body}) async {
    final uri = Uri.parse('${widget.baseUrl}$path');
    final response = body == null
        ? await http.get(uri).timeout(const Duration(seconds: 15))
        : await http
              .post(
                uri,
                headers: {'Content-Type': 'application/json'},
                body: jsonEncode(body),
              )
              .timeout(const Duration(seconds: 15));
    if (response.statusCode >= 300) {
      throw Exception('HTTP ${response.statusCode}: ${response.body}');
    }
    return jsonDecode(response.body);
  }

  void selectCycle(int? id) {
    selectedCycle = id;
    final cycle = cycles.where((c) => c['id'] == id).firstOrNull;
    if (cycle == null) return;
    season.text = cycle['season'].toString();
    variety.text = cycle['variety']?.toString() ?? '';
    sowing.text = cycle['sowing_date']?.toString() ?? '';
    crop = cycle['crop'].toString();
  }

  Future<void> refresh() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final data = await request(
        '/crop/cycles?parcel_id=${Uri.encodeQueryComponent(widget.parcelId)}',
      ) as List;
      if (!mounted) return;
      cycles = data.map((e) => Map<String, dynamic>.from(e as Map)).toList();
      selectedCycle = cycles.isEmpty
          ? null
          : (cycles.any((e) => e['id'] == selectedCycle)
                ? selectedCycle
                : cycles.first['id'] as int);
      selectCycle(selectedCycle);
      await refreshObservations();
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> refreshObservations() async {
    if (selectedCycle == null) {
      if (mounted) setState(() => observations = []);
      return;
    }
    final data = await request('/crop/cycles/$selectedCycle/bbch') as List;
    if (mounted) {
      setState(
        () => observations = data
            .map((e) => Map<String, dynamic>.from(e as Map))
            .toList(),
      );
    }
  }

  Future<void> saveCycle() async {
    if (saving) return;
    setState(() {
      saving = true;
      error = null;
    });
    try {
      final saved = await request(
        '/crop/cycles',
        body: {
          'parcel_id': widget.parcelId,
          'season': season.text.trim(),
          'crop': crop,
          'variety': variety.text.trim(),
          'sowing_date': sowing.text.trim().isEmpty ? null : sowing.text.trim(),
        },
      );
      if (!mounted) return;
      selectedCycle = saved['id'] as int;
      await refresh();
      if (!mounted) return;
      widget.onCropChanged?.call(crops[crop] ?? crop);
      widget.onChanged?.call();
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Future<void> saveBbch() async {
    if (saving) return;
    final value = int.tryParse(bbch.text.trim());
    if (selectedCycle == null || value == null || value < 0 || value > 99) {
      setState(() => error = 'Seleziona un ciclo e inserisci BBCH tra 0 e 99');
      return;
    }
    setState(() {
      saving = true;
      error = null;
    });
    try {
      await request(
        '/crop/cycles/$selectedCycle/bbch',
        body: {
          'observed_at': date.text.trim(),
          'bbch': value,
          'notes': notes.text.trim(),
        },
      );
      if (!mounted) return;
      bbch.clear();
      notes.clear();
      await refreshObservations();
      if (mounted) widget.onChanged?.call();
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Colture e fenologia BBCH',
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
          ),
          if (busy) const LinearProgressIndicator(),
          if (error != null)
            Text(error!, style: const TextStyle(color: Colors.red)),
          TextField(
            controller: season,
            decoration: const InputDecoration(labelText: 'Stagione (es. 2026)'),
          ),
          DropdownButton<String>(
            value: crop,
            isExpanded: true,
            items: {...crops, if (!crops.containsKey(crop)) crop: crop}.entries
                .map(
                  (e) => DropdownMenuItem(value: e.key, child: Text(e.value)),
                )
                .toList(),
            onChanged: (v) {
              if (v != null) setState(() => crop = v);
            },
          ),
          TextField(
            controller: variety,
            decoration: const InputDecoration(
              labelText: 'Varietà (facoltativa)',
            ),
          ),
          TextField(
            controller: sowing,
            decoration: const InputDecoration(
              labelText: 'Data semina (AAAA-MM-GG, facoltativa)',
            ),
          ),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: saving ? null : saveCycle,
              icon: const Icon(Icons.add),
              label: const Text('Salva ciclo'),
            ),
          ),
          if (cycles.isNotEmpty)
            DropdownButton<int>(
              isExpanded: true,
              value: selectedCycle,
              items: cycles
                  .map(
                    (c) => DropdownMenuItem<int>(
                      value: c['id'] as int,
                      child: Text(
                        '${c['season']} · ${crops[c['crop']] ?? c['crop']}',
                      ),
                    ),
                  )
                  .toList(),
              onChanged: (v) {
                setState(() => selectCycle(v));
                refreshObservations();
              },
            ),
          if (selectedCycle != null) ...[
            TextField(
              controller: date,
              decoration: const InputDecoration(
                labelText: 'Data osservazione (AAAA-MM-GG)',
              ),
            ),
            TextField(
              controller: bbch,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Stadio BBCH (0–99)',
              ),
            ),
            TextField(
              controller: notes,
              decoration: const InputDecoration(labelText: 'Note'),
            ),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: saving ? null : saveBbch,
                icon: const Icon(Icons.add),
                label: const Text('Registra BBCH'),
              ),
            ),
            for (final o in observations.take(5))
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${o['observed_at']} · BBCH ${o['bbch']} ${o['notes'] ?? ''}',
                    ),
                    if (o['phenology'] is Map) ...[
                      Text('${o['phenology']['description']}'),
                      if (o['phenology']['status'] == 'stale')
                        const Text(
                          'Rilievo storico: aggiorna la fase in campo.',
                        ),
                      for (final note
                          in o['phenology']['quality_notes'] as List? ?? [])
                        Text(
                          '$note',
                          style: TextStyle(color: Colors.orange.shade900),
                        ),
                    ],
                  ],
                ),
              ),
          ],
        ],
      ),
    ),
  );
}
