library constructor_calls;

class Foo {
  Foo();
  Foo.named(int value);
}

int bar() => 1;

void run() {
  new Foo(bar());
  const Foo.named(bar());
}
