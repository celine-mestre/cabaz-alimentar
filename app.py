"""
Cabaz alimentar — ferramenta de análise
UPE · DSSD · Secretaria-Geral do Governo

Executar localmente:   streamlit run app.py
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pathlib import Path

from src import eurostat
from src.calculos import (ESCALAS, decompor, despesa_do_agregado, intervalo_agregado,
                          resumo_decomposicao, resumo_iva, simular_iva,
                          unidades_equivalentes)
from src.config import (AZUL, CLASSES, CODIGOS, COICOP_ALIMENTAR, DOURADO,
                        PAISES, PAISES_POR_DEFEITO, POR_CODIGO, RODAPE,
                        UNIDADE, VERDE, VERMELHO, euro, mes_pt, percentagem)

LOGO = ""
try:
    LOGO = (Path(__file__).parent / "src" / "logo_b64.txt").read_text().strip()
except Exception:                                          # noqa: BLE001
    LOGO = ""

st.set_page_config(
    page_title="Cabaz alimentar — UPE/SGGov",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==========================================================================
# Estilo institucional
# ==========================================================================
st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Lexend:wght@300;400;500;600;700&display=swap');
  html, body, [class*="css"] {{ font-family: 'Lexend', Arial, sans-serif; }}

  .cabecalho {{
    background: linear-gradient(120deg, {AZUL} 0%, #1a3f6f 28%, {VERDE} 62%, #0a5228 100%);
    border-bottom: 3px solid {VERMELHO};
    padding: 22px 26px; border-radius: 12px; color: #fff; margin-bottom: 18px;
  }}
  .cab-topo {{ display: flex; align-items: center; gap: 13px; margin-bottom: 14px; }}
  .simbolo {{
    width: 46px; height: 46px; border-radius: 50%; background: #fff; flex: 0 0 46px;
    display: flex; align-items: center; justify-content: center;
    border: 1px solid rgba(23,23,21,.16);
  }}
  .simbolo img {{ width: 42px; height: 42px; display: block; border-radius: 50%; }}
  .cabecalho h1 {{
    font-size: 26px; font-weight: 600; margin: 0 0 6px; letter-spacing: -.5px;
    padding-left: 14px; border-left: 4px solid {DOURADO}; line-height: 1.25;
  }}
  .cabecalho p {{ margin: 0 0 0 18px; font-size: 13.5px; opacity: .93; }}
  .cabecalho .marca {{
    font-size: 11.5px; font-weight: 600; letter-spacing: .5px; opacity: .95; line-height: 1.4;
  }}

  .cartao {{
    background: #fff; border: 1px solid #e2e8f0; border-radius: 11px;
    padding: 13px 15px; box-shadow: 0 1px 3px rgba(23,23,21,.07);
    border-left: 4px solid var(--c); height: 100%;
  }}
  .cartao .topo {{ display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }}
  .cartao .emj {{ font-size: 21px; line-height: 1; }}
  .cartao .nm {{ font-size: 13px; font-weight: 600; line-height: 1.2; }}
  .cartao .cd {{ font-size: 9.5px; color: #6b7280; letter-spacing: .3px; }}
  .cartao .vl {{ font-size: 20px; font-weight: 600; letter-spacing: -.5px; }}
  .cartao .ln {{ display: flex; justify-content: space-between; align-items: baseline;
                 margin-top: 4px; font-size: 11.5px; }}
  .cartao .ct {{ font-size: 10.5px; color: #6b7280; margin-top: 7px;
                 border-top: 1px solid #eef1f4; padding-top: 6px; }}

  .nota {{
    border-left: 3px solid {DOURADO}; background: rgba(190,156,84,.09);
    border-radius: 0 8px 8px 0; padding: 11px 14px; font-size: 13px; margin: 12px 0;
  }}
  .nota .tt {{
    font-size: 10.5px; font-weight: 600; letter-spacing: .9px; text-transform: uppercase;
    color: {DOURADO}; margin-bottom: 4px;
  }}
  .nota.perigo {{ border-left-color: {VERMELHO}; background: rgba(208,33,23,.07); }}
  .nota.perigo .tt {{ color: {VERMELHO}; }}

  [data-testid="stMetricValue"] {{ font-size: 22px; font-weight: 600; }}
  [data-testid="stMetricLabel"] {{ font-size: 12px; }}
  .stTabs [data-baseweb="tab"] {{ font-size: 14px; font-weight: 500; }}
  footer {{ visibility: hidden; }}
</style>
""", unsafe_allow_html=True)


# ==========================================================================
# Obtenção de dados (executada no servidor — sem restrições de navegador)
# ==========================================================================
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def carregar_dados(anos_historico: int = 6):
    """Obtém tudo o que a aplicação precisa. Em cache durante 6 horas."""
    ano = date.today().year
    desde_indice = f"{ano - anos_historico}-01"
    desde_variacao = f"{ano - 3}-01"

    registo = []

    pesos_df, via1 = eurostat.ponderadores(CODIGOS)
    registo.append(("Ponderadores", via1, len(pesos_df)))

    indice_df, via2 = eurostat.indice_precos(COICOP_ALIMENTAR, desde_indice)
    registo.append(("Índice de preços", via2, len(indice_df)))

    var_df, via3 = eurostat.variacoes(
        [COICOP_ALIMENTAR] + CODIGOS, list(PAISES.keys()), desde_variacao
    )
    registo.append(("Variações e UE-27", via3, len(var_df)))

    # Âncora oficial em euros — Contas Nacionais (opcional: pode não estar
    # disponível para o último ano; a aplicação funciona sem ela).
    try:
        desp_df, via4 = eurostat.despesa_alimentar(ano - anos_historico)
        registo.append(("Despesa alimentar (Contas Nacionais)", via4, len(desp_df)))
    except Exception as exc:                                   # noqa: BLE001
        desp_df, via4 = pd.DataFrame(), f"indisponível ({exc})"
        registo.append(("Despesa alimentar (Contas Nacionais)", via4, 0))

    try:
        dim_df, via5 = eurostat.dimensao_agregado(ano - anos_historico)
        registo.append(("Dimensão média do agregado", via5, len(dim_df)))
    except Exception as exc:                                   # noqa: BLE001
        dim_df, via5 = pd.DataFrame(), f"indisponível ({exc})"
        registo.append(("Dimensão média do agregado", via5, 0))

    # --- ponderadores: ano mais recente de cada classe ---
    pesos_df = pesos_df.sort_values("time")
    pesos = pesos_df.groupby("coicop")["valor"].last().to_dict()
    ano_pesos = pesos_df["time"].max() if not pesos_df.empty else None

    # --- variações por classe (Portugal, mês mais recente) ---
    pt_classes = var_df[(var_df["geo"] == "PT") & (var_df["coicop"].isin(CODIGOS))]
    pt_classes = pt_classes.sort_values("time")
    variacoes_classe = pt_classes.groupby("coicop")["valor"].last().to_dict()
    mes_variacoes = pt_classes["time"].max() if not pt_classes.empty else None

    # --- séries globais de Portugal ---
    if not indice_df.empty:
        # A base do índice mudou ao longo do tempo (2015=100 → 2025=100).
        # Preferir a mais recente disponível; se nenhuma for reconhecida,
        # usar a unidade com mais observações.
        unidades = indice_df["unit"].value_counts()
        preferida = None
        for candidata in ("I25", "I15", "I05", "I96"):
            if candidata in unidades.index:
                preferida = candidata
                break
        if preferida is None:
            preferida = unidades.index[0]
        indice_pt = indice_df[indice_df["unit"] == preferida].sort_values("time")
        base_indice = preferida
    else:
        indice_pt, base_indice = indice_df, None

    var_pt = var_df[(var_df["geo"] == "PT") &
                    (var_df["coicop"] == COICOP_ALIMENTAR)].sort_values("time")

    # --- comparação europeia ---
    bench = var_df[var_df["coicop"] == COICOP_ALIMENTAR].sort_values("time")

    # --- âncora oficial: despesa alimentar por agregado ---
    despesa_ano, despesa_valor = None, None
    if not desp_df.empty:
        recente = desp_df.sort_values("time").iloc[-1]
        despesa_ano, despesa_valor = str(recente["time"]), float(recente["valor"])

    dimensao_media, dimensao_ano = None, None
    if not dim_df.empty:
        rec = dim_df.sort_values("time").iloc[-1]
        dimensao_ano, dimensao_media = str(rec["time"]), float(rec["valor"])

    return {
        "base_indice": (base_indice if not indice_df.empty else None),
        "dimensao_media": dimensao_media,
        "dimensao_ano": dimensao_ano,
        "despesa_ano": despesa_ano,
        "despesa_milhoes": despesa_valor,
        "pesos": pesos,
        "ano_pesos": ano_pesos,
        "variacoes_classe": variacoes_classe,
        "mes_variacoes": mes_variacoes,
        "indice_pt": indice_pt,
        "var_pt": var_pt,
        "bench": bench,
        "registo": registo,
        "momento": datetime.now(),
    }


def ancora_oficial(dados: dict, agregados: int) -> dict | None:
    """
    Converte a despesa alimentar nacional das Contas Nacionais numa despesa
    mensal por agregado e atualiza-a para o mês mais recente com o índice
    oficial de preços.

    Devolve None se os dados necessários não estiverem disponíveis.
    """
    if not dados.get("despesa_milhoes") or not agregados:
        return None

    ano_base = dados["despesa_ano"]
    mensal_base = dados["despesa_milhoes"] * 1e6 / agregados / 12

    indice = dados["indice_pt"]
    if indice.empty:
        return {"valor": mensal_base, "ano_base": ano_base,
                "mes": None, "fator": 1.0, "base_mensal": mensal_base}

    do_ano = indice[indice["time"].str.startswith(str(ano_base))]
    if do_ano.empty:
        return {"valor": mensal_base, "ano_base": ano_base,
                "mes": None, "fator": 1.0, "base_mensal": mensal_base}

    media_base = float(do_ano["valor"].mean())
    ultimo = indice.sort_values("time").iloc[-1]
    fator = float(ultimo["valor"]) / media_base if media_base else 1.0

    return {
        "valor": mensal_base * fator,
        "base_mensal": mensal_base,
        "ano_base": ano_base,
        "mes": str(ultimo["time"]),
        "fator": fator,
    }


# ==========================================================================
# Componentes visuais
# ==========================================================================
def cartao_classe(linha: pd.Series) -> str:
    var = linha["variacao"]
    cor_var = "#6b7280" if var is None else (VERMELHO if var > 0 else VERDE)
    contributo = ("Contributo: <strong>" + euro(linha["contributo"]) + "</strong>"
                  if linha["contributo"] is not None else "Aguarda dados")
    return f"""
    <div class="cartao" style="--c:{linha['cor']}">
      <div class="topo">
        <span class="emj">{linha['emoji']}</span>
        <span><span class="nm">{linha['classe']}</span><br>
        <span class="cd">COICOP {linha['codigo'][2:4]}.{linha['codigo'][4]}.{linha['codigo'][5]}</span></span>
      </div>
      <div class="vl">{euro(linha['valor'])}</div>
      <div class="ln">
        <span style="color:#6b7280">{linha['quota'] * 100:.1f} % do cabaz</span>
        <span style="color:{cor_var};font-weight:600">{percentagem(var)}</span>
      </div>
      <div class="ct">{contributo}</div>
    </div>"""


def grafico_donut(df: pd.DataFrame) -> go.Figure:
    dados = df[df["valor"] > 0].sort_values("valor", ascending=False)
    fig = go.Figure(go.Pie(
        labels=[f"{r.emoji} {r.classe}" for r in dados.itertuples()],
        values=dados["valor"],
        hole=.58,
        marker=dict(colors=list(dados["cor"]), line=dict(color="#fff", width=2)),
        textinfo="percent",
        textfont=dict(size=11),
        hovertemplate="<b>%{label}</b><br>%{value:.2f} €<br>%{percent}<extra></extra>",
    ))
    fig.update_layout(
        height=380, margin=dict(t=10, b=10, l=10, r=10),
        showlegend=True,
        legend=dict(orientation="v", x=1, y=.5, font=dict(size=11)),
        annotations=[dict(text=f"<b>{euro(dados['valor'].sum())}</b>",
                          x=.5, y=.5, font_size=17, showarrow=False)],
    )
    return fig


def grafico_historico(indice: pd.DataFrame, variacao: pd.DataFrame,
                      meses: int) -> go.Figure:
    idx = indice.tail(meses)
    var = variacao.tail(meses)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[mes_pt(t) for t in idx["time"]], y=idx["valor"],
        name="Índice de preços", line=dict(color=VERDE, width=2.6),
        hovertemplate="%{x}<br>Índice: %{y:.1f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[mes_pt(t) for t in var["time"]], y=var["valor"],
        name="Variação homóloga (%)", yaxis="y2",
        line=dict(color=VERMELHO, width=2, dash="dot"),
        hovertemplate="%{x}<br>Variação: %{y:.1f} %<extra></extra>",
    ))
    fig.update_layout(
        height=380, margin=dict(t=20, b=40, l=10, r=10),
        yaxis=dict(title="Índice"),
        yaxis2=dict(title="Variação homóloga (%)", overlaying="y", side="right",
                    zeroline=True, zerolinecolor="#cbd5e1"),
        legend=dict(orientation="h", y=1.13, x=0),
        hovermode="x unified", plot_bgcolor="#fff",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#eef1f4")
    return fig


def grafico_reparticao(sim: pd.DataFrame) -> go.Figure:
    dados = sim[sim["mecanico"].abs() > 0.001].copy()
    if dados.empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=[f"{r.emoji} {r.classe}" for r in dados.itertuples()],
        x=dados["efetivo"].abs(), name="Chega ao consumidor",
        orientation="h", marker_color=VERDE,
        hovertemplate="%{y}<br>Consumidor: %{x:.2f} €<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=[f"{r.emoji} {r.classe}" for r in dados.itertuples()],
        x=dados["margem"].abs(), name="Capturado na margem",
        orientation="h", marker_color=DOURADO,
        hovertemplate="%{y}<br>Margem: %{x:.2f} €<extra></extra>",
    ))
    fig.update_layout(
        barmode="stack", height=330, margin=dict(t=30, b=30, l=10, r=10),
        legend=dict(orientation="h", y=1.14, x=0),
        xaxis_title="Euros por cabaz", plot_bgcolor="#fff",
    )
    fig.update_xaxes(gridcolor="#eef1f4")
    return fig


# ==========================================================================
# Cabeçalho
# ==========================================================================
_logo_html = (
    f'<div class="simbolo"><img src="data:image/png;base64,{LOGO}" alt="SGGov"></div>'
    if LOGO else ""
)
st.markdown(f"""
<div class="cabecalho">
  <div class="cab-topo">
    {_logo_html}
    <div class="marca">SECRETARIA-GERAL DO GOVERNO · SUPORTE À DECISÃO<br>
    <span style="font-weight:400;opacity:.85">{UNIDADE}</span></div>
  </div>
  <h1>Despesa alimentar das famílias</h1>
  <p>Composição por tipo de produto, séries oficiais, simulador de IVA e comparação
  europeia. Dados obtidos em direto do Eurostat.</p>
</div>
""", unsafe_allow_html=True)

# ==========================================================================
# Carregamento (executado no servidor — sem restrições de navegador)
# ==========================================================================
try:
    with st.spinner("A obter dados oficiais do Eurostat…"):
        dados = carregar_dados()
    erro_carregamento = None
except Exception as exc:                                   # noqa: BLE001
    dados, erro_carregamento = None, exc

if erro_carregamento is not None:
    st.error(
        "**Não foi possível obter os dados do Eurostat.**\n\n"
        f"`{erro_carregamento}`\n\n"
        "Se esta aplicação estiver alojada no Streamlit Community Cloud, verifique o "
        "estado do serviço do Eurostat. Em execução local numa rede institucional, "
        "confirme se o acesso a `ec.europa.eu` está autorizado."
    )
    st.stop()

ultimo_mes = dados["mes_variacoes"] or (
    dados["var_pt"]["time"].max() if not dados["var_pt"].empty else "—"
)

# ==========================================================================
# Barra lateral — parâmetros
# ==========================================================================
with st.sidebar:
    st.markdown("### 🛒 Parâmetros")

    agregados = st.number_input(
        "Total de agregados familiares em Portugal", min_value=1,
        value=4_100_000, step=100_000,
        help=("Divisor: a despesa alimentar de todo o país é dividida por este número "
              "para obter a despesa de um agregado. Valor de referência dos Censos 2021 "
              "— confirme-o antes de usar os resultados."),
    )
    st.caption(
        "É o **divisor**: a despesa alimentar nacional é dividida por este número "
        "para obter a despesa de um agregado médio."
    )

    ancora = ancora_oficial(dados, agregados)

    st.divider()
    st.caption("**Valor de referência do cabaz**")

    opcoes = ["Oficial — calculado a partir das Contas Nacionais"]
    if ancora is None:
        opcoes = ["Externo — valor que eu introduzo"]
    else:
        opcoes.append("Externo — valor que eu introduzo")

    modo = st.radio("Origem do valor", opcoes, index=0, label_visibility="collapsed",
                    help=("Oficial: a aplicação calcula a despesa a partir de dados do "
                          "Eurostat. Externo: usa um valor de outra recolha, para comparação."))

    if modo.startswith("Oficial") and ancora is not None:
        media_agregado = float(ancora["valor"])
        valor_medio_agregado = media_agregado
        dim_media = dados.get("dimensao_media")

        st.metric("Agregado médio nacional", euro(media_agregado))
        if dim_media:
            st.caption(
                f"Corresponde a um agregado de **{('%.2f' % dim_media).replace('.', ',')} pessoas** "
                f"(média nacional, EU-SILC {dados.get('dimensao_ano')}). "
                f"Base: {euro(ancora['base_mensal'])}/mês em {ancora['ano_base']}, "
                f"atualizada pelo índice de preços (×{('%.3f' % ancora['fator']).replace('.', ',')})."
            )
        else:
            st.caption(
                f"Base: {euro(ancora['base_mensal'])}/mês em {ancora['ano_base']}, "
                f"atualizada pelo índice de preços (×{ancora['fator']:.3f}). "
                "Dimensão média do agregado indisponível."
            )

        st.divider()
        st.caption("**Composição do agregado a analisar**")
        ca, cb = st.columns(2)
        adultos = ca.number_input("Adultos", min_value=1, max_value=8, value=2, step=1)
        criancas = cb.number_input("Crianças (<14)", min_value=0, max_value=8, value=0, step=1)

        dim_efetiva = dim_media if dim_media else 2.5
        escala_chave = st.selectbox(
            "Escala de equivalência",
            options=list(ESCALAS.keys()), index=1,
            format_func=lambda k: ESCALAS[k]["nome"],
        )
        st.caption(ESCALAS[escala_chave]["nota"])
        with st.expander("O que é uma escala de equivalência?"):
            st.markdown("""
Duas pessoas não gastam o dobro de uma. Há partilha: compra-se a granel, desperdiça-se
menos, aproveitam-se sobras. Uma **escala de equivalência** traduz isso em números.

Os três valores — por exemplo **1 / 0,7 / 0,5** — significam:

| | Peso | Leitura |
|---|---|---|
| 1.º adulto | **1,0** | é a referência |
| Cada adulto a mais | **0,7** | custa 70 % do primeiro |
| Cada criança (<14) | **0,5** | custa 50 % do primeiro |

Um casal com duas crianças vale `1 + 0,7 + 0,5 + 0,5 = 2,7` **unidades de consumo
equivalente** — não 4. A despesa é calculada por unidade equivalente e multiplicada
por este total.

**Qual escolher?** A *OCDE modificada* (1 / 0,5 / 0,3) é a norma da UE, mas foi
construída para o consumo total, onde partilhar casa gera grandes poupanças. Na
alimentação a partilha é bem menor — não se divide uma refeição como se divide um
teto. Por isso a aplicação usa por defeito a intermédia e mostra sempre o intervalo.
            """)

        valor_cabaz = despesa_do_agregado(
            media_agregado, dim_efetiva, adultos, criancas, escala_chave)
        faixa = intervalo_agregado(media_agregado, dim_efetiva, adultos, criancas)

        composicao = (f"{adultos} adulto{'s' if adultos > 1 else ''}"
                      + (f" + {criancas} criança{'s' if criancas > 1 else ''}"
                         if criancas else ""))
        pessoas = adultos + criancas
        ue = unidades_equivalentes(adultos, criancas, escala_chave)

        st.metric(f"Despesa mensal estimada — {composicao}", euro(valor_cabaz))
        st.caption(
            f"**{pessoas} pessoa{'s' if pessoas > 1 else ''}** · "
            f"{('%.2f' % ue).replace('.', ',')} unidades de consumo equivalente. "
            f"Consoante a escala usada, o valor situa-se entre "
            f"**{euro(faixa['minimo'])}** e **{euro(faixa['maximo'])}**."
        )

        origem = (f"Contas Nacionais {ancora['ano_base']} · {composicao} · "
                  f"escala {ESCALAS[escala_chave]['nome']}")
        vezes_ano = 12
    else:
        valor_cabaz = st.number_input(
            "Valor observado (€)", min_value=0.0, value=250.00, step=0.01, format="%.2f",
            help="Valor de uma recolha externa, para comparação. Não é dado oficial.",
        )
        origem = st.text_input("Identificação da fonte", value="Recolha externa")
        periodicidade = st.selectbox(
            "Periodicidade", options=[("Semanal", 52), ("Mensal", 12), ("Anual", 1)],
            format_func=lambda x: x[0], index=1,
        )
        vezes_ano = periodicidade[1]
        st.caption(
            "⚠️ Valor não oficial. Serve para comparação com a estimativa oficial; "
            "não deve ser apresentado como número da Secretaria-Geral."
        )
        adultos, criancas, faixa, escala_chave = None, None, None, None
        valor_medio_agregado = valor_cabaz
        composicao = "valor externo"

    st.divider()
    st.caption("**Atualização dos dados**")
    if st.button("🔄 Recarregar do Eurostat", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption(f"**{UNIDADE}**")

# --- mensagem de estado ---
nota_ancora = ""
if dados.get("despesa_ano"):
    nota_ancora = f" · âncora de despesa de **{dados['despesa_ano']}**"
st.success(
    f"Dados oficiais carregados · último mês disponível **{mes_pt(ultimo_mes)}** · "
    f"ponderadores de **{dados['ano_pesos']}**{nota_ancora} · "
    f"atualizado às {dados['momento'].strftime('%H:%M de %d/%m/%Y')}"
)

# --- decomposição base, usada por vários separadores ---
df_decomp = decompor(valor_cabaz, dados["pesos"], dados["variacoes_classe"])
resumo = resumo_decomposicao(df_decomp, valor_cabaz)

aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "🛒 Cabaz e composição", "📈 Histórico", "🧾 Simulador de IVA",
    "🇪🇺 Comparação UE-27", "📚 Metodologia e fontes",
])

# ==========================================================================
# ABA 1 — Cabaz e composição
# ==========================================================================
with aba1:
    colunas = st.columns(5)
    colunas[0].metric(f"Despesa mensal — {composicao}", euro(valor_cabaz), help=origem)
    if resumo["contributo_total"] is not None:
        colunas[1].metric("Agravamento em 12 meses", euro(resumo["contributo_total"]),
                          percentagem(resumo["variacao_implicita"]))
        colunas[2].metric("Valor há um ano", euro(resumo["valor_ha_um_ano"]))
        if resumo["maior"]:
            maior = resumo["maior"]
            colunas[3].metric(f"{maior['emoji']} Maior contributo",
                              euro(maior["contributo"]),
                              percentagem(maior["variacao"]))
    colunas[4].metric(f"Equivalente anual (×{vezes_ano})", euro(valor_cabaz * vezes_ano))

    if faixa is not None:
        st.markdown(f"""
        <div class="nota">
          <div class="tt">A quantas pessoas corresponde este valor</div>
          O ponto de partida é a despesa alimentar do <strong>agregado médio
          português — {('%.2f' % (dados.get('dimensao_media') or 0)).replace('.', ',')} pessoas</strong> (EU-SILC
          {dados.get('dimensao_ano','—')}). O valor acima está ajustado para
          <strong>{composicao}</strong> através de uma escala de equivalência.
          Consoante a escala aplicada, o resultado situa-se entre
          <strong>{euro(faixa['minimo'])}</strong> e <strong>{euro(faixa['maximo'])}</strong> por mês.
          <br><br>
          <em>Ressalva:</em> as escalas de equivalência foram construídas para o consumo
          <em>total</em>, em que a partilha da habitação gera fortes economias de escala.
          Na alimentação essas economias são bem mais fracas — não se partilha uma refeição
          como se partilha um teto. A escala OCDE modificada, norma da UE para o rendimento,
          tende por isso a <strong>subestimar</strong> o custo alimentar de agregados maiores.
        </div>
        """, unsafe_allow_html=True)

        with st.expander("Comparar composições de agregado"):
            comps = [(1, 0, "1 adulto"), (2, 0, "Casal"), (1, 1, "Monoparental + 1"),
                     (1, 2, "Monoparental + 2"), (2, 1, "Casal + 1 criança"),
                     (2, 2, "Casal + 2 crianças"), (2, 3, "Casal + 3 crianças"),
                     (3, 1, "3 adultos + 1 criança")]
            dm = dados.get("dimensao_media") or 2.5
            linhas_c = []
            for a, c, rot in comps:
                iv = intervalo_agregado(valor_medio_agregado, dm, a, c)
                linhas_c.append({
                    "Composição": rot,
                    "Pessoas": a + c,
                    "Estimativa central (€/mês)": round(
                        despesa_do_agregado(valor_medio_agregado, dm, a, c, "ocde_original"), 2),
                    "Mínimo (€/mês)": round(iv["minimo"], 2),
                    "Máximo (€/mês)": round(iv["maximo"], 2),
                })
            df_c = pd.DataFrame(linhas_c)
            st.dataframe(df_c, use_container_width=True, hide_index=True)

            figc = go.Figure()
            figc.add_trace(go.Bar(
                x=df_c["Composição"], y=df_c["Mínimo (€/mês)"], name="Mínimo",
                marker_color="#cbd5e1"))
            figc.add_trace(go.Bar(
                x=df_c["Composição"], y=df_c["Estimativa central (€/mês)"] - df_c["Mínimo (€/mês)"],
                name="Até à estimativa central", marker_color=VERDE))
            figc.add_trace(go.Bar(
                x=df_c["Composição"], y=df_c["Máximo (€/mês)"] - df_c["Estimativa central (€/mês)"],
                name="Até ao máximo", marker_color=DOURADO))
            figc.update_layout(barmode="stack", height=340,
                               margin=dict(t=30, b=60, l=10, r=10),
                               yaxis_title="€ por mês",
                               legend=dict(orientation="h", y=1.14, x=0),
                               plot_bgcolor="#fff")
            figc.update_yaxes(gridcolor="#eef1f4")
            st.plotly_chart(figc, use_container_width=True)
            st.caption(
                "As barras mostram o intervalo entre a escala mais restritiva "
                "(OCDE modificada) e a mais generosa (per capita)."
            )

    with st.expander("🧮 Como é calculado — fórmula, fontes e o que este número não é"):
        st.markdown("""
**1 · Ponto de partida: quanto gasta o país em alimentação**

Das Contas Nacionais (`nama_10_co3_p3`) vem a despesa anual de todas as famílias
portuguesas em produtos alimentares, em euros. Divide-se pelo total de agregados
e por doze:

```
despesa mensal do agregado médio = despesa nacional anual ÷ n.º agregados ÷ 12
```

**2 · Atualização para o mês corrente**

As Contas Nacionais têm cerca de dois anos de desfasamento. O valor é trazido
para o presente com o índice oficial de preços alimentares (`prc_hicp_midx`):

```
valor atual = valor do ano-base × (índice do mês ÷ índice médio do ano-base)
```

**3 · Ajustamento à composição do agregado**

Aplica-se a escala de equivalência escolhida (ver barra lateral).

**4 · Repartição por tipo de produto**

Os **ponderadores oficiais** do índice de preços (`prc_hicp_inw`) dizem que
fração da despesa alimentar vai para cada um dos nove grupos. É essa estrutura
que reparte o valor total pelos cartões acima. A variação de cada grupo vem de
`prc_hicp_manr`.

```
valor do grupo i = despesa total × (ponderador i ÷ soma dos ponderadores)
```
        """)
        st.warning("""
**Este número não é um cabaz de compras.**

Não há quilos, nem litros, nem unidades. A aplicação trabalha com **despesa em
euros**, não com quantidades físicas. Não sabe quantos quilos de fruta ou de
legumes uma família compra — sabe apenas que fração do orçamento alimentar vai
para fruta e que essa fração encareceu X %.

Para raciocinar em quantidades seria preciso o **IDEF/INE**, que recolhe consumo
físico, ou dados de transação (e-fatura, *scanner data*).
        """)
        st.info("""
**E os preços? Os supermercados praticam preços muito diferentes.**

Praticam — e por isso a aplicação **não usa o preço de nenhum supermercado**.
Usa o índice oficial do INE, que resulta da recolha mensal de preços numa
amostra de estabelecimentos de todo o país (grande distribuição, comércio
tradicional, canais especializados), ponderada pelo peso de cada canal e de cada
região no consumo real.

O resultado é uma **média nacional representativa**, não o preço numa insígnia
concreta. Uma família que compre sempre no *discount* enfrenta níveis mais baixos;
outra em zona de baixa densidade, mais altos. O índice capta bem a **variação**;
o **nível** de cada família concreta varia em torno desta média.
        """)

    st.markdown("""
    <div class="nota">
      <div class="tt">O que são estes grupos</div>
      São os nove tipos de produto em que a estatística oficial divide a alimentação.
      A <strong>COICOP</strong> (Classificação do Consumo Individual por Objetivo) é a
      nomenclatura internacional que o INE e o Eurostat usam para organizar a despesa
      das famílias; o grupo 01.1 é «produtos alimentares» e 01.1.1 a 01.1.9 são as suas
      subdivisões — na prática: pão, carne, peixe, laticínios, óleos, fruta, legumes,
      doces e restantes.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### Composição por tipo de produto")
    for inicio in range(0, len(df_decomp), 3):
        cols = st.columns(3)
        for col, (_, linha) in zip(cols, df_decomp.iloc[inicio:inicio + 3].iterrows()):
            col.markdown(cartao_classe(linha), unsafe_allow_html=True)
    st.write("")

    esq, dir_ = st.columns([1, 1])
    with esq:
        st.markdown("#### Peso de cada tipo de produto")
        st.plotly_chart(grafico_donut(df_decomp), use_container_width=True)
    with dir_:
        st.markdown("#### Contributo para o agravamento")
        com_dados = df_decomp.dropna(subset=["contributo"]).sort_values("contributo")
        if com_dados.empty:
            st.info("Sem variações disponíveis para o período.")
        else:
            fig = go.Figure(go.Bar(
                y=[f"{r.emoji} {r.classe}" for r in com_dados.itertuples()],
                x=com_dados["contributo"], orientation="h",
                marker_color=[VERMELHO if v > 0 else VERDE for v in com_dados["contributo"]],
                hovertemplate="%{y}<br>%{x:.2f} €<extra></extra>",
            ))
            fig.update_layout(height=380, margin=dict(t=10, b=30, l=10, r=10),
                              xaxis_title="Euros", plot_bgcolor="#fff")
            fig.update_xaxes(gridcolor="#eef1f4", zerolinecolor="#cbd5e1")
            st.plotly_chart(fig, use_container_width=True)

    with st.expander("Ver tabela detalhada"):
        tabela = df_decomp[["codigo", "classe", "ponderador", "quota",
                            "valor", "variacao", "contributo"]].copy()
        tabela.columns = ["Código", "Classe", "Ponderador (‰)", "Quota",
                          "Valor (€)", "Variação (%)", "Contributo (€)"]
        st.dataframe(
            tabela, use_container_width=True, hide_index=True,
            column_config={
                "Quota": st.column_config.ProgressColumn(
                    "Quota", format="%.1f%%", min_value=0, max_value=1),
                "Valor (€)": st.column_config.NumberColumn(format="%.2f"),
                "Variação (%)": st.column_config.NumberColumn(format="%.1f"),
                "Contributo (€)": st.column_config.NumberColumn(format="%.2f"),
                "Ponderador (‰)": st.column_config.NumberColumn(format="%.1f"),
            },
        )
        st.download_button(
            "⬇️ Descarregar decomposição (CSV)",
            tabela.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            f"cabaz_decomposicao_{date.today()}.csv", "text/csv",
        )

    st.markdown("""
    <div class="nota">
      <div class="tt">O que esta decomposição é — e não é</div>
      O valor é repartido pelas classes oficiais; não corresponde a uma observação de
      preços produto a produto. Isto é uma <strong>reconstituição por classe COICOP</strong>, com ponderadores e
      índices oficiais — metodologicamente defensável e replicável, mas
      <strong>não é o preço observado produto a produto</strong>. Responde a
      «onde está o agravamento?», não substitui a recolha.
    </div>
    """, unsafe_allow_html=True)

# ==========================================================================
# ABA 2 — Histórico
# ==========================================================================
with aba2:
    st.markdown("#### Série oficial mensal — produtos alimentares em Portugal")
    meses = st.radio("Período", [12, 24, 36, 60], index=1, horizontal=True,
                     format_func=lambda m: f"{m} meses" if m < 60 else "5 anos")

    if dados["indice_pt"].empty:
        st.info("Sem série de índices disponível.")
    else:
        st.plotly_chart(
            grafico_historico(dados["indice_pt"], dados["var_pt"], meses),
            use_container_width=True,
        )

    var_pt = dados["var_pt"]
    if not var_pt.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Variação homóloga mais recente",
                  percentagem(var_pt["valor"].iloc[-1]),
                  help=f"Mês de referência: {mes_pt(var_pt['time'].iloc[-1])}")
        janela = var_pt.tail(meses)["valor"]
        c2.metric("Média do período", percentagem(janela.mean()))
        c3.metric("Máximo do período", percentagem(janela.max()))

    st.markdown("""
    <div class="nota">
      <div class="tt">Porque é que a série é mensal</div>
      A frequência mensal é a mais fina publicada por fonte oficial. Existem séries semanais de cabazes publicadas por entidades privadas, mas não
      são dados oficiais nem têm acesso automático — e as variações semanais são muito voláteis por efeitos de base e de promoção: em
      julho de 2026, a variação homóloga de um desses cabazes passou de +6,9 % para +4,3 %
      numa única semana sem que nada de estrutural tivesse mudado.
    </div>
    """, unsafe_allow_html=True)

    with st.expander("Ver série completa"):
        serie = dados["indice_pt"][["time", "valor"]].rename(
            columns={"time": "Período", "valor": "Índice"})
        var_tab = dados["var_pt"][["time", "valor"]].rename(
            columns={"time": "Período", "valor": "Variação homóloga (%)"})
        junto = serie.merge(var_tab, on="Período", how="outer").sort_values("Período")
        st.dataframe(junto, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Descarregar série (CSV)",
            junto.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            f"cabaz_serie_{date.today()}.csv", "text/csv",
        )

# ==========================================================================
# ABA 3 — Simulador de IVA
# ==========================================================================
with aba3:
    st.markdown("#### Cenário hipotético de alteração do IVA")

    CENARIOS = {
        "manual": ("✏️ Definir manualmente", None),
        "zero": ("🧺 «Cabaz zero» — isenção total (precedente 2023-24)", 0.0),
        "seis": ("📉 Taxa reduzida (6 %) em tudo", 6.0),
        "treze": ("📊 Taxa intermédia (13 %) em tudo", 13.0),
    }
    if "cenario_iva" not in st.session_state:
        st.session_state["cenario_iva"] = "zero"

    esq, dir_ = st.columns([2, 1])
    with esq:
        repercussao = st.slider(
            "Repercussão no preço ao consumidor (%)", 0, 100, 40, 5,
            help="Que fração da alteração de imposto chega efetivamente ao preço final.",
        ) / 100
    with dir_:
        cenario = st.radio(
            "Cenário a simular",
            options=list(CENARIOS.keys()),
            format_func=lambda k: CENARIOS[k][0],
            key="cenario_iva",
        )

    if cenario == "zero":
        st.markdown("""
        <div class="nota">
          <div class="tt">Precedente: o «cabaz zero» de 2023-24</div>
          Entre abril de 2023 e janeiro de 2024 vigorou em Portugal a isenção de IVA
          sobre uma lista taxativa de bens alimentares essenciais. A medição do seu
          efeito <strong>divergiu consoante quem media</strong> — a ASAE apurou uma
          redução acumulada superior a 10 % no cabaz monitorizado, a DECO apurou cerca
          de metade disso no período inicial. A diferença não estava nos factos, estava
          na metodologia: cabazes diferentes, períodos diferentes, critérios de recolha
          diferentes. É exatamente o tipo de divergência que o cursor de repercussão
          permite explorar aqui.
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div class="nota">
      <div class="tt">Porque é que a repercussão está a 40 % por defeito</div>
      A avaliação internacional de reduções de IVA na alimentação e na restauração —
      nomeadamente as experiências francesa (2009) e sueca — é
      <strong>consistentemente cética quanto à repercussão integral no preço</strong>:
      parte relevante do benefício é capturada na margem do operador. Os 40 % são um
      <strong>parâmetro de trabalho, não uma estimativa</strong>. Mova o cursor para
      testar a sensibilidade do resultado a esta hipótese.
    </div>
    """, unsafe_allow_html=True)

    editor = pd.DataFrame({
        "Classe": [f"{r.emoji} {r.classe}" for r in df_decomp.itertuples()],
        "Valor (€)": df_decomp["valor"].round(2),
        "Taxa atual (%)": df_decomp["iva_defeito"].astype(float),
        "Taxa do cenário (%)": df_decomp["iva_defeito"].astype(float),
    })

    taxa_forcada = CENARIOS[cenario][1]
    if taxa_forcada is not None:
        editor["Taxa do cenário (%)"] = float(taxa_forcada)

    # A chave do editor tem de variar com o cenário: caso contrário o Streamlit
    # mantém o estado do widget e as taxas do cenário nunca chegam à tabela.
    editado = st.data_editor(
        editor, use_container_width=True, hide_index=True,
        key=f"editor_iva_{cenario}",
        disabled=["Classe", "Valor (€)"],
        column_config={
            "Valor (€)": st.column_config.NumberColumn(format="%.2f"),
            "Taxa atual (%)": st.column_config.NumberColumn(
                min_value=0.0, max_value=30.0, step=0.5, format="%.1f"),
            "Taxa do cenário (%)": st.column_config.NumberColumn(
                min_value=0.0, max_value=30.0, step=0.5, format="%.1f"),
        },
    )

    taxas_atuais = dict(zip(df_decomp["codigo"], editado["Taxa atual (%)"]))
    taxas_cenario = dict(zip(df_decomp["codigo"], editado["Taxa do cenário (%)"]))

    sim = simular_iva(df_decomp, taxas_atuais, taxas_cenario, repercussao)
    agregados = st.number_input(
        "N.º de agregados familiares (para a extrapolação ilustrativa)",
        min_value=0, value=4_100_000, step=100_000,
    )
    res = resumo_iva(sim, valor_cabaz, vezes_ano, agregados)

    c = st.columns(5)
    c[0].metric("Novo valor do cabaz", euro(res["novo_valor"]),
                euro(res["efetivo"]) if abs(res["efetivo"]) > 0.005 else None)
    c[1].metric("Poupança por cabaz", euro(res["poupanca_cabaz"]),
                help=f"Efeito com repercussão integral: {euro(-res['mecanico'])}")
    c[2].metric("Poupança anual por agregado", euro(res["poupanca_ano"]))
    c[3].metric("Capturado na margem", euro(res["margem"]),
                f"{(1 - repercussao) * 100:.0f} % do efeito")
    c[4].metric("Receita de IVA por cabaz", euro(res["receita_cabaz"]),
                help=f"{euro(res['iva_antes'])} → {euro(res['iva_depois'])}")

    fig_rep = grafico_reparticao(sim)
    if fig_rep is not None:
        st.markdown("#### Como se reparte o benefício")
        st.plotly_chart(fig_rep, use_container_width=True)
    else:
        st.info("Defina um cenário diferente das taxas atuais para ver a repartição.")

    st.markdown("#### Ordens de grandeza a nível agregado")
    g1, g2 = st.columns(2)
    g1.metric("Poupança agregada anual",
              f"{res['poupanca_agregada_milhoes']:,.1f} M€".replace(",", " "))
    g2.metric("Variação de receita implícita",
              f"{res['receita_agregada_milhoes']:,.1f} M€".replace(",", " "))

    st.markdown("""
    <div class="nota perigo">
      <div class="tt">Isto não é uma estimativa de custo orçamental</div>
      É aritmética de ordens de grandeza. O cabaz de referência
      <strong>não representa a despesa alimentar total</strong> de um agregado
      (exclui produtos, canais e consumo fora de casa), nem os agregados são
      homogéneos. Uma estimativa de receita cessante exige a base tributável real
      por taxa — via Contas Nacionais, IDEF ou dados da Autoridade Tributária — e
      não se obtém por multiplicação.
    </div>
    """, unsafe_allow_html=True)

    with st.expander("Ver detalhe da simulação"):
        det = sim[["classe", "valor", "taxa_atual", "taxa_cenario",
                   "base", "mecanico", "efetivo", "margem", "novo_valor"]].copy()
        det.columns = ["Classe", "Valor (€)", "Taxa atual (%)", "Taxa cenário (%)",
                       "Base sem IVA (€)", "Efeito mecânico (€)",
                       "Efeito efetivo (€)", "Margem (€)", "Novo valor (€)"]
        st.dataframe(det.round(2), use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Descarregar simulação (CSV)",
            det.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            f"cabaz_simulacao_iva_{date.today()}.csv", "text/csv",
        )

# ==========================================================================
# ABA 4 — Comparação UE-27
# ==========================================================================
with aba4:
    st.markdown("#### Inflação alimentar comparada (IHPC, variação homóloga)")

    escolhidos = st.multiselect(
        "Países", options=list(PAISES.keys()),
        default=[p for p in PAISES_POR_DEFEITO if p in PAISES],
        format_func=lambda g: PAISES[g],
    )

    bench = dados["bench"]
    if not escolhidos or bench.empty:
        st.info("Selecione pelo menos um país.")
    else:
        fig = go.Figure()
        paleta = [VERDE, AZUL, DOURADO, VERMELHO, "#7a5ea8", "#c2681a",
                  "#0f8f9c", "#4a7c3f", "#8f4a6b", "#5a6b8f", "#a0568f", "#2980b9"]
        for i, geo in enumerate(escolhidos):
            serie = bench[bench["geo"] == geo].sort_values("time")
            if serie.empty:
                continue
            fig.add_trace(go.Scatter(
                x=[mes_pt(t) for t in serie["time"]], y=serie["valor"],
                name=PAISES[geo],
                line=dict(color=paleta[i % len(paleta)],
                          width=3.2 if geo == "PT" else 1.9,
                          dash="dot" if geo == "EU27_2020" else "solid"),
                hovertemplate="%{x}<br>%{y:.1f} %<extra>" + PAISES[geo] + "</extra>",
            ))
        fig.update_layout(height=420, margin=dict(t=20, b=40, l=10, r=10),
                          yaxis_title="Variação homóloga (%)",
                          legend=dict(orientation="h", y=1.12, x=0),
                          hovermode="x unified", plot_bgcolor="#fff")
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(gridcolor="#eef1f4", zerolinecolor="#cbd5e1")
        st.plotly_chart(fig, use_container_width=True)

        # --- ranking do último mês ---
        ultimo = bench["time"].max()
        ranking = bench[bench["time"] == ultimo].copy()
        ranking["pais"] = ranking["geo"].map(PAISES)
        ranking = ranking.dropna(subset=["pais"]).sort_values("valor", ascending=True)

        ue = ranking.loc[ranking["geo"] == "EU27_2020", "valor"]
        valor_ue = float(ue.iloc[0]) if not ue.empty else None

        st.markdown(f"""
        <div class="nota">
          <div class="tt">Como ler estes números</div>
          A <strong>variação homóloga</strong> compara o preço de um mês com o mesmo mês
          do ano anterior. «+4,2 %» significa que, em {mes_pt(ultimo)}, os alimentos
          custavam mais 4,2 % do que em {mes_pt(str(int(ultimo[:4]) - 1) + ultimo[4:])}.
          Não é o preço; é o <em>ritmo a que o preço está a subir</em>.
          <br><br>
          A <strong>posição relativa</strong> mostra esse ritmo lado a lado com os outros
          países. Estar acima da UE-27 significa que os preços estão a subir mais depressa
          aqui — não que sejam mais caros aqui. São coisas diferentes: um país pode ter
          preços altos a subir devagar, ou preços baixos a subir depressa.
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"#### Distância à média europeia em {mes_pt(ultimo)}")
        if valor_ue is not None:
            desvio = ranking.copy()
            desvio["gap"] = desvio["valor"] - valor_ue
            desvio = desvio[desvio["geo"] != "EU27_2020"].sort_values("gap")
            figd = go.Figure(go.Bar(
                y=desvio["pais"], x=desvio["gap"], orientation="h",
                marker_color=[VERDE if g == "PT" else
                              (VERMELHO if v > 0 else "#8fb3d0")
                              for g, v in zip(desvio["geo"], desvio["gap"])],
                text=[f"{v:+.1f} p.p.".replace(".", ",") for v in desvio["gap"]],
                textposition="outside",
                hovertemplate="%{y}: %{x:+.1f} p.p. face à UE-27<extra></extra>",
            ))
            figd.update_layout(
                height=max(300, 30 * len(desvio)),
                margin=dict(t=10, b=40, l=10, r=60),
                xaxis_title="Pontos percentuais acima (→) ou abaixo (←) da UE-27",
                plot_bgcolor="#fff", showlegend=False,
            )
            figd.update_xaxes(gridcolor="#eef1f4", zerolinecolor="#64748b", zerolinewidth=2)
            st.plotly_chart(figd, use_container_width=True)
            st.caption(
                "Cada barra é a diferença face à média da UE-27, em pontos percentuais. "
                "À direita da linha central: inflação alimentar mais rápida do que na UE. "
                "À esquerda: mais lenta. Portugal a verde."
            )

        st.markdown(f"#### Ordenação em {mes_pt(ultimo)}")
        fig2 = go.Figure(go.Bar(
            y=ranking["pais"], x=ranking["valor"], orientation="h",
            marker_color=[VERDE if g == "PT" else (AZUL if g == "EU27_2020" else "#b7c2ce")
                          for g in ranking["geo"]],
            text=[f"{v:.1f} %" for v in ranking["valor"]], textposition="outside",
            hovertemplate="%{y}: %{x:.1f} %<extra></extra>",
        ))
        fig2.update_layout(height=max(320, 30 * len(ranking)),
                           margin=dict(t=10, b=30, l=10, r=40),
                           xaxis_title="Variação homóloga (%)", plot_bgcolor="#fff")
        fig2.update_xaxes(gridcolor="#eef1f4", zerolinecolor="#cbd5e1")
        st.plotly_chart(fig2, use_container_width=True)

        if valor_ue is not None:
            tabela_b = ranking[["pais", "valor"]].copy()
            tabela_b["Face à UE-27 (p.p.)"] = (tabela_b["valor"] - valor_ue).round(1)
            tabela_b.columns = ["País", "Variação homóloga (%)", "Face à UE-27 (p.p.)"]
            st.dataframe(tabela_b.sort_values("Variação homóloga (%)", ascending=False),
                         use_container_width=True, hide_index=True)

# ==========================================================================
# ABA 5 — Metodologia e fontes
# ==========================================================================
with aba5:
    st.markdown("#### Metodologia e fontes")
    st.caption(
        "Documentação completa do método. A nota metodológica em anexo à ferramenta "
        "desenvolve estes pontos com as referências legais."
    )

    with st.expander("📘 O que é o IHPC — e porque não é o mesmo que o IPC", expanded=True):
        st.markdown("""
O **IHPC — Índice Harmonizado de Preços no Consumidor** é o índice de inflação construído
segundo metodologia comum a todos os Estados-Membros, precisamente para que os valores sejam
comparáveis entre países. Base legal: **Regulamento (UE) 2016/792**, desenvolvido pelo
Regulamento de Execução (UE) 2020/1148. Em inglês designa-se HICP.

Portugal produz **dois** índices, ambos calculados pelo INE a partir da mesma recolha de
preços, mas com âmbitos distintos:
        """)
        st.dataframe(pd.DataFrame([
            {"Índice": "IPC — Índice de Preços no Consumidor",
             "Para que serve": "Índice nacional: atualizações contratuais, indexação, leitura interna da inflação",
             "Âmbito": "Consumo das famílias residentes; inclui rendas imputadas"},
            {"Índice": "IHPC — Índice Harmonizado",
             "Para que serve": "Comparação entre Estados-Membros e política monetária do BCE",
             "Âmbito": "Consumo monetário no território (inclui não residentes); exclui rendas imputadas"},
        ]), use_container_width=True, hide_index=True)
        st.markdown(
            "As diferenças de âmbito produzem valores próximos mas não idênticos. "
            "**Esta ferramenta usa o IHPC** por ser a única base que permite comparar Portugal "
            "com os restantes Estados-Membros com garantia de que se mede a mesma coisa."
        )

    with st.expander("🧮 Como se calcula o IHPC"):
        st.markdown("""
O IHPC é um **índice de Laspeyres encadeado anualmente**. O cálculo tem dois níveis.

**Nível elementar** — sem ponderadores, combinam-se os relativos de preço, em regra por
média geométrica (fórmula de Jevons):
""")
        st.latex(r"I = \prod_i \left( \frac{p_{i,t}}{p_{i,0}} \right)^{1/n}")
        st.markdown("""
**Acima do nível elementar** — agregação ponderada, com encadeamento em dezembro do ano
anterior:
""")
        st.latex(r"I(m,y) = I(\text{Dez},y-1) \times \sum_i w_i^{\,y} \cdot \frac{I_i(m,y)}{I_i(\text{Dez},y-1)}")
        st.markdown("""
Os ponderadores seguem uma regra precisa, fixada no Regulamento de Execução (UE) 2020/1148:

1. Partem das **Contas Nacionais do ano y−2** — o último com dados de qualidade completa.
2. São **revistos para representar o ano y−1**, com toda a informação disponível.
3. São **atualizados a preços de dezembro de y−1**, para coincidir com o encadeamento.

Daqui decorre a propriedade essencial: **os ponderadores são revistos todos os anos**. É isso
que permite ao IHPC acompanhar alterações no padrão de consumo — quando as famílias trocam
novilho por frango, o ponderador da carne reflete-o no ano seguinte. Um cabaz de composição
fixa não o faz, e acumula por isso o chamado *viés de substituição*.

A variação homóloga obtém-se diretamente do índice:
""")
        st.latex(r"\pi(m) = \left[ \frac{I(m,y)}{I(m,y-1)} - 1 \right] \times 100")

    with st.expander("🔢 Os quatro passos desta ferramenta"):
        st.markdown("**1 · Âncora: quanto gasta o país em alimentação**")
        st.latex(r"\text{despesa mensal do agregado médio} = \frac{D(y)}{H \times 12}")
        st.caption("D(y) = despesa alimentar nacional anual (Contas Nacionais) · H = número de agregados")

        st.markdown("**2 · Atualização ao mês corrente**")
        st.latex(r"\text{valor atual} = \text{valor do ano-base} \times \frac{I(m)}{\bar{I}(y)}")
        st.caption("I(m) = índice do mês · Ī(y) = média anual do índice no ano-base")

        st.markdown("**3 · Ajustamento à composição do agregado**")
        st.latex(r"\text{despesa do agregado} = \text{valor atual} \times \frac{eq(A,C)}{eq(\bar{s})}")
        st.caption("A = adultos · C = crianças · s̄ = dimensão média nacional do agregado")

        st.markdown("**4 · Repartição por grupo de produto**")
        st.latex(r"V_i = \text{despesa total} \times \frac{w_i}{\sum_j w_j}")
        st.caption("wᵢ = ponderador oficial da classe i")

        st.markdown("**Contributo de cada grupo para o agravamento homólogo**")
        st.latex(r"\text{contributo}_i = V_i \cdot \frac{g_i}{1 + g_i}")
        st.markdown(
            "A soma dos contributos iguala exatamente a variação do total — a decomposição é "
            "**aditiva**, propriedade verificada por teste automático."
        )

    with st.expander("⚖️ Escalas de equivalência"):
        st.markdown(
            "Duas pessoas não gastam o dobro de uma: compra-se a granel, desperdiça-se menos, "
            "aproveitam-se sobras. As escalas traduzem essa partilha em coeficientes."
        )
        st.dataframe(pd.DataFrame([
            {"Escala": ESCALAS[k]["nome"], "1.º adulto": ESCALAS[k]["primeiro"],
             "Adulto adicional": ESCALAS[k]["adulto"], "Criança (<14)": ESCALAS[k]["crianca"],
             "Nota": ESCALAS[k]["nota"]}
            for k in ESCALAS
        ]), use_container_width=True, hide_index=True)
        st.latex(r"eq(A,C) = 1 + \alpha \cdot (A - 1) + \beta \cdot C")
        st.warning("""
**Porque não se usa a norma da UE por defeito.** A escala OCDE modificada é a norma europeia
para o *rendimento*, e foi construída para o consumo total, em que a partilha da habitação gera
fortes economias de escala. Na alimentação essas economias são bem mais fracas — não se partilha
uma refeição como se partilha um teto. Aplicá-la ao consumo alimentar **subestimaria** o custo
dos agregados maiores, que são justamente o grupo politicamente sensível.
        """)

    st.markdown("#### Origem dos dados")
    st.dataframe(pd.DataFrame([
        {"Elemento": "Ponderadores por classe", "Fonte": "Eurostat / INE",
         "Conjunto": "prc_hicp_inw", "O que mede": "Fração de cada mil euros de consumo total (‰)"},
        {"Elemento": "Índice de preços", "Fonte": "Eurostat / INE",
         "Conjunto": "prc_hicp_midx", "O que mede": "Nível do índice — não são euros"},
        {"Elemento": "Variação homóloga", "Fonte": "Eurostat / INE",
         "Conjunto": "prc_hicp_manr", "O que mede": "Subida face ao mesmo mês do ano anterior (%)"},
        {"Elemento": "Despesa alimentar (âncora)", "Fonte": "Eurostat / INE",
         "Conjunto": "nama_10_co3_p3", "O que mede": "Despesa efetiva em euros (Contas Nacionais)"},
        {"Elemento": "Dimensão do agregado", "Fonte": "Eurostat (EU-SILC)",
         "Conjunto": "ilc_lvph01", "O que mede": "N.º médio de pessoas por agregado"},
        {"Elemento": "Total de agregados", "Fonte": "Parâmetro do utilizador",
         "Conjunto": "—", "O que mede": "Divisor da despesa nacional"},
        {"Elemento": "Taxas de IVA", "Fonte": "Predefinidas, editáveis",
         "Conjunto": "CIVA, Lista I", "O que mede": "A validar por produto"},
        {"Elemento": "Repercussão", "Fonte": "Parâmetro do utilizador",
         "Conjunto": "—", "O que mede": "Hipótese, não estimativa"},
    ]), use_container_width=True, hide_index=True)

    st.info("""
**Nota sobre os ponderadores.** Somam 1 000 ‰ sobre **todo** o cabaz do IHPC — não sobre a
alimentação. As nove classes alimentares somam apenas o peso da alimentação no consumo total.
Por isso o cálculo normaliza pela soma das nove, e não pelos 1 000 ‰.
    """)

    st.markdown("#### Registo das ligações desta sessão")
    st.dataframe(pd.DataFrame(dados["registo"],
                              columns=["Dados pedidos", "Via de acesso usada",
                                       "N.º de observações"]),
                 use_container_width=True, hide_index=True)
    st.info("""
**«SDMX» não é um método de ponderação — é a via de acesso aos dados.**

SDMX (*Statistical Data and Metadata eXchange*) é a norma internacional de troca de dados
estatísticos, usada pelo Eurostat, INE, BCE e FMI. Aqui designa apenas **por que porta a
aplicação foi buscar os números**:

- **SDMX 2.1** — o filtro segue no próprio endereço, pelo que o Eurostat devolve exatamente as
  séries pedidas. É a via preferida.
- **API Statistics** — os filtros seguem como parâmetros. Usada se a primeira falhar.

Ambas devolvem **os mesmos números oficiais**. A via usada não afeta os resultados; consta aqui
apenas para diagnóstico.
    """)

    st.markdown("#### Limitações a declarar em qualquer uso")
    st.markdown("""
1. **A decomposição não é observação.** É uma imputação de um valor total por ponderadores
   oficiais; não substitui a recolha de preços produto a produto.
2. **Não há quantidades físicas.** A ferramenta mede despesa e variação de preço, não quilos
   nem litros. Para raciocinar em quantidades seria necessário o IDEF/INE ou dados de transação.
3. **Os preços são médias nacionais.** O índice resulta de recolha numa amostra de
   estabelecimentos de todo o país, ponderada por canal e região. Não corresponde ao preço de
   nenhuma insígnia: capta bem a variação; o nível de cada família oscila em torno da média.
4. **A âncora parte de uma média nacional.** Não distingue escalão de rendimento nem região.
5. **As escalas de equivalência são aproximações.** Construídas para o consumo total; o agregado
   médio é modelado como composto por adultos, porque a dimensão média é publicada sem
   decomposição etária. Daí a apresentação em intervalo.
6. **Desfasamento das Contas Nacionais.** A âncora assenta num ano com cerca de dois anos de
   desfasamento, atualizado por índice de preços.
7. **A correspondência COICOP → taxa de IVA é aproximada.** O Código do IVA classifica por
   produto (Lista I), não por classe COICOP.
8. **A repercussão é uma hipótese.** Qualquer resultado do simulador é condicional a esse
   parâmetro e deve ser apresentado como intervalo.
9. **Preço de prateleira não é preço pago.** Descontos de cartão e de talão não são
   integralmente captados.
10. **A extrapolação agregada é ilustrativa.** Não é uma estimativa de custo orçamental.
    """)

    st.warning("""
**Ressalva a confirmar nos metadados.** Os ponderadores do IHPC referem-se ao consumo *no
território* (inclui despesa de não residentes), enquanto a despesa das Contas Nacionais usada
como âncora pode estar em conceito nacional (residentes). Em Portugal, dado o peso do turismo,
a diferença não é trivial. Não afeta as variações, mas afeta o **nível** da âncora.
    """)

    st.markdown("#### Base legal e documentação")
    st.markdown("""
- [Regulamento (UE) 2016/792](https://eur-lex.europa.eu/legal-content/PT/TXT/?uri=CELEX%3A32016R0792) — quadro legal do IHPC
- Regulamento de Execução (UE) 2020/1148 — especificações metodológicas e técnicas
- [Eurostat — HICP methodology](https://ec.europa.eu/eurostat/statistics-explained/index.php/HICP_methodology)
- [Metadados do IHPC](https://ec.europa.eu/eurostat/cache/metadata/en/prc_hicp_esms.htm)
- [Eurostat — Derivação dos ponderadores](https://ec.europa.eu/eurostat/documents/10186/10693286/Derivation-of-HICP-weights-for-2022.pdf)
    """)

st.divider()
st.caption(RODAPE)
