import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:agroplan/keyboard_controls.dart';

void main() {
  testWidgets(
    'I campi nel pannello laterale restano sopra la tastiera e Fine',
    (tester) async {
      tester.view.viewInsets = const FakeViewPadding(bottom: 250);
      addTearDown(tester.view.resetViewInsets);
      final scaffold = GlobalKey<ScaffoldState>();
      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => KeyboardControls(child: child!),
          home: Scaffold(
            key: scaffold,
            endDrawer: const KeyboardAwareDrawer(
              child: SingleChildScrollView(
                child: Column(children: [SizedBox(height: 400), TextField()]),
              ),
            ),
          ),
        ),
      );
      scaffold.currentState!.openEndDrawer();
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byType(TextField));
      await tester.enterText(find.byType(TextField), 'Dato');
      await tester.pumpAndSettle();
      expect(
        tester.getBottomLeft(find.byType(TextField)).dy,
        lessThanOrEqualTo(
          tester.getTopLeft(find.widgetWithText(TextButton, 'Fine')).dy,
        ),
      );
    },
  );
  testWidgets(
    'Fine è sopra la tastiera numerica, conserva il testo e lascia spazio al campo',
    (tester) async {
      tester.view.viewInsets = const FakeViewPadding(bottom: 250);
      addTearDown(tester.view.resetViewInsets);
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => KeyboardControls(child: child!),
          home: Scaffold(
            body: Column(
              children: [
                TextField(
                  controller: controller,
                  keyboardType: TextInputType.number,
                ),
                const Text('Spazio del modulo'),
              ],
            ),
          ),
        ),
      );
      await tester.enterText(find.byType(TextField), '12,5');
      await tester.pump();
      final focused = tester
          .widget<EditableText>(find.byType(EditableText))
          .focusNode;
      expect(focused.hasFocus, isTrue);
      final fieldBottom = tester.getBottomLeft(find.byType(TextField)).dy;
      final barTop = tester
          .getTopLeft(find.widgetWithText(TextButton, 'Fine'))
          .dy;
      expect(fieldBottom, lessThan(barTop));
      await tester.tap(find.text('Fine'));
      await tester.pump();
      expect(focused.hasFocus, isFalse);
      expect(controller.text, '12,5');
    },
  );
  testWidgets(
    'Toccare fuori chiude la tastiera anche con tocco mobile e nelle finestre',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => KeyboardControls(child: child!),
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () => showDialog<void>(
                  context: context,
                  builder: (_) => const AlertDialog(
                    content: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        TextField(),
                        SizedBox(height: 70, child: Text('Fuori dal campo')),
                      ],
                    ),
                  ),
                ),
                child: const Text('Apri'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Apri'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'Una nota');
      await tester.pump();
      final focused = tester
          .widget<EditableText>(find.byType(EditableText))
          .focusNode;
      expect(focused.hasFocus, isTrue);
      await tester.tap(find.text('Fuori dal campo'));
      await tester.pump();
      expect(focused.hasFocus, isFalse);
      expect(find.text('Una nota'), findsOneWidget);
    },
  );
}
