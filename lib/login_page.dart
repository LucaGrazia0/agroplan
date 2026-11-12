import 'package:flutter/material.dart';

import 'api.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});
  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final username = TextEditingController();
  final password = TextEditingController();
  bool busy = false;
  String? error;

  @override
  void dispose() {
    username.dispose();
    password.dispose();
    super.dispose();
  }

  Future<void> submit() async {
    if (busy || username.text.trim().isEmpty || password.text.isEmpty) return;
    FocusScope.of(context).unfocus();
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await ApiSession.instance.login(username.text.trim(), password.text);
    } catch (e) {
      if (mounted) setState(() => error = 'Accesso non riuscito: $e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('AgroPlan')),
    body: Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: SizedBox(
          width: 380,
          child: AutofillGroup(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Icon(Icons.grass, size: 56, color: Color(0xFF32764A)),
                const SizedBox(height: 20),
                const Text(
                  'Accedi alla tua azienda',
                  style: TextStyle(fontSize: 24),
                ),
                const SizedBox(height: 20),
                TextField(
                  controller: username,
                  enabled: !busy,
                  autofillHints: const [AutofillHints.username],
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(labelText: 'Nome utente'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: password,
                  enabled: !busy,
                  obscureText: true,
                  autofillHints: const [AutofillHints.password],
                  onSubmitted: (_) => submit(),
                  decoration: const InputDecoration(labelText: 'Password'),
                ),
                const SizedBox(height: 20),
                if (error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(
                      error!,
                      style: const TextStyle(color: Colors.red),
                    ),
                  ),
                FilledButton(
                  onPressed: busy ? null : submit,
                  child: Text(busy ? 'Accesso in corso…' : 'Accedi'),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Usa l’account fornito dal responsabile della tua azienda.',
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}
