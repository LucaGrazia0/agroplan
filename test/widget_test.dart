import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:agroplan/main.dart';
import 'package:agroplan/api.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  setUp(
    () => useHttpClientForTesting(
      MockClient(
        (_) async => http.Response(
          '{"setup_required":false,"setup_enabled":false}',
          200,
        ),
      ),
    ),
  );
  tearDown(() => useHttpClientForTesting(http.Client()));
  testWidgets('La schermata iniziale richiede l’accesso all’azienda', (
    tester,
  ) async {
    await tester.pumpWidget(const AgroPlanApp());
    expect(find.text('Accedi alla tua azienda'), findsOneWidget);
    expect(find.byType(TextField), findsNWidgets(2));
    expect(find.text('Accedi'), findsOneWidget);
    await tester.tap(find.text('Accedi'));
    await tester.pump();
    expect(find.text('Accedi alla tua azienda'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  test(
    'Area particella e dati di sincronizzazione sopravvivono al salvataggio',
    () {
      final parcel = FarmParcel.fromJson({
        'id': 'campo-1',
        'name': 'Campo Nord',
        'crop': 'Frumento tenero',
        'soil': {'ph': '6.5'},
        'revision': 3,
        'pending': true,
        'points': [
          {'lat': 44.5, 'lng': 11.3},
          {'lat': 44.51, 'lng': 11.3},
          {'lat': 44.51, 'lng': 11.31},
        ],
      });
      final restored = FarmParcel.fromJson(parcel.toJson());
      expect(restored.id, 'campo-1');
      expect(restored.revision, 3);
      expect(restored.pending, isTrue);
      expect(restored.soil['ph'], '6.5');
      expect(restored.hectares, greaterThan(0));
      expect(restored.hectares, closeTo(parcel.hectares, 0.000001));
    },
  );
}
