import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:agroplan/api.dart';
import 'package:agroplan/login_page.dart';
import 'package:agroplan/satellite_scenes.dart';

void main() {
  tearDown(() {
    ApiSession.instance.clear();
    useHttpClientForTesting(http.Client());
  });
  test('Il browser usa lo stesso server e i client configurati mantengono il proprio URL', () {
    expect(
      resolveApiBaseUrl(
        '',
        Uri.parse('https://agroplan.example/app/'),
        isWeb: true,
      ),
      'https://agroplan.example',
    );
    expect(
      resolveApiBaseUrl(
        'https://api.example/',
        Uri.parse('https://app.example'),
        isWeb: true,
      ),
      'https://api.example',
    );
    expect(
      resolveApiBaseUrl('', Uri.parse('file:///app'), isWeb: false),
      'http://127.0.0.1:8091',
    );
  });
  test('Le date satellitari sono uniche, ordinate e senza valori invalidi', () {
    final days = acquisitionDays([
      {'datetime': '2026-11-02T10:00:00Z', 'cloud_cover': 20},
      {'datetime': '2026-11-02T11:00:00Z', 'cloud_cover': 5},
      {'datetime': '2026-11-03T10:00:00Z', 'cloud_cover': 10},
      {'datetime': 'bad', 'cloud_cover': 0},
      {'datetime': '2026-11-04T10:00:00Z', 'cloud_cover': 90},
    ]);
    expect(days.length, 2);
    expect(days.first['datetime'].toString(), startsWith('2026-11-03'));
    expect(days.last['cloud_cover'], 5);
  });
  testWidgets(
    'La modalità locale apre direttamente l’app senza modulo password',
    (tester) async {
      useHttpClientForTesting(
        MockClient(
          (_) async => http.Response(
            jsonEncode({
              'local_mode': true,
              'setup_required': false,
              'setup_enabled': false,
              'user': {'username': 'Uso locale', 'farm_id': 'azienda-locale'},
            }),
            200,
          ),
        ),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: ListenableBuilder(
            listenable: ApiSession.instance,
            builder: (_, _) => ApiSession.instance.authenticated
                ? const Text('App locale aperta')
                : const LoginPage(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('App locale aperta'), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
      expect(ApiSession.instance.localAccess, isTrue);
    },
  );

  testWidgets(
    'Il primo accesso richiede conferma password e attiva l’account',
    (tester) async {
      Map<String, dynamic>? posted;
      useHttpClientForTesting(
        MockClient((request) async {
          if (request.url.path == '/auth/status') {
            return http.Response(
              jsonEncode({
                'setup_required': true,
                'setup_enabled': true,
                'legacy_available': true,
              }),
              200,
            );
          }
          if (request.url.path == '/auth/setup') {
            posted = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response('{}', 201);
          }
          if (request.url.path == '/auth/login') {
            return http.Response(
              jsonEncode({
                'access_token': 'session-test',
                'user': {'username': 'luca', 'farm_id': 'farm-local'},
              }),
              200,
            );
          }
          return http.Response('{}', 404);
        }),
      );
      await tester.pumpWidget(
        const MaterialApp(
          home: LoginPage(initialSetupToken: 'setup-test-token'),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Crea il primo accesso'), findsOneWidget);
      await tester.enterText(
        find.widgetWithText(TextField, 'Nome utente'),
        'luca',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Password'),
        'a-secure-password',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Ripeti password'),
        'a-secure-password',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Identificativo azienda'),
        'farm-local',
      );
      await tester.ensureVisible(find.text('Crea account e accedi'));
      await tester.tap(find.text('Crea account e accedi'));
      await tester.pumpAndSettle();
      expect(posted?['setup_token'], 'setup-test-token');
      expect(posted?['claim_legacy'], false);
      expect(ApiSession.instance.authenticated, true);
    },
  );
}
