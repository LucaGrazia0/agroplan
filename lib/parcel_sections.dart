import 'package:flutter/material.dart';

class ParcelSections extends StatelessWidget {
  const ParcelSections({
    super.key,
    required this.selected,
    required this.onChanged,
  });
  final int selected;
  final ValueChanged<int> onChanged;
  static const labels = [
    'Analisi integrata',
    'Suolo',
    'Meteo',
    'Problematiche',
    'Coltura',
    'Mappa e satellite',
  ];
  static const icons = [
    Icons.auto_graph,
    Icons.science_outlined,
    Icons.cloud_outlined,
    Icons.health_and_safety_outlined,
    Icons.grass,
    Icons.map_outlined,
  ];
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      const Text('Scegli una sezione', style: TextStyle(fontSize: 12)),
      const SizedBox(height: 8),
      LayoutBuilder(
        builder: (context, constraints) => Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (var i = 0; i < labels.length; i++)
              SizedBox(
                width: (constraints.maxWidth - 8) / 2,
                child: Semantics(
                  selected: selected == i,
                  child: OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 12,
                      ),
                      backgroundColor: selected == i
                          ? const Color(0xFFDDEDDC)
                          : Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    onPressed: () => onChanged(i),
                    child: Column(
                      children: [
                        Icon(icons[i], size: 21),
                        const SizedBox(height: 4),
                        Text(labels[i], textAlign: TextAlign.center),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    ],
  );
}
