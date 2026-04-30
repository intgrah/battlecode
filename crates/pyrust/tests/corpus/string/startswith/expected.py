s = "hello, world"
if s.startswith("hello"):
    print("hi-prefix")
if s.endswith("world"):
    print("world-suffix")
if not s.startswith("xyz"):
    print("no xyz")
