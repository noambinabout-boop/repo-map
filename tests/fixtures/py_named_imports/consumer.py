from mod import parse, helper as h


# use() appelle deux noms explicitement importes depuis mod :
#   - parse() -> mod.py::parse   (le nom importe contourne le filtre builtin)
#   - h()     -> mod.py::helper  (alias 'helper as h' ; PAS de fan-out vers other.py::helper)
def use():
    return parse() + h()
