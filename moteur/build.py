#!/usr/bin/env python3
"""Moteur de montage « Code de GTA VI ».

Usage :
    python3 moteur/build.py 12            # une vidéo
    python3 moteur/build.py 12-15         # une plage (saute celles déjà montées)
    python3 moteur/build.py 3,7,9 --force # refait même si la vidéo existe déjà
    python3 moteur/build.py 12 --apercu   # planche d'images clés seulement (rapide, pour vérifier)
    python3 moteur/build.py 12 --reperes  # affiche juste les repères trouvés dans la voix

Pour chaque vidéo : lit son bloc dans situations.yaml, transcrit la voix (ElevenLabs, mot par mot),
calcule le minutage, extrait le gameplay, rend l'animation, génère les bruitages, mixe, et écrit
sorties/code-gta-vi-NN.mp4.
"""
import json, re, subprocess, sys, unicodedata, shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MOTEUR = ROOT / 'moteur'
ENTREES = ROOT / 'entrees'
SORTIES = ROOT / 'sorties'
CACHE = ROOT / '.cache'
sys.path.insert(0, str(MOTEUR))
import sfx as S  # noqa: E402

FPS = 30
STAR_GAPS = [1.2, 1.1, 1.0, 0.85, 0.7]       # écart entre les 6 étoiles (le tic-tac accélère)
DEFAUTS = {
    'duree_intro': 5.0,       # secondes de gameplay avant la pause
    'volume_jeu_db': 10,      # gain du son du jeu (les extraits sont souvent bas)
    'volume_suite_db': 8,     # gain du son du jeu pendant la suite (baissé auto. sous la voix)
    'volume_voix_db': 2,
    'volume_bruitages_db': -4,
    'revelation_apres': 2.3,  # si revelation_a absent : « Réponse » tombe ~2,3 s après la reprise
}


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        raise RuntimeError(f"Échec : {' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")
    return r.stdout


def norm(w):
    w = unicodedata.normalize('NFD', w.lower())
    w = ''.join(c for c in w if unicodedata.category(c) != 'Mn')
    return re.sub(r"[^a-z0-9']", '', w).replace("'", '')


def duree(path):
    return float(run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)]))


def trouve_fichier(num, prefixes, exts, nom=None):
    if nom:
        p = ENTREES / nom
        if not p.exists():
            raise FileNotFoundError(f'{p} introuvable')
        return p
    for f in sorted(ENTREES.iterdir()):
        stem = f.stem.lower()
        m = re.search(r'(\d+)$', stem)
        if m and int(m.group(1)) == num and any(stem.startswith(p) for p in prefixes) and f.suffix.lower() in exts:
            return f
    raise FileNotFoundError(f"Aucun fichier {prefixes[0]}-{num:02d} ({'/'.join(exts)}) dans {ENTREES}")


# ---------------------------------------------------------------- transcription
def transcrire(voix, work):
    cache = work / 'stt.json'
    if cache.exists() and cache.stat().st_mtime > voix.stat().st_mtime:
        return json.loads(cache.read_text())
    code = run(['curl', '-s', '-o', str(cache), '-w', '%{http_code}', '-X', 'POST',
                'https://api.elevenlabs.io/v1/speech-to-text', '-H', 'xi-api-key: proxy-injected',
                '-F', 'model_id=scribe_v1', '-F', 'language_code=fra', '-F', 'timestamps_granularity=word',
                '-F', 'tag_audio_events=true', '-F', f'file=@{voix}'])
    if code.strip() != '200':
        raise RuntimeError(f'Transcription ElevenLabs refusée (HTTP {code}) : {cache.read_text()[:300]}')
    return json.loads(cache.read_text())


def reperes(stt, v):
    """Trouve dans la voix les moments clés. Renvoie un dict de temps (secondes dans le fichier voix)."""
    W = [w for w in stt['words'] if w.get('type') == 'word' and norm(w['text'])]
    N = [norm(w['text']) for w in W]
    raw = [w['text'].strip(' .,:;!?…') for w in W]
    force = (v.get('ajustements') or {}).get('reperes') or {}

    def find(pred, start=0):
        for i in range(start, len(W)):
            if pred(i):
                return i
        return None

    r = {'debut': W[0]['start'], 'fin': W[-1]['end']}
    i_sit = find(lambda i: 'situation' in N[i])
    if i_sit is None:
        raise RuntimeError('« situation » introuvable dans la voix')
    r['situation'] = W[i_sit]['start']

    # mots du titre, dans l'ordre, juste après « situation »
    toks = [norm(t) for t in v['situation'].split()]
    times, j = [], i_sit + 1
    for t in toks:
        k = find(lambda i: N[i] == t or (len(t) > 3 and (N[i].startswith(t[:4]) or t.startswith(N[i][:4]))), j)
        if k is not None and k - j <= 4:
            times.append(W[k]['start']); j = k + 1
        else:
            times.append(None)
    known = [(i, x) for i, x in enumerate(times) if x is not None]
    if not known:
        raise RuntimeError('Aucun mot du titre retrouvé dans la voix : vérifier le champ « situation »')
    for i, x in enumerate(times):  # interpole les mots non retrouvés
        if x is None:
            prev = max([k for k in known if k[0] < i], default=known[0], key=lambda k: k[0])
            nxt = min([k for k in known if k[0] > i], default=known[-1], key=lambda k: k[0])
            times[i] = prev[1] + (nxt[1] - prev[1]) * ((i - prev[0]) / max(1, nxt[0] - prev[0])) if nxt[0] != prev[0] else prev[1] + 0.3 * (i - prev[0])
    r['titre'] = times
    i_tfin = max(j - 1, i_sit + 1)
    r['titre_fin'] = W[i_tfin]['end']

    # lettres A / B / C lues à voix haute (majuscule seule)
    ia = find(lambda i: raw[i] == 'A', i_tfin + 1)
    ib = find(lambda i: raw[i] == 'B', (ia or i_tfin) + 1)
    ic = find(lambda i: raw[i] == 'C', (ib or i_tfin) + 1)
    if None in (ia, ib, ic):
        raise RuntimeError('Les lettres A, B, C ne sont pas toutes retrouvées dans la voix')
    r['A'], r['B'], r['C'] = W[ia]['start'], W[ib]['start'], W[ic]['start']
    r['avant_A'] = W[ia - 1]['end']
    # fin de la phrase C puis « À toi de jouer… »
    icf = find(lambda i: W[i]['text'].rstrip().endswith(('.', '!', '?')), ic + 1) or ic + 1
    r['C_fin'] = W[icf]['end']
    r['jouer'] = W[min(icf + 1, len(W) - 1)]['start']
    ireg = find(lambda i: N[i] == 'regarde', icf + 1)
    if ireg is None:
        ireg = find(lambda i: 'seconde' in N[i], icf + 1)
        ireg = ireg + 1 if ireg is not None else icf + 2
    r['fin_question'] = W[ireg - 1]['end']
    r['regarde'] = W[ireg]['start']
    irep = find(lambda i: N[i] == 'reponse', ireg)
    r['reponse'] = W[irep]['start'] if irep is not None else W[ireg]['end'] + 1.0
    iout = find(lambda i: N[i] == 'et' and i + 1 < len(W) and N[i + 1] == 'toi', (irep or ireg) + 1)
    if iout is None:
        raise RuntimeError('« Et toi… » (fin) introuvable dans la voix')
    r['outro'] = W[iout]['start']
    r['avant_outro'] = W[iout - 1]['end']
    iab = find(lambda i: N[i].startswith('abonne'), iout)
    r['abonne'] = W[iab]['start'] if iab is not None else W[-1]['start']
    # phrase de commentaire entre le titre et A : le surlignage se déclenche au milieu
    r['surlignage'] = (r['titre_fin'] + r['avant_A']) / 2
    r.update({k: float(x) for k, x in force.items()})
    return r


# ---------------------------------------------------------------- minutage
def minutage(v, R, reg, clip_len):
    pause_a = float(v['pause_a'])
    intro_start = max(0.0, pause_a - reg['duree_intro'])
    pause = pause_a - intro_start
    O1 = pause + 0.05 - R['debut']           # « Dans cette situation » tombe sur la pause
    T = {'pause': pause}
    T['headSit'] = pause - 0.1
    T['move'] = [pause + 0.35, pause + 1.0]
    T['wordT'] = [x + O1 for x in R['titre']]
    T['panelIn'] = min(T['wordT'][0] - 0.35, max(T['move'][1], T['wordT'][0] - 0.35))
    T['hl'] = R['surlignage'] + O1
    a = R['A'] + O1
    T['toQuiz'] = [max(R['titre_fin'] + O1 + 0.2, a - 1.05), 0]
    T['toQuiz'][1] = T['toQuiz'][0] + 0.6
    T['headQuiz'] = T['toQuiz'][0]
    T['rows'] = [R[k] + O1 - 0.08 for k in 'ABC']
    T['rowsEnd'] = R['C_fin'] + O1
    T['headPlay'] = R['jouer'] + O1 - 0.1
    T['pillStars'] = R['fin_question'] + O1 + 0.1
    st = [T['pillStars'] + 0.3]
    for g in STAR_GAPS:
        st.append(st[-1] + g)
    T['stars'] = st
    T['timeUp'] = st[-1] + 0.25
    T['headWatch'] = T['timeUp'] + 0.2
    T['resume'] = T['timeUp'] + 0.4
    # 2e partie de la voix (« Regarde bien… » → fin), calée sur le gameplay si revelation_a est donné
    suite_a = float(v.get('suite_depuis', pause_a))   # la suite peut reprendre plus loin dans l'extrait
    O2 = T['resume'] + 0.1 - R['regarde']
    if v.get('revelation_a') is not None:
        O2 = max(O2, T['resume'] + (float(v['revelation_a']) - suite_a) - R['reponse'])
    else:
        O2 = max(O2, T['resume'] + reg['revelation_apres'] - R['reponse'])
    T['reveal'] = R['reponse'] + O2 - 0.05
    T['outro'] = [R['avant_outro'] + O2 + 0.2, 0]
    T['outro'][1] = T['outro'][0] + 0.6
    T['click'] = R['abonne'] + O2
    dur = R['fin'] + O2 + 1.5
    for k, d in ((v.get('ajustements') or {}).get('decalages') or {}).items():  # corrections ponctuelles
        if isinstance(T.get(k), list):
            T[k] = [x + float(d) for x in T[k]]
        elif k in T:
            T[k] += float(d)
    suite_len = min(T['outro'][0] + 0.4 - T['resume'], clip_len - suite_a)
    coupe = (R['fin_question'] + R['regarde']) / 2
    return T, dict(O1=O1, O2=O2, intro_start=intro_start, pause_a=pause_a, suite_a=suite_a, suite_len=suite_len,
                   coupe=coupe, duree=dur)


def evenements(T):
    """Bruitages, calés sur les mêmes moments que l'animation."""
    E = [(0.02, S.bubble(0.35)), (0.12, S.soft_swish(0.12)), (0.25, S.pop(1000, 400, 0.07, 0.25)),
         (T['pause'], S.clac(0.95)), (T['move'][0] - 0.05, S.whoosh(0.6, 0.4)), (T['panelIn'], S.bubble(0.45))]
    E += [(w - 0.06, S.pop(1100 + 50 * (i % 8), 420, 0.05, 0.12)) for i, w in enumerate(T['wordT'])]
    E += [(T['hl'], S.riser(0.45, 0.08)), (T['toQuiz'][0] - 0.08, S.whoosh(0.6, 0.4)), (T['toQuiz'][0], S.soft_swish(0.14))]
    E += [(r, S.bubble(0.45)) for r in T['rows']]
    E += [(T['headPlay'], S.soft_swish(0.14)), (T['pillStars'], S.pop(900, 300, 0.09, 0.4))]
    E += [(s, S.tick(i % 2 == 0, 1.3)) for i, s in enumerate(T['stars'])]
    E += [(s + 0.01, S.pop(1500 + 150 * i, 700, 0.05, 0.3)) for i, s in enumerate(T['stars'])]
    E += [(T['stars'][-1], S.riser(0.3, 0.22)), (T['headWatch'], S.soft_swish(0.14)),
          (T['resume'], S.pop(400, 1200, 0.12, 0.35)),
          (T['reveal'], S.soft_swish(0.14)), (T['reveal'] + 0.1, S.chime([523.3, 659.3, 784.0, 1046.5], 0.08, 0.4)),
          (T['reveal'] + 0.6, S.sparkle(0.25)), (T['reveal'] + 0.6, S.pop(800, 300, 0.1, 0.35)),
          (T['outro'][0] - 0.08, S.whoosh(0.6, 0.4)), (T['outro'][0] + 0.5, S.bubble(0.45)),
          (T['outro'][1] + 0.05, S.pop(700, 1400, 0.1, 0.3)),
          (T['click'], S.click(0.8)), (T['click'] + 0.1, S.chime([784.0, 1174.7], 0.06, 0.3, 0.4))]
    return E


def titre_mots(v):
    hl = {norm(w) for w in v.get('surligne') or []}
    return [[w, 'hl' if norm(w) in hl else ''] for w in v['situation'].split()]


# ---------------------------------------------------------------- une vidéo
def construire(v, reg, force=False, apercu=False, seulement_reperes=False):
    num = int(v['numero'])
    out = SORTIES / f'code-gta-vi-{num:02d}.mp4'
    if out.exists() and not (force or apercu or seulement_reperes):
        print(f'#{num:02d} déjà montée ({out.name}), je saute. (--force pour refaire)')
        return None
    reg = {**reg, **{k: v[k] for k in DEFAUTS if k in v}}
    work = CACHE / f'{num:02d}'
    work.mkdir(parents=True, exist_ok=True)
    clip = trouve_fichier(num, ['video', 'gameplay'], {'.mov', '.mp4', '.mkv', '.webm'}, v.get('gameplay'))
    voix = trouve_fichier(num, ['voix', 'voice', 'audio'], {'.mp3', '.wav', '.m4a'}, v.get('voix'))
    print(f'#{num:02d} gameplay={clip.name} voix={voix.name}')

    R = reperes(transcrire(voix, work), v)
    if seulement_reperes:
        print(json.dumps({k: (round(x, 2) if isinstance(x, float) else [round(y, 2) for y in x]) for k, x in R.items()}, ensure_ascii=False, indent=1))
        return None
    T, M = minutage(v, R, reg, duree(clip))
    lettres = 'ABC'
    rep = v['reponses']
    cfg = {'num': num, 'label': v['titre_gameplay'], 'title': titre_mots(v),
           'answers': [rep[k] for k in lettres], 'good': lettres.index(str(v['bonne_reponse']).strip().upper())}
    conf = {'cfg': cfg, 'T': T, 'duree': M['duree'], 'logo': f"file://{ROOT / 'assets' / 'logo.png'}"}

    # images du gameplay (intro, image figée, suite)
    sig = f"{clip.stat().st_mtime}-{M['intro_start']}-{M['pause_a']}-{M['suite_a']}-{M['suite_len']:.2f}"
    ancien = (work / 'images.sig').read_text() if (work / 'images.sig').exists() else ''
    if ancien != sig:
        for d in ('intro', 'suite'):
            shutil.rmtree(work / d, ignore_errors=True); (work / d).mkdir()
        vf = 'fps=30,scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720'
        run(['ffmpeg', '-v', 'error', '-y', '-ss', str(M['intro_start']), '-i', str(clip), '-t', str(T['pause']),
             '-vf', vf, '-q:v', '3', str(work / 'intro' / '%04d.jpg')])
        run(['ffmpeg', '-v', 'error', '-y', '-ss', str(M['pause_a']), '-i', str(clip), '-frames:v', '1',
             '-vf', vf.replace('fps=30,', ''), '-q:v', '2', str(work / 'freeze.jpg')])
        run(['ffmpeg', '-v', 'error', '-y', '-ss', str(M['suite_a']), '-i', str(clip), '-t', str(M['suite_len'] + 0.2),
             '-vf', vf, '-q:v', '3', str(work / 'suite' / '%04d.jpg')])
        (work / 'images.sig').write_text(sig)
    conf['images'] = {'intro': len(list((work / 'intro').glob('*.jpg'))), 'suite': len(list((work / 'suite').glob('*.jpg')))}
    (work / 'config.json').write_text(json.dumps(conf, ensure_ascii=False, indent=1))

    if apercu:
        clefs = [1.5, T['pause'] + 0.2, T['wordT'][-1] + 0.5, T['rows'][2] + 0.6, T['stars'][2] + 0.1,
                 T['resume'] + 0.8, T['reveal'] + 1.2, T['click'] + 0.6]
        run(['node', str(MOTEUR / 'render.js'), str(work), '--apercu', ','.join(f'{x:.2f}' for x in clefs)])
        planche = SORTIES / 'apercus' / f'apercu-{num:02d}.png'
        planche.parent.mkdir(parents=True, exist_ok=True)
        run(['ffmpeg', '-v', 'error', '-y', '-i', str(work / 'apercu_%04d.png'),
             '-vf', 'scale=360:640,tile=4x2:padding=8:color=0x14121e', '-frames:v', '1', str(planche)])
        print(f'#{num:02d} aperçu : {planche}')
        return planche

    # son : intro du jeu, suite du jeu, voix en 2 morceaux, bruitages
    a = lambda n: str(work / n)
    run(['ffmpeg', '-v', 'error', '-y', '-ss', str(M['intro_start']), '-i', str(clip), '-t', str(T['pause']), '-vn',
         '-ac', '2', '-ar', '48000', '-af', f"afade=t=out:st={max(0, T['pause'] - 0.03):.3f}:d=0.03", a('jeu_intro.wav')])
    run(['ffmpeg', '-v', 'error', '-y', '-ss', str(M['suite_a']), '-i', str(clip), '-t', str(M['suite_len']), '-vn',
         '-ac', '2', '-ar', '48000', '-af', f"afade=t=in:d=0.03,afade=t=out:st={max(0, M['suite_len'] - 0.5):.3f}:d=0.5", a('jeu_suite.wav')])
    d1, d2, c = int(M['O1'] * 1000), int((M['coupe'] + M['O2']) * 1000), M['coupe']
    run(['ffmpeg', '-v', 'error', '-y', '-i', str(voix), '-filter_complex',
         f"[0:a]atrim=0:{c:.3f},afade=t=out:st={c - 0.06:.3f}:d=0.06,asetpts=PTS-STARTPTS,adelay={d1}|{d1}[v1];"
         f"[0:a]atrim={c:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.05,adelay={d2}|{d2}[v2];"
         f"[v1][v2]amix=inputs=2:normalize=0,aformat=channel_layouts=stereo,aresample=48000,apad,atrim=0:{M['duree']:.3f}[v]",
         '-map', '[v]', a('voix_placee.wav')])
    S.mix(evenements(T), M['duree'], a('bruitages.wav'))

    print(f"#{num:02d} rendu de l'animation ({M['duree']:.1f} s)…")
    run(['node', str(MOTEUR / 'render.js'), str(work)])
    dr = int(T['resume'] * 1000)
    SORTIES.mkdir(exist_ok=True)
    run(['ffmpeg', '-v', 'error', '-y', '-i', a('video_muette.mp4'), '-i', a('voix_placee.wav'), '-i', a('bruitages.wav'),
         '-i', a('jeu_intro.wav'), '-i', a('jeu_suite.wav'), '-filter_complex',
         f"[1:a]volume={reg['volume_voix_db']}dB,asplit=2[vo][vsc];"
         f"[2:a]volume={reg['volume_bruitages_db']}dB[fx];"
         f"[3:a]volume={reg['volume_jeu_db']}dB,apad[g];"
         f"[4:a]volume={reg['volume_suite_db']}dB,adelay={dr}|{dr},apad,atrim=0:{M['duree']:.3f}[s0];"
         "[s0][vsc]sidechaincompress=threshold=0.02:ratio=8:attack=15:release=350:makeup=1[s];"
         "[vo][fx][g][s]amix=inputs=4:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
         '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-shortest', str(out)])
    print(f'#{num:02d} terminé : {out}')
    return out


def parse_nums(s):
    out = []
    for part in s.split(','):
        if '-' in part:
            a, b = part.split('-'); out += range(int(a), int(b) + 1)
        elif part:
            out.append(int(part))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print(__doc__); sys.exit(1)
    data = yaml.safe_load((ROOT / 'situations.yaml').read_text())
    reg = {**DEFAUTS, **(data.get('reglages') or {})}
    par_num = {int(v['numero']): v for v in data['videos']}
    for n in parse_nums(args[0]):
        if n not in par_num:
            print(f'#{n:02d} absente de situations.yaml, je saute.'); continue
        construire(par_num[n], reg, force='--force' in sys.argv, apercu='--apercu' in sys.argv,
                   seulement_reperes='--reperes' in sys.argv)


if __name__ == '__main__':
    main()
