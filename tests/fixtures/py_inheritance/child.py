from base import Base


# Child.run() appelle self.shared() : 'shared' n'existe pas dans Child, la resolution
# doit REMONTER l'heritage jusqu'a Base et emettre child.py::run -> base.py::shared
# (methode heritee vivant dans un autre fichier).
class Child(Base):
    def run(self):
        return self.shared()
