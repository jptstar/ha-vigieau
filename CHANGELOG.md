# Changelog

## Non publié

- Amélioration de la lisibilité des entités d’usage dans Home Assistant.
- Remplacement des états contenant le texte officiel complet par un état court ;
  le message intégral reste disponible dans l’attribut `description`.
- Ajout de préfixes explicites aux noms : `Message`, `Restriction` et
  `Interdit maintenant`.

## 0.2.0 - 2026-08-10

- Passage à la licence GNU GPL v3.0 ou ultérieure (`GPL-3.0-or-later`).
- Copyright attribué à Jean-Philippe TESTART (jptstar).
- Nouvelle identité visuelle originale et indépendante pour HACS.
- Mise à jour de toutes les URLs après le renommage du dépôt en
  `jptstar/vigieau-france-ha`.
- Les versions antérieures restent disponibles sous leur licence MIT d’origine.

## 0.1.1

- Intégration Home Assistant complète avec configuration graphique.
- Sélection AEP, SUP et SOU et profils VigiEau.
- Restitution des messages officiels par usage sans réécriture.
- Capteurs binaires conservateurs `Restriction` et `Interdit maintenant`.
- Gestion séparée du cas « Arrosage des pelouses interdit / autres usages 8h–20h ».
- Audit géographique national par codes INSEE et codes postaux.
- Gestion explicite des communes multi-zones (`HTTP 409`).
- Workflows Tests, HACS et Hassfest.

## 0.1.0 - 2026-08-10

- Première base de développement publique.
