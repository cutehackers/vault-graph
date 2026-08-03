library members;

class Widget {
  Widget();
  Widget.named();

  int first = makeValue(), second = makeValue();

  operator +(Widget other) => this;
}

int makeValue() => 1;
