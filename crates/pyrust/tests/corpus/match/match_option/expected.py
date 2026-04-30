def describe(opt):
    match opt:
        case None:
            return "nothing"
        case 0:
            return "zero"
        case _:
            return "non-zero"

print(describe(0))
print(describe(7))
print(describe(None))
