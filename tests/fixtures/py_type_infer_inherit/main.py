from child import Child


# c = Child() ; c.greet()  ->  inference (c est Child) COMPOSEE avec l'heritage :
# greet() n'est PAS dans Child, la resolution remonte a Base (autre fichier) via
# _resolve_method. Prouve que l'inference ne se limite pas au fichier de la classe.
def run():
    c = Child()
    return c.greet()
