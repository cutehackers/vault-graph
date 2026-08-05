library sample;

import "dart:async";

@deprecated
class Greeter extends Base with Mixin implements Interface {
  final String name;

  Future<String> greet() async {
    return name;
  }

  String get display => name;
}

mixin Mixin on Base {
  void mix() {}
}

extension GreeterExt on Greeter {
  String get shout => greet();
}

Future<void> testGreeting() async {
  final g = Greeter("x");
  await g.greet();
}
