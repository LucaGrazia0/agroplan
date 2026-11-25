import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Changes only this server/farm's cache after a confirmed server reset.
Future<bool> reconcileWorkspaceCache(
  SharedPreferences prefs,
  String cacheKey,
  String draftPrefix,
  int generation,
) async {
  if (generation < 0) {
    throw const FormatException('Versione area di lavoro non valida');
  }
  final key = '${cacheKey}_generation';
  final previous = prefs.getInt(key) ?? 0;
  if (generation < previous) {
    throw const FormatException(
      'Il server espone una versione precedente dell’area di lavoro.',
    );
  }
  if (generation != previous) {
    final saved = prefs.getString(cacheKey);
    final ids = <String>{};
    if (saved != null) {
      try {
        final data = jsonDecode(saved) as Map;
        for (final row in data['parcels'] as List? ?? []) {
          ids.add('${row['id']}');
        }
      } catch (_) {
        /* Keep the original bytes in the private backup. */
      }
    }
    final drafts = <String, String>{};
    for (final k in prefs.getKeys().where((k) => k.startsWith(draftPrefix))) {
      final text = prefs.getString(k);
      if (text == null) continue;
      try {
        final payload = (jsonDecode(text) as Map)['payload'] as Map;
        final id = '${payload['parcel_id']}';
        if (ids.contains(id) && k == '$draftPrefix$id') drafts[k] = text;
      } catch (_) {
        /* Unknown drafts remain untouched. */
      }
    }
    if (saved != null || drafts.isNotEmpty) {
      final ok = await prefs.setString(
        '${cacheKey}_before_reset_$previous',
        jsonEncode({'cache': saved, 'drafts': drafts}),
      );
      if (!ok) throw Exception('Copia locale precedente non conservata.');
    }
    if (saved != null && !await prefs.remove(cacheKey)) {
      throw Exception('Copia locale non aggiornata.');
    }
    for (final k in drafts.keys) {
      if (!await prefs.remove(k)) {
        throw Exception('Bozza precedente non aggiornata.');
      }
    }
  }
  if (!await prefs.setInt(key, generation)) {
    throw Exception('Versione area di lavoro non salvata.');
  }
  return generation != previous;
}
