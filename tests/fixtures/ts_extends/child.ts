import { Base } from './base';

// Child.run() appelle this.shared() : la resolution doit suivre la clause `extends Base`
// et emettre child.ts::run -> base.ts::shared (methode heritee dans un autre fichier).
export class Child extends Base {
  run() {
    return this.shared();
  }
}
