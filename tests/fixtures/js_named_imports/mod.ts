// Fixture imports nommes JS/TS — cf. journal "piste #3 session 6".
export function foo() {   // homonyme de other.ts::foo -> desambiguise par l'import
  return 1;
}

export function parse() { // nom homonyme d'un builtin : un appel direct serait filtre
  return 2;               // sans le binding d'import
}
