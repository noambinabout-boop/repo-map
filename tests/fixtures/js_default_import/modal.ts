// export default d'une CLASSE dont le nom (Modal) differe du nom local a l'import (M) :
// c'est ce qui prouve que la resolution suit le default export, pas un simple match de nom.
export default class Modal {
  draw() {
    return 1;
  }
}
