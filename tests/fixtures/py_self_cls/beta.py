# Beta.go() appelle self.helper(). 'helper' existe aussi dans alpha.py.
# La resolution par SCOPE doit produire UNE seule arete -> beta.py::helper,
# et surtout PAS de fan-out vers alpha.py::helper (le bug d'avant la piste #3).
class Beta:
    def go(self):
        return self.helper()   # -> beta.py::helper uniquement

    def helper(self):
        return 3
