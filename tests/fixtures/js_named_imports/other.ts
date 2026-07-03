export function foo() {   // homonyme de mod.ts::foo. consumer y accede via l'alias
  return 3;               // `import { foo as bar } from './other'`
}
