// Optional adapter for the authenticated AgroPlan client (lib/api.dart).
// Requires: flutter pub add http
// Flutter Web on Chrome, Mac: http://127.0.0.1:8000
// Android emulator: http://10.0.2.2:8000 (backend must bind to an accessible interface).
import 'dart:convert';
import 'dart:typed_data';

import 'package:agroplan/api.dart' as http;

import 'package:latlong2/latlong.dart';

class SentinelApi {
  SentinelApi({this.baseUrl = 'http://127.0.0.1:8000'});
  final String baseUrl;

  Map<String, dynamic> polygonGeometry(List<LatLng> vertices) {
    if (vertices.length < 3) {
      throw ArgumentError('Servono almeno 3 vertici');
    }
    final coords = vertices.map((p) => [p.longitude, p.latitude]).toList();
    coords.add([vertices.first.longitude, vertices.first.latitude]);
    return {
      'type': 'Polygon',
      'coordinates': [coords],
    };
  }

  Future<List<dynamic>> scenes({
    required List<LatLng> vertices,
    required DateTime from,
    required DateTime to,
    double maxCloud = 30,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/scenes'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'geometry': polygonGeometry(vertices),
        'start_date': _date(from),
        'end_date': _date(to),
        'max_cloud_coverage': maxCloud,
      }),
    );
    _check(response);
    return (jsonDecode(response.body) as Map<String, dynamic>)['scenes']
        as List<dynamic>;
  }

  Future<Uint8List> overlay({
    required List<LatLng> vertices,
    required DateTime date,
    String index = 'ndvi',
    double maxCloud = 30,
    int width = 512,
    int height = 512,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/overlay'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'geometry': polygonGeometry(vertices),
        'date': _date(date),
        'index': index,
        'max_cloud_coverage': maxCloud,
        'width': width,
        'height': height,
      }),
    );
    _check(response);
    return response.bodyBytes;
  }

  Future<Map<String, dynamic>> statistics({
    required List<LatLng> vertices,
    required DateTime date,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/statistics'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'geometry': polygonGeometry(vertices),
        'date': _date(date),
      }),
    );
    _check(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  String _date(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  void _check(http.Response response) {
    if (response.statusCode >= 400) {
      throw Exception(
        'Sentinel API HTTP ${response.statusCode}: ${response.body}',
      );
    }
  }
}
