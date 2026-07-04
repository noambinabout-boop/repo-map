# Homonymes volontaires : other.py::foo et other.py::bar. Sans resolution des imports
# de module, m.foo() / plain.bar() feraient un fan-out par nom vers CEUX-ci aussi.
def foo():
    return 2


def bar():
    return 2
