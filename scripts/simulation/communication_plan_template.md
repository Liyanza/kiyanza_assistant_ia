# Méthodologie de génération du plan marketing et de communication

Ce document définit la structure que doit suivre l'IA pour rédiger le plan
marketing et de communication d'une campagne (Kiyanza — cahier des charges
IA, section 4.3). Il est utilisé comme guide dans le prompt envoyé au LLM.

Modifiable sans toucher au code Python — si la structure attendue évolue
(nouvelle section, ordre différent), ajuster ce fichier suffit.

## Sections obligatoires, dans cet ordre

1. **Stratégie marketing proposée**
   Une à deux phrases résumant l'approche générale adoptée pour cette
   campagne, cohérente avec l'objectif déclaré (ex. notoriété, ventes,
   génération de leads) et le secteur d'activité.

2. **Plan de communication**
   Les messages clés à transmettre à la cible, adaptés au format créatif et
   au type de contenu choisis. Doit rester concret (pas de généralités du
   type "communiquer efficacement").

3. **Canaux de communication recommandés**
   Le canal principal simulé, plus 1 à 2 canaux complémentaires à faible
   coût pertinents pour une petite structure sur un marché émergent (ex.
   bouche-à-oreille, affichage local, WhatsApp, flyers) — jamais des canaux
   nécessitant un budget ou une expertise hors de portée d'une PME.

4. **Calendrier d'actions avant / pendant / après la campagne**
   - Avant : préparation des créations, ciblage, tests éventuels
   - Pendant : rythme de publication, suivi des premiers résultats
   - Après : bilan, remerciements clients, exploitation des retombées
   Adapter le nombre d'étapes à la durée réelle de la campagne (une
   campagne de 7 jours n'a pas le même calendrier qu'une campagne de
   60 jours).

## Règles de gestion à respecter (cahier des charges §4.3 et §6.5)

- La proposition doit être adaptée au budget déclaré : ne jamais recommander
  une action dont le coût dépasserait manifestement le budget total de la
  campagne.
- Rester réaliste pour une petite structure sans équipe marketing dédiée :
  pas d'actions demandant des compétences ou des outils spécialisés.
- Tenir compte des réalités des marchés en développement (connectivité
  variable, budgets limités) — privilégier des actions simples à exécuter.
- Toujours en français clair, sans jargon marketing non expliqué.
- Ne jamais inventer de partenariat, d'outil ou de fonctionnalité qui
  n'existe pas.

## Ton et longueur

Chaleureux mais professionnel, comme un consultant marketing qui s'adresse
à un entrepreneur non spécialiste. 250 à 350 mots maximum au total.
