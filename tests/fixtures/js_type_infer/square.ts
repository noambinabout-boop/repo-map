// Homonyme volontaire : Square.area existe pour prouver que le fan-out par nom
// (comportement AVANT inference) creerait une arete parasite render->square.ts::area,
// et que l'inference de type l'elimine (const c = new Circle() => c.area() ne vise que circle.ts::area).
export class Square {
  area() {
    return 4.0;
  }
}
