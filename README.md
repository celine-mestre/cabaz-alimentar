# Cabaz alimentar — ferramenta de análise

Aplicação de apoio à decisão sobre o cabaz alimentar em Portugal, desenvolvida
pela **Unidade de Pesquisa e Estatísticas (UPE)** da Direção de Serviços de
Suporte à Decisão, Secretaria-Geral do Governo.

Obtém dados oficiais em direto do Eurostat e permite decompor o valor do cabaz
por tipo de produto, acompanhar a série histórica, simular alterações do IVA e
comparar Portugal com os restantes Estados-Membros.

---

## Índice

1. [O que a aplicação faz](#o-que-a-aplicação-faz)
2. [Porquê Streamlit e não um ficheiro HTML](#porquê-streamlit-e-não-um-ficheiro-html)
3. [Estrutura do repositório](#estrutura-do-repositório)
4. [Instalação e execução local](#instalação-e-execução-local)
5. [Publicação no GitHub](#publicação-no-github)
6. [Alojamento no Streamlit Community Cloud](#alojamento-no-streamlit-community-cloud)
7. [Fontes de dados](#fontes-de-dados)
8. [Metodologia](#metodologia)
9. [Limitações a declarar](#limitações-a-declarar)
10. [Manutenção](#manutenção)
11. [Resolução de problemas](#resolução-de-problemas)

---

## O que a aplicação faz

A aplicação organiza-se em cinco separadores.

**1 · Cabaz e composição.** O valor de referência é, por defeito, **oficial**:
a despesa alimentar mensal por agregado, derivada das Contas Nacionais e
atualizada para o mês mais recente pelo índice oficial de preços. A aplicação
reparte-o pelas nove classes de produtos alimentares, usando os ponderadores do
índice harmonizado português, e aplica a cada classe a sua variação homóloga.
Devolve o contributo de cada tipo de produto para o agravamento — responde a
*«onde está o aumento?»*.

**2 · Histórico.** Série mensal oficial do índice de preços alimentares e da
variação homóloga, de 12 meses a 5 anos.

**3 · Simulador de IVA.** Permite definir uma taxa por classe e, sobretudo,
regular a **repercussão** — a fração da alteração de imposto que chega ao preço
final. Mostra quanto poupa o consumidor, quanto fica na margem do operador e
qual a variação de receita.

**4 · Comparação UE-27.** Inflação alimentar harmonizada de Portugal face à
UE-27 e aos países selecionados, com ordenação do último mês disponível.

**5 · Fontes e método.** Proveniência de cada elemento, registo das ligações da
sessão e limitações a declarar.

---

## Porquê Streamlit e não um ficheiro HTML

Uma versão anterior desta ferramenta era um ficheiro HTML autónomo que tentava
ler a API do Eurostat a partir do navegador. **Não funcionava** — e a razão não
era o código:

> Um navegador impede que uma página carregada de uma origem leia dados de outra
> origem (política de *same-origin*, controlada por cabeçalhos CORS). Uma página
> aberta a partir do disco tem origem `null`, e as redes institucionais
> reforçam ainda a restrição com *proxies* de saída.

Numa aplicação Streamlit, os pedidos ao Eurostat são feitos **pelo servidor, em
Python**, com a biblioteca `requests`. A política de mesma origem não se aplica a
pedidos servidor-a-servidor: o problema desaparece por construção.

Vantagens adicionais: os dados ficam em *cache* partilhada entre utilizadores,
a aplicação tem um endereço estável, e qualquer atualização feita no GitHub é
publicada automaticamente.

---

## Estrutura do repositório

```
cabaz-alimentar/
├── app.py                  # aplicação Streamlit (interface e separadores)
├── requirements.txt        # dependências
├── README.md               # este ficheiro
├── .gitignore
├── .streamlit/
│   └── config.toml         # tema institucional SGGov
├── src/
│   ├── __init__.py
│   ├── config.py           # classes COICOP, países, cores, formatação
│   ├── eurostat.py         # acesso aos dados (duas vias independentes)
│   └── calculos.py         # decomposição do cabaz e simulação de IVA
└── tests/
    └── test_calculos.py    # 11 testes dos cálculos analíticos
```

A separação entre **acesso a dados** (`eurostat.py`), **cálculo** (`calculos.py`)
e **apresentação** (`app.py`) é deliberada: permite testar a lógica sem levantar
a interface, e substituir a fonte de dados sem tocar no resto.

---

## Instalação e execução local

Requer **Python 3.10 ou superior**.

```bash
# 1. Obter o código
git clone https://github.com/<utilizador>/cabaz-alimentar.git
cd cabaz-alimentar

# 2. Criar e ativar um ambiente virtual
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Executar
streamlit run app.py
```

A aplicação abre em `http://localhost:8501`.

Para correr os testes:

```bash
pip install pytest
python -m pytest tests/ -v
```

---

## Publicação no GitHub

### Pela interface web (mais simples)

1. Em [github.com](https://github.com), clique em **New repository**.
2. Nome: `cabaz-alimentar`. Visibilidade: **Public** — necessário para o plano
   gratuito do Streamlit Community Cloud. Não adicione README, `.gitignore` nem
   licença (já existem).
3. **Create repository**.
4. No ecrã seguinte, escolha **uploading an existing file** e arraste todos os
   ficheiros e pastas.
5. **Commit changes**.

> **Atenção às pastas ocultas.** `.streamlit/` começa por ponto e alguns sistemas
> escondem-na. Se não a carregar, a aplicação funciona à mesma, mas sem o tema
> institucional. Em caso de dúvida, crie o ficheiro manualmente no GitHub com
> **Add file → Create new file** e o nome `.streamlit/config.toml` — escrever a
> barra cria a pasta automaticamente.

### Por linha de comandos

```bash
cd cabaz-alimentar
git init
git add .
git commit -m "Ferramenta do cabaz alimentar — versao inicial"
git branch -M main
git remote add origin https://github.com/<utilizador>/cabaz-alimentar.git
git push -u origin main
```

---

## Alojamento no Streamlit Community Cloud

1. Aceda a [share.streamlit.io](https://share.streamlit.io) e entre com a conta
   do GitHub.
2. **Create app** → **Deploy a public app from GitHub**.
3. Preencha:

   | Campo | Valor |
   |---|---|
   | Repository | `<utilizador>/cabaz-alimentar` |
   | Branch | `main` |
   | Main file path | `app.py` |
   | App URL | `cabaz-alimentar` (ou outro nome disponível) |

4. **Deploy**. A primeira instalação demora 2 a 4 minutos.

A aplicação fica em `https://<nome-escolhido>.streamlit.app`.

**Atualizações.** Qualquer alteração enviada para o ramo `main` é publicada
automaticamente em poucos segundos. Não é preciso repetir a publicação.

**Suspensão por inatividade.** No plano gratuito, aplicações sem visitas durante
alguns dias entram em suspensão e reativam-se no primeiro acesso seguinte
(demora cerca de 30 segundos). Não há perda de dados.

**Sem segredos a configurar.** As APIs do Eurostat são públicas e não exigem
chave nem registo, pelo que não é necessário preencher a secção *Secrets*.

---

## Fontes de dados

Todos os dados quantitativos provêm do **Eurostat**, que difunde o índice
harmonizado de preços no consumidor (IHPC) compilado pelos institutos nacionais
— no caso português, o **INE**.

| Elemento | Conjunto de dados | Frequência |
|---|---|---|
| Despesa alimentar (âncora em euros) | `nama_10_co3_p3` | Anual |
| Dimensão média do agregado | `ilc_lvph01` | Anual |
| Número de agregados familiares | `lfst_hhnhtych` (recuo: Censos 2021) | Anual |
| Ponderadores por classe | `prc_hicp_inw` | Anual |
| Índice de preços | `prc_hicp_midx` | Mensal |
| Variação homóloga | `prc_hicp_manr` | Mensal |
| Comparação UE-27 | `prc_hicp_manr` | Mensal |

### O número de agregados familiares

É o **divisor** de todo o cálculo: a despesa alimentar nacional é dividida por ele para obter
a despesa de um agregado. Duplicá-lo reduz o resultado a metade, pelo que não pode ser um
valor arbitrário.

A aplicação usa, por esta ordem:

1. **Eurostat / Inquérito ao Emprego** (`lfst_hhnhtych`) — valor anual, o mais recente disponível;
2. **INE, Censos 2021** — **4 149 096** agregados domésticos privados, se o anterior falhar.

O valor obtido é submetido a **verificação de plausibilidade** (entre 3,0 e 6,5 milhões). Fora
desse intervalo, presume-se que o conjunto devolvido não é o esperado e recorre-se ao valor
censitário, registando a ocorrência no diagnóstico. A despesa resultante é igualmente
verificada (entre 50 € e 3 000 € mensais por agregado); fora disso a aplicação mostra um erro
e desaconselha o uso dos números.

O campo está **bloqueado por defeito**. Existe uma opção de ajuste manual, destinada apenas a
testar cenários — quando ativada com um valor diferente do oficial, a aplicação avisa que os
resultados deixam de ser reproduzíveis a partir de fontes oficiais.


### A âncora em euros

O índice de preços dá **variações, nunca níveis**: não permite dizer «o cabaz
custa X euros». É preciso uma âncora em euros.

A aplicação usa uma âncora **oficial**: a despesa final das famílias em produtos
alimentares (`nama_10_co3_p3`, Contas Nacionais, COICOP 01.1, preços correntes),
dividida pelo número de agregados e por doze, e depois atualizada para o mês mais
recente com o índice oficial de preços:

```
despesa_mensal_base = despesa_nacional_ano / n.º agregados / 12
valor_atual         = despesa_mensal_base × (índice_mês / índice_médio_ano_base)
```

Assim, **toda a cadeia é oficial e reproduzível**, sem dependência de séries
privadas. As Contas Nacionais têm um desfasamento de cerca de dois anos, o que a
atualização pelo índice resolve.

Existe também um modo **«valor externo»**, para quem queira testar o que uma
recolha de terceiros implicaria. Esse valor é assinalado na interface como não
oficial e não deve ser apresentado como número da Secretaria-Geral.

### Composição do agregado

A despesa média por agregado esconde uma diferença que importa para política: um
agregado de uma pessoa e um casal com dois filhos não gastam o mesmo. A aplicação
mostra explicitamente **a quantas pessoas corresponde o valor médio** (dimensão
média do agregado, `ilc_lvph01`, EU-SILC) e permite ajustar a composição por
número de adultos e de crianças.

O ajustamento usa **escalas de equivalência**, o instrumento oficial para comparar
agregados de composição diferente:

| Escala | Primeiro adulto | Adulto adicional | Criança (<14) |
|---|---|---|---|
| Per capita | 1,0 | 1,0 | 1,0 |
| OCDE original | 1,0 | 0,7 | 0,5 |
| OCDE modificada (norma UE) | 1,0 | 0,5 | 0,3 |

**Ressalva metodológica importante.** Estas escalas foram construídas para o
consumo *total*, em que a partilha da habitação gera fortes economias de escala.
Na alimentação essas economias são bem mais fracas — não se partilha uma refeição
como se partilha um teto. A escala OCDE modificada, norma da UE para o rendimento,
tende por isso a **subestimar** o custo alimentar de agregados maiores. Por essa
razão a aplicação usa a OCDE original por defeito e apresenta **sempre um
intervalo** entre a escala mais restritiva e a mais generosa, em vez de um valor
único de falsa precisão.

O separador inclui um comparador de composições típicas (pessoa só, casal,
monoparental com filhos, casal com filhos), com o intervalo de cada uma.

### Sobre séries privadas de cabaz

Séries de cabaz publicadas por associações de consumidores são úteis para
compreender o debate público, mas **não são usadas como fonte desta aplicação**,
por três razões:

1. **Propriedade.** São produto de entidades privadas. Construir um instrumento
   público cujo número principal é o número de um privado levanta questões de
   propriedade intelectual e de dependência.
2. **Metodologia.** Assentam em composição fixa (índice de Laspeyres congelado),
   com viés de substituição conhecido — precisamente a limitação que a nota de
   enquadramento da UPE assinala.
3. **Posição institucional.** A nota recomenda que a Administração **não** crie
   nem valide um cabaz concorrente. Depender de um cabaz privado seria a outra
   face do mesmo problema.

A discussão analítica dessas séries mantém-se, e deve manter-se, na nota de
enquadramento: aí o objeto é explicar ao Gabinete o que cada instrumento mede.
Aqui o objeto é produzir números — e esses são oficiais.

### As duas vias de acesso

A aplicação tenta as vias por esta ordem:

1. **SDMX 2.1** — `…/sdmx/2.1/data/prc_hicp_manr/M.RCH_A.CP011.PT?format=SDMX-CSV`
   O filtro segue no próprio caminho do endereço, pelo que a seleção é
   obrigatoriamente feita no servidor do Eurostat. É a via preferida: evita
   respostas demasiado grandes.
2. **API Statistics** — `…/statistics/1.0/data/prc_hicp_manr?coicop=CP011&geo=PT&…`
   Filtros por parâmetro, resposta em JSON-stat. Usada se a primeira falhar.

O separador *Fontes e método* mostra, em cada sessão, qual das vias foi
efetivamente utilizada.

### Parâmetros que **não** são dados oficiais

- **N.º de agregados familiares** — parâmetro do utilizador, usado para converter
  a despesa nacional em despesa por agregado.
- **Valor externo** — quando escolhido em alternativa à âncora oficial.
- **Taxas de IVA** — predefinidas e editáveis. Ver limitação 4.
- **Repercussão** — hipótese de trabalho. Ver limitação 5.

---

## Metodologia

### Decomposição do cabaz

O valor total é repartido pelas nove classes na proporção dos ponderadores
oficiais. A cada classe aplica-se a respetiva variação homóloga.

Se uma classe vale hoje `Vᵢ` e cresceu `gᵢ` por cento, há um ano valia
`Vᵢ/(1+gᵢ)`. O acréscimo absoluto é:

```
contributoᵢ = Vᵢ · gᵢ / (1 + gᵢ)
```

A soma dos contributos iguala exatamente a variação do total — a decomposição é
aditiva, o que é verificado por teste automático.

### Simulação de IVA

Para cada classe, com taxa atual `t₀`, taxa do cenário `t₁` e repercussão `ρ`:

```
base        = valor / (1 + t₀)
efeito_mec  = base · (1 + t₁) − valor        (repercussão integral)
efeito_real = ρ · efeito_mec                 (o que chega ao consumidor)
margem      = (1 − ρ) · efeito_mec           (o que fica no operador)
```

**A repercussão é o parâmetro decisivo.** A avaliação internacional de reduções
de IVA na alimentação e na restauração — nomeadamente as experiências francesa
(2009) e sueca — é consistentemente cética quanto à transmissão integral para o
preço. O valor por defeito é 40 %, que é um parâmetro de trabalho e não uma
estimativa: convém sempre testar a sensibilidade do resultado movendo o cursor.

Nota que a simulação torna visível: **a receita cessante é a mesma qualquer que
seja a repercussão**. O que muda é quem fica com o dinheiro — o consumidor ou a
margem do operador.

---

## Limitações a declarar

Qualquer utilização destes resultados em suporte à decisão ou em comunicação
deve fazer-se acompanhar destas ressalvas:

1. **A decomposição não é observação.** É uma imputação de um valor total por
   ponderadores oficiais. Não substitui a recolha de preços produto a produto,
   que nenhuma fonte pública disponibiliza por interface automática.
2. **Ponderadores de consumo médio.** Os ponderadores do IHPC refletem a
   estrutura de despesa média das famílias — não a composição de nenhum cabaz
   específico, nem a de um agregado concreto.
3. **A âncora parte de uma média nacional.** A despesa por agregado resulta de
   dividir um agregado macroeconómico pelo número de agregados. O ajustamento por
   composição usa escalas de equivalência aplicadas a essa média — não substitui
   uma observação direta por tipo de agregado, que exigiria o IDEF/INE. Não
   distingue escalão de rendimento nem região.
4. **As escalas de equivalência são aproximações.** Foram construídas para o
   consumo total e subestimam o custo alimentar de agregados maiores; o agregado
   médio é modelado como composto por adultos, porque a dimensão média é publicada
   sem decomposição etária. Daí a apresentação em intervalo.
5. **Desfasamento das Contas Nacionais.** A âncora assenta num ano com cerca de
   dois anos de desfasamento, atualizado por índice de preços — capta a variação
   de preços, não eventuais alterações de comportamento de consumo desde então.
6. **A correspondência COICOP → taxa de IVA é aproximada.** O Código do IVA
   classifica por produto (Lista I), não por classe COICOP; uma mesma classe pode
   conter produtos a taxas diferentes.
7. **A repercussão é uma hipótese.** Qualquer resultado do simulador é condicional
   a esse parâmetro e deve ser apresentado como intervalo, nunca como valor único.
8. **Preço de prateleira não é preço pago.** Nem o cabaz nem o IHPC captam
   integralmente descontos de cartão e de talão. Só dados de transação
   (e-fatura, *scanner data*) o permitiriam.
9. **A extrapolação agregada é ilustrativa.** A multiplicação pelo número de
   agregados serve para dimensionar ordens de grandeza. **Não é uma estimativa de
   custo orçamental** — essa exigiria a base tributável real por taxa, via Contas
   Nacionais, IDEF ou dados da Autoridade Tributária.

---

## Tipografia institucional

A aplicação usa a **Lexend**, tipo de letra das normas gráficas da SGGov. É aplicada em três
camadas, porque nenhuma isolada cobre tudo:

1. **Tema do Streamlit** (`.streamlit/config.toml`) — `font` e `headingFont` no formato
   `Família:URL`, suportado a partir do Streamlit 1.50. Cobre a generalidade da interface.
2. **CSS injetado** (`app.py`) — cobre componentes que não herdam sempre do tema: métricas,
   tabelas, widgets, barra lateral. O código mantém tipo monoespaçado, por legibilidade.
3. **Template do Plotly** — os gráficos são desenhados em SVG e **não herdam a fonte da
   página**. A função `grafico()` impõe a Lexend e usa `theme=None`, para que o tema do
   Streamlit não sobreponha o template institucional.

### Consideração de privacidade

A fonte é servida pelo **Google Fonts**. Isso significa que o navegador de cada utilizador
estabelece ligação a servidores da Google, transmitindo o endereço IP. Para uma aplicação da
Administração Pública, é uma dependência a ponderar.

Alternativa sem dependência externa: descarregar os ficheiros `.woff2` da Lexend para uma pasta
`static/` no repositório e declará-los localmente:

```toml
[server]
enableStaticServing = true

[[theme.fontFaces]]
family = "Lexend"
url = "app/static/Lexend-Regular.woff2"
weight = 400
style = "normal"

[theme]
font = "Lexend, sans-serif"
```

Nesse caso, é preciso substituir também o `@import` do CSS em `app.py` por uma declaração
`@font-face` apontando ao mesmo caminho.

## Manutenção

**Periodicidade dos dados.** O Eurostat publica o IHPC mensalmente, cerca de duas
a três semanas após o fim do mês de referência. Os ponderadores são revistos
anualmente. A aplicação guarda os dados em *cache* durante 6 horas; o botão
**Recarregar do Eurostat**, na barra lateral, força a atualização.

**Alterar classes, países ou taxas por defeito.** Editar `src/config.py`. As
listas `CLASSES` e `PAISES` controlam tudo o que aparece na interface.

**Se o Eurostat alterar a nomenclatura.** Está prevista a transição para a
ECOICOP versão 2. Se os códigos `CP011x` deixarem de responder, basta atualizar o
campo `cod` em `CLASSES`; o resto da aplicação não precisa de alterações.

**Antes de qualquer alteração aos cálculos**, correr `python -m pytest tests/ -v`.
Os 11 testes cobrem a aditividade da decomposição e a aritmética do IVA, incluindo
casos-limite conhecidos.

---

## Resolução de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| «Não foi possível obter os dados» na nuvem | Serviço do Eurostat indisponível | Aguardar e usar **Recarregar**; confirmar em `ec.europa.eu/eurostat` |
| O mesmo erro em execução local | Rede institucional a bloquear a saída | Pedir à Transformação Digital a autorização de `ec.europa.eu`, ou usar a versão alojada |
| Aplicação demora ~30 s a abrir | Reativação após suspensão por inatividade | Normal no plano gratuito |
| Tema sem as cores institucionais | Pasta `.streamlit/` não foi carregada | Criar `.streamlit/config.toml` diretamente no GitHub |
| `ModuleNotFoundError` na publicação | Dependência em falta | Confirmar que `requirements.txt` está na raiz do repositório |
| Tabelas vazias mas sem erro | Códigos COICOP alterados na fonte | Verificar `src/config.py` face à nomenclatura em vigor |

Para diagnóstico detalhado, o separador **Fontes e método** mostra o registo das
ligações da sessão: que pedidos foram feitos, por que via e quantas observações
devolveram.

---

## Créditos e estatuto

Desenvolvido pela **Unidade de Pesquisa e Estatísticas (UPE)**, Direção de
Serviços de Suporte à Decisão, Secretaria-Geral do Governo.

Dados: **Eurostat** — reutilização livre com indicação da fonte, nos termos da
política de reutilização da Comissão Europeia.

> **Estatuto do produto.** Ferramenta de trabalho interno. Não constitui posição
> oficial da Secretaria-Geral do Governo. Os valores carecem de reconfirmação
> junto das fontes primárias antes de qualquer utilização em suporte à decisão
> política ou em comunicação pública.
