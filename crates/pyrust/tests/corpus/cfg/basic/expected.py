from __future__ import annotations

def marker():
    print("debug")

marker()
if True:
    print("if-debug")
else:
    print("if-release")
banner = "[debug-stmt]"
print(banner)
