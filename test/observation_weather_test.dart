import 'package:agroplan/analysis_report.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Il rilievo mostra copertura e ritardo senza cambiare data', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final data = {
      'crop_review': {
        'observation_weather': {
          'observation_date': '2026-11-24',
          'start_date': '2026-11-10',
          'end_date': '2026-11-23',
          'available_through': '2026-11-19',
          'available_days': 10,
          'paired_days': 9,
          'climatic_balance_mm': -9,
          'missing_dates': [
            '2026-11-20',
            '2026-11-21',
            '2026-11-22',
            '2026-11-23',
          ],
          'trailing_missing_dates': [
            '2026-11-20',
            '2026-11-21',
            '2026-11-22',
            '2026-11-23',
          ],
          'coverage': {
            'rain': {
              'valid_days': 10,
              'missing_dates': ['2026-11-20'],
            },
            'et0': {
              'valid_days': 9,
              'missing_dates': ['2026-11-18'],
            },
          },
          'rain_mm': 20,
          'et0_mm': 27,
        },
      },
    };
    for (final section in [0, 2, 3]) {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: AnalysisReport(data: data, section: section),
            ),
          ),
        ),
      );
      expect(find.text('Rilievo del 24/11/2026'), findsOneWidget);
      expect(find.text('10 giorni con dati su 14'), findsOneWidget);
      expect(find.text('Meteo disponibile fino al 19/11/2026'), findsOneWidget);
      expect(
        find.textContaining('20/11/2026, 21/11/2026, 22/11/2026, 23/11/2026'),
        findsOneWidget,
      );
      expect(
        find.text('P − ET₀: -9 mm sui 9 giorni confrontabili.'),
        findsOneWidget,
      );
      expect(find.textContaining('Il ritardo non richiede'), findsOneWidget);
      expect(tester.takeException(), isNull);
    }
    await tester.tap(find.text('Copertura e valori disponibili'));
    await tester.pumpAndSettle();
    expect(find.text('Pioggia: 20 mm'), findsOneWidget);
    expect(
      find.textContaining('Date senza valore: 18/11/2026'),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });
}
