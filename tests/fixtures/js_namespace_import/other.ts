// Homonyme volontaire : other.ts::foo. Sans resolution du namespace, ns.foo() ferait
// un fan-out par nom vers CE foo aussi. La resolution le limite a mod.ts::foo.
export function foo() {
  return 2;
}
