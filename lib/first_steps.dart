import 'package:flutter/material.dart';

class FirstSteps extends StatelessWidget {
  const FirstSteps({super.key, required this.onCreate, this.ready = true});
  final VoidCallback onCreate;
  final bool ready;
  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.eco_outlined, size: 36, color: Color(0xFF32764A)),
          const SizedBox(height: 12),
          const Text(
            'Benvenuto in AgroPlan',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          const Text('Inizia dalla tua prima particella.'),
          const SizedBox(height: 16),
          const Text(
            '1. Disegna i confini sulla mappa.\n\n2. Inserisci la coltura e i dati che hai.\n\n3. Registra ciò che osservi e avvia l’analisi integrata.',
          ),
          const SizedBox(height: 18),
          FilledButton.icon(
            onPressed: ready ? onCreate : null,
            icon: const Icon(Icons.add_location_alt_outlined),
            label: const Text('Crea la prima particella'),
          ),
          if (!ready)
            const Padding(
              padding: EdgeInsets.only(top: 12),
              child: Text(
                'Verifica dell’area di lavoro in corso. Serve il collegamento al server per il primo avvio.',
              ),
            ),
        ],
      ),
    ),
  );
}
