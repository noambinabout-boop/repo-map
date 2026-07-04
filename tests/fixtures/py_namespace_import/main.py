import mymod as m
import plain


# m.foo()     ->  'import mymod as m' lie le module mymod : resout vers mymod.py::foo
# plain.bar() ->  'import plain'       lie le module plain : resout vers plain.py::bar
# (aucun fan-out vers other.py::foo / other.py::bar).
def run():
    return m.foo() + plain.bar()
