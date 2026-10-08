# Lavland — animação do reel

Transforma a arte estática da loja (`assets/lavland-source.webp`) num vídeo
vertical 1080x1920 pronto para Reels/TikTok, sem nenhuma ferramenta paga.

**Saída:** `out/lavland-reel.mp4` — 12s, 30fps, H.264, ~5 MB.

## O que se move

| Elemento | Como |
|---|---|
| Câmera | Ken Burns: zoom de 1.0 → 1.075 com pan suave em direção aos rostos |
| Parallax | As duas pessoas são recortadas numa camada própria que aproxima ~1.7× mais rápido que o fundo |
| Tambores | As 3 secadoras giram contínuo; as 2 lavadoras fazem o vai-e-vem do ciclo de lavagem. O reflexo do vidro fica parado |
| Luzes | LED do teto, letreiro e painéis das máquinas pulsam em ritmos diferentes |
| Pessoas | Respiração sutil (sobe/desce 2px, "infla" 0,4%) e um leve balanço lateral |
| Textos | 4 mensagens em sequência, com varrida de luz nas trocas |

## Rodar

```bash
pip install pillow numpy
apt-get install -y ffmpeg

python3 src/render_reel.py              # 12s, 1080x1920, 30fps
python3 src/render_reel.py --preview    # 1 frame por segundo em PNG, ~9s
python3 src/render_reel.py --duration 8 --fps 24
```

Render completo leva ~4 min. O `--preview` serve para conferir enquadramento
e texto antes de gastar os 4 minutos.

## Trocar a copy

Tudo que aparece escrito está no dicionário `COPY`, no topo de
`src/render_reel.py`:

```python
COPY = {
    "badge": "24H",
    "a_title": "LAVLAND",
    "b_title": "ABERTO 24 HORAS",
    "c_words": ["LAVA", "SECA", "DOBRA"],
    "d_title": "BAIXE O APP LAVLAND",
    ...
}
```

Os textos atuais são placeholders baseados só no que já aparece na arte
(24h, Lavanderia Express, app, toalhas dobradas). Nenhum é uma promessa
comercial — troque por preço, prazo ou endereço reais antes de publicar.

A linha do tempo está escrita para 12s e é reescalada sozinha quando você
muda `--duration`. As marcas estão nas chamadas `place(...)` em
`overlay_frame`.

## Limites

- **Som:** o arquivo sai mudo. Instagram e TikTok pedem áudio — adicione uma
  trilha da biblioteca da própria plataforma na hora de postar, que já vem
  licenciada.
- **Pessoas:** o que o código faz é respiração e balanço. Acenar, piscar e
  virar o rosto exige IA de vídeo — os prompts prontos estão em
  [`prompts/ia-video.md`](prompts/ia-video.md).
- **Recorte:** a silhueta das pessoas é um polígono traçado à mão
  (`PEOPLE_POLY`), não uma segmentação automática. Ele preenche os vãos entre
  as pernas, o que é invisível no deslocamento de poucos pixels do parallax,
  mas apareceria se você aumentasse `FG_DEPTH` muito além de 2.
- **Enquadramento:** o corte 9:16 perde a faixa à esquerda da arte (o selo
  "24h" da parede) para manter as cinco máquinas em quadro. O selo foi
  recriado como overlay no canto superior esquerdo.

## Logo

Se você tiver o logo Lavland em PNG com fundo transparente, jogue em
`assets/logo.png`. Hoje o título usa a fonte Inter — a constante `LOGO` já
está declarada em `src/render_reel.py` para quem for plugar a arte real.

---

# Homem mais alto (edição do vídeo)

Pedido: pegar `assets/video-original.mp4` (13,6s, 720x960, 30fps, com áudio e
legenda queimada) e deixar **só** o homem mais alto que a mulher, sem mexer em
mais nada.

**Saída:** `out/lavland-homem-mais-alto.mp4` — mesma resolução, duração
(13,567s), fps e faixa de áudio copiada bit a bit do original.

## Como funciona

```bash
pip install opencv-python-headless mediapipe pillow numpy
apt-get install -y ffmpeg libegl1

ffmpeg -i assets/video-original.mp4 -start_number 0 /tmp/work/src_%04d.png
python3 src/analyze_people.py     # ~2 min: detecta e separa as duas pessoas
python3 src/render_taller.py      # ~1 min: escala o homem e recompõe
```

`src/analyze_people.py` usa o MediaPipe Pose Landmarker para achar as duas
pessoas em cada frame e guardar uma máscara por pessoa.

`src/render_taller.py` escala o homem em **1,09** (`--scale` para mudar)
ancorado nos pés dele, o que faz ele crescer só para cima — os sapatos
continuam no mesmo ponto do chão, então piso, sombra e enquadramento não
mudam. Depois a mulher volta por cima, recortada do frame original, e a
legenda é recolocada na posição exata.

Escolha do 1,09: medindo os 319 frames com as duas pessoas detectadas, o homem
era em média 2% mais baixo. Com 1,09 ele fica mais alto em 98,7% dos frames,
com folga mediana de 46px acima da cabeça dela, e sem nunca sair pelo topo do
quadro.

## Armadilhas que apareceram no caminho

| Problema | Solução |
|---|---|
| MediaPipe devolvia a MESMA pessoa duas vezes quando eles se encostam (47% dos frames) | plano B: detecta um, apaga ele do quadro com inpaint, detecta de novo |
| `numpy_view()` da máscara aponta para memória liberada do MediaPipe | copiar o array; sem isso o processo morre com segfault |
| A máscara do homem invadia as pernas da mulher | cada pixel vai para o esqueleto mais próximo, com distância máxima do próprio dono |
| Landmark do pé dele caía do lado da mulher quando ele está cortado no quadro | âncora vem do centro de massa da base da própria máscara |
| A legenda era escalada junto e aparecia duplicada | remover a legenda antes de escalar e recolocar por cima no fim |
| O inpaint borrava o braço esticado dele | preencher o buraco com o fundo do próprio quadro escalado, que ali já é fundo de verdade |
| A âncora tremia e ele "pulsava" de tamanho | média móvel da âncora, respeitando cortes de cena |
| A máscara vazava no card final do logo e o deformava | trava que só empresta máscara de um vizinho se a cena for a mesma |

## Limites

- Sobram artefatos leves onde o braço dele está bem esticado (por volta de
  3s-4s): o preenchimento do fundo atrás do braço antigo não é perfeito. Em
  velocidade normal quase não se vê, mas pausando dá para notar.
- 6 frames em 329 ficaram sem detecção das duas pessoas e saem idênticos ao
  original.
- Os 78 frames finais são o card do logo, sem pessoas — passam intactos.

---

# Tutorial "Como gravar para a agência" (SuperLav)

Vídeo para mandar ao cliente ensinando a gravar os takes que a agência vai
editar. Montado só com os takes brutos da própria lavanderia, com o jeito
certo e os erros lado a lado.

**Saída:** `out/tutorial-gravacao.mp4` — 81s, 1080x1920, 30fps, ~38 MB.

## Roteiro

| Parte | Mensagem | Takes |
|---|---|---|
| Abertura | Como gravar vídeos para a agência | 0850 |
| Passo 1 | Celular em pé (certo × deitado) | 0838, 0836 |
| Passo 2 | Mostre onde fica: fachada e chegada | 0773, 0759 |
| Passo 3 | Passo a passo do serviço | 0775, 0776, 0779, 0873, 0780 |
| Passo 4 | Chegue perto: detalhes | 0814, 0841 |
| Passo 5 | Ambiente com movimento lento | 0830, 0856 |
| Passo 6 | Fale para a câmera (áudio original) | 0851, 0795 |
| Cuidado | Chão, lente suja, gravação sem querer, cortar cedo | 0799, 0825, 0823, 0795 |
| Checklist | 7 regras antes de gravar | — |

## Rodar

```bash
python3 src/render_tutorial.py --takes /pasta/com/os/IMG_xxxx.MP4 --out out/tutorial-gravacao.mp4
```

Os takes não ficam no repositório (são ~750 MB, na pasta do Drive do
cliente). Para trocar um trecho ou um texto, edite a lista `SECTIONS` no topo
do script: cada cena tem o take, o intervalo em segundos, o texto e se é
"ok" (assim sim) ou "bad" (assim não). O `CHECKLIST` fica logo abaixo.

## Áudio

- Falas (Passo 6) entram altas; o resto mantém o som ambiente baixinho.
- A trilha é gerada pelo próprio script (pad + arpejo), sem direitos
  autorais, e abaixa sozinha quando alguém fala.

## Limites

- Só 53 dos 92 takes da pasta entraram na análise: a conexão com o Drive
  não baixa arquivos acima de ~5 MB. Os takes longos (provavelmente as falas
  mais completas) ficaram de fora.
- Sem transcrição automática: o modelo de voz não pôde ser baixado nesta
  rede. As falas usadas são curtas e entram com o áudio original.

---

# Vídeo de dicas (ajuste do vídeo de WhatsApp)

Vídeo de 3 min, gravado pela agência na SuperLav, com dicas para o cliente:
fachada, vertical e horizontal, entorno, localização e estacionamento.

**Saída:** `out/dicas-gravacao.mp4` — 2:39, 1080x1920, 30fps, ~63 MB.

- **Áudio original**, só com o volume nivelado (-14 LUFS). Sem trilha.
- Cortes de silêncios e respiros, e as duas demonstrações sem fala
  (filmando o entorno e o posto) encurtadas para o melhor pedaço.
- Subido de 576x1024 para 1080x1920, com nitidez e cor levemente realçadas.
- Título de cada dica no topo e a frase-chave na base, no mesmo visual do
  tutorial.

```bash
python3 src/edit_dicas.py --src video-do-whatsapp.mp4 --out out/dicas-gravacao.mp4
```

Os cortes (`KEEP`) e os textos (`SECTIONS`, `CALLOUTS`) ficam no topo do
script, em segundos do vídeo original. Eles foram tirados de uma transcrição
com Whisper (modelo `small`, baixado dos releases do sherpa-onnx no GitHub) e
conferidos transcrevendo o vídeo final de novo.
