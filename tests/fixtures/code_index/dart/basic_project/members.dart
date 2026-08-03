library members;

class Widget {
  Widget();
  Widget.named();

  int first = makeValue(), second = makeValue();

  operator +(Widget other) => this;
  operator [](int index) => this;
  operator []=(int index, Widget value) {}
  operator ~() => this;
  set title(String value) {}
  factory Widget.make(int value) => Widget();
  void greet(String message) {}
  T convert<T>(T value) => value;
}

int makeValue() => 1;
