// Homonyme volontaire : Panel.draw(). Sans resolution du default, `const x = new M()`
// ne typerait pas x (M != nom de classe connu) et x.draw() ferait un fan-out qui
// toucherait CE draw() aussi. La resolution du default limite a modal.ts::draw.
export class Panel {
  draw() {
    return 3;
  }
}
