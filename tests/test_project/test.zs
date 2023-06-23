module Test {
    class Foo {
        class Bar < Foo  { fun Bar(this) {} }

        fun Foo(this: Foo): Foo { return this; }

        var x: Foo;

        fun foo(this: Foo): Foo {
            return foo(this);
            return Goo();
            return Baz();
            return Foo();
            return Bar();
        }
    }

    class Baz < Goo {
        fun Baz(this) {}
    }

    class Goo < Foo {
        fun Goo(this) { return this; }
    }

    fun foo(goo: Goo): Foo {}
}
