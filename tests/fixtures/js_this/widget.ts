// Widget.parse est un homonyme de Service.parse. Il ne doit recevoir AUCUNE arete
// depuis Service.run() : la resolution par scope reste dans le fichier de la classe.
export class Widget {
  parse() {
    return 2;
  }
}
