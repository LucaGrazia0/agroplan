import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:agroplan/api.dart';
import 'package:agroplan/workspace_cache.dart';
import 'package:agroplan/first_steps.dart';
import 'package:agroplan/workspace_panel.dart';

void main() {
  tearDown(() => useHttpClientForTesting(http.Client()));
  test('Un reset pulisce solo la copia corrente, conserva il backup e non si ripete', () async {
    const cache = 'cache-server-farm';
    const prefix = 'field_draft_server_farm_';
    final old = jsonEncode({
      'parcels': [
        {'id': 'old'},
      ],
      'soilOutbox': [
        {'parcel_id': 'old'},
      ],
    });
    SharedPreferences.setMockInitialValues({
      cache: old,
      '${prefix}old': jsonEncode({
        'payload': {'parcel_id': 'old'},
      }),
      '${prefix}b_other': jsonEncode({
        'payload': {'parcel_id': 'other'},
      }),
      'different-farm': 'unchanged',
      'agroplan_api_url': 'https://server.example',
    });
    final prefs = await SharedPreferences.getInstance();
    expect(await reconcileWorkspaceCache(prefs, cache, prefix, 0), false);
    expect(prefs.getString(cache), old);
    expect(await reconcileWorkspaceCache(prefs, cache, prefix, 1), true);
    expect(prefs.getString(cache), isNull);
    expect(prefs.getString('${prefix}old'), isNull);
    expect(prefs.getString('${cache}_before_reset_0'), isNotNull);
    expect(prefs.getString('${prefix}b_other'), isNotNull);
    expect(prefs.getString('different-farm'), 'unchanged');
    expect(prefs.getString('agroplan_api_url'), 'https://server.example');
    await prefs.setString(cache, 'new-data');
    expect(await reconcileWorkspaceCache(prefs, cache, prefix, 1), false);
    expect(prefs.getString(cache), 'new-data');
    await expectLater(
      reconcileWorkspaceCache(prefs, cache, prefix, 0),
      throwsFormatException,
    );
    expect(prefs.getString(cache), 'new-data');
  });
  testWidgets('Il primo avvio attende la verifica prima di creare dati', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: FirstSteps(ready: false, onCreate: () {})),
      ),
    );
    expect(
      tester
          .widget<FilledButton>(
            find.byWidgetPredicate((w) => w is FilledButton),
          )
          .onPressed,
      isNull,
    );
    expect(find.textContaining('Verifica dell’area di lavoro'), findsOneWidget);
  });
  testWidgets(
    'Il nuovo avvio guida alla prima particella senza esempi precaricati',
    (tester) async {
      var created = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: FirstSteps(onCreate: () => created++)),
        ),
      );
      expect(find.text('Benvenuto in AgroPlan'), findsOneWidget);
      await tester.tap(find.text('Crea la prima particella'));
      expect(created, 1);
    },
  );
  testWidgets('Un archivio si ripristina con conferma ed è aggiuntivo', (
    tester,
  ) async {
    var restored = false;
    var changed = 0;
    useHttpClientForTesting(
      MockClient((r) async {
        if (r.method == 'POST') {
          expect(r.url.path, endsWith('/restore'));
          expect(jsonDecode(r.body)['expected_generation'], 1);
          restored = true;
          return http.Response('{"generation":1,"restored_parcels":2}', 200);
        }
        if (r.url.path.endsWith('/status')) {
          return http.Response(
            jsonEncode({'generation': 1, 'active_parcels': restored ? 3 : 1}),
            200,
          );
        }
        return http.Response(
          jsonEncode([
            {
              'id': 'archive-test',
              'created_at': '2026-11-23T10:00:00',
              'parcel_count': 2,
              'restored_at': restored ? '2026-11-23T11:00:00' : null,
            },
          ]),
          200,
        );
      }),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: WorkspacePanel(
            onChanged: () async {
              changed++;
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(TextButton, 'Ripristina'));
    await tester.pumpAndSettle();
    expect(restored, false);
    await tester.tap(find.widgetWithText(FilledButton, 'Ripristina'));
    await tester.pumpAndSettle();
    expect(restored, true);
    expect(changed, 1);
    expect(find.text('3 particelle attive'), findsOneWidget);
  });
}
