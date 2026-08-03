# GARDE-FOU de la regle : une METHODE homonyme ne capte pas un appel direct. `solo()`
# appele hors de la classe ne peut pas designer Widget.solo (il faudrait self.solo()) ->
# le repli fan-out d'avant reste en place, y compris son arete vers gamma.py::solo
# (bruit preexistant, fige ici pour qu'une regression le rende visible).
class Widget:
    def solo(self):
        return 5


def call_solo():
    return solo()
