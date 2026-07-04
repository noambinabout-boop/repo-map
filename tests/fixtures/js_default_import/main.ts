import M from './modal';
import b from './builder';

// import default sous un nom local DIFFERENT du symbole exporte :
//   - const x = new M() ; x.draw()  ->  M = default de modal.ts = class Modal ->
//     inference de type + resolution du default -> modal.ts::draw (pas deco.ts::draw).
//   - b()  ->  b = default de builder.ts = function build -> builder.ts::build.
export function run() {
  const x = new M();
  x.draw();
  return b();
}
