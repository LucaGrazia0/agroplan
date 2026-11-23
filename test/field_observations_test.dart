import 'dart:convert';

import 'package:agroplan/api.dart';
import 'package:agroplan/field_observations.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  tearDown(() => useHttpClientForTesting(http.Client()));
  testWidgets('Il rilievo viene salvato e compare nello storico', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1000, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final rows = <Map<String, dynamic>>[];
    var changed = 0;
    useHttpClientForTesting(
      MockClient((request) async {
        if (request.method == 'PUT') {
          final data = jsonDecode(request.body) as Map<String, dynamic>;
          rows.add({...data, 'id': request.url.pathSegments.last});
          return http.Response(jsonEncode(rows.last), 200);
        }
        return http.Response(jsonEncode(rows), 200);
      }),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: FieldObservations(
              parcelId: 'field-1',
              onChanged: () => changed++,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ingiallimento'));
    final note = find.byWidgetPredicate(
      (w) =>
          w is TextField &&
          w.decoration?.labelText == 'Descrivi quello che vedi',
    );
    await tester.enterText(note, 'Foglie giovani ingiallite');
    await tester.tap(find.text('Salva rilievo'));
    await tester.pumpAndSettle();
    expect(changed, 1);
    expect(rows.single['symptoms'], ['yellowing']);
    expect(find.textContaining('Foglie giovani ingiallite'), findsOneWidget);
  });
  testWidgets('La bozza viene recuperata dopo un invio non riuscito', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1000, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    useHttpClientForTesting(
      MockClient(
        (r) async => http.Response(
          r.method == 'GET' ? '[]' : '{}',
          r.method == 'GET' ? 200 : 503,
        ),
      ),
    );
    Widget page() => MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: FieldObservations(parcelId: 'field-1', onChanged: () {}),
        ),
      ),
    );
    await tester.pumpWidget(page());
    await tester.pumpAndSettle();
    final note = find.byWidgetPredicate(
      (w) =>
          w is TextField &&
          w.decoration?.labelText == 'Descrivi quello che vedi',
    );
    await tester.enterText(note, 'Rilievo da inviare');
    await tester.tap(find.text('Salva rilievo'));
    await tester.pumpAndSettle();
    await tester.pumpWidget(const SizedBox());
    await tester.pumpWidget(page());
    await tester.pumpAndSettle();
    expect(
      tester.widget<TextField>(note).controller!.text,
      'Rilievo da inviare',
    );
  });
  testWidgets('I dettagli del rilievo vengono inviati insieme ai sintomi', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1000, 2000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    Map<String, dynamic>? saved;
    useHttpClientForTesting(
      MockClient((r) async {
        if (r.method == 'PUT') {
          saved = jsonDecode(r.body) as Map<String, dynamic>;
          return http.Response(
            r.body,
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }
        return http.Response('[]', 200);
      }),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: FieldObservations(parcelId: 'field-1', onChanged: () {}),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ingiallimento'));
    await tester.tap(find.text('Dettagli per migliorare l’analisi'));
    await tester.pumpAndSettle();
    await tester.tap(
      find
          .ancestor(
            of: find.text('Foglie interessate'),
            matching: find.byType(DropdownButtonFormField<String>),
          )
          .first,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Giovani').last);
    await tester.pumpAndSettle();
    await tester.tap(
      find
          .ancestor(
            of: find.text('Distribuzione dei sintomi'),
            matching: find.byType(DropdownButtonFormField<String>),
          )
          .first,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('A chiazze').last);
    await tester.pumpAndSettle();
    await tester.tap(
      find
          .ancestor(
            of: find.text('Aspetto delle radici'),
            matching: find.byType(DropdownButtonFormField<String>),
          )
          .first,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Scure o danneggiate').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Salva rilievo'));
    await tester.tap(find.text('Salva rilievo'));
    await tester.pumpAndSettle();
    expect(saved?['leaf_age'], 'young');
    expect(saved?['distribution'], 'patches');
    expect(saved?['root_condition'], 'damaged');
    expect(saved?['symptoms'], ['yellowing']);
  });
}
