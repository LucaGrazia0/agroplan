import 'package:flutter/material.dart';

/// Scaffold drawers otherwise extend behind the keyboard independently of body.
class KeyboardAwareDrawer extends StatelessWidget {
  const KeyboardAwareDrawer({super.key, required this.child});
  final Widget child;
  @override
  Widget build(BuildContext context) => Drawer(
    child: Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: SafeArea(child: child),
    ),
  );
}

/// Covers fields in pages and dialogs, including iOS numeric keyboards.
class KeyboardControls extends StatelessWidget {
  const KeyboardControls({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final query = MediaQuery.of(context);
    final keyboard = query.viewInsets.bottom;
    const toolbarHeight = 48.0;
    return Actions(
      actions: {
        EditableTextTapOutsideIntent:
            CallbackAction<EditableTextTapOutsideIntent>(
              onInvoke: (intent) {
                intent.focusNode.unfocus();
                return null;
              },
            ),
      },
      child: Stack(
        fit: StackFit.expand,
        children: [
          MediaQuery(
            data: query.copyWith(
              viewInsets: query.viewInsets.copyWith(
                bottom: keyboard > 0 ? keyboard + toolbarHeight : 0,
              ),
            ),
            child: child,
          ),
          if (keyboard > 0)
            Positioned(
              left: 0,
              right: 0,
              bottom: keyboard,
              height: toolbarHeight,
              child: Material(
                elevation: 4,
                color: Theme.of(context).colorScheme.surfaceContainerHigh,
                child: Align(
                  alignment: Alignment.centerRight,
                  child: TextButton.icon(
                    onPressed: () =>
                        FocusManager.instance.primaryFocus?.unfocus(),
                    icon: const Icon(Icons.keyboard_hide_outlined),
                    label: const Text('Fine'),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
