# Couverture de l'interprétation — VigiEau France v0.1.1

Corpus : export officiel VigiEau du 8 août 2026, 2 882 descriptions distinctes.

## Résultat

- `conditional` : 1 608
- `unknown` : 917
- `advisory` : 159
- `time_ban` : 131
- `total_ban` : 56
- `no_restriction` : 9
- `mixed` : 2

À 12:00, sur les 2 882 descriptions uniques :

- `True` (interdit avec certitude) : 167
- `False` (non interdit avec certitude) : 188
- `None` / `unknown` (pas de conclusion sûre) : 2 527

Cette faible proportion d'états binaires déterministes est volontaire : le message officiel reste la référence et les formulations conditionnelles, mixtes ou non reconnues ne sont jamais assimilées à une autorisation.

## Cas de validation Alsace

Le corpus contient le message :

> Arrosage des pelouses interdit. Interdiction horaire de 8h à 20h pour les autres usages.

L'interpréteur le scinde en deux règles :

- `Arrosage des pelouses` : interdiction permanente ;
- `Autres usages` : interdiction quotidienne de 08:00 à 20:00.

Le capteur binaire global de la carte reste indéterminé pour « interdit maintenant », car la carte contient deux sous-règles différentes. Les deux sous-règles disposent chacune de leur propre capteur binaire déterministe.
