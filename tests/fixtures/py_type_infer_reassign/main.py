from alpha import Alpha
from beta import Beta


# x reaffecte a DEUX types differents dans le meme scope -> type AMBIGU : on n'infere PAS,
# on retombe sur le fan-out par nom (invariant "jamais d'arete perdue"). x.act() vise donc
# les DEUX methodes act (alpha + beta). Grave la decision de conception : prudence anti-perte.
def run():
    x = Alpha()
    x = Beta()
    return x.act()
