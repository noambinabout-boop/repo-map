def main():
    return 3


def inner():               # homonyme de la closure d'alpha.py, jamais atteignable d'ici
    return 4


def run():
    return main()          # -> beta.py::main SEULEMENT (pas alpha.py::main)
