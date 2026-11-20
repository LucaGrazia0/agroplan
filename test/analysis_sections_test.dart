import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:agroplan/api.dart';
import 'package:agroplan/analysis_report.dart';
import 'package:agroplan/agronomy_panel.dart';
import 'package:agroplan/parcel_sections.dart';
import 'package:agroplan/water_parameters.dart';

Map<String, dynamic> report() => {
  'crop_review': {
    'summary': 'Sintesi',
    'manual_assessment': {
      'engine_version': 'test',
      'references': [],
      'domains': {
        for (final key in ['soil', 'weather', 'problems'])
          key: {
            'status': 'partial',
            'summary': key,
            'findings': [
              {
                'title': 'Risultato $key',
                'status': 'available',
                'evidence': 'Misura $key',
                'interpretation': 'Lettura $key',
                'next_check': 'Verifica $key',
                'source_ids': [],
              },
            ],
          },
      },
    },
  },
  'windows': {},
};

Widget page(Widget child) => MaterialApp(
  home: Scaffold(body: SingleChildScrollView(child: child)),
);

void main() {
  tearDown(() {
    ApiSession.instance.clear();
    useHttpClientForTesting(http.Client());
  });
  testWidgets(
    'Suolo, meteo e problematiche mostrano solo il proprio risultato',
    (tester) async {
      for (var section = 1; section <= 3; section++) {
        await tester.pumpWidget(
          page(AnalysisReport(data: report(), section: section)),
        );
        final key = ['soil', 'weather', 'problems'][section - 1];
        expect(find.text('Risultato $key'), findsOneWidget);
        for (final other in [
          'soil',
          'weather',
          'problems',
        ].where((v) => v != key)) {
          expect(find.text('Risultato $other'), findsNothing);
        }
      }
    },
  );
  testWidgets('Cambiare sezione conserva analisi e non richiede nuovi dati', (
    tester,
  ) async {
    var calls = 0;
    useHttpClientForTesting(
      MockClient((r) async {
        calls++;
        return http.Response(jsonEncode(report()), 200);
      }),
    );
    for (final section in [0, 1, 2, 3]) {
      await tester.pumpWidget(
        page(
          AgronomyPanel(
            key: const ValueKey('panel'),
            parcelId: 'field',
            latitude: 44.5,
            longitude: 11.3,
            baseUrl: apiBaseUrl,
            section: section,
          ),
        ),
      );
      await tester.pumpAndSettle();
    }
    expect(calls, 1);
    expect(find.text('Risultato problems'), findsOneWidget);
  });
  testWidgets('Le sezioni restano leggibili su schermo stretto', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(360, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var selection = 0;
    await tester.pumpWidget(
      page(
        ParcelSections(selected: selection, onChanged: (v) => selection = v),
      ),
    );
    await tester.tap(find.text('Problematiche'));
    expect(selection, 3);
    expect(find.text('Suolo'), findsOneWidget);
    expect(find.text('Meteo'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  testWidgets('Salvare Kc conserva le misure del suolo aggiornate sul server', (
    tester,
  ) async {
    var gets = 0;
    Map? saved;
    var changes = 0;
    useHttpClientForTesting(
      MockClient((r) async {
        if (r.method == 'PUT') {
          saved = jsonDecode(r.body) as Map;
          return http.Response(r.body, 200);
        }
        gets++;
        return http.Response(
          jsonEncode({
            'observed_at': '2026-11-10',
            'field_capacity_percent': gets == 1 ? 30 : 32,
            'wilting_point_percent': 15,
            'root_depth_m': .8,
          }),
          200,
        );
      }),
    );
    await tester.pumpWidget(
      page(
        WaterParametersPanel(
          parcelId: 'field',
          weather: true,
          onSaved: () => changes++,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Parametri per ETc'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Coefficiente Kc verificato'),
      '1,15',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Kc valido dal (AAAA-MM-GG)'),
      '2026-11-01',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Kc valido al (AAAA-MM-GG)'),
      '2026-11-18',
    );
    await tester.ensureVisible(find.text('Salva parametri'));
    await tester.tap(find.text('Salva parametri'));
    await tester.pumpAndSettle();
    expect(saved?['field_capacity_percent'], 32);
    expect(saved?['observed_at'], '2026-11-10');
    expect(saved?['kc'], 1.15);
    expect(changes, 1);
  });
}
