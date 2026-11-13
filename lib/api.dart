import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as transport;
import 'package:shared_preferences/shared_preferences.dart';
export 'package:http/http.dart' show Response, ClientException;

String resolveApiBaseUrl(String configured, Uri page, {required bool isWeb}) {
  if (configured.trim().isNotEmpty) {
    return configured.trim().replaceFirst(RegExp(r'/+$'), '');
  }
  if (isWeb && (page.scheme == 'https' || page.scheme == 'http')) {
    return page.origin;
  }
  return 'http://127.0.0.1:8091';
}

const _compiledApiUrl = String.fromEnvironment('AGROPLAN_API_URL');
String? _nativeApiUrl;
bool get nativeServerConfigured =>
    kIsWeb || _nativeApiUrl != null || _compiledApiUrl.trim().isNotEmpty;
String get apiBaseUrl =>
    _nativeApiUrl ??
    resolveApiBaseUrl(_compiledApiUrl, Uri.base, isWeb: kIsWeb);

String validateServerUrl(String value) {
  final uri = Uri.tryParse(value.trim());
  if (uri == null ||
      uri.scheme != 'https' ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment) {
    throw const FormatException(
      'Inserisci l’indirizzo HTTPS del server AgroPlan.',
    );
  }
  return uri.toString().replaceFirst(RegExp(r'/+$'), '');
}

Future<void> restoreNativeServer() async {
  if (kIsWeb) return;
  final saved = (await SharedPreferences.getInstance()).getString(
    'agroplan_api_url',
  );
  if (saved != null) {
    try {
      _nativeApiUrl = validateServerUrl(saved);
    } on FormatException {
      /* Ask again. */
    }
  }
}

Future<void> configureNativeServer(String value) async {
  if (kIsWeb) throw StateError('Il browser usa il proprio server.');
  final validated = validateServerUrl(value);
  final saved = await (await SharedPreferences.getInstance()).setString(
    'agroplan_api_url',
    validated,
  );
  if (!saved) throw Exception('Impossibile salvare il server. Riprova.');
  ApiSession.instance.clear();
  _nativeApiUrl = validated;
}

@visibleForTesting
void resetNativeServerForTesting() {
  _nativeApiUrl = null;
}

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
  bool localAccess = false;
  bool get authenticated => _token != null || localAccess;

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
    localAccess = false;
    _token = data['access_token'] as String;
    this.username = data['user']['username'] as String;
    farmId = data['user']['farm_id'] as String;
    notifyListeners();
  }

  Future<Map<String, dynamic>> accountStatus() async {
    final response = await _client
        .get(Uri.parse('$apiBaseUrl/auth/status'))
        .timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) throw Exception('Server non raggiungibile');
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    if (data['local_mode'] == true) {
      localAccess = true;
      _token = null;
      username = data['user']['username'] as String;
      farmId = data['user']['farm_id'] as String;
      notifyListeners();
    }
    return data;
  }

  Future<void> setup({
    required String username,
    required String password,
    required String farmId,
    required String token,
    required bool claimLegacy,
  }) async {
    final response = await _client
        .post(
          Uri.parse('$apiBaseUrl/auth/setup'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'username': username,
            'password': password,
            'farm_id': farmId,
            'setup_token': token,
            'claim_legacy': claimLegacy,
          }),
        )
        .timeout(const Duration(seconds: 20));
    if (response.statusCode != 201) {
      final data = jsonDecode(response.body);
      final detail = data is Map ? data['detail'] : null;
      throw Exception(
        detail is String
            ? detail
            : 'Controlla nome utente, azienda e password.',
      );
    }
    await login(username, password);
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
    if (_token == null && !localAccess) return;
    localAccess = false;
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
