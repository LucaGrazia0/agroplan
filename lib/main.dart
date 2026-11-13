import 'dart:ui' as ui;
import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'api.dart' as http;

import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'soil_panel.dart';
import 'crop_panel.dart';
import 'agronomy_panel.dart';
import 'api.dart';
import 'login_page.dart';
import 'integrations_dialog.dart';
import 'satellite_scenes.dart';
import 'crop_overview.dart';

part 'parcel_sync.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await restoreNativeServer();
  await ApiSession.instance.restorePairedDevice();
  runApp(const AgroPlanApp());
}

class AgroPlanApp extends StatelessWidget {
  const AgroPlanApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'AgroPlan',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF32764A)),
      useMaterial3: true,
    ),
    home: ListenableBuilder(
      listenable: ApiSession.instance,
      builder: (context, _) => ApiSession.instance.authenticated
          ? AgroPlanHome(key: ValueKey(ApiSession.instance.farmId))
          : LoginPage(configureServerOnStart: !nativeServerConfigured),
    ),
  );
}

class FarmParcel {
  FarmParcel({
    required this.id,
    required this.name,
    required this.points,
    required this.crop,
    this.soil = const {},
    this.revision = 0,
    this.pending = false,
  });
  final String id;
  String name;
  final List<LatLng> points;
  String crop;
  Map<String, String> soil;
  int revision;
  bool pending;

  double get hectares => polygonArea(points) / 10000;

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'crop': crop,
    'soil': soil,
    'revision': revision,
    'pending': pending,
    'points': points
        .map((p) => {'lat': p.latitude, 'lng': p.longitude})
        .toList(),
  };

  factory FarmParcel.fromJson(Map<String, dynamic> json) => FarmParcel(
    id: json['id'].toString(),
    revision: (json['revision'] as num?)?.toInt() ?? 0,
    pending: json['pending'] == true,
    name: json['name'].toString(),
    crop: json['crop'].toString(),
    soil: json['soil'] is Map
        ? Map<String, String>.from(
            (json['soil'] as Map).map(
              (k, v) => MapEntry(k.toString(), v.toString()),
            ),
          )
        : {},
    points: (json['points'] as List)
        .map(
          (p) => LatLng(
            (p['lat'] as num).toDouble(),
            (p['lng'] as num).toDouble(),
          ),
        )
        .toList(),
  );
}

// Approximate spherical area, suitable for a prototype (not cadastral surveys).
double polygonArea(List<LatLng> points) {
  if (points.length < 3) return 0;
  const radius = 6371008.8;
  double sum = 0;
  for (var i = 0; i < points.length; i++) {
    final a = points[i];
    final b = points[(i + 1) % points.length];
    final lat1 = a.latitude * math.pi / 180;
    final lat2 = b.latitude * math.pi / 180;
    final lon1 = a.longitude * math.pi / 180;
    final lon2 = b.longitude * math.pi / 180;
    var deltaLon = lon2 - lon1;
    if (deltaLon > math.pi) deltaLon -= 2 * math.pi;
    if (deltaLon < -math.pi) deltaLon += 2 * math.pi;
    sum += deltaLon * (2 + math.sin(lat1) + math.sin(lat2));
  }
  return (sum * radius * radius / 2).abs();
}

bool containsPoint(LatLng point, List<LatLng> polygon) {
  if (polygon.length < 3) return false;
  var inside = false;
  var j = polygon.length - 1;
  for (var i = 0; i < polygon.length; i++) {
    final xi = polygon[i].longitude;
    final yi = polygon[i].latitude;
    final xj = polygon[j].longitude;
    final yj = polygon[j].latitude;
    if ((yi > point.latitude) != (yj > point.latitude)) {
      final intersection = (xj - xi) * (point.latitude - yi) / (yj - yi) + xi;
      if (point.longitude < intersection) inside = !inside;
    }
    j = i;
  }
  return inside;
}

class AgroPlanHome extends StatefulWidget {
  const AgroPlanHome({super.key});

  @override
  State<AgroPlanHome> createState() => _AgroPlanHomeState();
}

class _AgroPlanHomeState extends _ParcelSyncState with _ParcelSync {
  final mapController = MapController();
  final drawingPoints = <LatLng>[];
  bool drawing = false;
  bool satellite = false;
  bool editingVertices = false;
  int? movingVertex;
  String indexLayer = "Nessuno";
  // Copernicus backend locale. Su Android emulator usare 10.0.2.2;
  // su dispositivi fisici usare l'IP LAN del Mac e un server accessibile in rete.
  static String get copernicusBaseUrl => apiBaseUrl;
  DateTime satelliteDate = DateTime.now().toUtc().subtract(
    const Duration(days: 7),
  );
  bool satelliteDateChosen = false;
  bool satelliteBusy = false;
  String? satelliteError;
  String? overlayParcelId;
  Uint8List? overlayPng;
  LatLngBounds? overlayBounds;
  List<Map<String, dynamic>> availableScenes = [];
  int satelliteRequestId = 0;
  Map<String, dynamic>? parcelStats;
  List<Map<String, dynamic>> temporalStats = [];
  bool statsBusy = false;
  String? statsError;
  int statsRequestId = 0;

  // Meteo: cache legata alla particella, senza modificare le richieste Copernicus.
  Map<String, dynamic>? weatherData;
  String? weatherParcelId;
  bool weatherBusy = false;
  String? weatherError;
  int weatherRequestId = 0;

  @override
  void clearWeather() {
    weatherRequestId++;
    weatherData = null;
    weatherParcelId = null;
    weatherBusy = false;
    weatherError = null;
  }

  Future<void> loadWeather() async {
    final parcel = selectedParcel;
    if (parcel == null || parcel.points.isEmpty || weatherBusy) return;
    final requestId = ++weatherRequestId;
    // Prima versione: media dei vertici; non è il centroide geometrico.
    final latitude =
        parcel.points.map((p) => p.latitude).reduce((a, b) => a + b) /
        parcel.points.length;
    final longitude =
        parcel.points.map((p) => p.longitude).reduce((a, b) => a + b) /
        parcel.points.length;
    setState(() {
      weatherBusy = true;
      weatherError = null;
    });
    try {
      final response = await http
          .post(
            Uri.parse('$copernicusBaseUrl/weather'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'latitude': latitude,
              'longitude': longitude,
              'history_days': 180,
            }),
          )
          .timeout(const Duration(seconds: 100));
      if (response.statusCode != 200) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      final result = Map<String, dynamic>.from(
        jsonDecode(response.body) as Map,
      );
      if (!mounted ||
          requestId != weatherRequestId ||
          selectedId != parcel.id) {
        return;
      }
      setState(() {
        weatherData = result;
        weatherParcelId = parcel.id;
        weatherBusy = false;
      });
    } catch (e) {
      if (!mounted ||
          requestId != weatherRequestId ||
          selectedId != parcel.id) {
        return;
      }
      setState(() {
        weatherBusy = false;
        weatherError = 'Meteo non disponibile: $e';
      });
    }
  }

  Widget buildWeatherPanel(FarmParcel parcel) {
    final data = weatherParcelId == parcel.id ? weatherData : null;
    final current = data?['current'] is Map
        ? Map<String, dynamic>.from(data!['current'] as Map)
        : <String, dynamic>{};
    final history = data?['history'] is List
        ? (data!['history'] as List)
              .whereType<Map>()
              .map((e) => Map<String, dynamic>.from(e))
              .toList()
        : <Map<String, dynamic>>[];
    final forecast = data?['forecast'] is List
        ? (data!['forecast'] as List)
              .whereType<Map>()
              .map((e) => Map<String, dynamic>.from(e))
              .toList()
        : <Map<String, dynamic>>[];
    final rainByDay = <String, double>{};
    for (final row in history) {
      if (row['date'] is String && row['precipitation_sum'] is num) {
        rainByDay[row['date'] as String] = (row['precipitation_sum'] as num)
            .toDouble();
      }
    }
    final satelliteValues = temporalStats
        .where((e) => e['mean'] is num && e['date'] is String)
        .toList();
    double? previousRain(String date, int days) {
      final end = DateTime.tryParse(date);
      if (end == null) return null;
      var sum = 0.0;
      for (var offset = 1; offset <= days; offset++) {
        final d = end.subtract(Duration(days: offset));
        final key =
            '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
        final rain = rainByDay[key];
        if (rain == null) {
          return null; // Never treat missing weather as zero rainfall.
        }
        sum += rain;
      }
      return sum;
    }

    final matching = satelliteValues
        .map(
          (row) => <String, dynamic>{
            'date': row['date'],
            'mean': row['mean'],
            'rain7': previousRain(row['date'] as String, 7),
            'rain15': previousRain(row['date'] as String, 15),
            'rain30': previousRain(row['date'] as String, 30),
          },
        )
        .where((row) => row['rain7'] != null)
        .toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'Meteo della particella',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: weatherBusy ? null : loadWeather,
          icon: const Icon(Icons.cloud_sync_outlined),
          label: Text(data == null ? 'Carica meteo' : 'Aggiorna meteo'),
        ),
        if (weatherBusy)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: LinearProgressIndicator(),
          ),
        if (weatherError != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              weatherError!,
              style: const TextStyle(color: Colors.red),
            ),
          ),
        if (data != null) ...[
          const SizedBox(height: 8),
          Text('Temperatura attuale: ${current['temperature_2m'] ?? '—'} °C'),
          Text(
            'Umidità: ${current['relative_humidity_2m'] ?? '—'}% · Vento: ${current['wind_speed_10m'] ?? '—'} km/h',
          ),
          const SizedBox(height: 10),
          Text(
            'Precipitazioni nei 7 giorni storici: ${data['rain_7d_mm'] ?? '—'} mm',
          ),
          Text(
            '15 giorni: ${data['rain_15d_mm'] ?? '—'} mm · 30 giorni: ${data['rain_30d_mm'] ?? '—'} mm',
          ),
          Text(
            'Storico disponibile fino al ${data['historical_end'] ?? '—'} (non fino a oggi)',
            style: const TextStyle(fontSize: 11, color: Colors.black54),
          ),
          if (forecast.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Text(
              'Previsioni prossimi giorni',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            for (final row in forecast.take(7))
              Padding(
                padding: const EdgeInsets.only(top: 3),
                child: Text(
                  '${row['date'] ?? '—'} · ${row['temperature_2m_min'] ?? '—'}–${row['temperature_2m_max'] ?? '—'} °C · Pioggia ${row['precipitation_sum'] ?? '—'} mm',
                  style: const TextStyle(fontSize: 12),
                ),
              ),
          ],
          if (history.isNotEmpty) ...[
            const SizedBox(height: 14),
            const Text(
              'Precipitazioni giornaliere (ultimi 30 giorni disponibili)',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 6),
            SizedBox(
              height: 150,
              child: CustomPaint(
                painter: WeatherRainPainter(
                  history.length > 30
                      ? history.sublist(history.length - 30)
                      : history,
                ),
                child: const SizedBox.expand(),
              ),
            ),
          ],
          const SizedBox(height: 14),
          Text(
            'Confronto ${indexLayer == 'Nessuno' ? 'satellite' : indexLayer} × precipitazioni',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 5),
          if (satelliteValues.isEmpty)
            const Text(
              'Carica anche “Statistiche e andamento temporale” per confrontare satellite e piogge.',
              style: TextStyle(fontSize: 12),
            ),
          if (satelliteValues.isNotEmpty && matching.isEmpty)
            const Text(
              'Lo storico meteo non copre i 7 giorni precedenti alle acquisizioni. Ricarica il meteo.',
              style: TextStyle(fontSize: 12),
            ),
          if (matching.isNotEmpty) ...[
            const Text(
              'Linea verde: indice satellitare · barre blu: pioggia nei 7 giorni precedenti (assi distinti).',
              style: TextStyle(fontSize: 11),
            ),
            if (matching.length >= 2)
              SizedBox(
                height: 205,
                child: CustomPaint(
                  painter: NdviRainComparisonPainter(matching),
                  child: const SizedBox.expand(),
                ),
              ),
            const SizedBox(height: 6),
            const Text(
              'Data · Indice · Pioggia antecedente 7 / 15 / 30 giorni (mm)',
              style: TextStyle(fontWeight: FontWeight.w600, fontSize: 11),
            ),
            for (final row in matching)
              Text(
                '${row['date']} · ${statNumber(row['mean'])} · ${statNumber(row['rain7'], digits: 1)} / ${statNumber(row['rain15'], digits: 1)} / ${statNumber(row['rain30'], digits: 1)}',
                style: const TextStyle(fontSize: 12),
              ),
          ],
          const SizedBox(height: 8),
          const Text(
            'Fonte: Open-Meteo. Dati modellati su griglia, non misure in campo. '
            'Per interpretare l’effetto delle piogge sulla vegetazione occorrono anche i giorni precedenti, '
            'la coltura e la fase fenologica.',
            style: TextStyle(fontSize: 11),
          ),
        ],
      ],
    );
  }

  @override
  String? selectedId;

  static const crops = [
    'Non assegnata',
    'Frumento tenero',
    'Frumento duro',
    'Orzo',
    'Mais',
    'Avena',
    'Segale',
    'Triticale',
  ];

  @override
  void initState() {
    super.initState();
    loadParcels();
  }

  Future<void> loadParcels() => restoreParcels();

  @override
  Future<void> saveParcels() => persistParcels();

  FarmParcel? get selectedParcel {
    for (final p in parcels) {
      if (p.id == selectedId) return p;
    }
    return null;
  }

  void handleMapTap(TapPosition tap, LatLng position) {
    if (editingVertices && selectedParcel != null) {
      if (movingVertex != null) {
        setState(() {
          selectedParcel!.points[movingVertex!] = position;
          movingVertex = null;
          clearSatelliteOverlay();
          clearWeather();
        });
        saveParcels();
      }
      return;
    }
    if (drawing) {
      setState(() => drawingPoints.add(position));
      return;
    }
    FarmParcel? found;
    for (final p in parcels.reversed) {
      if (containsPoint(position, p.points)) {
        found = p;
        break;
      }
    }
    setState(() {
      if (selectedId != found?.id) {
        clearSatelliteOverlay();
        clearWeather();
        availableScenes = [];
        satelliteDateChosen = false;
      }
      selectedId = found?.id;
    });
  }

  void startDrawing() => setState(() {
    editingVertices = false;
    movingVertex = null;
    drawing = true;
    selectedId = null;
    drawingPoints.clear();
    availableScenes = [];
    satelliteDateChosen = false;
    clearSatelliteOverlay();
    clearWeather();
  });

  void cancelDrawing() => setState(() {
    drawing = false;
    drawingPoints.clear();
  });

  void startEditing() => setState(() {
    drawing = false;
    editingVertices = true;
    movingVertex = null;
  });

  void stopEditing() => setState(() {
    editingVertices = false;
    movingVertex = null;
  });

  Future<void> addVertexAtMidpoint(int index) async {
    final parcel = selectedParcel;
    if (parcel == null) return;
    final a = parcel.points[index];
    final b = parcel.points[(index + 1) % parcel.points.length];
    setState(
      () => parcel.points.insert(
        index + 1,
        LatLng((a.latitude + b.latitude) / 2, (a.longitude + b.longitude) / 2),
      ),
    );
    setState(() {
      clearSatelliteOverlay();
      clearWeather();
    });
    await saveParcels();
  }

  Future<void> removeVertex(int index) async {
    final parcel = selectedParcel;
    if (parcel == null || parcel.points.length <= 3) return;
    setState(() {
      parcel.points.removeAt(index);
      movingVertex = null;
      clearSatelliteOverlay();
      clearWeather();
    });
    await saveParcels();
  }

  Map<String, dynamic> parcelGeometry(FarmParcel parcel) => {
    'type': 'Polygon',
    'coordinates': [
      [
        ...parcel.points.map((p) => [p.longitude, p.latitude]),
        [parcel.points.first.longitude, parcel.points.first.latitude],
      ],
    ],
  };

  LatLngBounds parcelBounds(FarmParcel parcel) {
    final south = parcel.points.map((p) => p.latitude).reduce(math.min);
    final north = parcel.points.map((p) => p.latitude).reduce(math.max);
    final west = parcel.points.map((p) => p.longitude).reduce(math.min);
    final east = parcel.points.map((p) => p.longitude).reduce(math.max);
    return LatLngBounds(LatLng(south, west), LatLng(north, east));
  }

  void clearSatelliteStats() {
    statsRequestId++;
    parcelStats = null;
    temporalStats = [];
    statsBusy = false;
    statsError = null;
  }

  String formatSatelliteDate(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  Future<void> loadSatelliteStatistics() async {
    final parcel = selectedParcel;
    if (parcel == null || indexLayer == 'Nessuno' || statsBusy) return;
    final id = ++statsRequestId;
    setState(() {
      statsBusy = true;
      statsError = null;
      parcelStats = null;
      temporalStats = [];
    });
    try {
      if (!satelliteDateChosen) {
        if (availableScenes.isEmpty) await searchSatelliteScenes();
        if (!mounted || id != statsRequestId || selectedId != parcel.id) return;
        if (availableScenes.isEmpty) {
          setState(() {
            statsBusy = false;
            statsError = 'Nessuna acquisizione utilizzabile disponibile.';
          });
          return;
        }
        setState(() {
          satelliteDate = DateTime.parse(
            availableScenes.first['datetime'].toString(),
          );
          satelliteDateChosen = true;
        });
      }
      final selectedDay = formatSatelliteDate(satelliteDate);
      final dates = <String>{selectedDay};
      for (final scene in availableScenes) {
        final d = scene['datetime']?.toString();
        if (d != null && d.length >= 10) dates.add(d.substring(0, 10));
      }
      // Statistics must not depend on the user having pressed "Search scenes".
      // When fewer than two dates are known, query Catalog automatically.
      if (dates.length < 2) {
        final end = DateTime.now().toUtc();
        final start = end.subtract(const Duration(days: 90));
        final catalogResponse = await http
            .post(
              Uri.parse('$copernicusBaseUrl/scenes'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({
                'geometry': parcelGeometry(parcel),
                'start_date': formatSatelliteDate(start),
                'end_date': formatSatelliteDate(end),
                'max_cloud_coverage': 30,
                'limit': 100,
              }),
            )
            .timeout(const Duration(seconds: 45));
        if (catalogResponse.statusCode != 200) {
          throw Exception(
            'Ricerca acquisizioni HTTP ${catalogResponse.statusCode}: ${catalogResponse.body}',
          );
        }
        final catalog =
            jsonDecode(catalogResponse.body) as Map<String, dynamic>;
        final discovered = acquisitionDays(
          (catalog['scenes'] as List<dynamic>? ?? []).map(
            (e) => Map<String, dynamic>.from(e as Map),
          ),
        );
        for (final scene in discovered) {
          final d = scene['datetime']?.toString();
          if (d != null && d.length >= 10) dates.add(d.substring(0, 10));
        }
        if (!mounted || id != statsRequestId || selectedId != parcel.id) return;
        setState(() {
          availableScenes = discovered;
        });
      }
      final ordered = dates.toList()..sort();
      // At most 30 distinct dates; always include the currently selected date.
      final recent = ordered.reversed.take(29).toList();
      if (!recent.contains(selectedDay)) recent.add(selectedDay);
      recent.sort();
      final response = await http
          .post(
            Uri.parse('$copernicusBaseUrl/parcel-timeseries'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'geometry': parcelGeometry(parcel),
              'dates': recent,
              'index': indexLayer.toLowerCase(),
              'max_cloud_coverage': 30,
            }),
          )
          .timeout(const Duration(seconds: 240));
      if (response.statusCode != 200) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      final result = jsonDecode(response.body) as Map<String, dynamic>;
      if (!mounted || id != statsRequestId || selectedId != parcel.id) return;
      final values = (result['observations'] as List<dynamic>? ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
      Map<String, dynamic>? selectedStats;
      for (final item in values) {
        if (item['date'] == selectedDay) selectedStats = item;
      }
      setState(() {
        temporalStats = values;
        parcelStats = selectedStats;
        statsBusy = false;
      });
    } catch (e) {
      if (!mounted || id != statsRequestId) return;
      setState(() {
        statsBusy = false;
        statsError = 'Statistiche non disponibili: $e';
      });
    }
  }

  String statNumber(dynamic n, {int digits = 3}) =>
      n is num ? n.toStringAsFixed(digits).replaceAll('.', ',') : '—';

  Widget buildSatelliteStats() {
    final data = parcelStats;
    final valid = temporalStats.where((e) => e['mean'] is num).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 10),
        OutlinedButton.icon(
          onPressed: statsBusy ? null : loadSatelliteStatistics,
          icon: const Icon(Icons.show_chart),
          label: const Text('Statistiche e andamento temporale'),
        ),
        if (statsBusy)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 10),
            child: LinearProgressIndicator(),
          ),
        if (statsError != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(statsError!, style: const TextStyle(color: Colors.red)),
          ),
        if (data != null) ...[
          const SizedBox(height: 12),
          Text(
            'Statistiche ${indexLayer.toUpperCase()} · ${data['date']}',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          if (data['mean'] == null)
            const Text('Nessun pixel valido per questa acquisizione.'),
          if (data['mean'] != null) ...[
            Text('Media: ${statNumber(data['mean'])}'),
            Text('Minimo: ${statNumber(data['min'])}'),
            Text('Massimo: ${statNumber(data['max'])}'),
            Text(
              'Pixel validi: ${statNumber(data['valid_percent'], digits: 1)}%',
            ),
            Text(
              'Campioni analizzati: ${data['sample_count'] ?? '—'} · validi: ${data['valid_count'] ?? '—'}',
              style: const TextStyle(fontSize: 12),
            ),
          ],
        ],
        if (temporalStats.isNotEmpty) ...[
          const SizedBox(height: 14),
          Text(
            'Andamento temporale · ${valid.length} acquisizioni valide su ${temporalStats.length}',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 6),
          if (valid.length < 2)
            const Text(
              'Servono almeno due date con osservazioni valide per il grafico.',
            ),
          if (valid.length >= 2)
            SizedBox(
              height: 190,
              child: CustomPaint(
                painter: SatelliteTrendPainter(temporalStats),
                child: const SizedBox.expand(),
              ),
            ),
          const SizedBox(height: 6),
          const Text(
            'Ogni punto rappresenta la media dei pixel validi nella particella. '
            'Le date senza dati restano escluse dal tracciato. '
            'Nuvolosità e condizioni atmosferiche possono influenzare il confronto.',
            style: TextStyle(fontSize: 11),
          ),
        ],
      ],
    );
  }

  @override
  void clearSatelliteOverlay() {
    satelliteRequestId++;
    clearSatelliteStats();
    overlayPng = null;
    overlayBounds = null;
    overlayParcelId = null;
    satelliteError = null;
    satelliteBusy = false;
  }

  Future<void> searchSatelliteScenes() async {
    final parcel = selectedParcel;
    if (parcel == null || satelliteBusy) return;
    final requestId = ++satelliteRequestId;
    setState(() {
      satelliteBusy = true;
      satelliteError = null;
      availableScenes = [];
    });
    try {
      final end = DateTime.now();
      final start = end.subtract(const Duration(days: 90));
      String day(DateTime d) =>
          '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
      final response = await http
          .post(
            Uri.parse('$copernicusBaseUrl/scenes'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'geometry': parcelGeometry(parcel),
              'start_date': day(start),
              'end_date': day(end),
              'max_cloud_coverage': 30,
              'limit': 50,
            }),
          )
          .timeout(const Duration(seconds: 45));
      if (response.statusCode != 200) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      final scenes = acquisitionDays(
        (decoded['scenes'] as List<dynamic>? ?? []).map(
          (e) => Map<String, dynamic>.from(e as Map),
        ),
      );
      if (!mounted ||
          requestId != satelliteRequestId ||
          selectedId != parcel.id) {
        return;
      }
      setState(() {
        availableScenes = scenes;
        satelliteBusy = false;
        if (scenes.isNotEmpty) {
          satelliteDate = DateTime.parse(scenes.first['datetime'].toString());
          satelliteDateChosen = true;
        } else {
          satelliteError = 'Nessuna acquisizione con nuvolosità della scena ≤30% negli ultimi 90 giorni.';
        }
      });
    } catch (e) {
      if (!mounted || requestId != satelliteRequestId) return;
      setState(() {
        satelliteBusy = false;
        satelliteError = 'Ricerca non riuscita: $e';
      });
    }
  }

  Future<void> loadSatelliteOverlay() async {
    final parcel = selectedParcel;
    if (parcel == null || satelliteBusy || indexLayer == 'Nessuno') return;
    if (!satelliteDateChosen) {
      if (availableScenes.isEmpty) {
        await searchSatelliteScenes();
      } else {
        setState(() {
          satelliteDate = DateTime.parse(
            availableScenes.first['datetime'].toString(),
          );
          satelliteDateChosen = true;
        });
      }
      if (!mounted || selectedId != parcel.id || !satelliteDateChosen) return;
    }
    final requestId = ++satelliteRequestId;
    final day =
        '${satelliteDate.year.toString().padLeft(4, '0')}-${satelliteDate.month.toString().padLeft(2, '0')}-${satelliteDate.day.toString().padLeft(2, '0')}';
    setState(() {
      satelliteBusy = true;
      satelliteError = null;
      overlayPng = null;
      overlayParcelId = null;
    });
    try {
      final response = await http
          .post(
            Uri.parse('$copernicusBaseUrl/overlay'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'geometry': parcelGeometry(parcel),
              'date': day,
              'max_cloud_coverage': 30,
              'index': indexLayer.toLowerCase(),
              'width': 512,
              'height': 512,
            }),
          )
          .timeout(const Duration(seconds: 90));
      if (response.statusCode != 200 ||
          !(response.headers['content-type'] ?? '').contains('image/png')) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      if (!mounted ||
          requestId != satelliteRequestId ||
          selectedId != parcel.id) {
        return;
      }
      setState(() {
        overlayPng = response.bodyBytes;
        overlayBounds = parcelBounds(parcel);
        overlayParcelId = parcel.id;
        satelliteBusy = false;
      });
      await loadSatelliteStatistics();
    } catch (e) {
      if (!mounted || requestId != satelliteRequestId) return;
      setState(() {
        satelliteBusy = false;
        satelliteError = 'Elaborazione non riuscita: $e';
      });
    }
  }

  Future<void> finishDrawing() async {
    if (drawingPoints.length < 3 ||
        drawingPoints.toSet().length < 3 ||
        polygonArea(drawingPoints) <= 0.01) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Disegna almeno tre vertici distinti che racchiudano una superficie.',
          ),
        ),
      );
      return;
    }
    final controller = TextEditingController(
      text: 'Particella ${parcels.length + 1}',
    );
    var chosenCrop = crops.first;
    final result = await showDialog<Map<String, String>>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, updateDialog) => AlertDialog(
          title: const Text('Nuova particella'),
          content: SizedBox(
            width: 350,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: controller,
                  decoration: const InputDecoration(
                    labelText: 'Nome particella',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 16),
                DropdownButtonFormField<String>(
                  initialValue: chosenCrop,
                  isExpanded: true,
                  decoration: const InputDecoration(
                    labelText: 'Coltura',
                    border: OutlineInputBorder(),
                  ),
                  items: crops
                      .map((c) => DropdownMenuItem(value: c, child: Text(c)))
                      .toList(),
                  onChanged: (value) {
                    if (value != null) updateDialog(() => chosenCrop = value);
                  },
                ),
                const SizedBox(height: 12),
                Text(
                  'Superficie: ${(polygonArea(drawingPoints) / 10000).toStringAsFixed(3)} ha',
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Annulla'),
            ),
            FilledButton(
              onPressed: () {
                if (controller.text.trim().isEmpty) return;
                Navigator.pop(dialogContext, {
                  'name': controller.text.trim(),
                  'crop': chosenCrop,
                });
              },
              child: const Text('Salva'),
            ),
          ],
        ),
      ),
    );
    controller.dispose();
    if (!mounted || result == null) return;
    final parcel = FarmParcel(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      name: result['name']!,
      crop: result['crop']!,
      points: List.of(drawingPoints),
    );
    setState(() {
      parcels.add(parcel);
      selectedId = parcel.id;
      drawing = false;
      drawingPoints.clear();
    });
    await saveParcels();
  }

  Future<void> changeCrop(FarmParcel parcel, String crop) async {
    setState(() => parcel.crop = crop);
    await saveParcels();
  }

  Future<bool> saveSoilToBackend(
    FarmParcel parcel,
    Map<String, String> values,
  ) async {
    double? number(String key) =>
        double.tryParse((values[key] ?? '').replaceAll(',', '.'));

    final data = <String, dynamic>{
      'client_id': DateTime.now().microsecondsSinceEpoch.toString(),
      'parcel_id': parcel.id,
      'sample_date': DateTime.now().toIso8601String().substring(0, 10),
      'source': 'laboratory',
      'ph': number('ph'),
      'nitrogen_g_kg': number('nitrogen'),
      'sand_percent': number('sand'),
      'silt_percent': number('silt'),
      'clay_percent': number('clay'),
      'phosphorus_mg_kg': number('phosphorus'),
      'potassium_mg_kg': number('potassium'),
      'notes': [
        if ((values['texture'] ?? '').isNotEmpty)
          'Tessitura: ${values['texture']}',
        if ((values['organic'] ?? '').isNotEmpty)
          'Sostanza organica (%): ${values['organic']}',
        if ((values['cec'] ?? '').isNotEmpty) 'CSC: ${values['cec']}',
        if ((values['notes'] ?? '').isNotEmpty) values['notes']!,
      ].join(' | '),
    };

    pendingSoil.add(data);
    await writeCache();
    if (mounted) await syncParcels();
    return !pendingSoil.any((item) => item['client_id'] == data['client_id']);
  }

  Future<void> editSoil(FarmParcel parcel) async {
    final fields = <String, String>{
      'texture': 'Tessitura (es. franco-argillosa)',
      'ph': 'pH',
      'organic': 'Sostanza organica (%)',
      'sand': 'Sabbia (%)',
      'silt': 'Limo (%)',
      'clay': 'Argilla (%)',
      'nitrogen': 'Azoto totale (g/kg)',
      'phosphorus': 'Fosforo assimilabile (mg/kg)',
      'potassium': 'Potassio scambiabile (mg/kg)',
      'cec': 'CSC (cmol(+)/kg)',
      'notes': 'Note sul suolo / campionamento',
    };
    final controllers = {
      for (final key in fields.keys)
        key: TextEditingController(text: parcel.soil[key] ?? ''),
    };
    final formKey = GlobalKey<FormState>();
    final result = await showDialog<Map<String, String>>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('Analisi del suolo - ${parcel.name}'),
        content: SizedBox(
          width: 460,
          height: 460,
          child: Form(
            key: formKey,
            child: ListView(
              children: [
                const Text(
                  'Inserisci i valori misurati in laboratorio. Lascia vuoti i campi non disponibili.',
                ),
                const SizedBox(height: 12),
                for (final entry in fields.entries) ...[
                  TextFormField(
                    controller: controllers[entry.key],
                    decoration: InputDecoration(
                      labelText: entry.value,
                      border: const OutlineInputBorder(),
                    ),
                    keyboardType: entry.key == 'texture' || entry.key == 'notes'
                        ? TextInputType.text
                        : const TextInputType.numberWithOptions(decimal: true),
                    validator: (value) {
                      if (value == null ||
                          value.trim().isEmpty ||
                          entry.key == 'texture' ||
                          entry.key == 'notes') {
                        return null;
                      }
                      final number = double.tryParse(
                        value.trim().replaceAll(',', '.'),
                      );
                      if (number == null) return 'Inserisci un numero valido';
                      if (entry.key == 'ph' && (number < 0 || number > 14)) {
                        return 'Il pH deve essere tra 0 e 14';
                      }
                      if ([
                            'organic',
                            'sand',
                            'silt',
                            'clay',
                          ].contains(entry.key) &&
                          (number < 0 || number > 100)) {
                        return 'Valore tra 0 e 100';
                      }
                      if (number < 0) return 'Non può essere negativo';
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                ],
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Annulla'),
          ),
          FilledButton(
            onPressed: () {
              if (!formKey.currentState!.validate()) return;
              Navigator.pop(dialogContext, {
                for (final e in controllers.entries)
                  if (e.value.text.trim().isNotEmpty)
                    e.key: e.value.text.trim(),
              });
            },
            child: const Text('Salva analisi'),
          ),
        ],
      ),
    );
    for (final c in controllers.values) {
      c.dispose();
    }
    if (!mounted || result == null) return;
    setState(() => parcel.soil = result);
    await saveParcels();

    final savedOnline = await saveSoilToBackend(parcel, result);
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          savedOnline ? 'Analisi salvata localmente e nel database.' : 'Analisi salvata sul dispositivo, in attesa di sincronizzazione.',
        ),
      ),
    );
  }

  Future<void> deleteSelected() async {
    final parcel = selectedParcel;
    if (parcel == null) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Eliminare la particella?'),
        content: Text('Vuoi eliminare "${parcel.name}"?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Annulla'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Elimina'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      parcels.removeWhere((p) => p.id == parcel.id);
      selectedId = null;
      clearSatelliteOverlay();
      clearWeather();
      availableScenes = [];
    });
    await saveParcels();
  }

  void focusParcel(FarmParcel parcel) {
    setState(() {
      if (selectedId != parcel.id) {
        clearSatelliteOverlay();
        clearWeather();
        availableScenes = [];
        satelliteDateChosen = false;
      }
      selectedId = parcel.id;
    });
    final center = LatLng(
      parcel.points.map((p) => p.latitude).reduce((a, b) => a + b) /
          parcel.points.length,
      parcel.points.map((p) => p.longitude).reduce((a, b) => a + b) /
          parcel.points.length,
    );
    mapController.move(center, 16);
  }

  @override
  Widget build(BuildContext context) {
    final selected = selectedParcel;
    final wide = MediaQuery.sizeOf(context).width >= 800;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: const Color(0xFF32764A),
        foregroundColor: Colors.white,
        title: const Row(
          children: [Icon(Icons.grass), SizedBox(width: 10), Text('AgroPlan')],
        ),
        actions: [
          IconButton(
            tooltip: 'Verifica collegamenti',
            icon: const Icon(Icons.hub_outlined),
            onPressed: () {
              final points = selectedParcel?.points;
              showDialog<void>(
                context: context,
                builder: (_) => IntegrationsDialog(
                  latitude: points == null || points.isEmpty
                      ? 44.65
                      : points.map((p) => p.latitude).reduce((a, b) => a + b) /
                            points.length,
                  longitude: points == null || points.isEmpty
                      ? 11.18
                      : points.map((p) => p.longitude).reduce((a, b) => a + b) /
                            points.length,
                ),
              );
            },
          ),
          IconButton(
            tooltip: 'Sincronizza particelle',
            onPressed: syncing ? null : syncParcels,
            icon: const Icon(Icons.sync),
          ),
          IconButton(
            tooltip: 'Analisi colturale aziendale',
            onPressed: () => showDialog<void>(
              context: context,
              builder: (_) => const CropOverview(),
            ),
            icon: const Icon(Icons.analytics_outlined),
          ),
          if (!ApiSession.instance.localAccess)
            IconButton(
              tooltip: 'Esci (${ApiSession.instance.username})',
              onPressed: ApiSession.instance.logout,
              icon: const Icon(Icons.logout),
            ),
          if (!wide)
            Builder(
              builder: (context) => IconButton(
                tooltip: 'Le mie particelle',
                icon: const Icon(Icons.menu),
                onPressed: () => Scaffold.of(context).openEndDrawer(),
              ),
            ),
          if (drawing)
            TextButton.icon(
              onPressed: cancelDrawing,
              icon: const Icon(Icons.close, color: Colors.white),
              label: const Text(
                'Annulla',
                style: TextStyle(color: Colors.white),
              ),
            ),
        ],
      ),
      endDrawer: wide
          ? null
          : Drawer(child: SafeArea(child: buildSidebar(selected))),
      body: Row(
        children: [
          if (wide) SizedBox(width: 320, child: buildSidebar(selected)),
          Expanded(
            child: Stack(
              children: [
                FlutterMap(
                  mapController: mapController,
                  options: MapOptions(
                    initialCenter: const LatLng(44.65, 11.20),
                    initialZoom: 11,
                    onTap: handleMapTap,
                  ),
                  children: [
                    TileLayer(
                      urlTemplate: satellite
                          ? 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
                          : 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                      userAgentPackageName: 'com.agroplan.app',
                    ),
                    if (overlayPng != null &&
                        overlayBounds != null &&
                        overlayParcelId == selectedId)
                      OverlayImageLayer(
                        overlayImages: [
                          OverlayImage(
                            bounds: overlayBounds!,
                            imageProvider: MemoryImage(overlayPng!),
                            opacity: 0.85,
                          ),
                        ],
                      ),
                    PolygonLayer(
                      polygons: [
                        for (final parcel in parcels)
                          Polygon(
                            points: parcel.points,
                            color: parcel.id == selectedId
                                ? Colors.orange.withValues(
                                    alpha: overlayPng != null ? 0.06 : 0.40,
                                  )
                                : Colors.green.withValues(alpha: 0.12),
                            borderColor: parcel.id == selectedId
                                ? Colors.deepOrange
                                : Colors.green.shade800,
                            borderStrokeWidth: 3,
                          ),
                        if (drawingPoints.length >= 3)
                          Polygon(
                            points: drawingPoints,
                            color: Colors.blue.withValues(alpha: 0.20),
                            borderColor: Colors.blue,
                            borderStrokeWidth: 2,
                          ),
                      ],
                    ),
                    if (drawingPoints.length >= 2)
                      PolylineLayer(
                        polylines: [
                          Polyline(
                            points: drawingPoints,
                            color: Colors.blue,
                            strokeWidth: 3,
                          ),
                        ],
                      ),
                    if (editingVertices && selected != null)
                      MarkerLayer(
                        markers: [
                          for (int i = 0; i < selected.points.length; i++)
                            Marker(
                              point: selected.points[i],
                              width: 36,
                              height: 36,
                              child: GestureDetector(
                                onTap: () => setState(() => movingVertex = i),
                                onLongPress: () => removeVertex(i),
                                child: Icon(
                                  Icons.location_on,
                                  color: movingVertex == i
                                      ? Colors.deepOrange
                                      : Colors.blue,
                                  size: 32,
                                ),
                              ),
                            ),
                        ],
                      ),
                    MarkerLayer(
                      markers: [
                        for (final point in drawingPoints)
                          Marker(
                            point: point,
                            width: 16,
                            height: 16,
                            child: const Icon(
                              Icons.circle,
                              color: Colors.blue,
                              size: 13,
                            ),
                          ),
                      ],
                    ),
                    const RichAttributionWidget(
                      attributions: [
                        TextSourceAttribution('OpenStreetMap contributors'),
                        TextSourceAttribution(
                          'Imagery: Esri, Maxar, Earthstar Geographics and contributors',
                        ),
                      ],
                    ),
                  ],
                ),
                Positioned(
                  top: 16,
                  left: 16,
                  child: Card(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 10),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.layers_outlined),
                          const SizedBox(width: 8),
                          DropdownButton<bool>(
                            value: satellite,
                            underline: const SizedBox.shrink(),
                            items: const [
                              DropdownMenuItem(
                                value: false,
                                child: Text('Stradale OSM'),
                              ),
                              DropdownMenuItem(
                                value: true,
                                child: Text('Satellite (Esri)'),
                              ),
                            ],
                            onChanged: (value) {
                              if (value != null) {
                                setState(() => satellite = value);
                              }
                            },
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                Positioned(
                  top: 16,
                  right: 16,
                  child: Column(
                    children: [
                      FloatingActionButton.small(
                        heroTag: 'zoomIn',
                        onPressed: () => mapController.move(
                          mapController.camera.center,
                          mapController.camera.zoom + 1,
                        ),
                        child: const Icon(Icons.add),
                      ),
                      const SizedBox(height: 8),
                      FloatingActionButton.small(
                        heroTag: 'zoomOut',
                        onPressed: () => mapController.move(
                          mapController.camera.center,
                          mapController.camera.zoom - 1,
                        ),
                        child: const Icon(Icons.remove),
                      ),
                    ],
                  ),
                ),
                Positioned(
                  bottom: 20,
                  left: 16,
                  right: 16,
                  child: Center(
                    child: Card(
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Wrap(
                          alignment: WrapAlignment.center,
                          spacing: 10,
                          runSpacing: 8,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            if (!drawing)
                              FilledButton.icon(
                                onPressed: startDrawing,
                                icon: const Icon(Icons.draw),
                                label: const Text('Disegna particella'),
                              ),
                            if (drawing) ...[
                              Text('Vertici: ${drawingPoints.length}'),
                              OutlinedButton.icon(
                                onPressed: drawingPoints.isEmpty
                                    ? null
                                    : () => setState(
                                        () => drawingPoints.removeLast(),
                                      ),
                                icon: const Icon(Icons.undo),
                                label: const Text('Annulla punto'),
                              ),
                              FilledButton.icon(
                                onPressed: drawingPoints.length >= 3
                                    ? finishDrawing
                                    : null,
                                icon: const Icon(Icons.check),
                                label: const Text('Termina'),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget buildSidebar(FarmParcel? selected) => Container(
    color: const Color(0xFFF5F7F3),
    child: ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text(
          'Le mie particelle',
          style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 6),
        Text('Azienda: ${ApiSession.instance.farmId}'),
        Text('${parcels.length} appezzamenti registrati'),
        if (syncing) const LinearProgressIndicator(),
        if (syncError != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text(syncError!, style: const TextStyle(color: Colors.red)),
          ),
        TextButton.icon(
          onPressed: importLegacyParcels,
          icon: const Icon(Icons.file_download),
          label: const Text('Importa particelle precedenti'),
        ),
        const SizedBox(height: 16),
        if (parcels.isEmpty)
          const Card(
            child: Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                'Nessuna particella presente.\nPremi "Disegna particella" sulla mappa per aggiungere il primo campo.',
              ),
            ),
          ),
        for (final parcel in parcels)
          Card(
            color: selectedId == parcel.id
                ? const Color(0xFFDDEDDC)
                : Colors.white,
            child: ListTile(
              leading: const Icon(Icons.landscape, color: Color(0xFF32764A)),
              title: Text(parcel.name),
              subtitle: Text(
                '${parcel.hectares.toStringAsFixed(3)} ha\n${parcel.crop}',
              ),
              isThreeLine: true,
              selected: selectedId == parcel.id,
              onTap: () => focusParcel(parcel),
            ),
          ),
        if (selected != null) ...[
          const SizedBox(height: 20),
          const Divider(),
          const Text(
            'Scheda particella',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 16),
          if (selected.revision == 0)
            const Text(
              'Salvataggio della particella sul server in attesa. Premi Sincronizza se la rete è disponibile.',
            ),
          if (selected.revision > 0)
            CropPanel(
              key: ValueKey('crop-${selected.id}'),
              parcelId: selected.id,
              baseUrl: copernicusBaseUrl,
              onChanged: () => setState(() => agronomyRevision++),
              onCropChanged: (crop) {
                changeCrop(selected, crop);
              },
            ),
          const SizedBox(height: 12),
          if (selected.points.isNotEmpty && selected.revision > 0)
            SoilPanel(
              key: ValueKey('soil-${selected.id}'),
              parcelId: selected.id,
              revision: '${selected.soil}-$soilRevision',
              latitude:
                  selected.points
                      .map((p) => p.latitude)
                      .reduce((a, b) => a + b) /
                  selected.points.length,
              longitude:
                  selected.points
                      .map((p) => p.longitude)
                      .reduce((a, b) => a + b) /
                  selected.points.length,
              points: selected.points
                  .map((p) => {'lat': p.latitude, 'lng': p.longitude})
                  .toList(),
            ),

          if (selected.points.isNotEmpty && selected.revision > 0)
            AgronomyPanel(
              key: ValueKey('agronomy-${selected.id}'),
              revision: agronomyRevision,
              parcelId: selected.id,
              baseUrl: copernicusBaseUrl,
              latitude:
                  selected.points
                      .map((p) => p.latitude)
                      .reduce((a, b) => a + b) /
                  selected.points.length,
              longitude:
                  selected.points
                      .map((p) => p.longitude)
                      .reduce((a, b) => a + b) /
                  selected.points.length,
            ),
          const SizedBox(height: 12),
          Text(selected.name, style: const TextStyle(fontSize: 18)),
          const SizedBox(height: 8),
          Text('Superficie: ${selected.hectares.toStringAsFixed(3)} ha'),
          const SizedBox(height: 16),
          DropdownButtonFormField<String>(
            key: ValueKey(selected.id),
            initialValue: selected.crop,
            isExpanded: true,
            decoration: const InputDecoration(
              labelText: 'Coltura',
              border: OutlineInputBorder(),
            ),
            items: crops
                .map((crop) => DropdownMenuItem(value: crop, child: Text(crop)))
                .toList(),
            onChanged: (value) {
              if (value != null) changeCrop(selected, value);
            },
          ),
          const SizedBox(height: 16),
          FilledButton.tonalIcon(
            onPressed: editingVertices ? stopEditing : startEditing,
            icon: const Icon(Icons.edit_location_alt),
            label: Text(
              editingVertices ? 'Termina modifica confini' : 'Modifica vertici',
            ),
          ),
          if (editingVertices) ...[
            const SizedBox(height: 8),
            const Text(
              'Tocca un vertice sulla mappa, poi tocca la nuova posizione. Pressione lunga sul vertice per eliminarlo (minimo 3).',
            ),
            for (int i = 0; i < selected.points.length; i++)
              TextButton.icon(
                onPressed: () => addVertexAtMidpoint(i),
                icon: const Icon(Icons.add_location_alt_outlined),
                label: Text('Aggiungi vertice dopo ${i + 1}'),
              ),
          ],
          const SizedBox(height: 18),
          const Text(
            'Analisi satellitare Copernicus',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            key: ValueKey('satellite-$indexLayer'),
            initialValue: indexLayer,
            decoration: const InputDecoration(
              labelText: 'Indice satellitare',
              border: OutlineInputBorder(),
            ),
            items: const [
              'Nessuno',
              'NDVI',
              'DVI',
            ].map((v) => DropdownMenuItem(value: v, child: Text(v))).toList(),
            onChanged: (v) {
              if (v != null) {
                setState(() {
                  indexLayer = v;
                  clearSatelliteOverlay();
                });
              }
            },
          ),
          if (indexLayer != 'Nessuno') ...[
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: satelliteBusy ? null : searchSatelliteScenes,
              icon: const Icon(Icons.satellite_alt),
              label: const Text('Cerca acquisizioni Sentinel-2'),
            ),
            if (availableScenes.isNotEmpty) ...[
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                key: ValueKey(
                  'scenes-${selected.id}-${availableScenes.map((s) => s['datetime']).join(',')}-${formatSatelliteDate(satelliteDate)}',
                ),
                initialValue:
                    availableScenes.any(
                      (s) =>
                          s['datetime'].toString().substring(0, 10) ==
                          formatSatelliteDate(satelliteDate),
                    )
                    ? formatSatelliteDate(satelliteDate)
                    : null,
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'Acquisizione',
                  border: OutlineInputBorder(),
                ),
                items: availableScenes.map((scene) {
                  final date = scene['datetime'].toString().substring(0, 10);
                  final clouds = scene['cloud_cover'];
                  return DropdownMenuItem(
                    value: date,
                    child: Text('$date · nuvole $clouds%'),
                  );
                }).toList(),
                onChanged: (v) {
                  if (v != null) {
                    setState(() {
                      satelliteDate = DateTime.parse(v);
                      satelliteDateChosen = true;
                      clearSatelliteOverlay();
                    });
                  }
                },
              ),
            ] else ...[
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: satelliteBusy
                    ? null
                    : () async {
                        final picked = await showDatePicker(
                          context: context,
                          initialDate: satelliteDate,
                          firstDate: DateTime(2017),
                          lastDate: DateTime.now(),
                        );
                        if (picked != null) {
                          setState(() {
                            satelliteDate = picked;
                            satelliteDateChosen = true;
                            clearSatelliteOverlay();
                          });
                        }
                      },
                icon: const Icon(Icons.calendar_month),
                label: Text(
                  'Data: ${satelliteDate.day}/${satelliteDate.month}/${satelliteDate.year}',
                ),
              ),
            ],
            const SizedBox(height: 8),
            FilledButton.icon(
              onPressed: satelliteBusy ? null : loadSatelliteOverlay,
              icon: const Icon(Icons.layers),
              label: Text('Visualizza $indexLayer sulla mappa'),
            ),
            if (overlayPng != null && overlayParcelId == selected.id)
              TextButton.icon(
                onPressed: () => setState(clearSatelliteOverlay),
                icon: const Icon(Icons.visibility_off),
                label: const Text('Nascondi immagine'),
              ),
            if (satelliteBusy)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: LinearProgressIndicator(),
              ),
            if (satelliteError != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  satelliteError!,
                  style: const TextStyle(color: Colors.red),
                ),
              ),
            buildSatelliteStats(),
            const SizedBox(height: 8),
            const Text(
              'La nuvolosità si riferisce alla scena intera. Il PNG è ritagliato sul perimetro della particella.',
              style: TextStyle(fontSize: 12),
            ),
          ],
          const SizedBox(height: 18),
          buildWeatherPanel(selected),
          const SizedBox(height: 18),
          const Text(
            'Analisi del terreno',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          if (selected.soil.isEmpty) const Text('Nessuna analisi inserita.'),
          for (final entry in selected.soil.entries)
            Padding(
              padding: const EdgeInsets.only(bottom: 5),
              child: Text('${entry.key}: ${entry.value}'),
            ),
          const SizedBox(height: 8),
          FilledButton.tonalIcon(
            onPressed: () => editSoil(selected),
            icon: const Icon(Icons.science_outlined),
            label: const Text('Inserisci / modifica analisi'),
          ),
          const SizedBox(height: 16),
          OutlinedButton.icon(
            onPressed: deleteSelected,
            icon: const Icon(Icons.delete_outline),
            label: const Text('Elimina particella'),
          ),
          const SizedBox(height: 12),
          const Text(
            'Prossimamente: analisi del suolo, meteo, fenologia e immagini satellitari.',
            style: TextStyle(color: Colors.grey),
          ),
        ],
      ],
    ),
  );
}

class SatelliteTrendPainter extends CustomPainter {
  SatelliteTrendPainter(this.observations);
  final List<Map<String, dynamic>> observations;

  @override
  void paint(Canvas canvas, Size size) {
    final points = observations
        .where((e) => e['mean'] is num && e['date'] is String)
        .toList();
    if (points.length < 2) return;
    final values = points.map((e) => (e['mean'] as num).toDouble()).toList();
    var minV = values.reduce(math.min);
    var maxV = values.reduce(math.max);
    if ((maxV - minV).abs() < 0.01) {
      minV -= 0.05;
      maxV += 0.05;
    }
    final first = DateTime.parse(points.first['date'] as String)
        .millisecondsSinceEpoch
        .toDouble();
    final last = DateTime.parse(points.last['date'] as String)
        .millisecondsSinceEpoch
        .toDouble();
    final span = math.max(1.0, last - first);
    const left = 43.0, right = 10.0, top = 12.0, bottom = 30.0;
    final w = math.max(1.0, size.width - left - right);
    final h = math.max(1.0, size.height - top - bottom);
    final axis = Paint()
      ..color = const Color(0xFFB8C5BA)
      ..strokeWidth = 1;
    final textStyle = const TextStyle(fontSize: 10, color: Color(0xFF4D5B50));
    void label(String text, Offset offset) {
      final tp = TextPainter(
        text: TextSpan(text: text, style: textStyle),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, offset);
    }

    for (var i = 0; i <= 4; i++) {
      final y = top + h * i / 4;
      canvas.drawLine(Offset(left, y), Offset(left + w, y), axis);
      label(
        (maxV - (maxV - minV) * i / 4).toStringAsFixed(2),
        Offset(1, y - 6),
      );
    }
    final path = ui.Path();
    for (var i = 0; i < points.length; i++) {
      final t = DateTime.parse(points[i]['date'] as String)
          .millisecondsSinceEpoch
          .toDouble();
      final x = left + (t - first) / span * w;
      final y = top + (maxV - values[i]) / (maxV - minV) * h;
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = const Color(0xFF287545)
        ..strokeWidth = 2.5
        ..style = PaintingStyle.stroke,
    );
    for (var i = 0; i < points.length; i++) {
      final t = DateTime.parse(points[i]['date'] as String)
          .millisecondsSinceEpoch
          .toDouble();
      final x = left + (t - first) / span * w;
      final y = top + (maxV - values[i]) / (maxV - minV) * h;
      canvas.drawCircle(
        Offset(x, y),
        3.5,
        Paint()..color = const Color(0xFF287545),
      );
    }
    final firstDate = points.first['date'].toString();
    final lastDate = points.last['date'].toString();
    label(
      '${firstDate.substring(8, 10)}/${firstDate.substring(5, 7)}',
      Offset(left, top + h + 8),
    );
    label(
      '${lastDate.substring(8, 10)}/${lastDate.substring(5, 7)}',
      Offset(left + w - 32, top + h + 8),
    );
  }

  @override
  bool shouldRepaint(covariant SatelliteTrendPainter oldDelegate) =>
      oldDelegate.observations != observations;
}

class WeatherRainPainter extends CustomPainter {
  WeatherRainPainter(this.days);
  final List<Map<String, dynamic>> days;

  @override
  void paint(Canvas canvas, Size size) {
    if (days.isEmpty) return;
    const left = 34.0, right = 8.0, top = 10.0, bottom = 24.0;
    final w = math.max(1.0, size.width - left - right);
    final h = math.max(1.0, size.height - top - bottom);
    final values = days
        .map((e) => (e['precipitation_sum'] as num?)?.toDouble() ?? 0.0)
        .toList();
    final maxRain = math.max(1.0, values.reduce(math.max));
    final axis = Paint()
      ..color = const Color(0xFFB8C5BA)
      ..strokeWidth = 1;
    final bar = Paint()..color = const Color(0xFF398AC0);
    final labelStyle = const TextStyle(fontSize: 10, color: Color(0xFF4D5B50));
    void label(String value, Offset offset) {
      final tp = TextPainter(
        text: TextSpan(text: value, style: labelStyle),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, offset);
    }

    for (var i = 0; i <= 2; i++) {
      final y = top + h * i / 2;
      canvas.drawLine(Offset(left, y), Offset(left + w, y), axis);
      label((maxRain * (1 - i / 2)).toStringAsFixed(0), Offset(1, y - 5));
    }
    final step = w / days.length;
    for (var i = 0; i < days.length; i++) {
      final barHeight = h * values[i] / maxRain;
      canvas.drawRect(
        Rect.fromLTWH(
          left + i * step + 1,
          top + h - barHeight,
          math.max(1, step - 2),
          barHeight,
        ),
        bar,
      );
    }
    String shortDate(Map<String, dynamic> row) {
      final date = row['date']?.toString() ?? '';
      return date.length >= 10
          ? '${date.substring(8, 10)}/${date.substring(5, 7)}'
          : date;
    }

    label(shortDate(days.first), Offset(left, top + h + 7));
    label(
      shortDate(days.last),
      Offset(math.max(left, left + w - 35), top + h + 7),
    );
  }

  @override
  bool shouldRepaint(covariant WeatherRainPainter oldDelegate) =>
      oldDelegate.days != days;
}

/// Green NDVI/DVI line and blue antecedent 7-day precipitation bars.
/// Scales are independent; do not infer causality from visual alignment.
class NdviRainComparisonPainter extends CustomPainter {
  NdviRainComparisonPainter(this.rows);
  final List<Map<String, dynamic>> rows;

  @override
  void paint(Canvas canvas, Size size) {
    if (rows.length < 2) return;
    final data =
        rows
            .where(
              (r) =>
                  r['mean'] is num && r['rain7'] is num && r['date'] is String,
            )
            .toList()
          ..sort(
            (a, b) => (a['date'] as String).compareTo(b['date'] as String),
          );
    if (data.length < 2) return;
    const left = 43.0, right = 44.0, top = 16.0, bottom = 30.0;
    final w = math.max(1.0, size.width - left - right);
    final h = math.max(1.0, size.height - top - bottom);
    final values = data.map((e) => (e['mean'] as num).toDouble()).toList();
    final rain = data.map((e) => (e['rain7'] as num).toDouble()).toList();
    var lo = values.reduce(math.min), hi = values.reduce(math.max);
    if ((hi - lo).abs() < 0.02) {
      lo -= 0.05;
      hi += 0.05;
    }
    final maxRain = math.max(1.0, rain.reduce(math.max));
    final start = DateTime.parse(data.first['date'] as String)
        .millisecondsSinceEpoch
        .toDouble();
    final end = DateTime.parse(data.last['date'] as String)
        .millisecondsSinceEpoch
        .toDouble();
    final span = math.max(1.0, end - start);
    final axis = Paint()
      ..color = const Color(0xFFB8C5BA)
      ..strokeWidth = 1;
    final bars = Paint()..color = const Color(0x663A8CC0);
    final line = Paint()
      ..color = const Color(0xFF287545)
      ..strokeWidth = 2.5
      ..style = PaintingStyle.stroke;
    void label(String value, double x, double y) {
      final tp = TextPainter(
        text: TextSpan(
          text: value,
          style: const TextStyle(fontSize: 10, color: Color(0xFF4D5B50)),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(x, y));
    }

    for (var i = 0; i <= 4; i++) {
      final y = top + h * i / 4;
      canvas.drawLine(Offset(left, y), Offset(left + w, y), axis);
      label((hi - (hi - lo) * i / 4).toStringAsFixed(2), 0, y - 6);
      label((maxRain * (1 - i / 4)).toStringAsFixed(0), left + w + 6, y - 6);
    }
    final path = ui.Path();
    for (var i = 0; i < data.length; i++) {
      final t = DateTime.parse(data[i]['date'] as String).millisecondsSinceEpoch
          .toDouble();
      final x = left + (t - start) / span * w;
      final y = top + (hi - values[i]) / (hi - lo) * h;
      final bh = rain[i] / maxRain * h;
      canvas.drawRect(Rect.fromLTWH(x - 3, top + h - bh, 6, bh), bars);
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
      canvas.drawCircle(
        Offset(x, y),
        2.5,
        Paint()..color = const Color(0xFF287545),
      );
    }
    canvas.drawPath(path, line);
    String shortDate(String d) => '${d.substring(8, 10)}/${d.substring(5, 7)}';
    label(shortDate(data.first['date'] as String), left, top + h + 8);
    label(shortDate(data.last['date'] as String), left + w - 30, top + h + 8);
  }

  @override
  bool shouldRepaint(covariant NdviRainComparisonPainter oldDelegate) =>
      oldDelegate.rows != rows;
}
