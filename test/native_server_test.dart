import 'dart:convert';

import 'package:agroplan/api.dart';
import 'package:agroplan/login_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    resetNativeServerForTesting();
  });
  tearDown(() {
    ApiSession.instance.clear();
    resetNativeServerForTesting();
    useHttpClientForTesting(http.Client());
  });

  test('Il server nativo resta configurato dopo la riapertura', () async {
    await configureNativeServer(' https://api.example/agroplan/ ');
    expect(apiBaseUrl, 'https://api.example/agroplan');
    resetNativeServerForTesting();
    expect(nativeServerConfigured, isFalse);
    await restoreNativeServer();
    expect(apiBaseUrl, 'https://api.example/agroplan');
    expect(nativeServerConfigured, isTrue);
    for (final value in [
      'http://localhost:8091',
      'https://user:password@api.example',
      'https://api.example/?token=secret',
      'file:///tmp/api',
      '',
    ]) {
      expect(() => validateServerUrl(value), throwsFormatException);
    }
  });

  testWidgets('La configurazione collega le richieste al server scelto', (
    tester,
  ) async {
    final requests = <Uri>[];
    useHttpClientForTesting(
      MockClient((request) async {
        requests.add(request.url);
        return http.Response(
          jsonEncode({'setup_required': false, 'setup_enabled': false}),
          200,
        );
      }),
    );
    await tester.pumpWidget(
      const MaterialApp(home: LoginPage(configureServerOnStart: true)),
    );
    expect(requests, isEmpty);
    await tester.enterText(find.byType(TextField), 'https://api.example');
    await tester.tap(find.text('Collega server'));
    await tester.pumpAndSettle();
    expect(requests.single, Uri.parse('https://api.example/auth/status'));
    expect(find.text('Accedi alla tua azienda'), findsOneWidget);
    await tester.tap(find.text('Configura server'));
    await tester.pumpAndSettle();
    expect(find.text('Collega il tuo server'), findsOneWidget);
  });
}
