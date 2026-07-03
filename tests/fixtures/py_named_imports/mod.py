# Fixture imports nommes Python — cf. journal "piste #3 session 5".
def parse():   # nom homonyme d'un builtin JS ubiquitaire : un appel direct parse()
    return 1   # serait exclu par le filtre SANS le binding d'import


def helper():  # homonyme de other.py::helper -> teste la desambiguisation par import
    return 2
