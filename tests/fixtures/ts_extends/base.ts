// Fixture heritage TS via extends — cf. journal "piste #3 session 4".
// 'shared' n'est defini que dans la classe mere, dans un autre fichier.
export class Base {
  shared() {
    return 1;
  }
}
