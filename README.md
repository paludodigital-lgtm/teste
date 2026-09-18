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
