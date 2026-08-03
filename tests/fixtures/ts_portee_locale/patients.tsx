// Fixture portee locale, decalquee du cas REEL de denta-scribe (03/08) : deux ecrans
// definissent chacun leur `loadPatients` dans un effet. Sans le correctif, l'appel de l'un
// pointait AUSSI la definition de l'autre -> faux lien entre deux parties de l'app qui
// n'ont rien a voir, et une fiche qui ment.
export function PatientsScreen() {
  useEffect(() => {
    async function loadPatients(): Promise<void> {
      await fetch("/api/patients");
    }
    void loadPatients();          // -> patients.tsx::loadPatients SEULEMENT
  }, []);
  return null;
}
