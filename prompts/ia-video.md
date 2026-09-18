# Prompts de imagem→vídeo (Lavland)

O que o código **não** faz é mover as pessoas de verdade: piscar, acenar,
respirar, virar o rosto. Isso hoje só sai bem numa IA de vídeo. Abaixo estão
prompts prontos para colar, usando `assets/lavland-source.webp` como imagem
de entrada.

**Como usar:** em qualquer ferramenta image-to-video (Kling, Runway, Hailuo,
Veo, Luma), suba a imagem, cole o prompt positivo, cole o negativo no campo
de negative prompt, e gere 5s. Depois emenda os trechos no `render_reel.py`
ou num editor.

Regra que vale para todas: **peça pouco movimento**. Prompt pedindo muita
ação faz o modelo redesenhar os rostos, e os dois atendentes deixam de ser
os mesmos entre um clipe e outro.

---

## Clipe 1 — abertura (5s)

> Cinematic slow push-in on two cheerful laundromat attendants standing side
> by side in a bright purple and orange laundry store. Both breathe naturally
> and blink. The woman in the purple polo shifts her weight slightly and her
> smile widens. The man in the light blue polo holding folded towels turns his
> head a few degrees toward camera. Dryer drums rotate slowly behind them,
> ceiling LED strips glow steadily. Subtle camera dolly forward. Photoreal
> stylized illustration look, consistent character faces, 9:16 vertical.

**Negativo:** `face morphing, changing facial features, extra fingers, warped
hands, distorted logos, text warping, melting clothes, duplicated people,
fast motion, camera shake, background people appearing`

---

## Clipe 2 — o aceno (5s)

> The man in the light blue polo raises his free right hand and waves once at
> the camera, friendly and slow. The woman in the purple polo keeps her hand
> on her hip and nods slightly, smiling. Both blink naturally. The stack of
> folded towels stays steady in his left arm. Static camera, very slight
> handheld float. Washing machine drums turn in the background. Consistent
> character identity, stylized illustration, 9:16 vertical.

**Negativo:** mesmo do clipe 1, mais `dropping towels, arm detaching,
duplicate arms, hand through body`

---

## Clipe 3 — as máquinas (5s)

> Slow camera pan right across a row of stacked laundromat machines labeled
> SECADORA 01, 02, 03 and LAVADORA. Dryer drums spin steadily with laundry
> tumbling inside, visible through the round glass doors. Amber and purple
> control panels glow. Warm store lighting, shallow depth of field, no people
> in frame. Stylized illustration look, 9:16 vertical.

**Negativo:** `people, hands, text warping, flickering, strobing, logo
distortion`

---

## Clipe 4 — fechamento sobre o tapete (5s)

> Slow camera tilt down from the two smiling attendants to the orange Lavland
> floor mat in the foreground. The attendants hold their pose, breathing and
> blinking. Soft reflections move across the polished tile floor. Static
> framing at the end, ready for a logo overlay. Stylized illustration,
> consistent faces, 9:16 vertical.

**Negativo:** mesmo do clipe 1, mais `mat text warping, floor distortion`

---

## Ajustes por ferramenta

| Ferramenta | O que mexer |
|---|---|
| **Kling 2.x** | Modo "Professional", CFG ~0.4. Baixo CFG preserva mais o rosto original. |
| **Runway Gen-3/4** | Use o campo *Motion Brush* só nos braços e nos tambores; deixe os rostos de fora. |
| **Hailuo / MiniMax** | Prompts curtos funcionam melhor — corte cada prompt acima pela metade. |
| **Veo** | Aceita o prompt inteiro. Peça "subtle" duas vezes, ele tende a exagerar o movimento. |
| **Luma Dream Machine** | Ligue *Enhance prompt: off*, senão ele reescreve e muda a cena. |

## Depois de gerar

Os clipes saem em 5s cada. Para montar os 20s finais na mesma trilha:

```bash
ffmpeg -f concat -safe 0 -i lista.txt -c:v libx264 -crf 20 -pix_fmt yuv420p \
       -vf "scale=1080:1920,fps=30" out/lavland-ia.mp4
```

Onde `lista.txt` é uma linha `file 'clipe1.mp4'` por trecho, na ordem.

Para reaproveitar os textos animados deste repositório por cima dos clipes de
IA, renderize só as camadas de texto com fundo transparente e use
`overlay` no ffmpeg — as funções `card_title`, `card_words`, `card_cta` e
`card_badge` em `src/render_reel.py` já devolvem RGBA.
