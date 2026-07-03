import { foo } from './mod';
import { parse } from './mod';
import { foo as bar } from './other';

// use() appelle trois noms importes :
//   - foo()   -> mod.ts::foo    (desambiguise : pas other.ts::foo)
//   - parse() -> mod.ts::parse  (le nom importe contourne le filtre builtin)
//   - bar()   -> other.ts::foo  (alias 'foo as bar' ; noeud = nom d'ORIGINE 'foo')
function use() {
  return foo() + parse() + bar();
}
