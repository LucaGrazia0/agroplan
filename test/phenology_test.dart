import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:agroplan/api.dart';
import 'package:agroplan/crop_panel.dart';

void main() {
  tearDown(() => useHttpClientForTesting(http.Client()));
  testWidgets(
    'La scheda Coltura mostra la descrizione specifica e le date discordanti',
    (tester) async {
      useHttpClientForTesting(
        MockClient((request) async {
          if (request.url.path.endsWith('/bbch')) {
            return http.Response(
              jsonEncode([
                {
                  'id': 1,
                  'observed_at': '2026-11-01',
                  'bbch': 39,
                  'notes': '',
                  'phenology': {
                    'description': 'Almeno nove nodi riconoscibili',
                    'status': 'date_conflict',
                    'quality_notes': [
                      'Il rilievo della pianta precede la semina registrata: chiarisci ciclo e date.',
                    ],
                  },
                },
              ]),
              200,
            );
          }
          return http.Response(
            jsonEncode([
              {
                'id': 1,
                'crop': 'mais',
                'season': '2026',
                'sowing_date': '2026-11-10',
                'variety': '',
              },
            ]),
            200,
          );
        }),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: CropPanel(parcelId: 'field', baseUrl: apiBaseUrl),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Colture e fenologia BBCH'));
      await tester.pumpAndSettle();
      expect(find.text('Almeno nove nodi riconoscibili'), findsOneWidget);
      expect(find.textContaining('precede la semina'), findsOneWidget);
    },
  );
}
