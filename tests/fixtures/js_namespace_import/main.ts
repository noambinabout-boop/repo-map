import * as ns from './mod';

// ns.foo()  ->  ns lie le MODULE mod.ts (import * as ns) : resout vers mod.ts::foo
// SEULEMENT (pas de fan-out vers other.ts::foo).
export function run() {
  return ns.foo();
}
