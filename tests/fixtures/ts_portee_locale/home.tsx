export function HomeScreen() {
  useEffect(() => {
    async function loadPatients(): Promise<void> {
      await fetch("/api/patients?recent=1");
    }
    void loadPatients();          // -> home.tsx::loadPatients SEULEMENT
  }, []);
  return null;
}
