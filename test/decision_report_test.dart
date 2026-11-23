import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:agroplan/api.dart';
import 'package:agroplan/agronomy_panel.dart';
import 'package:agroplan/decision_report.dart';

Map<String, dynamic> decision(String title) => {
  'headline': title,
  'summary': 'Rilievo e meteo hanno date confrontabili.',
  'status': 'needs_verification',
  'inputs': [
    {
      'id': 'weather',
      'label': 'Meteo',
      'status': 'available',
      'detail': 'Dal 10 al 16 novembre: P − ET₀ -9 mm.',
    },
  ],
  'conclusions': [
    {
      'title': 'Appassimento: verifica acqua e radici',
      'explanation': 'Il saldo negativo non dimostra da solo stress.',
      'input_ids': ['weather'],
      'source_ids': [],
    },
  ],
  'next_steps': ['Misura l’umidità alla profondità radicale.'],
  'missing_inputs': ['Aggiungi la fase BBCH.'],
  'limits': 'Ipotesi da verificare in campo.',
  'references': [],
};
Widget page(Widget child) => MaterialApp(
  home: Scaffold(body: SingleChildScrollView(child: child)),
);

void main() {
  tearDown(() => useHttpClientForTesting(http.Client()));
  testWidgets(
    'Il ritorno mostra conclusioni, prossima azione e input che lo motivano',
    (tester) async {
      await tester.pumpWidget(
        page(DecisionReport(data: decision('Ci sono segnali da verificare'))),
      );
      expect(find.text('Ci sono segnali da verificare'), findsOneWidget);
      expect(
        find.text('Appassimento: verifica acqua e radici'),
        findsOneWidget,
      );
      expect(
        find.text('Misura l’umidità alla profondità radicale.'),
        findsOneWidget,
      );
      await tester.tap(find.text('Dati su cui si basa'));
      await tester.pumpAndSettle();
      expect(find.textContaining('P − ET₀ -9 mm'), findsOneWidget);
    },
  );
  testWidgets(
    'Analizza tutti gli input aggiorna il ritorno anche senza confini',
    (tester) async {
      var calls = 0;
      useHttpClientForTesting(
        MockClient((r) async {
          calls++;
          final posted = jsonDecode(r.body) as Map;
          expect(posted['latitude'], isNull);
          return http.Response(
            jsonEncode({
              'crop_review': {
                'decision_support': decision('Valutazione $calls'),
              },
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }),
      );
      await tester.pumpWidget(
        page(
          AgronomyPanel(
            parcelId: 'legacy',
            latitude: null,
            longitude: null,
            baseUrl: apiBaseUrl,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Analisi integrata'), findsOneWidget);
      expect(calls, 1);
      expect(find.text('Valutazione 1'), findsOneWidget);
      await tester.tap(find.text('Analizza tutti gli input'));
      await tester.pumpAndSettle();
      expect(calls, 2);
      expect(find.text('Valutazione 2'), findsOneWidget);
    },
  );
}
