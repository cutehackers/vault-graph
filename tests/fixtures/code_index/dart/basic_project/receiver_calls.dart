library receiver_calls;

String foo() => '';

class Receiver {
  void run() {}

  void verify() {
    "x".trim();
    this.run();
    (foo()).bar();
    getObj().run();
    foo().bar();
    run();
  }
}

Receiver getObj() => Receiver();
Receiver foo() => Receiver();
