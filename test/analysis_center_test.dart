import 'dart:convert';

import 'package:agroplan/analysis_center.dart';
import 'package:agroplan/api.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  tearDown(() {
    ApiSession.instance.clear();
    useHttpClientForTesting(http.Client());
  });
  testWidgets(
    'Il Centro conserva il rilievo e salva i segni come approfondimento',
    (tester) async {
      tester.view.physicalSize = const Size(360, 850);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      Map latest = {
        'id': 'original',
        'parcel_id': 'field-1',
        'observed_at': '2026-11-25',
        'symptoms': ['spots'],
        'severity': 'mild',
        'notes': 'Nota conservata',
        'leaf_age': 'old',
      };
      Map? saved;
      useHttpClientForTesting(
        MockClient((r) async {
          if (r.url.path == '/analysis-center/schema') {
            return http.Response(
              jsonEncode({
                'signs': {'white_powder': 'Patina bianca superficiale'},
                'choices': {
                  for (final key in [
                    'field_pattern',
                    'progression',
                    'recent_event',
                  ])
                    key: {'unknown': 'Non so'},
                },
                'vision': {
                  'available': false,
                  'message': 'Modello in preparazione',
                },
              }),
              200,
            );
          }
          if (r.method == 'PUT') {
            saved = jsonDecode(r.body) as Map;
            latest = {...saved!, 'id': 'new-record'};
            return http.Response(jsonEncode(latest), 200);
          }
          return http.Response(
            jsonEncode({
              'crop_review': {
                'visual_context': {'latest': latest},
                'analysis_center': {
                  'headline': 'Piste da approfondire',
                  'candidates': [],
                  'questions': [],
                  'sources': [],
                  'limitations': [],
                  'coverage': [],
                },
              },
            }),
            200,
          );
        }),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: AnalysisCenter(
                parcelId: 'field-1',
                onSectionRequested: (_) {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Centro analisi'), findsOneWidget);
      expect(find.textContaining('25/11/2026'), findsOneWidget);
    await tester.tap(find.text('Rilievo'));
    await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Patina bianca superficiale'));
      await tester.tap(find.text('Patina bianca superficiale'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(
        find.text('Salva approfondimento e rianalizza'),
      );
      await tester.tap(find.text('Salva approfondimento e rianalizza'));
      await tester.pumpAndSettle();
      expect(saved!['observed_at'], '2026-11-25');
      expect(saved!['notes'], 'Nota conservata');
      expect(saved!['leaf_age'], 'old');
      expect(saved!['diagnostic_details']['signs'], ['white_powder']);
      expect(saved!.containsKey('id'), isFalse);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('Un errore del server lascia un percorso chiaro per riprovare', (
    tester,
  ) async {
    useHttpClientForTesting(MockClient((r) async => http.Response('{}', 503)));
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: AnalysisCenter(
              parcelId: 'field-1',
              onSectionRequested: (_) {},
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.textContaining('Centro analisi non disponibile'),
      findsOneWidget,
    );
    expect(find.text('Aggiorna il quadro'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
