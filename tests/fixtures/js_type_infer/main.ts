import { Circle } from './circle';

// const c = new Circle() ; c.area()  ->  inference de type : c est de type Circle,
// donc c.area() resout vers circle.ts::area SEULEMENT (pas square.ts::area).
// NB : `new Circle()` n'est pas un call_expression -> aucune arete vers le constructeur
// (comportement existant du moteur), d'ou la seule arete attendue = l'appel de methode.
export function render() {
  const c = new Circle();
  return c.area();
}
