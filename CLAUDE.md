# Code de GTA VI — mode d'emploi pour Claude

Chaîne de vidéos courtes (YouTube Shorts / TikTok, 9:16) au format « code de la route » sur des
extraits de gameplay GTA VI de l'utilisateur. Le style est **validé** : ne pas le changer sans demande.

## Ce que l'utilisateur envoie pour chaque vidéo
1. l'extrait de gameplay (.mov / .mp4) ;
2. la voix off en MP3, générée **par lui** sur le site ElevenLabs (voix Victoria) ;
3. le texte : titre du gameplay, seconde de pause, situation, réponses A/B/C, bonne réponse,
   éventuellement la seconde où la réponse se voit dans l'extrait, et le script de la voix.

## Marche à suivre
1. Copier les fichiers reçus dans `entrees/` sous les noms `video-NN.<ext>` et `voix-NN.mp3`
   (NN = numéro de la vidéo, sur 2 chiffres).
2. Corriger l'orthographe de ses textes **sans changer son ton ni son argot** (il a choisi de garder
   « gonzesse », par exemple). Garder les textes courts pour qu'ils se lisent à l'écran.
3. Ajouter un bloc dans `situations.yaml` (copier le modèle de la vidéo 1). Toujours regarder
   l'extrait (planche d'images + sous-titres du jeu) pour vérifier la bonne réponse et le moment où elle
   se voit (`revelation_a`). Si la réponse arrive longtemps après la pause, utiliser `suite_depuis`
   pour que « la suite » reprenne juste avant (sinon la suite est trop longue). Si l'extrait est
   trop court pour couvrir la voix de la révélation (~10 s), mettre `suite_ralenti: 0.5`.
4. `python3 moteur/build.py NN --reperes` : vérifier que tous les repères de la voix sont trouvés.
5. `python3 moteur/build.py NN --apercu` : regarder `sorties/apercus/apercu-NN.png` (8 images clés).
6. `python3 moteur/build.py NN` (≈ 6 min pour 50 s ; lancer en arrière-plan pour plusieurs vidéos).
   Une plage : `python3 moteur/build.py 12-15` saute celles déjà dans `sorties/`. `--force` pour refaire.
7. Envoyer `sorties/code-gta-vi-NN.mp4` avec SendUserFile.

Si l'utilisateur donne seulement une idée en vrac, écrire le script drôle et absurde avec des
intonations ElevenLabs v3 entre crochets (`[mysterious]`, `[whispers]`, `[laughs]`, `[sarcastic]`,
`[excited]`, `[warm]`…) et le faire valider avant qu'il génère la voix.

## Réponses en image
Une réponse peut être une image (mème…) : `B: {image: reponse-NN-B.jpg}` (fichier dans `entrees/`,
légende facultative avec `texte:`). Les réponses texte gardent la ligne classique (en haut) et les
réponses image s'affichent en tuiles côte à côte dessous. La voix doit quand même dire la lettre
(« B : … ») ; l'utilisateur peut mettre un son de mème à la place de la description.
Plusieurs bonnes réponses : `bonne_reponse: B, C` (toutes passent au vert, titre « Réponse B et C ! »).

## Le script de la voix doit contenir (le moteur s'y cale automatiquement)
- « Dans cette situation… » au début (→ la pause/flash) ;
- la situation, mot pour mot comme le champ `situation` (→ les mots du titre pop dessus) ;
- « A : … », « B : … », « C : … » (lettres lues seules, → chaque réponse pop) ;
- « À toi de jouer … cinq secondes » puis **« Regarde bien »** (→ timer de 6 étoiles entre les deux) ;
- **« Réponse X »** (→ révélation) ; puis **« Et toi, t'avais trouvé ? Abonne-toi… »** (→ fin, clic).
Si un repère n'est pas trouvé, le forcer dans le bloc : `ajustements: {reperes: {regarde: 24.86}}`
(temps en secondes dans le fichier voix ; clés : debut, situation, A, B, C, C_fin, jouer,
fin_question, regarde, reponse, avant_outro, outro, abonne, surlignage).

## Blancs dans la voix
Si la voix enchaîne trop vite (ex. « B, C » d'affilée), insérer des blancs :
`ajustements: {silences: [[11.30, 1.8], [12.06, 1.8]]}` = [temps dans la voix d'origine, durée].
Tous les repères après un blanc sont décalés automatiquement (les repères forcés restent en temps d'origine).

## Sons de mème
`sons: [[11.12, vine_boom], [11.86, vine_boom]]` dans le bloc = [temps dans la voix d'origine, son].
`vine_boom` est recréé par programme (libre de droits, pas l'original) ; un fichier de `entrees/`
(ex. `bruh-05.mp3`) marche aussi. Volume : `volume_memes_db` dans le bloc.

## Corrections précises (« à 45,2 s le pop est trop grand »)
- Repérer l'élément avec `.cache/NN/config.json` (clé `T` = moments clés en secondes de la vidéo finale).
- Changement de **minutage d'une seule vidéo** : `ajustements: {decalages: {reveal: 0.3}}`
  (ajoute des secondes à une clé de T), puis `build.py NN --force`.
- Volumes d'une seule vidéo : mettre `volume_jeu_db`, `volume_suite_db`, `volume_voix_db`,
  `volume_bruitages_db` directement dans son bloc.
- Changement de **style** (taille, couleur, animation) : `moteur/template.html` → touche toutes les
  vidéos ; ne refaire que celles que l'utilisateur demande.
- Bruitages : `moteur/sfx.py` (sons synthétisés, libres de droits) et `evenements()` dans `build.py`.

## Le moteur
- `moteur/build.py` : transcription mot à mot de la voix (API ElevenLabs speech-to-text), repères,
  minutage, extraction du gameplay, bruitages, mixage (voix, bruitages, son du jeu baissé sous la voix,
  normalisation -14 LUFS).
- `moteur/template.html` : l'animation (une page web rendue image par image, 1080×1920, 30 i/s).
- `moteur/render.js` : rendu Playwright → `.cache/NN/video_muette.mp4`.
- `assets/logo.png` : logo GILY (rond au-dessus du bouton S'abonner).
- `entrees/`, `sorties/`, `.cache/` ne sont pas versionnés (fichiers lourds).

## ElevenLabs
- La clé est un secret réseau de l'environnement cloud « tweet- » pour `api.elevenlabs.io` : le proxy
  l'injecte. Envoyer `xi-api-key: proxy-injected`. Ne jamais demander la clé dans le chat.
- Offre gratuite : la synthèse avec les voix de la bibliothèque (Victoria…) est refusée par l'API,
  d'où les MP3 générés par l'utilisateur sur le site. La transcription (speech-to-text) fonctionne.
- L'offre gratuite n'autorise pas l'usage commercial : le rappeler si la chaîne est monétisée.

## Style validé (ne pas changer sans demande)
Fond pastel (rose, lilas, menthe) qui bouge lentement ; titre en haut qui change en flou mot à mot ;
gameplay en carte horizontale qui remonte à la pause ; situation dans une carte juste dessous qui
devient la carte quiz (réponses en verre type iOS) ; étiquette sur le gameplay (titre, « ❚❚ Pause »,
6 étoiles qui se remplissent avec tic-tac, « ▶ La suite ») ; après le timer la suite de l'extrait
joue et la bonne réponse passe en vert ; fin : logo rond GILY + bouton « S'abonner » cliqué.
Pas de sous-titres. Pas de musique (ajoutée à la publication si besoin).

## Plus tard
Publication automatique YouTube (puis TikTok).
