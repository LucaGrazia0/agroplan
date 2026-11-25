import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:agroplan/api.dart';
import 'package:agroplan/water_parameters.dart';

void main() {
  tearDown(() => useHttpClientForTesting(http.Client()));
  testWidgets(
    'Il referto dell’acqua conserva le date e i parametri meteo aggiornati',
    (tester) async {
      Map? saved;
      var reads = 0;
      useHttpClientForTesting(
        MockClient((request) async {
          if (request.method == 'PUT') {
            saved = jsonDecode(request.body) as Map;
            return http.Response(request.body, 200);
          }
          reads++;
          return http.Response(
            jsonEncode({
              'observed_at': '2026-11-20',
              'field_capacity_percent': 30,
              'wilting_point_percent': 10,
              'root_depth_m': 1,
              'moisture_percent': 15,
              'kc': reads == 1 ? 1 : 1.2,
              'kc_from': '2026-11-01',
              'kc_to': '2026-11-20',
            }),
            200,
          );
        }),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: WaterParametersPanel(
                parcelId: 'field',
                weather: false,
                onSaved: () {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Parametri idrici misurati'));
      await tester.pumpAndSettle();
      for (final entry in {
        'Frazione p effettiva verificata (0–1 esclusi)': '0,5',
        'Data del campione di acqua (AAAA-MM-GG)': '2026-11-19',
        'ECw acqua irrigua a 25 °C (dS/m)': '0,1',
        'SAR dello stesso campione di acqua': '1',
      }.entries) {
        final field = find.widgetWithText(TextFormField, entry.key);
        await tester.ensureVisible(field);
        await tester.enterText(field, entry.value);
      }
      await tester.ensureVisible(find.text('Salva parametri'));
      await tester.tap(find.text('Salva parametri'));
      await tester.pumpAndSettle();
      expect(saved?['water_sample_date'], '2026-11-19');
      expect(saved?['observed_at'], '2026-11-20');
      expect(saved?['depletion_fraction'], .5);
      expect(saved?['water_ec_ds_m'], .1);
      expect(saved?['water_sar'], 1);
      expect(saved?['kc'], 1.2);
    },
  );
}
