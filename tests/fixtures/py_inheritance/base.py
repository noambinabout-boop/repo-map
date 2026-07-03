# Fixture heritage Python — cf. journal "piste #3 session 3".
# 'shared' est defini SEULEMENT dans la classe mere, dans un AUTRE fichier.
class Base:
    def shared(self):
        return 1
