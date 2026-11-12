import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as transport;
export 'package:http/http.dart' show Response, ClientException;

const apiBaseUrl = String.fromEnvironment(
  'AGROPLAN_API_URL',
  defaultValue: 'http://127.0.0.1:8000',
);

transport.Client _client = transport.Client();

@visibleForTesting
void useHttpClientForTesting(transport.Client client) {
  _client.close();
  _client = client;
}

class ApiSession extends ChangeNotifier {
  static final instance = ApiSession();
  String? _token;
  String? username;
  String? farmId;
  bool get authenticated => _token != null;

  Future<void> login(String username, String password) async {
    final response = await _client
        .post(
          Uri.parse('$apiBaseUrl/auth/login'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'username': username, 'password': password}),
        )
        .timeout(const Duration(seconds: 20));
    if (response.statusCode != 200) {
      throw Exception(
        response.statusCode == 429
            ? 'Troppi tentativi. Riprova tra qualche minuto.'
            : response.statusCode == 401
            ? 'Nome utente o password non validi.'
            : 'Accesso non disponibile. Riprova.',
      );
    }
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    _token = data['access_token'] as String;
    this.username = data['user']['username'] as String;
    farmId = data['user']['farm_id'] as String;
    notifyListeners();
  }

  Future<void> logout() async {
    final token = _token;
    clear();
    if (token != null) {
      try {
        await _client
            .post(
              Uri.parse('$apiBaseUrl/auth/logout'),
              headers: {'Authorization': 'Bearer $token'},
            )
            .timeout(const Duration(seconds: 10));
      } catch (_) {
        // The local session is already cleared; the server session expires.
      }
    }
  }

  void clear() {
    if (_token == null) return;
    _token = null;
    username = null;
    farmId = null;
    notifyListeners();
  }
}

Map<String, String> _headers(Map<String, String>? headers) => {
  ...?headers,
  if (ApiSession.instance._token != null)
    'Authorization': 'Bearer ${ApiSession.instance._token}',
};

Future<transport.Response> _check(Future<transport.Response> request) async {
  // A late response from an old session must not log out a new account.
  final token = ApiSession.instance._token;
  final response = await request;
  if (response.statusCode == 401 && token == ApiSession.instance._token) {
    ApiSession.instance.clear();
  }
  return response;
}

Future<transport.Response> get(Uri url, {Map<String, String>? headers}) =>
    _check(_client.get(url, headers: _headers(headers)));
Future<transport.Response> post(
  Uri url, {
  Map<String, String>? headers,
  Object? body,
}) => _check(_client.post(url, headers: _headers(headers), body: body));
Future<transport.Response> put(
  Uri url, {
  Map<String, String>? headers,
  Object? body,
}) => _check(_client.put(url, headers: _headers(headers), body: body));
Future<transport.Response> delete(Uri url, {Map<String, String>? headers}) =>
    _check(_client.delete(url, headers: _headers(headers)));
