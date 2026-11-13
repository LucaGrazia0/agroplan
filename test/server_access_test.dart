import 'package:agroplan/api.dart';
import 'package:agroplan/login_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  tearDown(() {
    ApiSession.instance.clear();
    useHttpClientForTesting(http.Client());
  });
  testWidgets('Un server precedente non mostra un modulo password inutile', (
    tester,
  ) async {
    useHttpClientForTesting(
      MockClient((_) async => http.Response('{"detail":"Not Found"}', 404)),
    );
    await tester.pumpWidget(const MaterialApp(home: LoginPage()));
    await tester.pumpAndSettle();
    expect(find.textContaining('versione precedente'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
    expect(find.text('Riprova collegamento'), findsOneWidget);
  });
  testWidgets('Un errore di rete non invita a inserire credenziali', (
    tester,
  ) async {
    useHttpClientForTesting(
      MockClient((_) async => throw http.ClientException('offline')),
    );
    await tester.pumpWidget(const MaterialApp(home: LoginPage()));
    await tester.pumpAndSettle();
    expect(find.textContaining('Collegamento non riuscito'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
  });
  testWidgets(
    'Il client nativo propone abbinamento senza nome utente o password',
    (tester) async {
      useHttpClientForTesting(
        MockClient(
          (_) async => http.Response(
            '{"setup_required":false,"setup_enabled":false,"pairing_available":true}',
            200,
          ),
        ),
      );
      await tester.pumpWidget(const MaterialApp(home: LoginPage()));
      await tester.pumpAndSettle();
      expect(find.text('Abbina questo dispositivo'), findsOneWidget);
      expect(find.text('Nome utente'), findsNothing);
      expect(find.text('Password'), findsNothing);
    },
  );
}
