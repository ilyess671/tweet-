# Code de GTA VI — montage automatique

Chaque vidéo est montée automatiquement à partir de 3 choses que tu envoies à Claude.

## Ce que tu envoies à chaque fois

1. **L'extrait de gameplay** (la vidéo brute).
2. **La voix off en MP3**, générée sur ElevenLabs avec Victoria (modèle Eleven v3).
3. **Un message comme celui-ci :**

```
Vidéo 2
Titre gameplay : Braquage à l'épicerie
Pause à : 8 s
Réponse visible à : 10,2 s        (facultatif)
La suite reprend à : 22 s         (facultatif, sinon elle reprend à la pause)
Situation : Jason tente un braquage discret à l'épicerie
Surligner : braquage discret      (facultatif)
A : La police attend Jason à la sortie
B : Il se fait désarmer par une gonzesse ✅
C : Le braquage se passe sans souci
Script : (le texte de la voix)
```

Si tu n'as qu'une idée en vrac, envoie-la : Claude écrit le script drôle avec les intonations,
tu le valides, tu génères la voix sur ElevenLabs et tu l'envoies.

## Règles pour le script de la voix

Pour que tout se cale tout seul, la voix doit dire, dans cet ordre :
- « Dans cette situation… »
- la situation, avec les mêmes mots qu'à l'écran
- « A : … », « B : … », « C : … »
- « À toi de jouer… t'as cinq secondes »
- « Regarde bien… »
- « Réponse B ! » (avec la bonne lettre)
- « Et toi, t'avais trouvé ? Abonne-toi pour la prochaine situation ! »

Génère tout le script d'un coup, dans un seul fichier, sans musique.

## Ce que tu peux demander

- « Fais les vidéos 12 à 15 » : les vidéos déjà montées sont sautées.
- « Refais la 7 » : remontage forcé.
- « Sur la 7, à 37 s le son de victoire est trop fort » : correction précise, seule cette vidéo est refaite.

## Dossiers

- `situations.yaml` : un bloc par vidéo (textes, seconde de pause, réglages).
- `moteur/` : le programme de montage.
- `assets/logo.png` : ton logo.
- `entrees/` et `sorties/` : les vidéos (pas sauvegardées sur GitHub, garde tes copies).
