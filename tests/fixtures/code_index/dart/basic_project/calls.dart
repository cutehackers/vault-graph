library calls;

class Receiver {
  void greet(String value) {}
}

void bar(int value) {}
void named({required int value}) {}

void run(Receiver obj, int y, String arg) {
  bar(y);
  named(value: y);
  obj.greet(arg);
}
