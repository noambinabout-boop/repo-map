from circle import Circle


# c = Circle() ; c.area()  ->  inference de type : c est de type Circle,
# donc c.area() resout vers circle.py::area SEULEMENT (pas square.py::area).
def render():
    c = Circle()
    return c.area()
