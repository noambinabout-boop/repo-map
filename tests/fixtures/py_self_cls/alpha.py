# Fixture self/cls (Python) — cf. journal "piste #3 session 1".
# Intention verifiee par expected.json :
#   - self.parse() -> alpha.py::parse  (bien que 'parse' soit un nom JS ubiquitaire :
#     le filtre ALL_BUILTINS est saute pour un recepteur self/cls)
#   - self.list()  -> alpha.py::list   (bien que 'list' soit un builtin Python)
#   - cls.parse()  -> alpha.py::parse  (le recepteur 'cls' est traite comme 'self')
# 'helper' existe ici ET dans beta.py : c'est le piege anti-fan-out (voir beta.py).
class Alpha:
    def run(self):
        xs = [self.parse() for _ in range(2)]   # comprehension + self.parse()
        return self.list(), xs                    # self.list() : collision avec le builtin

    @classmethod
    def make(cls):
        return cls.parse(None)                    # recepteur 'cls' -> Alpha.parse

    def parse(self):
        return 1

    def list(self):
        return 2

    def helper(self):     # homonyme de Beta.helper (autre fichier) : ne doit PAS
        return 9          # recevoir l'arete emise par Beta.go()
