import { hello } from "test2.zs";
import { a, A } from hello();
import { Void, Boolean as bool } from hello("module:core");


module Test {
    class Foo {
        class Bar < Foo  { fun new(this: Bar): Bar { return this.x; } }

        fun new(this: Foo): Foo { return this; }

        fun new(this, x): hello(Void) {}

        var x: Foo;

        fun foo(this: Foo, {other: Bar}): bool { return true; }

        fun foo(this: Foo, other: Bar, other2: Foo): bool {
            //return foo(this);
            return foo(this, other: Bar());
            /*return Goo();
            return Baz();
            return Foo();
            return Bar();*/
        }
    }

    class Baz < Goo {
        fun new(this) { return this; }
    }

    class Goo < Foo {
        fun new(this): A.blah(bool) { return true; }
    }

    fun foo(goo: Foo.Bar): Void { }

    import { Type as type } from "module:core";

    //fun generic(value: T, { T: type } ): T;
}
