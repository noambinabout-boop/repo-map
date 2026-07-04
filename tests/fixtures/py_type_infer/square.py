# Homonyme volontaire : Square.area existe pour prouver que le fan-out par nom
# (comportement AVANT inference) cree une arete parasite main->square.py::area,
# et que l'inference de type l'elimine (c = Circle() => c.area() ne vise que circle.py::area).
class Square:
    def area(self):
        return 4.0
