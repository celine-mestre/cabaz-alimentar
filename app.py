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
from src.config import (AGREGADOS, AGREGADOS_ANO, AGREGADOS_CENSOS, AGREGADOS_FONTE,
                        COD_AGREGADOS,
                        DIMENSAO_RECUO, DIMENSAO_RECUO_FONTE,
                        AZUL, CLASSES, CODIGOS, COICOP_ALIMENTAR, DOURADO,
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

  .barra {{
    display: flex; align-items: center; gap: 11px;
    background: linear-gradient(120deg, {AZUL} 0%, #1a3f6f 30%, {VERDE} 70%, #0a5228 100%);
    border-bottom: 2px solid {VERMELHO}; border-radius: 8px;
    padding: 9px 15px; margin-bottom: 14px; color: #fff;
  }}
  .barra .sim {{
    width: 32px; height: 32px; border-radius: 50%; background: #fff;
    padding: 1px; flex: 0 0 32px; display: block;
  }}
  .barra .bt {{ display: flex; flex-direction: column; line-height: 1.25; }}
  .barra .bt strong {{ font-size: 11.5px; font-weight: 600; letter-spacing: .45px; }}
  .barra .bt span {{ font-size: 10px; opacity: .85; }}
  .barra .bd {{
    margin-left: auto; font-size: 14px; font-weight: 600; letter-spacing: -.2px;
    padding-left: 13px; border-left: 3px solid {DOURADO};
  }}
  @media (max-width: 640px) {{ .barra .bd {{ display: none; }} }}

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

    # Janela generosa para as fontes anuais e semestrais. Custa pouco em volume
    # e garante que, mesmo com atraso de publicação, há sempre uma observação —
    # a aplicação usa depois a mais recente de cada série.
    JANELA = 8

    registo = []

    pesos_df, via1 = eurostat.ponderadores(CODIGOS)
    registo.append(("Ponderadores", via1, len(pesos_df)))

    indice_df, via2 = eurostat.indice_precos(COICOP_ALIMENTAR, desde_indice)
    registo.append(("Índice de preços", via2, len(indice_df)))

    var_df, via3 = eurostat.variacoes(
        [COICOP_ALIMENTAR] + CODIGOS, list(PAISES.keys()), desde_variacao
    )
    registo.append(("Variações e UE-27", via3, len(var_df)))

    # Agregados especiais: separam choque conjuntural de inflação estrutural.
    try:
        agr_esp_df, via12 = eurostat.variacoes(
            COD_AGREGADOS, ["PT", "EU27_2020"], f"{ano - anos_historico}-01")
        registo.append(("Agregados especiais do índice", via12, len(agr_esp_df)))
    except Exception as exc:                                   # noqa: BLE001
        agr_esp_df, via12 = pd.DataFrame(), f"indisponível ({exc})"
        registo.append(("Agregados especiais do índice", via12, 0))

    # Âncora oficial em euros — Contas Nacionais (opcional: pode não estar
    # disponível para o último ano; a aplicação funciona sem ela).
    try:
        desp_df, via4 = eurostat.despesa_alimentar(ano - JANELA)
        registo.append(("Despesa alimentar (Contas Nacionais)", via4, len(desp_df)))
    except Exception as exc:                                   # noqa: BLE001
        desp_df, via4 = pd.DataFrame(), f"indisponível ({exc})"
        registo.append(("Despesa alimentar (Contas Nacionais)", via4, 0))

    try:
        dim_df, via5 = eurostat.dimensao_agregado(ano - JANELA)
        registo.append(("Dimensão média do agregado", via5, len(dim_df)))
    except Exception as exc:                                   # noqa: BLE001
        dim_df, via5 = pd.DataFrame(), f"indisponível ({exc})"
        registo.append(("Dimensão média do agregado", via5, 0))

    try:
        agr_df, via6 = eurostat.numero_agregados(ano - JANELA)
        registo.append(("N.º de agregados familiares", via6, len(agr_df)))
    except Exception as exc:                                   # noqa: BLE001
        agr_df, via6 = pd.DataFrame(), f"indisponível ({exc})"
        registo.append(("N.º de agregados familiares", via6, 0))

    # Nível de preços comparado — a codificação das categorias das PPP não é a
    # mesma do índice de preços, pelo que se tentam várias e se usa a primeira
    # que responda. Se nenhuma responder, o painel respetivo não é apresentado.
    pli_df, pli_cat = pd.DataFrame(), None
    for candidato in eurostat.PPP_CANDIDATOS_ALIMENTOS:
        try:
            tentativa, via7 = eurostat.nivel_precos(
                list(PAISES.keys()), candidato, ano - JANELA)
            if not tentativa.empty:
                pli_df, pli_cat = tentativa, candidato
                registo.append((f"Nível de preços ({candidato})", via7, len(tentativa)))
                break
        except Exception:                                      # noqa: BLE001
            continue
    if pli_df.empty:
        registo.append(("Nível de preços comparado", "indisponível", 0))

    # Esforço alimentar — coeficiente de Engel (alimentação / consumo total)
    # Os dois lados do coeficiente de Engel são obtidos em separado: se o
    # agregado total falhar, a despesa alimentar por país continua disponível.
    partes_engel = []
    try:
        tot_df, via8a = eurostat.despesa_total_consumo(list(PAISES.keys()), ano - JANELA)
        registo.append(("Consumo total das famílias", via8a, len(tot_df)))
        partes_engel.append(tot_df)
    except Exception as exc:                                   # noqa: BLE001
        registo.append(("Consumo total das famílias", f"indisponível ({exc})", 0))
    try:
        ali_df, via8b = eurostat.despesa_alimentar_paises(list(PAISES.keys()), ano - JANELA)
        registo.append(("Despesa alimentar por país", via8b, len(ali_df)))
        partes_engel.append(ali_df)
    except Exception as exc:                                   # noqa: BLE001
        registo.append(("Despesa alimentar por país", f"indisponível ({exc})", 0))
    engel_df = pd.concat(partes_engel, ignore_index=True) if len(partes_engel) == 2 else pd.DataFrame()

    try:
        sm_df, via9 = eurostat.salario_minimo(list(PAISES.keys()), ano - JANELA)
        registo.append(("Salário mínimo nacional", via9, len(sm_df)))
    except Exception as exc:                                   # noqa: BLE001
        sm_df, via9 = pd.DataFrame(), f"indisponível ({exc})"
        registo.append(("Salário mínimo nacional", via9, 0))

    # Rendimento das famílias: média e mediana. A média é a coerente com a
    # despesa (que também é uma média); a mediana fica disponível para
    # caracterizar o agregado do meio da distribuição.
    try:
        sme_df, via11 = eurostat.salario_medio(list(PAISES.keys()), ano - JANELA)
        registo.append(("Salário médio líquido", via11, len(sme_df)))
    except Exception as exc:                                   # noqa: BLE001
        sme_df, via11 = pd.DataFrame(), f"indisponível ({exc})"
        registo.append(("Salário médio líquido", via11, 0))

    rend_por_tipo = {}
    for indic, nome_indic in [("MEI_E", "médio"), ("MED_E", "mediano")]:
        try:
            df_r, via_r = eurostat.rendimento(list(PAISES.keys()), ano - JANELA, indic)
            registo.append((f"Rendimento {nome_indic} equivalente", via_r, len(df_r)))
            rend_por_tipo[indic] = df_r
        except Exception as exc:                               # noqa: BLE001
            registo.append((f"Rendimento {nome_indic} equivalente",
                            f"indisponível ({exc})", 0))

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

    # --- comparação europeia: todos os grupos, todos os países ---
    bench_todos = var_df.sort_values("time")
    bench = var_df[var_df["coicop"] == COICOP_ALIMENTAR].sort_values("time")

    # --- âncora oficial: despesa alimentar por agregado ---
    despesa_ano, despesa_valor = None, None
    if not desp_df.empty:
        recente = desp_df.sort_values("time").iloc[-1]
        despesa_ano, despesa_valor = str(recente["time"]), float(recente["valor"])

    # --- número de agregados: preferir o valor anual do Eurostat ---
    agregados_valor, agregados_ano, agregados_fonte = None, None, None
    if not agr_df.empty:
        rec_a = agr_df.sort_values("time").iloc[-1]
        candidato = int(round(float(rec_a["valor"]) * 1000))          # vem em milhares
        # Verificação de plausibilidade: um valor fora deste intervalo indica que
        # o conjunto devolvido não é o esperado (dimensão errada, unidade errada,
        # série trocada). Nesse caso recorre-se ao valor censitário, que é seguro.
        if 3_000_000 <= candidato <= 6_500_000:
            agregados_valor = candidato
            agregados_ano = str(rec_a["time"])
            agregados_fonte = "Eurostat / Inquérito ao Emprego (EU-LFS)"
        else:
            registo.append(
                ("N.º de agregados — verificação",
                 f"valor implausível ({candidato:,}); usado o dos Censos".replace(",", " "), 0)
            )

    dimensao_media, dimensao_ano = None, None
    if not dim_df.empty:
        rec = dim_df.sort_values("time").iloc[-1]
        dimensao_ano, dimensao_media = str(rec["time"]), float(rec["valor"])

    # --- coeficiente de Engel por país, ano mais recente comum ---
    engel = {}
    if not engel_df.empty:
        for geo in engel_df["geo"].unique():
            sub = engel_df[engel_df["geo"] == geo]
            tot = sub[sub["coicop"] == "TOTAL"].sort_values("time")
            ali = sub[sub["coicop"] == "CP011"].sort_values("time")
            if tot.empty or ali.empty:
                continue
            anos_comuns = sorted(set(tot["time"]) & set(ali["time"]))
            if not anos_comuns:
                continue
            a = anos_comuns[-1]
            t = float(tot[tot["time"] == a]["valor"].iloc[0])
            f = float(ali[ali["time"] == a]["valor"].iloc[0])
            if t > 0:
                engel[geo] = {"ano": a, "quota": f / t * 100,
                              "total": t, "alimentar": f}

    rendimento = {}
    for indic, df_r in rend_por_tipo.items():
        rendimento[indic] = {}
        for geo in df_r["geo"].unique():
            sub = df_r[df_r["geo"] == geo].sort_values("time")
            if not sub.empty:
                rendimento[indic][geo] = {"ano": str(sub["time"].iloc[-1]),
                                          "valor": float(sub["valor"].iloc[-1])}

    salario_med = {}
    if not sme_df.empty:
        for geo in sme_df["geo"].unique():
            sub = sme_df[sme_df["geo"] == geo].sort_values("time")
            if not sub.empty:
                salario_med[geo] = {"ano": str(sub["time"].iloc[-1]),
                                    "valor": float(sub["valor"].iloc[-1])}

    salario = {}
    if not sm_df.empty:
        for geo in sm_df["geo"].unique():
            sub = sm_df[sm_df["geo"] == geo].sort_values("time")
            if not sub.empty:
                salario[geo] = {"periodo": str(sub["time"].iloc[-1]),
                                "valor": float(sub["valor"].iloc[-1])}

    return {
        "agregados_especiais": agr_esp_df,
        "engel": engel,
        "rendimento": rendimento,
        "salario": salario,
        "salario_medio": salario_med,
        "pli": pli_df,
        "pli_cat": pli_cat,
        "agregados_valor": agregados_valor,
        "agregados_ano": agregados_ano,
        "agregados_fonte": agregados_fonte,
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
        "bench_todos": bench_todos,
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
        return {"valor": mensal_base, "ano_base": ano_base, "plausivel": True,
                "mes": None, "fator": 1.0, "base_mensal": mensal_base}

    do_ano = indice[indice["time"].str.startswith(str(ano_base))]
    if do_ano.empty:
        return {"valor": mensal_base, "ano_base": ano_base, "plausivel": True,
                "mes": None, "fator": 1.0, "base_mensal": mensal_base}

    media_base = float(do_ano["valor"].mean())
    ultimo = indice.sort_values("time").iloc[-1]
    fator = float(ultimo["valor"]) / media_base if media_base else 1.0

    resultado_valor = mensal_base * fator
    plausivel = 50.0 <= resultado_valor <= 3000.0

    return {
        "plausivel": plausivel,
        "valor": resultado_valor,
        "base_mensal": mensal_base,
        "ano_base": ano_base,
        "mes": str(ultimo["time"]),
        "fator": fator,
    }


# ==========================================================================
# Componentes visuais
# ==========================================================================
def csv_com_fonte(df: pd.DataFrame, titulo: str, dados: dict, extra=None) -> bytes:
    """
    Exporta em CSV com cabeçalho de proveniência, para que o ficheiro seja
    autoexplicativo fora da aplicação.
    """
    linhas = [
        f"# {titulo}",
        "# Produzido por: Unidade de Pesquisa e Estatisticas (UPE) - DSSD - Secretaria-Geral do Governo",
        "# Fonte dos dados: Eurostat (indice harmonizado de precos no consumidor e contas nacionais)",
        "# Conjuntos: prc_hicp_midx, prc_hicp_manr, prc_hicp_inw, nama_10_co3_p3, ilc_lvph01",
        f"# Ultimo mes disponivel: {dados.get('mes_variacoes') or '-'}",
        f"# Ponderadores de: {dados.get('ano_pesos') or '-'}",
        f"# Ancora de despesa: Contas Nacionais {dados.get('despesa_ano') or '-'}",
        f"# Extraido em: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    for chave, valor in (extra or []):
        linhas.append(f"# {chave}: {valor}")
    linhas += [
        "# Documento de trabalho interno - nao constitui posicao oficial da Secretaria-Geral do Governo.",
        "",
    ]
    corpo = df.to_csv(index=False, sep=";", decimal=",")
    return ("\n".join(linhas) + corpo).encode("utf-8-sig")


def cartao_classe(linha: pd.Series) -> str:
    var = linha["variacao"]
    cor_var = "#6b7280" if var is None else (VERMELHO if var > 0 else VERDE)
    quota = f"{linha['quota'] * 100:.1f}".replace(".", ",")
    if linha["contributo"] is not None:
        sinal = "encareceu" if linha["contributo"] > 0 else "baixou"
        contributo = (f"{sinal} <strong>{euro(abs(linha['contributo']))}</strong> "
                      "no último ano")
    else:
        contributo = "Aguarda dados"
    var_txt = "—" if var is None else f"{percentagem(var)} num ano"
    return f"""
    <div class="cartao" style="--c:{linha['cor']}">
      <div class="topo">
        <span class="emj">{linha['emoji']}</span>
        <span><span class="nm">{linha['classe']}</span><br>
        <span class="cd">COICOP {linha['codigo'][2:4]}.{linha['codigo'][4]}.{linha['codigo'][5]}</span></span>
      </div>
      <div class="vl">{euro(linha['valor'])}</div>
      <div class="ln">
        <span style="color:#6b7280">{quota} % da despesa</span>
        <span style="color:{cor_var};font-weight:600">{var_txt}</span>
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
    f'<img class="sim" src="data:image/png;base64,{LOGO}" alt="SGGov">' if LOGO else ""
)
st.markdown(f"""
<div class="barra">
  {_logo_html}
  <div class="bt">
    <strong>SECRETARIA-GERAL DO GOVERNO</strong>
    <span>Suporte à Decisão · {UNIDADE}</span>
  </div>
  <div class="bd">Despesa alimentar das famílias</div>
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

    # --- número de agregados: sempre o valor oficial ---
    if dados.get("agregados_valor"):
        agregados = int(dados["agregados_valor"])
        agr_fonte = f"{dados['agregados_fonte']}, {dados['agregados_ano']}"
    else:
        agregados = AGREGADOS_CENSOS
        agr_fonte = AGREGADOS_FONTE

    ancora = ancora_oficial(dados, agregados)
    if ancora is None:
        st.error(
            "Não foi possível calcular a despesa a partir das Contas Nacionais. "
            "Consulte o registo de ligações no separador Metodologia."
        )
        st.stop()

    media_agregado = float(ancora["valor"])
    valor_medio_agregado = media_agregado
    dim_media = dados.get("dimensao_media")

    if not ancora.get("plausivel", True):
        st.error(
            "⚠️ **Valor fora do intervalo plausível.** Verifique o registo de ligações "
            "no separador Metodologia. **Não use estes números.**"
        )

    st.caption("**Composição do agregado**")
    ca, cb = st.columns(2)
    adultos = ca.number_input(
        "Com 14+ anos", min_value=1, max_value=10, value=2, step=1,
        help=("Todas as pessoas com 14 ou mais anos, incluindo jovens dependentes. "
              "A partir dessa idade, a escala de equivalência atribui o mesmo peso "
              "alimentar — um jovem de 15 anos come como um adulto, mesmo que não "
              "aufira rendimento."))
    criancas = cb.number_input(
        "Menos de 14 anos", min_value=0, max_value=10, value=0, step=1,
        help=("14 anos é o limiar definido pelas próprias escalas de equivalência "
              "da OCDE e do Eurostat — não é a definição demográfica de criança. "
              "Ver separador Metodologia."))

    dim_efetiva = dim_media if dim_media else DIMENSAO_RECUO
    escala_chave = st.selectbox(
        "Escala de equivalência", options=list(ESCALAS.keys()), index=1,
        format_func=lambda k: ESCALAS[k]["nome"],
        help="Como se ajusta a despesa ao número de pessoas. Ver separador Metodologia.",
    )

    valor_cabaz = despesa_do_agregado(
        media_agregado, dim_efetiva, adultos, criancas, escala_chave)
    faixa = intervalo_agregado(media_agregado, dim_efetiva, adultos, criancas)

    # O rótulo tem de refletir o que a escala mede: pessoas com 14 ou mais anos
    # pesam como adultos, tenham ou não rendimento próprio.
    if criancas:
        composicao = (f"{adultos} com 14+ anos e {criancas} "
                      + ("menores de 14" if criancas > 1 else "menor de 14"))
    else:
        composicao = f"{adultos} pessoa{'s' if adultos > 1 else ''} com 14+ anos"
    pessoas = adultos + criancas
    ue = unidades_equivalentes(adultos, criancas, escala_chave)
    origem = (f"Contas Nacionais {ancora['ano_base']} · {composicao} · "
              f"escala {ESCALAS[escala_chave]['nome']}")
    vezes_ano = 12

    st.divider()
    st.metric(f"Despesa mensal — {composicao}", euro(valor_cabaz))
    st.caption(f"{pessoas} pessoa{'s' if pessoas > 1 else ''} · "
               f"intervalo entre escalas de {euro(faixa['minimo'])} a {euro(faixa['maximo'])}")

    with st.expander("Comparar as três escalas"):
        maior_que_media = pessoas > dim_efetiva
        st.dataframe(
            pd.DataFrame([
                {"Escala": ESCALAS[k]["nome"].split(" (")[0],
                 "Coeficientes": f"{ESCALAS[k]['primeiro']:.0f} / "
                                 f"{ESCALAS[k]['adulto']:.1f} / "
                                 f"{ESCALAS[k]['crianca']:.1f}".replace(".", ","),
                 "Despesa (€)": round(faixa["por_escala"][k], 2)}
                for k in ESCALAS
            ]), use_container_width=True, hide_index=True)

        st.markdown(f"""
**Porque é que a escala com coeficientes menores dá aqui um valor {'menor' if maior_que_media else 'maior'}?**

O ponto de partida é sempre o **agregado médio português — {('%.2f' % dim_efetiva).replace('.', ',')} pessoas**.
A escala não serve para calcular a despesa a partir do zero: serve para **ajustar** desse
agregado médio para o seu. E é aplicada aos **dois lados** do cálculo — ao seu agregado e ao
agregado médio que serve de referência.

Daí resulta um comportamento que à primeira vista surpreende:

| O seu agregado | Escala com economias de escala mais fortes dá… |
|---|---|
| **Menor** que {('%.2f' % dim_efetiva).replace('.', ',')} pessoas | valor **mais alto** |
| **Maior** que {('%.2f' % dim_efetiva).replace('.', ',')} pessoas | valor **mais baixo** |

A razão: coeficientes menores significam que **cada pessoa a mais custa menos**. Isso
comprime as diferenças entre agregados de dimensão diferente — todos se aproximam da média.
Um casal, sendo **menor** que a média, aproxima-se dela *por cima*; um casal com três filhos,
sendo **maior**, aproxima-se dela *por baixo*.

O ponto de viragem é exatamente a dimensão média. Com {pessoas} pessoa{'s' if pessoas > 1 else ''},
está **{'acima' if maior_que_media else 'abaixo'}** dela.
        """)
        st.caption(
            "É por isto que a aplicação apresenta sempre um intervalo: nenhuma das três escalas "
            "é a resposta certa para a alimentação, e a escolha entre elas altera o resultado "
            "em sentidos diferentes consoante a dimensão do agregado."
        )

    _agr_txt = f"{agregados:,}".replace(",", "\u00a0")
    _mes_txt = mes_pt(ancora["mes"]) if ancora["mes"] else "—"
    with st.expander("De onde vem este valor"):
        st.markdown(
            "Da **despesa alimentar de todas as famílias portuguesas** registada nas Contas "
            f"Nacionais, dividida pelo número de agregados ({_agr_txt}), atualizada ao mês "
            "corrente pelo índice oficial de preços e ajustada à composição indicada acima."
            "\n\n"
            f"**N.º de agregados:** {agr_fonte}  \n"
            f"**Base de despesa:** Contas Nacionais {ancora['ano_base']}, a preços de {_mes_txt}"
        )

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

from contextlib import contextmanager


@contextmanager
def painel(nome: str):
    """
    Isola cada separador. Se algo falhar — um conjunto de dados com estrutura
    inesperada, um estado de sessão preso de uma versão anterior — o erro fica
    contido nesse separador, com indicação do que fazer, em vez de derrubar a
    aplicação inteira.
    """
    try:
        yield
    except Exception as exc:                                   # noqa: BLE001
        st.error(
            f"**Não foi possível apresentar «{nome}».**\n\n"
            f"`{type(exc).__name__}: {exc}`\n\n"
            "Os restantes separadores continuam a funcionar. Passos a tentar, por esta ordem:\n"
            "1. **Recarregar do Eurostat** na barra lateral — limpa a cache de dados;\n"
            "2. **Recarregar a página** com Ctrl+F5 — limpa o estado da sessão;\n"
            "3. Consultar o **registo de ligações** no separador Metodologia, para ver "
            "se algum conjunto de dados falhou."
        )


aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "🛒 Cabaz e composição", "📈 Histórico", "🧾 Simulador de IVA",
    "🇪🇺 Comparação UE-27", "📚 Metodologia e fontes",
])

# ==========================================================================
# ABA 1 — Cabaz e composição
# ==========================================================================
with aba1:
    with painel("Despesa e composição"):
        colunas = st.columns(5)
        colunas[0].metric(f"Despesa mensal — {composicao}", euro(valor_cabaz), help=origem)
        if resumo["contributo_total"] is not None:
            colunas[1].metric("Agravamento nos últimos 12 meses", euro(resumo["contributo_total"]),
                              percentagem(resumo["variacao_implicita"]))
            colunas[2].metric("Despesa há 12 meses", euro(resumo["valor_ha_um_ano"]))
            if resumo["maior"]:
                maior = resumo["maior"]
                colunas[3].metric(f"{maior['emoji']} Maior contributo",
                                  euro(maior["contributo"]),
                                  percentagem(maior["variacao"]))
        colunas[4].metric("Equivalente anual", euro(valor_cabaz * vezes_ano))

        dim_txt = ('%.1f' % dim_efetiva).replace('.', ',')
        r1, r2, r3 = st.columns([1, 1, 2])
        r1.metric(f"Agregado médio nacional ({dim_txt} pessoas)",
                  euro(valor_medio_agregado),
                  help="Valor de referência antes de qualquer ajustamento de composição.")
        r2.metric("Equivalente anual", euro(valor_medio_agregado * 12))
        eng_pt = (dados.get("engel") or {}).get("PT")
        if eng_pt:
            r3.metric("Do que as famílias gastam, vai para comida",
                      f"{eng_pt['quota']:.1f} %".replace(".", ","),
                      help=(f"Coeficiente de Engel, {eng_pt['ano']}. Quanto do consumo total "
                            "das famílias portuguesas vai para comida. Comparação europeia "
                            "no separador UE-27."))
        else:
            r3.markdown(
            f"<div style='padding-top:14px;font-size:12.5px;color:#4a4a48'>"
            f"É este o ponto de partida do cálculo: a despesa alimentar de um agregado "
            f"com a dimensão média portuguesa ({dim_txt} pessoas). Os valores em cima "
            f"estão ajustados para <strong>{composicao}</strong>.</div>",
            unsafe_allow_html=True)

        st.info("""
    **Como ler os cartões.** O valor grande é quanto da despesa mensal vai para esse grupo.
    A percentagem à direita é a **variação homóloga** — de quanto os preços desse grupo subiram
    face ao **mesmo mês do ano anterior** (não face ao mês anterior). A linha de baixo mostra o
    **contributo**: quantos euros desse aumento se devem a esse grupo em concreto. A soma dos
    contributos de todos os grupos dá exatamente o agravamento total dos últimos 12 meses.
        """)

        for inicio in range(0, len(df_decomp), 3):
            cols = st.columns(3)
            for col, (_, linha) in zip(cols, df_decomp.iloc[inicio:inicio + 3].iterrows()):
                col.markdown(cartao_classe(linha), unsafe_allow_html=True)

        st.write("")
        esq, dir_ = st.columns([1, 1])
        with esq:
            st.markdown("**Peso de cada grupo na despesa**")
            st.caption("Fração da despesa alimentar mensal que vai para cada tipo de produto.")
            st.plotly_chart(grafico_donut(df_decomp), use_container_width=True)
        with dir_:
            st.markdown("**Quanto cada grupo pesou no agravamento**")
            st.caption("Euros de aumento nos últimos 12 meses atribuíveis a cada grupo.")
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

        # ---- esforço do agregado escolhido ----
        st.divider()
        st.markdown(f"#### Quanto pesa no orçamento — {composicao}")

        rendimentos = dados.get("rendimento") or {}
        sm_pt = (dados.get("salario") or {}).get("PT")
        sme_pt = (dados.get("salario_medio") or {}).get("PT")
        tem_rend = any(rendimentos.get(k, {}).get("PT") for k in ("MEI_E", "MED_E"))

        if not tem_rend and not sm_pt and not sme_pt:
            st.info(
                "Os indicadores de rendimento não estão disponíveis nesta sessão. "
                "Consulte o registo de ligações no separador Metodologia."
            )
        else:
            ca_, cb_ = st.columns([1, 2])
            with ca_:
                trabalhadores = st.number_input(
                    "Quantos auferem rendimento", min_value=1, max_value=int(adultos),
                    value=min(int(adultos), 2), step=1,
                    help=("Das pessoas com 14 ou mais anos, quantas auferem "
                          "efetivamente rendimento. Jovens dependentes, estudantes "
                          "e pessoas sem rendimento próprio não contam — mas "
                          "continuam a pesar na despesa alimentar."),
                )
                dependentes = int(adultos) - int(trabalhadores)
            with cb_:
                st.markdown(
                    f"<div style='padding-top:26px;font-size:12.5px;color:#4a4a48'>"
                    f"<strong>{pessoas}</strong> pessoa{'s' if pessoas > 1 else ''} a "
                    f"alimentar · <strong>{trabalhadores}</strong> "
                    + ("auferem" if trabalhadores > 1 else "aufere")
                    + " rendimento"
                    + (f" · <strong>{dependentes}</strong> com 14+ anos sem rendimento próprio"
                       if dependentes else "")
                    + (f" · <strong>{criancas}</strong> com menos de 14 anos"
                       if criancas else "")
                    + f"<br>Despesa alimentar mensal: <strong>{euro(valor_cabaz)}</strong>."
                    "</div>",
                    unsafe_allow_html=True)

                if dependentes:
                    st.warning(f"""
    **{dependentes} pessoa{'s' if dependentes > 1 else ''} com 14 ou mais anos sem rendimento
    próprio.** Adolescentes, estudantes ou outros dependentes **comem como adultos** — a escala de
    equivalência atribui-lhes o mesmo peso alimentar — mas **não trazem receita**. É a composição
    em que o esforço alimentar é mais elevado, e a que os indicadores médios menos revelam.
                    """)

            st.caption(
                "⚠️ Estes valores são **limites superiores** — despesa e rendimento vêm de "
                "fontes com bases estatísticas diferentes. Explicação em «O que estes números "
                "assumem», no fim desta secção."
            )

            # --- construir as referências disponíveis ---
            refs = []
            indic_r = None
            if tem_rend:
                disponiveis = [k for k in ("MEI_E", "MED_E")
                               if rendimentos.get(k, {}).get("PT")]
                indic_r = "MEI_E" if "MEI_E" in disponiveis else disponiveis[0]
                r = rendimentos[indic_r]["PT"]
                ue_ocde = unidades_equivalentes(adultos, criancas, "ocde_modificada")
                refs.append({
                    "ref": "Rendimento das famílias (EU-SILC)",
                    "detalhe": (f"{'Médio' if indic_r == 'MEI_E' else 'Mediano'} equivalente "
                                f"{r['ano']} × {('%.2f' % ue_ocde).replace('.', ',')} unidades"),
                    "mensal": r["valor"] * ue_ocde / 12,
                    "natureza": "líquido",
                })
            if sme_pt:
                refs.append({
                    "ref": f"{trabalhadores} × salário médio",
                    "detalhe": f"Remuneração média anual, bruta, {sme_pt['ano']}",
                    "mensal": sme_pt["valor"] * trabalhadores / 12,
                    "natureza": "bruto",
                })
            if sm_pt:
                refs.append({
                    "ref": f"{trabalhadores} × salário mínimo",
                    "detalhe": f"Valor legal bruto, {sm_pt['periodo']}",
                    "mensal": sm_pt["valor"] * trabalhadores,
                    "natureza": "bruto",
                })

            for r in refs:
                r["esforco"] = valor_cabaz / r["mensal"] * 100 if r["mensal"] else None

            tab_r = pd.DataFrame([{
                "Referência": r["ref"],
                "Rendimento mensal": euro(r["mensal"]),
                "Esforço alimentar": (f"{r['esforco']:.1f} %".replace(".", ",")
                                      if r["esforco"] is not None else "—"),
                "Natureza": r["natureza"],
                "Detalhe": r["detalhe"],
            } for r in refs])
            st.dataframe(tab_r, use_container_width=True, hide_index=True)

            figR = go.Figure(go.Bar(
                y=[r["ref"] for r in refs],
                x=[r["esforco"] for r in refs], orientation="h",
                marker_color=[VERDE if r["natureza"] == "líquido" else DOURADO
                              for r in refs],
                text=[f"{r['esforco']:.1f} %".replace(".", ",") for r in refs],
                textposition="outside",
                hovertemplate="%{y}: %{x:.1f} % do rendimento<extra></extra>"))
            figR.update_layout(height=max(200, 60 * len(refs)),
                               margin=dict(t=20, b=40, l=10, r=70),
                               xaxis_title="Fatia do rendimento absorvida pela alimentação (%)",
                               plot_bgcolor="#fff", showlegend=False)
            figR.update_xaxes(gridcolor="#eef1f4")
            st.plotly_chart(figR, use_container_width=True)

            st.info(
                "**Sobre o cenário do salário mínimo.** Não é o agregado típico — é o **limiar "
                "inferior** da distribuição. Mas não é caso raro: cerca de um quarto dos "
                "trabalhadores portugueses aufere a remuneração mínima, e é precisamente aí "
                "que a pressão alimentar mais aperta. Serve para dimensionar o pior caso "
                "plausível, não para caracterizar a generalidade das famílias."
            )
            st.caption(
                "**Verde:** rendimento **líquido** — depois de impostos e contribuições. "
                "**Dourado:** valores **brutos** — salário médio e salário mínimo, antes de "
                "descontos. O rendimento efetivamente disponível é inferior, pelo que o esforço "
                "real sobre eles é **superior** ao apresentado. Verde e dourado não são "
                "diretamente comparáveis entre si."
            )

            with st.expander("⚠️ O que estes números assumem — leitura obrigatória"):
                st.error("""
**São limites superiores, não estimativas.** O **numerador** — a despesa alimentar — vem das
**Contas Nacionais**; o **denominador** — o rendimento — vem do **EU-SILC**. São universos
estatísticos diferentes: as Contas Nacionais incluem rendas imputadas, consumo de instituições
sem fins lucrativos e consumo no território, incluindo o de não residentes; o EU-SILC mede
rendimento monetário líquido dos residentes.

O consumo por agregado das Contas Nacionais é estruturalmente **cerca de 1,8 vezes** o
rendimento do EU-SILC — rácio que implicaria taxa de poupança fortemente negativa.
**Combinar as duas bases sobrestima o esforço.**

Leia as **diferenças entre composições** e a **direção** como informativas; o **nível** como
majorante.
                """)
                st.markdown(f"""
    **1 · As crianças não auferem rendimento.** O número de salários multiplica-se pelos
    **adultos com rendimento** indicados acima, nunca pelo total de pessoas. Um casal com dois
    filhos e dois salários continua a ter dois salários — mas quatro pessoas a alimentar, e é
    essa assimetria que faz o esforço subir.

    **2 · Bruto e líquido não se misturam.** Só o **rendimento do EU-SILC** é líquido — já
    descontados impostos e contribuições, e somadas as prestações. O **salário médio** e o
    **salário mínimo** são **brutos**: é o que consta do contrato ou do diploma, antes de
    qualquer desconto. Como o rendimento efetivamente disponível é inferior aos valores brutos,
    o esforço real sobre eles é **superior** ao que aqui aparece.

    **3 · O agregado está num valor central da distribuição.** Agregados abaixo dele têm esforço
    **superior** ao apresentado — e é justamente aí que a pressão alimentar mais se faz sentir.
    Uma medida por escalão de rendimento exigiria o IDEF/INE ou microdados do EU-SILC.

    **4 · As três escalas cruzam-se na dimensão média — e é isso que explica o resultado
    contraintuitivo.** Ver o gráfico logo abaixo deste bloco.

    **5 · Numerador e denominador usam escalas diferentes.** A despesa alimentar é ajustada pela
    escala que escolheu na barra lateral (**{ESCALAS[escala_chave]["nome"].split(" (")[0]}**); o
    rendimento do EU-SILC tem de usar a **OCDE modificada**, que é a que esse inquérito aplica.
    A consequência é mensurável:

    | Escala usada na despesa | 1 adulto | Casal | Casal + 2 |
    |---|---|---|---|
    | OCDE modificada (igual à do rendimento) | 25,9 % | 25,9 % | 25,9 % |
    | OCDE original | 22,3 % | 25,2 % | 28,6 % |
    | Per capita | 18,4 % | 24,5 % | 35,0 % |

    *(valores ilustrativos, com dados de referência)*

    Se as duas escalas coincidirem, **o esforço é constante** seja qual for a composição — ambos
    os lados escalam de forma idêntica. A subida com o número de pessoas resulta, portanto, da
    **diferença entre as escalas**. Isso não invalida a leitura, porque a alimentação tem
    economias de escala genuinamente mais fracas do que o consumo total; mas a **magnitude**
    depende da escala escolhida.

    **Como usar:** leia a **direção** como robusta e o **valor exato** como condicional. Teste
    sempre a sensibilidade mudando a escala na barra lateral.
                """)

            # ---- gráfico do cruzamento das escalas ----
            with st.expander("📐 Porque é que as escalas dão resultados diferentes — e cruzam"):
                st.markdown(f"""
Cada escala responde à mesma pergunta de forma diferente: **quanto custa cada pessoa a mais?**

| Escala | 1.ª pessoa | Cada pessoa a mais |
|---|---|---|
| Per capita | 1,0 | **1,0** — sem partilha |
| OCDE original | 1,0 | **0,7** — desconto moderado |
| OCDE modificada | 1,0 | **0,5** — desconto forte |

O que confunde: **todas partem do mesmo sítio** — a despesa do agregado médio português, com
**{('%.2f' % dim_efetiva).replace('.', ',')} pessoas**. A escala não calcula do zero: distribui
a partir dessa referência. Por isso **as três cruzam-se exatamente nessa dimensão**.
                """)

                tam = [1, 1.5, 2, 2.5, 3, 4, 5, 6]
                figS = go.Figure()
                cores_s = {"per_capita": "#7a5ea8", "ocde_original": VERDE,
                           "ocde_modificada": DOURADO}
                for chave in ESCALAS:
                    e_ = ESCALAS[chave]
                    eq_med = e_["primeiro"] + e_["adulto"] * (max(dim_efetiva, 1.0) - 1)
                    por_unidade = valor_medio_agregado / eq_med if eq_med else 0
                    ys = [por_unidade * (e_["primeiro"] + e_["adulto"] * (n - 1)) for n in tam]
                    figS.add_trace(go.Scatter(
                        x=tam, y=ys, name=e_["nome"].split(" (")[0],
                        line=dict(color=cores_s[chave], width=2.6),
                        hovertemplate="%{x} pessoas: %{y:.0f} €<extra>"
                                      + e_["nome"].split(" (")[0] + "</extra>"))
                figS.add_vline(
                    x=dim_efetiva, line_width=2, line_dash="dash", line_color="#64748b",
                    annotation_text=f"agregado médio: {('%.2f' % dim_efetiva).replace('.', ',')}",
                    annotation_position="top")
                figS.update_layout(height=340, margin=dict(t=46, b=40, l=10, r=10),
                                   xaxis_title="Pessoas no agregado (todas com 14+ anos)",
                                   yaxis_title="Despesa alimentar mensal (€)",
                                   legend=dict(orientation="h", y=1.22, x=0),
                                   hovermode="x unified", plot_bgcolor="#fff")
                figS.update_xaxes(gridcolor="#eef1f4")
                figS.update_yaxes(gridcolor="#eef1f4")
                st.plotly_chart(figS, use_container_width=True)

                st.success("""
**A leitura do gráfico — é isto que responde à dúvida.**

**À esquerda do cruzamento**, agregados **menores** que a média: a OCDE modificada dá valores
**mais altos**. Se cada pessoa a mais custa pouco (0,5), então ter menos gente do que a média
**poupa pouco** — fica-se perto do valor médio. Na per capita, em que cada pessoa vale a
totalidade, ter menos gente **desconta muito mais**.

**À direita**, agregados **maiores**: inverte-se. Se cada pessoa a mais custa pouco, acrescentar
gente **aumenta pouco** — e a OCDE modificada passa a dar os valores mais baixos.

**Em resumo:** desconto forte **comprime** as diferenças, aproximando todos os agregados da
média; desconto fraco **amplifica-as**. O cruzamento está sempre na dimensão média, porque é aí
que não há nada a descontar nem a acrescentar.
                """)


        # ------- blocos recolhíveis lado a lado, para reduzir o deslocamento -------
        e1, e2, e3 = st.columns(3)

        with e1.expander("🧮 Como é calculado"):
            st.markdown("""
    **1 ·** Das Contas Nacionais vem a despesa anual de todas as famílias em produtos
    alimentares. Divide-se pelo número de agregados e por doze.

    **2 ·** O valor é trazido ao mês corrente pelo índice oficial de preços.

    **3 ·** Ajusta-se à composição do agregado pela escala de equivalência.

    **4 ·** Reparte-se pelos nove grupos com os ponderadores oficiais do índice.

    As fórmulas completas estão no separador **Metodologia**.
            """)
            st.warning(
                "**Não é um cabaz de compras.** Não há quilos nem litros: há euros e variações "
                "de preço. E os preços são médias nacionais do INE, não de uma insígnia concreta."
            )

        with e2.expander("👥 Comparar composições"):
            comps = [(1, 0, "1 adulto"), (2, 0, "Casal"), (1, 1, "Monoparental + 1"),
                     (1, 2, "Monoparental + 2"), (2, 1, "Casal + 1 criança"),
                     (2, 2, "Casal + 2 crianças"), (2, 3, "Casal + 3 crianças")]
            dm = dados.get("dimensao_media") or DIMENSAO_RECUO
            linhas_c = []
            for a, c, rot in comps:
                iv = intervalo_agregado(valor_medio_agregado, dm, a, c)
                linhas_c.append({
                    "Composição": rot, "Pessoas": a + c,
                    "Central (€)": round(despesa_do_agregado(
                        valor_medio_agregado, dm, a, c, "ocde_original"), 2),
                    "Mín. (€)": round(iv["minimo"], 2),
                    "Máx. (€)": round(iv["maximo"], 2),
                })
            st.dataframe(pd.DataFrame(linhas_c), use_container_width=True, hide_index=True)
            st.caption(
                f"Agregado médio nacional: {('%.2f' % dm).replace('.', ',')} pessoas. "
                "O intervalo resulta das diferentes escalas de equivalência."
            )

        with e3.expander("📋 Tabela detalhada"):
            tabela = df_decomp[["codigo", "classe", "ponderador", "quota",
                                "valor", "variacao", "contributo"]].copy()
            tabela.columns = ["Código", "Grupo", "Ponderador (‰)", "Quota",
                              "Valor (€)", "Variação (%)", "Contributo (€)"]
            st.dataframe(tabela, use_container_width=True, hide_index=True,
                         column_config={
                             "Quota": st.column_config.ProgressColumn(
                                 "Quota", format="%.1f%%", min_value=0, max_value=1),
                             "Valor (€)": st.column_config.NumberColumn(format="%.2f"),
                             "Variação (%)": st.column_config.NumberColumn(format="%.1f"),
                             "Contributo (€)": st.column_config.NumberColumn(format="%.2f"),
                             "Ponderador (‰)": st.column_config.NumberColumn(format="%.1f"),
                         })
            st.download_button(
                "⬇️ CSV", csv_com_fonte(tabela, "Decomposicao por grupo de produto", dados,
                                        extra=[("Composicao do agregado", composicao),
                                               ("Escala", ESCALAS[escala_chave]["nome"])]),
                f"despesa_alimentar_decomposicao_{date.today()}.csv", "text/csv",
                use_container_width=True)

    # ==========================================================================
    # ABA 2 — Histórico
    # ==========================================================================
with aba2:
    with painel("Histórico"):
        st.markdown("#### Índice de preços dos produtos alimentares — Portugal")

        base = dados.get("base_indice") or "—"
        st.info(f"""
    **Em que consiste o índice.** Não são euros. É um número que mede o **nível dos preços**
    relativamente a um ano de referência, ao qual se atribui o valor 100. A base atualmente em
    vigor é **{base}**: se o índice estiver em 118, os preços dos produtos alimentares estão
    18 % acima do que estavam nesse ano de referência.

    O índice **não diz quanto custa** um cabaz — diz de quanto os preços se afastaram do
    ponto de partida. É por isso que a despesa em euros do primeiro separador precisa de uma
    âncora nas Contas Nacionais: o índice sozinho nunca daria um valor em euros.

    A **variação homóloga** (linha vermelha) é derivada do índice: compara cada mês com o mesmo
    mês do ano anterior.
        """)

        if dados["indice_pt"].empty:
            st.info("Sem série de índices disponível.")
            periodos, inicio_sel, fim_sel = [], None, None
        else:
            periodos = sorted(dados["indice_pt"]["time"].unique())
            pre = periodos[-25] if len(periodos) > 25 else periodos[0]
            inicio_sel, fim_sel = st.select_slider(
                "Intervalo a apresentar",
                options=periodos, value=(pre, periodos[-1]),
                format_func=mes_pt,
            )
            st.caption(
                f"A mostrar de **{mes_pt(inicio_sel)}** a **{mes_pt(fim_sel)}** — "
                f"{periodos.index(fim_sel) - periodos.index(inicio_sel) + 1} meses. "
                "Arraste as extremidades para alterar."
            )

            idx_sel = dados["indice_pt"][
                (dados["indice_pt"]["time"] >= inicio_sel) &
                (dados["indice_pt"]["time"] <= fim_sel)]
            var_sel = dados["var_pt"][
                (dados["var_pt"]["time"] >= inicio_sel) &
                (dados["var_pt"]["time"] <= fim_sel)]

            st.plotly_chart(
                grafico_historico(idx_sel, var_sel, len(idx_sel)),
                use_container_width=True,
            )

            if len(idx_sel) >= 2:
                acum = (idx_sel["valor"].iloc[-1] / idx_sel["valor"].iloc[0] - 1) * 100
                st.info(
                    f"**Variação acumulada no intervalo escolhido: {percentagem(acum)}** — "
                    f"de {mes_pt(inicio_sel)} a {mes_pt(fim_sel)}. "
                    "É frequentemente a leitura mais eloquente: a taxa homóloga de um mês "
                    "isolado diz pouco; o acumulado desde uma data de referência diz muito."
                )

        var_pt = dados["var_pt"]
        if not var_pt.empty and inicio_sel is not None:
            janela = var_pt[(var_pt["time"] >= inicio_sel) &
                            (var_pt["time"] <= fim_sel)]["valor"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Variação mais recente", percentagem(var_pt["valor"].iloc[-1]),
                      help=f"Mês de referência: {mes_pt(var_pt['time'].iloc[-1])}")
            if len(janela):
                c2.metric("Média do intervalo", percentagem(janela.mean()))
                c3.metric("Máximo do intervalo", percentagem(janela.max()))
                c4.metric("Mínimo do intervalo", percentagem(janela.min()))

        st.caption(
            "Frequência mensal — a mais fina publicada por fonte oficial. Existem séries semanais "
            "de cabazes publicadas por entidades privadas, mas não são dados oficiais nem têm "
            "acesso automático, e as variações semanais são muito voláteis por efeitos de base."
        )

        # ---------- o que está por trás da inflação alimentar ----------
        agr_esp = dados.get("agregados_especiais")
        if agr_esp is not None and not agr_esp.empty:
            st.divider()
            st.markdown("#### O que está por trás da subida")
            st.info("""
    A alimentação não é um bloco homogéneo. **Os frescos e os transformados obedecem a lógicas
    diferentes** — e distingui-los muda a resposta de política:

    - **Não transformados** (carne, peixe, fruta, legumes) reagem a clima, sazonalidade e custos de
      transporte. Uma subida aqui é tipicamente **choque de oferta**: passa, mas dói no imediato.
    - **Transformados** (pão, laticínios, conservas) refletem custos de produção e distribuição já
      incorporados. Uma subida aqui tende a ser **mais persistente**.

    Um choque de oferta em frescos não se combate com os mesmos instrumentos que uma inflação
    instalada nos transformados. Daí que a decomposição não seja um detalhe técnico.
            """)

            pt_esp = agr_esp[agr_esp["geo"] == "PT"]
            meses_esp = sorted(pt_esp["time"].unique())
            if inicio_sel is not None:
                meses_esp = [m for m in meses_esp if inicio_sel <= m <= fim_sel]

            so_alim = st.toggle(
                "Mostrar também os agregados de enquadramento", value=False,
                help=("Inflação geral e subjacente. Não são alimentação — servem para situar "
                      "a subida alimentar no conjunto dos preços."))
            visiveis = [a for a in AGREGADOS
                        if so_alim or a["grupo"] == "alimentacao"]

            if visiveis and meses_esp:
                figA = go.Figure()
                for a in visiveis:
                    sub = pt_esp[pt_esp["coicop"] == a["cod"]].set_index("time")["valor"]
                    if sub.empty:
                        continue
                    figA.add_trace(go.Scatter(
                        x=[mes_pt(m) for m in meses_esp],
                        y=[sub.get(m) for m in meses_esp],
                        name=a["nome"],
                        line=dict(color=a["cor"], width=a["larg"],
                                  dash="dot" if a["grupo"] == "enquadramento" else "solid"),
                        hovertemplate="%{x}<br>%{y:.1f} %<extra>" + a["nome"] + "</extra>"))
                figA.update_layout(height=400, margin=dict(t=20, b=40, l=10, r=10),
                                   yaxis_title="Variação homóloga (%)",
                                   legend=dict(orientation="h", y=1.16, x=0),
                                   hovermode="x unified", plot_bgcolor="#fff")
                figA.update_xaxes(showgrid=False)
                figA.update_yaxes(gridcolor="#eef1f4", zerolinecolor="#cbd5e1")
                st.plotly_chart(figA, use_container_width=True)
                if so_alim:
                    st.caption("A tracejado, os agregados de enquadramento — não são alimentação.")

                ult_esp = meses_esp[-1]
                linhas_a = []
                for a in visiveis:
                    sub = pt_esp[(pt_esp["coicop"] == a["cod"]) & (pt_esp["time"] == ult_esp)]
                    if sub.empty:
                        continue
                    ue_sub = agr_esp[(agr_esp["geo"] == "EU27_2020") &
                                     (agr_esp["coicop"] == a["cod"]) &
                                     (agr_esp["time"] == ult_esp)]
                    linhas_a.append({
                        "": ("🍽️" if a["grupo"] == "alimentacao" else "📊"),
                        "Agregado": a["nome"],
                        "Portugal (%)": round(float(sub["valor"].iloc[0]), 1),
                        "UE-27 (%)": (round(float(ue_sub["valor"].iloc[0]), 1)
                                      if not ue_sub.empty else None),
                        "Para que serve": a["porque"],
                    })
                if linhas_a:
                    st.dataframe(pd.DataFrame(linhas_a), use_container_width=True, hide_index=True)
                    st.caption(
                        f"Variação homóloga em {mes_pt(ult_esp)}. 🍽️ componentes da alimentação · "
                        "📊 agregados de enquadramento, que não são alimentação."
                    )
                    st.download_button(
                        "⬇️ Descarregar (CSV com fonte)",
                        csv_com_fonte(pd.DataFrame(linhas_a).drop(columns=[""]),
                                      "Decomposicao da inflacao alimentar", dados,
                                      extra=[("Mes de referencia", ult_esp)]),
                        f"despesa_alimentar_decomposicao_{date.today()}.csv", "text/csv")

        serie = dados["indice_pt"][["time", "valor"]].rename(
            columns={"time": "Período", "valor": f"Índice ({base})"})
        var_tab = dados["var_pt"][["time", "valor"]].rename(
            columns={"time": "Período", "valor": "Variação homóloga (%)"})
        junto = serie.merge(var_tab, on="Período", how="outer").sort_values("Período")

        st.download_button(
            "⬇️ Descarregar série completa (CSV com fonte)",
            csv_com_fonte(junto, "Serie do indice de precos alimentares - Portugal", dados,
                          extra=[("Base do indice", base), ("Classe COICOP", "CP011")]),
            f"despesa_alimentar_serie_{date.today()}.csv", "text/csv",
        )

    # ==========================================================================
    # ABA 3 — Simulador de IVA
    # ==========================================================================
with aba3:
    with painel("Simulador de IVA"):
        st.markdown("#### Cenário hipotético de alteração do IVA")

        CENARIOS = {
            "manual": ("✏️ Definir manualmente", None),
            "zero": ("🧺 «Cabaz zero» — isenção total (precedente 2023-24)", 0.0),
            "seis": ("📉 Taxa reduzida (6 %) em tudo", 6.0),
            "treze": ("📊 Taxa intermédia (13 %) em tudo", 13.0),
        }
        # O estado de sessão persiste entre versões da aplicação. Se ficar com um
        # valor que já não existe nas opções atuais, o Streamlit levanta exceção —
        # por isso valida-se antes de usar.
        if st.session_state.get("cenario_iva") not in CENARIOS:
            st.session_state["cenario_iva"] = "zero"

        esq, dir_ = st.columns([2, 1])
        with dir_:
            cenario = st.radio(
                "Cenário a simular",
                options=list(CENARIOS.keys()),
                format_func=lambda k: CENARIOS[k][0],
                key="cenario_iva",
            )
        with esq:
            st.markdown("**Quanto da descida do imposto chega ao preço na prateleira?**")
            repercussao = st.slider(
                "Fração que chega ao consumidor", 0, 100, 40, 5,
                format="%d %%", label_visibility="collapsed",
            ) / 100

            ao_consumidor = int(round(repercussao * 100))
            na_margem = 100 - ao_consumidor
            st.markdown(f"""
    <div style="background:#f5f7f9;border-radius:8px;padding:11px 14px;font-size:13px;margin-top:2px">
    Por cada <strong>1,00 €</strong> de imposto que o Estado deixa de cobrar:
    <div style="display:flex;gap:18px;margin-top:8px">
      <div style="flex:1">
        <div style="font-size:20px;font-weight:600;color:{VERDE}">{ao_consumidor} cêntimos</div>
        <div style="font-size:11.5px;color:#4a4a48">descem o preço — poupança do consumidor</div>
      </div>
      <div style="flex:1">
        <div style="font-size:20px;font-weight:600;color:{DOURADO}">{na_margem} cêntimos</div>
        <div style="font-size:11.5px;color:#4a4a48">ficam na margem de quem vende</div>
      </div>
    </div>
    </div>
    """, unsafe_allow_html=True)

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

        with st.expander("Porque é que este cursor está a 40 % — e porque é o número que mais importa"):
            st.markdown("""
    Quando o Estado baixa o IVA, **não é garantido que o preço na loja desça na mesma medida**.
    Parte da descida pode ficar retida na margem de quem vende. A esse fenómeno chama-se
    *repercussão*, e é o parâmetro que decide se uma descida de IVA beneficia o consumidor ou o
    operador.

    A avaliação internacional é **consistentemente cética quanto à repercussão integral**:

    - **França, 2009** — descida do IVA na restauração de 19,6 % para 5,5 %. Estima-se que apenas
      uma pequena fração tenha chegado ao preço final; a maior parte foi absorvida em margem e
      salários.
    - **Suécia** — resultados semelhantes em avaliações do setor alimentar e da restauração.

    Os **40 %** são um **parâmetro de trabalho, não uma estimativa** para Portugal. Servem para
    que o resultado não seja apresentado como se a descida chegasse toda ao consumidor — o que a
    evidência não sustenta.

    **O que fazer com ele:** mova o cursor e observe a sensibilidade do resultado. Se a conclusão
    se mantiver entre 20 % e 60 %, é robusta. Se mudar de sinal, o resultado depende inteiramente
    de uma hipótese — e deve ser apresentado como intervalo, nunca como valor único.

    Repare ainda num ponto que a simulação torna visível: **a receita que o Estado deixa de cobrar
    é a mesma seja qual for a repercussão**. O que muda é apenas quem fica com o dinheiro.
            """)

        editor = pd.DataFrame({
            "Grupo": [f"{r.emoji} {r.classe}" for r in df_decomp.itertuples()],
            "Valor (€)": df_decomp["valor"].round(2),
            "Taxa atual (%)": df_decomp["iva_defeito"].astype(float),
            "Taxa do cenário (%)": df_decomp["iva_defeito"].astype(float),
        })

        # O editor de taxas guarda estado por chave. Versões anteriores permitiam
        # valores fora da lista legal (era um campo numérico livre); se esse estado
        # sobreviver, o seletor rejeita-o. Limpa-se o que não seja válido.
        for _k in [k for k in list(st.session_state.keys()) if str(k).startswith("editor_iva_")]:
            try:
                _est = st.session_state[_k]
                _edicoes = (_est or {}).get("edited_rows", {}) if isinstance(_est, dict) else {}
                for _linha in list(_edicoes.values()):
                    for _col, _val in list(_linha.items()):
                        if "Taxa" in str(_col) and float(_val) not in (0.0, 6.0, 13.0, 23.0):
                            del st.session_state[_k]
                            raise StopIteration
            except StopIteration:
                continue
            except Exception:                                      # noqa: BLE001
                st.session_state.pop(_k, None)

        taxa_forcada = CENARIOS[cenario][1]
        if taxa_forcada is not None:
            editor["Taxa do cenário (%)"] = float(taxa_forcada)

        # Só as taxas que existem no Código do IVA (continente). Uma caixa de texto
        # livre permitiria valores impossíveis — 80 %, por exemplo — e produziria
        # resultados sem qualquer significado.
        TAXAS_LEGAIS = [0.0, 6.0, 13.0, 23.0]
        col_taxa = st.column_config.SelectboxColumn(
            options=TAXAS_LEGAIS, required=True,
            help="Taxas em vigor no continente: isenção, reduzida (6 %), intermédia (13 %), normal (23 %).",
        )

        # A chave do editor tem de variar com o cenário: caso contrário o Streamlit
        # mantém o estado do widget e as taxas do cenário nunca chegam à tabela.
        editado = st.data_editor(
            editor, use_container_width=True, hide_index=True,
            key=f"editor_iva_{cenario}",
            disabled=["Grupo", "Valor (€)"],
            column_config={
                "Valor (€)": st.column_config.NumberColumn(format="%.2f"),
                "Taxa atual (%)": col_taxa,
                "Taxa do cenário (%)": col_taxa,
            },
        )

        if cenario == "manual":
            st.caption(
                "Escolha a taxa de cada grupo nas duas colunas da direita. Só estão disponíveis "
                "as taxas que existem no Código do IVA — isenção, 6 %, 13 % e 23 %."
            )

        taxas_atuais = dict(zip(df_decomp["codigo"], editado["Taxa atual (%)"]))
        taxas_cenario = dict(zip(df_decomp["codigo"], editado["Taxa do cenário (%)"]))

        sim = simular_iva(df_decomp, taxas_atuais, taxas_cenario, repercussao)
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
        st.caption(
            f"Extrapolação para **{agregados:,}".replace(",", "\u00a0")
            + "** agregados — o mesmo valor usado em toda a aplicação (ver barra lateral)."
        )
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
                "⬇️ Descarregar simulação (CSV com fonte)",
                csv_com_fonte(det.round(2), "Simulacao de alteracao do IVA", dados,
                              extra=[("Cenario", CENARIOS[cenario][0]),
                                     ("Repercussao assumida", f"{repercussao*100:.0f}%"),
                                     ("Composicao do agregado", composicao),
                                     ("AVISO", "As taxas e a repercussao sao parametros do utilizador, nao dados oficiais")]),
                f"despesa_alimentar_simulacao_iva_{date.today()}.csv", "text/csv",
            )

    # ==========================================================================
    # ABA 4 — Comparação UE-27
    # ==========================================================================
with aba4:
    with painel("Comparação UE-27"):
        vista = st.radio(
            "O que quer ver",
            ["💶 Quão caros são os alimentos",
             "🧾 Que fatia do orçamento consomem",
             "📈 A que ritmo estão a subir"],
            horizontal=True, label_visibility="collapsed",
        )
        ver_precos = vista.startswith("💶")
        ver_esforco = vista.startswith("🧾")

        st.info(
            "**São três perguntas diferentes.** «Quão caros são» compara o *nível* dos preços entre "
            "países. «Que fatia do orçamento consomem» mede o *esforço* das famílias — quanto do que "
            "gastam vai para comida. «A que ritmo sobem» compara a *inflação*. Um país pode ter "
            "preços baixos e ainda assim um esforço alimentar elevado, se os rendimentos forem "
            "baixos — e é esse cruzamento que interessa à política."
        )

        pli = dados.get("pli")

        # ==================== VISTA: NÍVEL DE PREÇOS ====================
        if ver_precos:
            if pli is None or pli.empty:
                st.warning(
                    "O índice de nível de preços não está disponível nesta sessão. "
                    "Consulte o registo de ligações no separador Metodologia. "
                    "Use entretanto a vista «A que ritmo estão a subir»."
                )
            else:
                ano_pli = pli["time"].max()
                pli_ult = pli[pli["time"] == ano_pli].copy()
                pli_ult["pais"] = pli_ult["geo"].map(PAISES)
                pli_ult = pli_ult.dropna(subset=["pais"]).sort_values("valor")

                pt_pli = pli_ult.loc[pli_ult["geo"] == "PT", "valor"]
                if not pt_pli.empty:
                    v = float(pt_pli.iloc[0])
                    posicao = "mais caros" if v > 100 else "mais baratos"
                    d1, d2, d3 = st.columns(3)
                    d1.metric(f"Portugal em {ano_pli}", f"{v:.0f}".replace(".", ","),
                              help="Índice: média da UE-27 = 100")
                    d2.metric("Face à média da UE-27",
                              f"{abs(v - 100):.0f} % {posicao}".replace(".", ","))
                    posto = int((pli_ult["geo"] != "EU27_2020").cumsum()[
                        pli_ult["geo"] == "PT"].iloc[0])
                    total = int((pli_ult["geo"] != "EU27_2020").sum())
                    d3.metric("Posição", f"{posto}.º de {total}",
                              help="Do mais barato para o mais caro, entre os países selecionados")

                figp = go.Figure(go.Bar(
                    y=pli_ult["pais"], x=pli_ult["valor"], orientation="h",
                    marker_color=[VERDE if g == "PT" else (AZUL if g == "EU27_2020" else "#b7c2ce")
                                  for g in pli_ult["geo"]],
                    text=[f"{x:.0f}".replace(".", ",") for x in pli_ult["valor"]],
                    textposition="outside",
                    hovertemplate="%{y}: %{x:.0f} (UE-27 = 100)<extra></extra>",
                ))
                figp.add_vline(x=100, line_width=2, line_dash="dash", line_color="#64748b",
                               annotation_text="média UE-27", annotation_position="top")
                figp.update_layout(height=max(320, 34 * len(pli_ult)),
                                   margin=dict(t=42, b=40, l=10, r=70),
                                   xaxis_title="Nível de preços dos alimentos (média UE-27 = 100)",
                                   plot_bgcolor="#fff", showlegend=False)
                figp.update_xaxes(gridcolor="#eef1f4")
                st.plotly_chart(figp, use_container_width=True)
                st.caption(
                    "Barras à direita da linha: alimentos mais caros do que a média europeia. "
                    "À esquerda: mais baratos. Portugal a verde. Fonte: programa de Paridades de "
                    f"Poder de Compra Eurostat-OCDE (`prc_ppp_ind_1`, categoria "
                    f"`{dados.get('pli_cat')}`). Publicação **anual** — indicador de nível, não de "
                    "conjuntura."
                )

        # ==================== VISTA: ESFORÇO (COEFICIENTE DE ENGEL) ====================
        elif ver_esforco:
            engel = dados.get("engel") or {}
            if not engel:
                st.warning(
                    "**O indicador de esforço não está disponível nesta sessão.**\n\n"
                    "O cálculo precisa de dois valores das Contas Nacionais — a despesa "
                    "alimentar e o consumo total das famílias. O separador **Metodologia**, "
                    "no bloco «Registo das ligações desta sessão», mostra qual dos dois "
                    "falhou e porquê."
                )
            else:
                st.markdown("""
    **O coeficiente de Engel.** É a fração do consumo total das famílias que vai para alimentação.
    Chama-se assim por **Ernst Engel**, o estatístico que em 1857 formulou a regularidade que ainda
    hoje se verifica: *quanto menor o rendimento, maior a fatia do orçamento gasta em comida*.

    É um dos indicadores mais antigos e mais robustos de bem-estar económico — e comparável entre
    países sem conversão cambial, por ser um rácio.
                """)
                st.warning("""
    **Atenção: este número não tem salários no denominador.**

    O coeficiente de Engel é **despesa sobre despesa** — não despesa sobre rendimento:

    | | Numerador | Denominador |
    |---|---|---|
    | **Coeficiente de Engel** (aqui) | O que as famílias gastam em **comida** | O que as famílias gastam em **tudo** |
    | **Esforço alimentar** (separador «Despesa e composição») | O que o agregado gasta em **comida** | O que o agregado **recebe** |

    Por isso os dois números são diferentes e não se substituem. Este mede **como se reparte o
    orçamento de consumo**; o seguinte mede **quanto do rendimento é absorvido pela comida**.

    E também por isso **este indicador não responde à composição do agregado** que escolheu na
    barra lateral: é um rácio macroeconómico nacional — a despesa alimentar de *todas* as famílias
    sobre o consumo total de *todas* elas. Não existe versão «por agregado» nas Contas Nacionais.
                """)

                linhas_e = []
                for geo, d in engel.items():
                    if geo not in PAISES:
                        continue
                    linhas_e.append({"geo": geo, "pais": PAISES[geo],
                                     "quota": d["quota"], "ano": d["ano"]})
                df_e = pd.DataFrame(linhas_e).sort_values("quota")

                pt_e = engel.get("PT")
                ue_e = engel.get("EU27_2020")
                if pt_e:
                    e1, e2, e3 = st.columns(3)
                    e1.metric(f"Portugal ({pt_e['ano']}) — do que gastam",
                              f"{pt_e['quota']:.1f} %".replace(".", ","),
                              help=("De cada 100 € que as famílias portuguesas gastam em tudo "
                                    "— casa, transportes, saúde, lazer —, esta fração vai para "
                                    "alimentação. Não envolve salários nem rendimentos."))
                    if ue_e:
                        dif = pt_e["quota"] - ue_e["quota"]
                        dif_txt = f"{dif:+.1f}".replace(".", ",") + " p.p."
                        e2.metric("Face à média da UE-27", dif_txt)
                    posto = int((df_e["geo"] != "EU27_2020").cumsum()[
                        df_e["geo"] == "PT"].iloc[0])
                    total_p = int((df_e["geo"] != "EU27_2020").sum())
                    e3.metric("Posição", f"{posto}.º de {total_p}",
                              help="Do menor esforço para o maior")

                figE = go.Figure(go.Bar(
                    y=df_e["pais"], x=df_e["quota"], orientation="h",
                    marker_color=[VERDE if g == "PT" else (AZUL if g == "EU27_2020" else "#b7c2ce")
                                  for g in df_e["geo"]],
                    text=[f"{v:.1f} %".replace(".", ",") for v in df_e["quota"]],
                    textposition="outside",
                    hovertemplate="%{y}: %{x:.1f} % do consumo<extra></extra>"))
                if ue_e:
                    figE.add_vline(x=ue_e["quota"], line_width=2, line_dash="dash",
                                   line_color="#64748b", annotation_text="média UE-27",
                                   annotation_position="top")
                figE.update_layout(height=max(320, 34 * len(df_e)),
                                   margin=dict(t=42, b=40, l=10, r=80),
                                   xaxis_title="Fatia do consumo das famílias gasta em alimentação (%)",
                                   plot_bgcolor="#fff", showlegend=False)
                figE.update_xaxes(gridcolor="#eef1f4")
                st.plotly_chart(figE, use_container_width=True)
                st.caption(
                    "Barras mais longas significam **maior esforço alimentar**: mais do orçamento "
                    "familiar absorvido por comida, menos disponível para tudo o resto. "
                    "Fonte: Contas Nacionais (`nama_10_co3_p3`), rácio CP011/CP00. Publicação anual."
                )

                with st.expander("Descarregar dados do esforço"):
                    tab_e = df_e[["pais", "quota", "ano"]].copy()
                    tab_e.columns = ["País", "Fatia do consumo em alimentação (%)", "Ano"]
                    tab_e["Fatia do consumo em alimentação (%)"] = \
                        tab_e["Fatia do consumo em alimentação (%)"].round(1)
                    st.dataframe(tab_e.sort_values("Fatia do consumo em alimentação (%)",
                                                   ascending=False),
                                 use_container_width=True, hide_index=True)
                    st.download_button(
                        "⬇️ CSV com fonte",
                        csv_com_fonte(tab_e, "Coeficiente de Engel - esforco alimentar", dados,
                                      extra=[("Indicador", "Despesa alimentar / consumo total das familias"),
                                             ("Conjunto", "nama_10_co3_p3, CP011 / CP00")]),
                        f"despesa_alimentar_engel_{date.today()}.csv", "text/csv")

        # ==================== VISTA: INFLAÇÃO ====================
        else:
            cpais, cgrupo = st.columns([3, 2])
            with cpais:
                escolhidos = st.multiselect(
                    "Países", options=list(PAISES.keys()),
                    default=[p for p in PAISES_POR_DEFEITO if p in PAISES],
                    format_func=lambda g: PAISES[g],
                )
            with cgrupo:
                opcoes_grupo = [COICOP_ALIMENTAR] + CODIGOS
                rotulos = {COICOP_ALIMENTAR: "🍽️ Todos os alimentos"}
                rotulos.update({c["cod"]: f"{c['emoji']} {c['nome']}" for c in CLASSES})
                grupo_sel = st.selectbox(
                    "Grupo de produto", options=opcoes_grupo,
                    format_func=lambda g: rotulos[g],
                    help="Compare a inflação de um tipo de produto específico entre países.",
                )

            bench_todos = dados["bench_todos"]
            bench, _ts = {}, {}
            for _, lb in bench_todos[bench_todos["coicop"] == grupo_sel].iterrows():
                bench.setdefault(lb["geo"], {})[lb["time"]] = lb["valor"]
                _ts[lb["time"]] = 1
            tempos_b = sorted(_ts)

            if grupo_sel != COICOP_ALIMENTAR:
                st.caption(
                    f"A comparar **{rotulos[grupo_sel].split(' ', 1)[1]}**. Grupos individuais são "
                    "bastante mais voláteis do que o agregado alimentar — a fruta e os legumes, em "
                    "particular, sofrem efeitos sazonais e climáticos fortes."
                )

            if not escolhidos or not tempos_b:
                st.info("Selecione pelo menos um país.")
            else:
                fig = go.Figure()
                paleta = [VERDE, AZUL, DOURADO, VERMELHO, "#7a5ea8", "#c2681a",
                          "#0f8f9c", "#4a7c3f", "#8f4a6b", "#5a6b8f", "#a0568f", "#2980b9"]
                for i, geo in enumerate(escolhidos):
                    if geo not in bench:
                        continue
                    fig.add_trace(go.Scatter(
                        x=[mes_pt(t) for t in tempos_b],
                        y=[bench[geo].get(t) for t in tempos_b],
                        name=PAISES[geo],
                        line=dict(color=paleta[i % len(paleta)],
                                  width=3.2 if geo == "PT" else 1.9,
                                  dash="dot" if geo == "EU27_2020" else "solid"),
                        hovertemplate="%{x}<br>%{y:.1f} %<extra>" + PAISES[geo] + "</extra>",
                    ))
                fig.update_layout(height=400, margin=dict(t=20, b=40, l=10, r=10),
                                  yaxis_title="Variação homóloga (%)",
                                  legend=dict(orientation="h", y=1.12, x=0),
                                  hovermode="x unified", plot_bgcolor="#fff")
                fig.update_xaxes(showgrid=False)
                fig.update_yaxes(gridcolor="#eef1f4", zerolinecolor="#cbd5e1")
                st.plotly_chart(fig, use_container_width=True)

                ultimo = tempos_b[-1]
                ranking = pd.DataFrame([
                    {"geo": g, "valor": v[ultimo]}
                    for g, v in bench.items() if v.get(ultimo) is not None])
                ranking["pais"] = ranking["geo"].map(PAISES)
                ranking = ranking.dropna(subset=["pais"])
                ue = ranking.loc[ranking["geo"] == "EU27_2020", "valor"]
                valor_ue = float(ue.iloc[0]) if not ue.empty else None

                st.markdown(f"#### Posição em {mes_pt(ultimo)}")
                ordenado = ranking.sort_values("valor", ascending=True)
                cores, etiquetas = [], []
                for geo, valor in zip(ordenado["geo"], ordenado["valor"]):
                    gap = (valor - valor_ue) if valor_ue is not None else None
                    if geo == "PT":
                        cores.append(VERDE)
                    elif geo == "EU27_2020":
                        cores.append(AZUL)
                    elif gap is not None and gap > 0:
                        cores.append("#e08b84")
                    else:
                        cores.append("#8fb3d0")
                    if gap is None or geo == "EU27_2020":
                        etiquetas.append(f"{valor:.1f} %".replace(".", ","))
                    else:
                        etiquetas.append(f"{valor:.1f} %  ({gap:+.1f} p.p.)".replace(".", ","))

                figc = go.Figure(go.Bar(
                    y=ordenado["pais"], x=ordenado["valor"], orientation="h",
                    marker_color=cores, text=etiquetas, textposition="outside",
                    hovertemplate="%{y}: %{x:.1f} %<extra></extra>"))
                if valor_ue is not None:
                    figc.add_vline(x=valor_ue, line_width=2, line_dash="dash",
                                   line_color="#64748b",
                                   annotation_text=f"média UE-27: {valor_ue:.1f} %".replace(".", ","),
                                   annotation_position="top")
                figc.update_layout(height=max(330, 34 * len(ordenado)),
                                   margin=dict(t=42, b=40, l=10, r=120),
                                   xaxis_title="Variação homóloga dos preços alimentares (%)",
                                   plot_bgcolor="#fff", showlegend=False)
                figc.update_xaxes(gridcolor="#eef1f4", zerolinecolor="#cbd5e1")
                st.plotly_chart(figc, use_container_width=True)
                st.caption(
                    "A linha tracejada é a média da UE-27: à direita, inflação mais rápida do que na "
                    "UE; à esquerda, mais lenta. Entre parênteses, a distância em pontos percentuais."
                )

                if valor_ue is not None:
                    tb = ranking[["pais", "valor"]].copy()
                    tb["Face à UE-27 (p.p.)"] = (tb["valor"] - valor_ue).round(1)
                    tb.columns = ["País", "Variação homóloga (%)", "Face à UE-27 (p.p.)"]
                    tb = tb.sort_values("Variação homóloga (%)", ascending=False)
                    st.download_button(
                        "⬇️ Descarregar comparação (CSV com fonte)",
                        csv_com_fonte(tb, "Comparacao europeia da inflacao alimentar", dados,
                                      extra=[("Mes de referencia", ultimo),
                                             ("Grupo", grupo_sel)]),
                        f"despesa_alimentar_ue27_{date.today()}.csv", "text/csv")

    # ==========================================================================
    # ABA 5 — Metodologia e fontes
    # ==========================================================================
with aba5:
    with painel("Metodologia e fontes"):
        st.markdown("#### Metodologia e fontes")
        st.caption(
            "Documentação completa do método. A nota metodológica em anexo à ferramenta "
            "desenvolve estes pontos com as referências legais."
        )

        with st.expander("📘 O que é o IHPC — e porque não é o mesmo que o IPC"):
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

            st.markdown("""
    **Como a escala é aplicada — e uma propriedade que convém ter presente.**

    O ponto de partida é a despesa do agregado médio nacional. A escala não calcula a despesa a
    partir do zero: **ajusta** desse agregado médio para o agregado em análise, e é aplicada aos
    **dois lados** do rácio — ao numerador e ao denominador.

    Daqui decorre um comportamento que à primeira vista surpreende: como o denominador também
    depende da escala, **o efeito de mudar de escala inverte-se** conforme o agregado seja maior
    ou menor do que a média nacional.

    Coeficientes menores significam que cada pessoa a mais custa menos, o que **comprime as
    diferenças** entre agregados de dimensão diferente. Um agregado menor do que a média
    aproxima-se dela por cima — o valor sobe. Um agregado maior aproxima-se dela por baixo — o
    valor desce. O ponto de viragem é exatamente a dimensão média.

    Não é um artefacto do cálculo: é o que qualquer normalização por escala de equivalência
    produz. É também a razão pela qual a aplicação apresenta sempre um intervalo, e não um valor
    único.
            """)
            st.warning("""
    **Porque não se usa a norma da UE por defeito.** A escala OCDE modificada é a norma europeia
    para o *rendimento*, e foi construída para o consumo total, em que a partilha da habitação gera
    fortes economias de escala. Na alimentação essas economias são bem mais fracas — não se partilha
    uma refeição como se partilha um teto. Aplicá-la ao consumo alimentar **subestimaria** o custo
    dos agregados maiores, que são justamente o grupo politicamente sensível.
            """)

        with st.expander("💰 Rendimento e salários — o que é bruto, o que é líquido"):
            st.markdown("""
    Três fontes distintas alimentam os indicadores de esforço. **A diferença entre bruto e líquido
    não é um detalhe: muda o resultado de forma material** e, se ignorada, leva a subestimar a
    pressão sobre quem aufere menos.

    | Fonte | Conjunto | O que é | Natureza | Frequência |
    |---|---|---|---|---|
    | Rendimento das famílias | [`ilc_di03`](https://ec.europa.eu/eurostat/databrowser/view/ilc_di03/default/table) | Rendimento monetário do agregado, todas as fontes | **Líquido** | Anual |
    | Salário médio | [`nama_10_a10`](https://ec.europa.eu/eurostat/databrowser/view/nama_10_a10/default/table) ÷ [`nama_10_a10_e`](https://ec.europa.eu/eurostat/databrowser/view/nama_10_a10_e/default/table) | Massa salarial ÷ trabalhadores por conta de outrem | **Bruto** | Anual |
    | Salário mínimo | [`earn_mw_cur`](https://ec.europa.eu/eurostat/databrowser/view/earn_mw_cur/default/table) | Valor legal mensal | **Bruto** | Semestral (janeiro e julho) |

    **Rendimento das famílias.** Vem do EU-SILC e é o mais completo: inclui salários, pensões,
    prestações sociais, rendimentos de capital e transferências, deduzidos impostos e contribuições.
    É publicado **por unidade de consumo equivalente** — já dividido pelas unidades do agregado,
    segundo a escala OCDE modificada. Para obter o rendimento de um agregado concreto, multiplica-se
    pelas suas unidades equivalentes.

    Estão disponíveis a **média** e a **mediana**. A aplicação usa a média por defeito, porque a
    despesa alimentar também é uma média — combinar média com mediana inflacionaria o rácio.

    **Salário médio.** Calculado a partir das Contas Nacionais: massa salarial (remunerações e
    salários) dividida pelo número de trabalhadores por conta de outrem. É uma remuneração **bruta**
    — antes de imposto e contribuições do trabalhador.

    Duas vantagens sobre as séries de remunerações líquidas: os códigos são estáveis, e fica na
    **mesma base estatística** da despesa alimentar usada como âncora — o que evita mais uma mistura
    de universos. Sendo bruto, é comparável com o salário mínimo, mas **não** com o rendimento
    líquido do EU-SILC.

    **Salário mínimo.** É o **valor legal bruto**, tal como fixado por diploma. Não desconta a
    contribuição do trabalhador para a Segurança Social nem o imposto retido, nem inclui prestações
    familiares. O rendimento efetivamente disponível de quem aufere o mínimo é **inferior** ao valor
    apresentado — logo, o esforço alimentar real é **superior** ao que este rácio indica.

    É por essa razão que a aplicação assinala as duas naturezas com cores distintas e adverte que
    não são diretamente comparáveis entre si.

    **Quem come e quem aufere não são o mesmo conjunto.** O multiplicador de salários é o número de
    pessoas que **efetivamente auferem rendimento**, nunca o total do agregado. E há um caso em que
    a diferença é decisiva: **os jovens entre os 14 e os 18 anos**.

    Para a escala de equivalência, uma pessoa de 15 ou 17 anos conta como adulta — come como
    adulta, e é isso que a escala mede. Mas não aufere rendimento. Um agregado de dois pais e dois
    adolescentes tem **quatro pessoas com peso alimentar de adulto e dois rendimentos**.

    É a composição em que o esforço alimentar é mais elevado, e precisamente a que os indicadores
    médios menos revelam. A aplicação assinala-a quando ocorre.
            """)

        with st.expander("🔄 Como a aplicação se mantém atualizada"):
            st.markdown("""
    **Não há dados gravados na aplicação.** Nada é fixado no código: em cada arranque, a aplicação
    pede ao Eurostat as séries de que precisa e usa **a observação mais recente de cada uma**.

    **Como escolhe o valor mais recente.** Para cada série, ordena as observações por período e fica
    com a última. Isso funciona qualquer que seja a periodicidade — mensal (`2026-06`), semestral
    (`2026S1`) ou anual (`2026`) — porque a codificação de períodos do Eurostat é ordenável.
    A consequência prática: **quando o Eurostat publicar um mês novo, a aplicação passa a usá-lo sem
    qualquer alteração ao código**.

    **Janela de pedido.** As séries anuais e semestrais são pedidas com **oito anos** de margem. É
    folgado de propósito: se uma publicação atrasar, continua a haver observações no intervalo e a
    aplicação não fica sem dados. As séries mensais usam janelas mais curtas, por serem densas.

    **Cache de seis horas.** Os dados ficam guardados em memória durante seis horas, para não repetir
    pedidos desnecessários — as séries mudam no máximo uma vez por mês. O botão **Recarregar do
    Eurostat**, na barra lateral, limpa a cache e força um pedido novo.

    **O período de cada valor está sempre visível.** Cada indicador mostra o seu período de
    referência — «Salário mínimo (2026S1)», «Contas Nacionais 2024» — para que nunca se confunda a
    data da consulta com a data do dado.
            """)
            st.info("""
    **Quando esperar dados novos**

    | Dado | Publicação |
    |---|---|
    | Estimativa rápida do índice (só agregados) | Último dia útil do mês de referência |
    | **Índice completo, com todas as classes** | **Cerca do dia 17 do mês seguinte** |
    | Ponderadores | Com os dados de janeiro, em fevereiro |
    | Salário mínimo | Janeiro e julho |
    | Rendimento e salário médio (EU-SILC) | Anual, com cerca de um ano de desfasamento |
    | Contas Nacionais (âncora em euros) | Anual, com cerca de dois anos de desfasamento |
    | Paridades de poder de compra | Junho do ano seguinte |

    O separador mostra sempre o último mês disponível no topo da aplicação. Se um valor parecer
    desatualizado, é porque a fonte ainda não publicou — não porque a aplicação não o foi buscar.
            """)
            st.warning("""
    **Alteração metodológica de fevereiro de 2026.** A partir dos dados de janeiro de 2026, o índice
    passou a ser compilado segundo a **ECOICOP versão 2** (alinhada com a COICOP 2018) e o período de
    referência passou para **2025 = 100**. As séries com a classificação anterior foram arquivadas.

    A aplicação prefere automaticamente a base mais recente disponível, com recuo ordenado para as
    anteriores. Se em algum momento as classes de produtos deixarem de responder, é nesta alteração
    que se deve olhar primeiro.
            """)

        with st.expander("🗂️ Origem dos dados — conjuntos utilizados e ligações"):
            st.markdown("""
    Todos os dados quantitativos são obtidos em direto do **Eurostat**, que difunde as estatísticas
    compiladas pelos institutos nacionais — no caso português, o **INE**. As ligações abrem
    diretamente o conjunto no Data Browser do Eurostat.

    | Elemento | Conjunto | O que mede | Frequência |
    |---|---|---|---|
    | Ponderadores por grupo | [`prc_hicp_inw`](https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_inw/default/table) | Fração de cada mil euros de consumo total (‰) | Anual |
    | Índice de preços | [`prc_hicp_midx`](https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_midx/default/table) | Nível do índice — não são euros | Mensal |
    | Variação homóloga | [`prc_hicp_manr`](https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_manr/default/table) | Subida face ao mesmo mês do ano anterior (%) | Mensal |
    | Despesa alimentar (âncora) | [`nama_10_co3_p3`](https://ec.europa.eu/eurostat/databrowser/view/nama_10_co3_p3/default/table) | Despesa efetiva em euros (Contas Nacionais) | Anual |
    | Dimensão do agregado | [`ilc_lvph01`](https://ec.europa.eu/eurostat/databrowser/view/ilc_lvph01/default/table) | N.º médio de pessoas por agregado | Anual |
    | N.º de agregados | [`lfst_hhnhtych`](https://ec.europa.eu/eurostat/databrowser/view/lfst_hhnhtych/default/table) | Total de agregados familiares (milhares) | Anual |
    | Nível de preços comparado | [`prc_ppp_ind_1`](https://ec.europa.eu/eurostat/databrowser/view/prc_ppp_ind_1/default/table) | Quão caros são os alimentos (UE-27 = 100) | Anual |
    | Rendimento das famílias | [`ilc_di03`](https://ec.europa.eu/eurostat/databrowser/view/ilc_di03/default/table) | Rendimento líquido equivalente, médio e mediano | Anual |
    | Salário médio | [`nama_10_a10`](https://ec.europa.eu/eurostat/databrowser/view/nama_10_a10/default/table) ÷ `nama_10_a10_e` | Remuneração média **bruta** dos trabalhadores por conta de outrem | Anual |
    | Salário mínimo | [`earn_mw_cur`](https://ec.europa.eu/eurostat/databrowser/view/earn_mw_cur/default/table) | Valor legal mensal, **bruto** | Semestral |

    **Parâmetros que não são dados oficiais**

    | Parâmetro | Origem | Nota |
    |---|---|---|
    | Taxas de IVA | Predefinidas, editáveis | Limitadas às do Código do IVA; correspondência ao grupo COICOP é aproximada |
    | Adultos com rendimento | Parâmetro do utilizador | Multiplicador dos salários; as crianças não entram |
    | Repercussão | Parâmetro do utilizador | Hipótese de trabalho, não estimativa |

    **Recuo do n.º de agregados:** se o conjunto anual do Eurostat não estiver disponível ou
    devolver um valor implausível, a aplicação usa o valor censitário — **4 149 096** agregados
    domésticos privados ([INE, Censos 2021](https://www.ine.pt)).
            """)
            st.info(
                "**Sobre os ponderadores.** Somam 1 000 ‰ sobre **todo** o cabaz do índice — não "
                "sobre a alimentação. Os nove grupos alimentares somam apenas o peso da alimentação "
                "no consumo total. Por isso o cálculo normaliza pela soma dos nove, e não pelos 1 000 ‰."
            )

        with st.expander("🔌 Registo das ligações desta sessão"):
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

        with st.expander("🏷️ De onde vem a classificação COICOP"):
            st.markdown("""
    A **COICOP** — *Classification of Individual Consumption According to Purpose* — é uma
    classificação das **Nações Unidas** (Divisão de Estatística), não do Eurostat. Serve para
    organizar a despesa de consumo das famílias **por finalidade**, e é usada mundialmente nas
    Contas Nacionais e nos inquéritos às despesas.

    A União Europeia adota-a numa versão própria, a **ECOICOP** (*European COICOP*), tornada
    obrigatória para o índice de preços pelo Regulamento (UE) 2016/792. É por isso que os mesmos
    códigos aparecem no INE, no Eurostat e nos institutos de todos os Estados-Membros: não é uma
    convenção do Eurostat, é uma norma internacional que o Eurostat implementa.

    A hierarquia relevante aqui:

    | Nível | Código | Designação |
    |---|---|---|
    | Divisão | 01 | Produtos alimentares e bebidas não alcoólicas |
    | Grupo | 01.1 | Produtos alimentares |
    | Classes | 01.1.1 a 01.1.9 | Pão e cereais, carne, peixe, laticínios, óleos, fruta, legumes, doces, outros |

    Estas nove classes são usadas nesta aplicação porque são o **nível mais fino em que o Eurostat
    publica simultaneamente ponderadores e índices** para todos os Estados-Membros. Qualquer outro
    agrupamento — fresco contra processado, saudável contra não saudável — exigiria microdados que
    não existem em acesso público.

    *Nota: a ECOICOP foi revista com a COICOP 2018; as séries com a classificação anterior estão
    arquivadas. A aplicação usa sempre a base mais recente disponível.*
            """)

        with st.expander("👶 Porquê «crianças com menos de 14 anos» e não outra idade"):
            st.markdown("""
    O limiar dos 14 anos **não é uma escolha desta aplicação nem a definição demográfica de
    criança**. É o limiar inscrito nas próprias escalas de equivalência:

    - **Escala OCDE modificada**, norma do Eurostat para o rendimento: 1,0 ao primeiro adulto,
      0,5 a cada pessoa adicional **com 14 ou mais anos**, 0,3 a cada pessoa **com menos de 14**.
    - **Escala OCDE original**: 1,0 / 0,7 / 0,5, com o mesmo limiar.

    Alterar o limiar para 15, 16 ou 18 anos invalidaria os coeficientes — que foram estimados com
    aquela fronteira. Para usar outra idade seria preciso outra escala, estimada em conformidade.

    Isto é distinto das definições demográficas do INE, que variam consoante o contexto: nas
    estatísticas demográficas «jovens» são frequentemente os 0-14 anos; na proteção de menores, a
    menoridade vai até aos 18. São conceitos com finalidades diferentes, e não se misturam com os
    limiares das escalas de equivalência.

    **Consequência prática que importa reter.** Entre os 14 e os 18 anos, uma pessoa conta como
    adulta para efeitos de peso alimentar — e com razão, porque come como adulta — mas não aufere
    rendimento. Por isso a aplicação separa as duas contagens: **pessoas com 14 ou mais anos**
    determina a despesa; **quantas auferem rendimento** determina o denominador do esforço. Não são
    o mesmo número, e confundi-los subestima a pressão sobre as famílias com adolescentes.
            """)

        with st.expander("⚠️ Limitações a declarar em qualquer uso"):
            st.markdown("""
    1. **A decomposição não é observação.** É uma imputação de um valor total por ponderadores
       oficiais; não substitui a recolha de preços produto a produto.
    2. **Não há quantidades físicas.** A ferramenta mede despesa e variação de preço, não quilos
       nem litros. Para raciocinar em quantidades seria necessário o IDEF/INE ou dados de transação.
    3. **A âncora parte de uma média nacional.** Não distingue escalão de rendimento nem região.
    4. **As escalas de equivalência são aproximações — e há um viés quantificável.** Construídas
       para o consumo total; além disso, o agregado médio nacional é modelado como composto **apenas
       por adultos**, porque a dimensão média é publicada sem decomposição etária. Como o agregado
       médio real inclui menores, que pesam menos na escala, o denominador fica **sobrestimado em
       cerca de 4 a 5 %** — e todos os valores por agregado saem **subestimados na mesma proporção**.
       O viés é sistemático e na mesma direção para todas as composições, pelo que não afeta as
       comparações entre elas.
    5. **Desfasamento das Contas Nacionais.** A âncora assenta num ano com cerca de dois anos de
       desfasamento, atualizado por índice de preços.
    6. **A correspondência COICOP → taxa de IVA é aproximada.** O Código do IVA classifica por
       produto (Lista I), não por classe COICOP.
    7. **A repercussão é uma hipótese.** Qualquer resultado do simulador é condicional a esse
       parâmetro e deve ser apresentado como intervalo.
    8. **A extrapolação agregada é ilustrativa.** Não é uma estimativa de custo orçamental.
            """)
            st.warning("""
    **9 · O preço usado não é o preço que uma família concreta paga.** Há duas razões distintas,
    e ambas devem ser declaradas:

    **Dispersão entre operadores.** O índice é uma **média nacional ponderada** de uma amostra de
    estabelecimentos — grande distribuição, comércio tradicional, canais especializados —, com
    peso atribuído a cada canal e região segundo o consumo real. Mas os operadores praticam preços
    muito diferentes entre si: quem compre sempre em *discount* enfrenta níveis abaixo desta
    média; quem viva em zona de baixa densidade, acima. O índice capta bem a **variação**; o
    **nível** de cada família oscila em torno dele, e essa dispersão não é visível aqui.

    **Preço de prateleira e preço pago.** Mesmo dentro do mesmo estabelecimento, descontos de
    cartão de fidelização e de talão não são integralmente captados na recolha. O preço exposto
    não é o preço efetivamente pago, e o desvio entre ambos varia no tempo e entre insígnias.

    Só dados de transação — e-fatura ou *scanner data* — permitiriam medir o preço realmente pago
    e a sua dispersão entre operadores e territórios.
            """)
            st.warning("""
    **Ressalva a confirmar nos metadados.** Os ponderadores do IHPC referem-se ao consumo *no
    território* (inclui despesa de não residentes), enquanto a despesa das Contas Nacionais usada
    como âncora pode estar em conceito nacional (residentes). Em Portugal, dado o peso do turismo,
    a diferença não é trivial. Não afeta as variações, mas afeta o **nível** da âncora.
            """)

        with st.expander("📖 Base legal e documentação"):
            st.markdown("""
    **Quadro legal do índice**

    - [Regulamento (UE) 2016/792](https://eur-lex.europa.eu/legal-content/PT/TXT/?uri=CELEX%3A32016R0792) — quadro legal do IHPC
    - Regulamento de Execução (UE) 2020/1148 — especificações metodológicas e técnicas
    - Regulamento (CE) n.º 1445/2007 — regras comuns das Paridades de Poder de Compra

    **Documentação metodológica**

    - [Eurostat — HICP methodology](https://ec.europa.eu/eurostat/statistics-explained/index.php/HICP_methodology)
    - [Metadados do IHPC](https://ec.europa.eu/eurostat/cache/metadata/en/prc_hicp_esms.htm)
    - [Derivação dos ponderadores do IHPC](https://ec.europa.eu/eurostat/documents/10186/10693286/Derivation-of-HICP-weights-for-2022.pdf)
    - [Metadados das Paridades de Poder de Compra](https://ec.europa.eu/eurostat/cache/metadata/en/prc_ppp_esms.htm)
    - [Níveis comparativos de preços — Statistics Explained](https://ec.europa.eu/eurostat/statistics-explained/index.php?title=Comparative_price_levels_of_consumer_goods_and_services)

    **Classificação**

    - COICOP — Divisão de Estatística das Nações Unidas
    - ECOICOP — versão europeia, obrigatória por regulamento

    **Fontes nacionais**

    - [INE](https://www.ine.pt) — Índice de Preços no Consumidor, Censos 2021, Inquérito às Despesas das Famílias
            """)

st.divider()
st.caption(RODAPE)
