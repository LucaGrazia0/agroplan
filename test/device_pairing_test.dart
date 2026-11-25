import 'dart:convert';

import 'package:agroplan/api.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test(
    'L’abbinamento sopravvive alla riapertura e l’uscita lo revoca',
    () async {
      FlutterSecureStorage.setMockInitialValues({});
      final calls = <String>[];
      useHttpClientForTesting(
        MockClient((request) async {
          calls.add(request.url.path);
          return http.Response(
            jsonEncode({
              'access_token': 'test-only-opaque-token',
              'expires_in': 3600,
              'user': {'username': 'owner', 'farm_id': 'farm-test'},
            }),
            200,
          );
        }),
      );
      final first = ApiSession();
      await first.pairDevice(
        'test-only-pairing-code-with-at-least-32-characters',
      );
      final reopened = ApiSession();
      await reopened.restorePairedDevice();
      expect(reopened.authenticated, isTrue);
      expect(reopened.farmId, 'farm-test');
      await reopened.logout();
      final loggedOut = ApiSession();
      await loggedOut.restorePairedDevice();
      expect(loggedOut.authenticated, isFalse);
      expect(calls, contains('/auth/logout'));
      useHttpClientForTesting(http.Client());
    },
  );
}
