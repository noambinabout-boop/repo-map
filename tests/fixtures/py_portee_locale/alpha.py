# Fixture portee locale (correctif homonymes, session du 03/08). alpha et beta definissent
# CHACUN leur `main()` : l'appel local ne doit pas se repandre vers l'homonyme du voisin.
def main():
    return 1


def run():
    return main()          # -> alpha.py::main SEULEMENT (pas beta.py::main)


def outer():
    def inner():           # homonyme de beta.py::inner, qui lui est au niveau module
        return 2
    return inner()         # -> alpha.py::inner : closure visible depuis la ligne d'appel
