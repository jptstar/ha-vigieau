# VigiEau France for Home Assistant

<div align="center">
  <img src="https://raw.githubusercontent.com/jptstar/vigieau-france-ha/main/brand/logo%402x.png" width="180" alt="Logo indépendant VigiEau France">
</div>

**Auteur : Jean-Philippe TESTART ([jptstar](https://github.com/jptstar))**

VigiEau France est une intégration Home Assistant **non officielle et indépendante** utilisant l’API publique officielle VigiEau.

Son objectif est de restituer dans Home Assistant, pour une même localisation, une même provenance d’eau et un même profil, les mêmes informations réglementaires et la même logique de sélection que le site **vigieau.gouv.fr**. Le texte officiel des restrictions reste toujours la donnée de référence.

> Ce projet n’est ni affilié ni approuvé par l’État français. L’arrêté préfectoral ou municipal applicable reste le texte juridiquement opposable.

## Support et maintenance

VigiEau France est une intégration Home Assistant que j’ai initialement
développée par plaisir et pour mon usage personnel.

Les retours précis et les diagnostics Home Assistant peuvent m’aider à améliorer
la compatibilité avec certaines configurations et à corriger les bugs. Je suis
disposé à consacrer du temps à ces améliorations lorsque cela m’est possible.
Toutefois, VigiEau France reste un projet personnel réalisé sur mon temps libre
et non mon activité principale. Les réponses, analyses et correctifs peuvent
donc parfois prendre du temps.

L’intégration masque l’adresse et les coordonnées précises dans ses diagnostics.
Par précaution, vérifiez néanmoins leur contenu avant de les publier dans une
issue GitHub.

## Principes

- recherche d’adresse via le service public français d’adresses ;
- choix entre une adresse, les coordonnées de Home Assistant, un code postal ou
  un point sélectionné sur la carte ;
- géocodage direct et inverse via le service public Géoplateforme ;
- appel VigiEau avec code INSEE et coordonnées précises lorsque nécessaire ;
- récupération de toutes les zones applicables, sans imposer `profil` ou `zoneType` dans l’appel principal ;
- sources d’eau `AEP`, `SUP` et `SOU` ;
- profils particulier, professionnel, collectivité et exploitation agricole ;
- sélection explicite lorsqu’il existe plusieurs zones d’un même type d’eau ;
- affichage de toutes les cartes d’usage applicables au profil sélectionné ;
- conservation intégrale de `nom`, `thematique` et `description` fournis par VigiEau ;
- arrêtés et dates exposés lorsqu’ils sont fournis par l’API ;
- aucune absence de donnée n’est transformée en autorisation.

## Entités Home Assistant

Chaque localisation crée notamment des capteurs :

- Situation
- Zone
- Type d’eau
- Profil
- Arrêté en vigueur
- Dernière actualisation
- un capteur par usage/restriction affiché par VigiEau

Home Assistant les répartit sur deux appareils liés : l’appareil principal regroupe les capteurs d’information et les messages officiels ; l’appareil enfant **Restrictions VigiEau** regroupe uniquement les capteurs binaires `Restriction` et `Interdit maintenant`. Les deux listes restent ainsi séparées dans l’interface. La situation, la zone, le type d’eau, le profil, l’arrêté en vigueur et la dernière actualisation sont rangés dans la catégorie **Diagnostic**.

Pour conserver une liste lisible, les capteurs de message affichent l’état court `Ouvrir pour lire` lorsqu’un texte officiel existe, ou `Aucun message` dans le cas contraire. Ouvrez l’entité pour consulter le texte officiel intégral dans l’attribut `description`, quelle que soit sa longueur. Le nom de l’usage apparaît en premier : `Nom - Message`, `Nom - Restriction` et `Nom - Interdit maintenant`. Une icône adaptée identifie immédiatement le type d’usage, par exemple potager, pelouse, golf, véhicule, fontaine, piscine ou terrain de sport.

## Capteurs binaires

Chaque usage reçoit deux capteurs binaires complémentaires :

- **Restriction** : `ON` seulement lorsqu’une restriction est explicitement identifiable ;
- **Interdit maintenant** : `ON` ou `OFF` seulement lorsque la formulation permet une conclusion déterministe à l’heure locale ; sinon l’état reste `unknown`.

Les règles d’un même message ne sont jamais fusionnées entre usages. Par exemple :

> Arrosage des pelouses interdit. Interdiction horaire de 8h à 20h pour les autres usages.

est interprété en deux sous-règles distinctes : pelouse interdite en permanence et autres usages interdits de 08:00 à 20:00. Le message officiel reste affiché intégralement quelle que soit l’interprétation binaire.

## Installation HACS

### Ajout direct

[![Ajouter VigiEau France à HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jptstar&repository=vigieau-france-ha&category=integration)

Cliquez sur le bouton, ouvrez votre instance Home Assistant, puis confirmez l’ajout du dépôt dans HACS.

### Ajout manuel dans HACS

1. Dans HACS, ouvrez **Intégrations**.
2. Ouvrez le menu `⋮`, puis sélectionnez **Dépôts personnalisés**.
3. Ajoutez `https://github.com/jptstar/vigieau-france-ha`.
4. Sélectionnez le type **Integration**, puis confirmez avec **Ajouter**.
5. Recherchez **VigiEau France** dans HACS et ouvrez sa fiche.
6. Sélectionnez **Télécharger**, puis confirmez la version proposée.
7. Redémarrez Home Assistant.
8. Ouvrez **Paramètres → Appareils et services → Ajouter une intégration**, puis recherchez **VigiEau France**.

Le domaine Home Assistant est `vigieau_france`.

Un redémarrage est nécessaire après l’installation ou la mise à jour du code de
l’intégration. Une modification du README ou de ses images ne nécessite pas de
redémarrage de Home Assistant.

## Audit national

Le dépôt contient `tools/audit_geography.py` et le workflow **National VigiEau audit**. Il parcourt la liste officielle des communes françaises, leurs codes INSEE et codes postaux, interroge l’API VigiEau et signale notamment :

- les communes nécessitant une localisation précise (`HTTP 409`) ;
- les types d’eau et zones observés ;
- les erreurs de résolution ;
- les messages rencontrés par l’API ;
- la couverture géographique par code postal.

Le corpus national de messages est traité comme une donnée d’audit, pas comme une table métier figée utilisée pour décider de la réglementation. Une nouvelle formulation VigiEau reste affichable même si elle n’est pas encore interprétable par un capteur binaire.

## Développement

```bash
python -m pip install pytest
pytest -q
```

GitHub Actions exécute également HACS validation et Hassfest.

## Sources fonctionnelles

- VigiEau : `https://vigieau.gouv.fr`
- API publique : `https://api.vigieau.gouv.fr/api`
- Documentation API : dépôt public `MTES-MCT/vigieau-api`
- Géocodage public : `https://data.geopf.fr/geocodage`
- Communes et codes postaux : `https://geo.api.gouv.fr/communes`

## Licence

Copyright © 2026 Jean-Philippe TESTART (jptstar).

Ce projet est distribué sous la licence **GNU General Public License v3.0 ou
ultérieure** (`GPL-3.0-or-later`). Les versions modifiées ou redistribuées
doivent respecter les conditions de cette licence et conserver les mentions de
copyright et de licence. Consultez le fichier [LICENSE](LICENSE).

La licence couvre uniquement cette intégration indépendante et son code. Elle
ne confère aucun droit sur VigiEau, les marques, logos, données, contenus,
services ou logiciels de l’État français et de leurs détenteurs respectifs.
Ce projet reste non officiel et sans affiliation avec l’administration.

Les versions publiées avant le passage à la GPL restent utilisables selon la
licence MIT sous laquelle elles ont été distribuées. La version 0.2.0 et les
versions ultérieures sont publiées sous `GPL-3.0-or-later`.
