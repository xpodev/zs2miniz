fun foo(a, b, c, { d, e, f }, *args, **kwargs: string) {

}


foo(1, 2, 3, d: 4, f: 3, e: "hello", 1, 2, 3, 4, 5, 6, 7, foo: "foo", bar: "bar", baz: "baz");
