// Rendu image par image du modèle d'animation (moteur/template.html) vers une vidéo muette.
// Usage : node moteur/render.js <dossier-de-travail> [--apercu t1,t2,...]
//   <dossier-de-travail> contient config.json et les images intro/, suite/, freeze.jpg (écrits par build.py)
//   --apercu : n'écrit que quelques images PNG (apercu_XX.png) au lieu de la vidéo.
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

(async () => {
  const work = path.resolve(process.argv[2]);
  const conf = JSON.parse(fs.readFileSync(path.join(work, 'config.json'), 'utf8'));
  const FPS = 30, DUR = conf.duree;
  const { pause, resume } = conf.T;
  const NI = conf.images.intro, NS = conf.images.suite;
  const pad = n => String(n).padStart(4, '0');
  const src = t => {
    if (t < pause) return `file://${work}/intro/${pad(Math.min(NI, Math.floor(t * FPS + 1e-6) + 1))}.jpg`;
    if (t < resume) return `file://${work}/freeze.jpg`;
    return `file://${work}/suite/${pad(Math.min(NS, Math.floor((t - resume) * FPS + 1e-6) + 1))}.jpg`;
  };

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  await page.addInitScript(c => { window.CONFIG = c; }, conf);
  await page.goto('file://' + path.join(__dirname, 'template.html'));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
  const draw = t => page.evaluate(async ([t, s]) => {
    const im = document.getElementById('gimg');
    if (im.getAttribute('src') !== s) { im.src = s; await im.decode(); }
    window.render(t);
  }, [t, src(t)]);

  const i = process.argv.indexOf('--apercu');
  if (i > 0) {
    const times = process.argv[i + 1].split(',').map(Number);
    for (const [k, t] of times.entries()) {
      await draw(t);
      await page.screenshot({ path: path.join(work, `apercu_${pad(k)}.png`) });
    }
  } else {
    const out = path.join(work, 'video_muette.mp4');
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-',
      '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '19', '-preset', 'medium', out]);
    const total = Math.round(FPS * DUR);
    for (let f = 0; f < total; f++) {
      await draw(f / FPS);
      const buf = await page.screenshot({ type: 'jpeg', quality: 92 });
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
      if (f % 150 === 0) process.stdout.write(`  images ${f}/${total}\n`);
    }
    ff.stdin.end();
    await new Promise(r => ff.on('close', r));
  }
  await browser.close();
})();
