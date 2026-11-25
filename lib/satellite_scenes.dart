// Several tiles can cover a parcel on the same day. The selector represents
// acquisition days, so retain one (least cloudy) scene per UTC date.
List<Map<String, dynamic>> acquisitionDays(
  Iterable<Map<String, dynamic>> scenes,
) {
  final byDay = <String, Map<String, dynamic>>{};
  for (final scene in scenes) {
    final timestamp = DateTime.tryParse(scene['datetime']?.toString() ?? '');
    final clouds = scene['cloud_cover'];
    if (timestamp == null ||
        clouds is! num ||
        !clouds.isFinite ||
        clouds > 30 ||
        clouds < 0) {
      continue;
    }
    final day = timestamp.toUtc().toIso8601String().substring(0, 10);
    final previous = byDay[day];
    if (previous == null || clouds < (previous['cloud_cover'] as num)) {
      byDay[day] = {...scene, 'datetime': timestamp.toUtc().toIso8601String()};
    }
  }
  final dates = byDay.keys.toList()..sort((a, b) => b.compareTo(a));
  return [for (final day in dates) byDay[day]!];
}
