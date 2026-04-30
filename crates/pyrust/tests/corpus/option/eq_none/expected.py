a: int | None = 3
b: int | None = None
if a is None:
    print("a is none")
else:
    print("a is some")
if b is not None:
    print("b is some")
else:
    print("b is none")
