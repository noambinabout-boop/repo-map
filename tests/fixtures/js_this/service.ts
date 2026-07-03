// Fixture this.foo() (TS) — cf. journal "piste #3 session 2".
// this.parse() doit resoudre vers service.ts::parse (recepteur 'this' = classe
// englobante), sans etre exclu comme faux builtin et sans fan-out vers widget.ts::parse.
export class Service {
  run() {
    return this.parse();
  }

  parse() {
    return 1;
  }
}
