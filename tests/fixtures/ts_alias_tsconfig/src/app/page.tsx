// Fixture alias tsconfig (03/08). Sans la lecture de `compilerOptions.paths`, un
// import `@/...` n'est pas resolu : l'appel retombe sur la resolution par nom et
// se repand vers l'homonyme de src/legacy/db.ts. C'est la norme sur Next/Vite, donc
// c'est le cas majoritaire sur un vrai projet, pas un cas exotique.
import { save } from "@/lib/db";
import { settings } from "@config";

export function Page() {
  save();                  // -> src/lib/db.ts::save SEULEMENT (pas src/legacy/db.ts)
  return settings();       // -> src/config.ts::settings (motif d'alias SANS etoile)
}
