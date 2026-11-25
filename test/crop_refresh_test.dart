import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:agroplan/api.dart';
import 'package:agroplan/crop_panel.dart';
import 'package:agroplan/agronomy_panel.dart';

void main() {
  tearDown(() {
    ApiSession.instance.clear();
    useHttpClientForTesting(http.Client());
  });

  testWidgets('Salvare un ciclo e una BBCH aggiorna gli indicatori', (
    tester,
  ) async {
    var analysisCalls = 0;
    var changes = 0;
    var revision = 0;
    final cycles = <Map<String, dynamic>>[];
    final observations = <Map<String, dynamic>>[];
    useHttpClientForTesting(
      MockClient((request) async {
        if (request.url.path == '/crop/cycles') {
          if (request.method == 'POST') {
            final cycle = {
              ...jsonDecode(request.body) as Map<String, dynamic>,
              'id': 1,
            };
            cycles
              ..clear()
              ..add(cycle);
            return http.Response(jsonEncode(cycle), 201);
          }
          return http.Response(jsonEncode(cycles), 200);
        }
        if (request.url.path == '/crop/cycles/1/bbch') {
          if (request.method == 'POST') {
            final observation = {
              ...jsonDecode(request.body) as Map<String, dynamic>,
              'id': 1,
            };
            observations.add(observation);
            return http.Response(jsonEncode(observation), 201);
          }
          return http.Response(jsonEncode(observations), 200);
        }
        if (request.url.path == '/agronomy/analyze') {
          analysisCalls++;
          return http.Response(
            jsonEncode({
              'source': 'Test',
              'historical_end': '2026-10-01',
              'crop_context': cycles.isEmpty
                  ? null
                  : {
                      ...cycles.first,
                      'latest_bbch': observations.isEmpty
                          ? null
                          : observations.last,
                    },
              'windows': {},
              'warnings': [],
              'monitoring_alerts': [],
            }),
            200,
          );
        }
        return http.Response('{}', 404);
      }),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: StatefulBuilder(
              builder: (context, setState) => Column(
                children: [
                  CropPanel(
                    parcelId: 'campo-1',
                    baseUrl: apiBaseUrl,
                    onChanged: () {
                      setState(() {
                        revision++;
                        changes++;
                      });
                    },
                  ),
                  AgronomyPanel(
                    parcelId: 'campo-1',
                    latitude: 44.5,
                    longitude: 11.3,
                    baseUrl: apiBaseUrl,
                    revision: revision,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(analysisCalls, 1);
    await tester.ensureVisible(find.text('Salva ciclo'));
    await tester.tap(find.text('Salva ciclo'));
    await tester.pumpAndSettle();
    expect(changes, 1);
    expect(analysisCalls, 2);
    await tester.enterText(
      find.widgetWithText(TextField, 'Stadio BBCH (0–99)'),
      '25',
    );
    await tester.ensureVisible(find.text('Registra BBCH'));
    await tester.tap(find.text('Registra BBCH'));
    await tester.pumpAndSettle();
    expect(changes, 2);
    expect(analysisCalls, 3);
    expect(find.textContaining('BBCH 25 (osservato'), findsOneWidget);
  });

  test('Token inviato alle API e revocato dopo risposta 401', () async {
    String? sentAuthorization;
    useHttpClientForTesting(
      MockClient((request) async {
        if (request.url.path == '/auth/login') {
          return http.Response(
            jsonEncode({
              'access_token': 'test-token',
              'user': {'username': 'luca', 'farm_id': 'farm-a'},
            }),
            200,
          );
        }
        sentAuthorization = request.headers['Authorization'];
        return http.Response('{}', 401);
      }),
    );
    await ApiSession.instance.login('luca', 'password');
    // Use the production facade to exercise authorization and session clearing.
    await _requestParcels();
    expect(sentAuthorization, 'Bearer test-token');
    expect(ApiSession.instance.authenticated, isFalse);
  });
}

Future<void> _requestParcels() async {
  await get(Uri.parse('$apiBaseUrl/parcels'));
}
