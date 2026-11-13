import 'package:flutter/material.dart';

import 'api.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key, this.initialSetupToken});
  final String? initialSetupToken;
  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final username = TextEditingController();
  final password = TextEditingController();
  final confirmation = TextEditingController();
  final farm = TextEditingController(text: 'azienda-locale');
  final setupToken = TextEditingController();
  bool busy = false;
  bool checking = true;
  bool tokenFromLink = false;
  bool setupRequired = false;
  bool setupEnabled = false;
  bool legacyAvailable = false;
  bool claimLegacy = false;
  String? error;

  @override
  void initState() {
    super.initState();
    final fragment = Uri.tryParse(Uri.base.fragment);
    setupToken.text =
        widget.initialSetupToken ??
        fragment?.queryParameters['setup_token'] ??
        '';
    tokenFromLink = setupToken.text.isNotEmpty;
    checkServer();
  }

  Future<void> checkServer() async {
    try {
      final status = await ApiSession.instance.accountStatus();
      if (!mounted) return;
      setState(() {
        setupRequired = status['setup_required'] == true;
        setupEnabled = status['setup_enabled'] == true;
        legacyAvailable = status['legacy_available'] == true;
        checking = false;
        error = null;
      });
    } catch (_) {
      if (mounted) {
        setState(() {
          checking = false;
          error = 'Server non raggiungibile. Avvia AgroPlan e premi Riprova.';
        });
      }
    }
  }

  @override
  void dispose() {
    username.dispose();
    password.dispose();
    confirmation.dispose();
    farm.dispose();
    setupToken.dispose();
    super.dispose();
  }

  Future<void> submit() async {
    if (busy || checking) return;
    if (username.text.trim().isEmpty || password.text.isEmpty) {
      setState(() => error = 'Inserisci nome utente e password.');
      return;
    }
    final creating = setupRequired && setupEnabled;
    if (creating &&
        (password.text.length < 12 || password.text != confirmation.text)) {
      setState(
        () => error = 'Usa almeno 12 caratteri e ripeti la stessa password.',
      );
      return;
    }
    FocusScope.of(context).unfocus();
    setState(() {
      busy = true;
      error = null;
    });
    try {
      if (creating) {
        await ApiSession.instance.setup(
          username: username.text.trim(),
          password: password.text,
          farmId: farm.text.trim(),
          token: setupToken.text.trim(),
          claimLegacy: claimLegacy,
        );
      } else {
        await ApiSession.instance.login(username.text.trim(), password.text);
      }
    } catch (e) {
      if (mounted) {
        setState(() => error = e.toString().replaceFirst('Exception: ', ''));
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final creating = setupRequired && setupEnabled;
    if (checking) {
      return const Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 16),
              Text('Apertura AgroPlan…'),
            ],
          ),
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(title: const Text('AgroPlan')),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: SizedBox(
            width: 400,
            child: AutofillGroup(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(Icons.grass, size: 56, color: Color(0xFF32764A)),
                  const SizedBox(height: 20),
                  Text(
                    creating
                        ? 'Crea il primo accesso'
                        : 'Accedi alla tua azienda',
                    style: const TextStyle(fontSize: 24),
                  ),
                  const SizedBox(height: 16),
                  if (checking) const LinearProgressIndicator(),
                  if (setupRequired && !setupEnabled)
                    const Text(
                      'Il responsabile deve creare il primo account sul server prima dell’accesso.',
                    ),
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
                    autofillHints: [
                      creating
                          ? AutofillHints.newPassword
                          : AutofillHints.password,
                    ],
                    onSubmitted: (_) {
                      if (!creating) submit();
                    },
                    decoration: const InputDecoration(labelText: 'Password'),
                  ),
                  if (creating) ...[
                    TextField(
                      controller: confirmation,
                      enabled: !busy,
                      obscureText: true,
                      autofillHints: const [AutofillHints.newPassword],
                      decoration: const InputDecoration(
                        labelText: 'Ripeti password',
                      ),
                    ),
                    TextField(
                      controller: farm,
                      enabled: !busy,
                      decoration: const InputDecoration(
                        labelText: 'Identificativo azienda',
                        helperText:
                            'Lettere, numeri, trattino o trattino basso.',
                      ),
                    ),
                    if (!tokenFromLink)
                      TextField(
                        controller: setupToken,
                        enabled: !busy,
                        decoration: const InputDecoration(
                          labelText: 'Codice di attivazione',
                          helperText: 'Apri il collegamento generato da Avvia AgroPlan.',
                        ),
                      ),
                    if (legacyAvailable)
                      CheckboxListTile(
                        value: claimLegacy,
                        contentPadding: EdgeInsets.zero,
                        title: const Text(
                          'Associa a questa azienda i dati locali già presenti',
                        ),
                        onChanged: busy
                            ? null
                            : (value) =>
                                  setState(() => claimLegacy = value ?? false),
                      ),
                    const Text(
                      'La password resta sul tuo server in forma protetta. Non inviarla in chat.',
                    ),
                  ],
                  const SizedBox(height: 20),
                  if (error != null) ...[
                    Text(error!, style: const TextStyle(color: Colors.red)),
                    TextButton(
                      onPressed: busy ? null : checkServer,
                      child: const Text('Riprova collegamento'),
                    ),
                  ],
                  FilledButton(
                    onPressed: busy || checking ? null : submit,
                    child: Text(
                      busy
                          ? 'Attendi…'
                          : creating
                          ? 'Crea account e accedi'
                          : 'Accedi',
                    ),
                  ),
                  const SizedBox(height: 12),
                  if (!creating)
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
}
