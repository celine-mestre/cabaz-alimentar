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
from src.config import (AGREGADOS_ANO, AGREGADOS_CENSOS, AGREGADOS_FONTE,
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
  @import url('https://fonts.googleapis.com/css2?family=Lexend:wght@300;400;500;600;700&display=swap');
  html, body, [class*="css"] {{ font-family: 'Lexend', Arial, sans-serif; }}

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

    try:
        agr_df, via6 = eurostat.numero_agregados(ano - anos_historico)
        registo.append(("N.º de agregados familiares", via6, len(agr_df)))
    except Exception as exc:                                   # noqa: BLE001
        agr_df, via6 = pd.DataFrame(), f"indisponível ({exc})"
        registo.append(("N.º de agregados familiares", via6, 0))

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

    return {
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
    adultos = ca.number_input("Adultos", min_value=1, max_value=8, value=2, step=1)
    criancas = cb.number_input("Crianças (<14)", min_value=0, max_value=8, value=0, step=1)

    dim_efetiva = dim_media if dim_media else 2.5
    escala_chave = st.selectbox(
        "Escala de equivalência", options=list(ESCALAS.keys()), index=1,
        format_func=lambda k: ESCALAS[k]["nome"],
        help="Como se ajusta a despesa ao número de pessoas. Ver separador Metodologia.",
    )

    valor_cabaz = despesa_do_agregado(
        media_agregado, dim_efetiva, adultos, criancas, escala_chave)
    faixa = intervalo_agregado(media_agregado, dim_efetiva, adultos, criancas)

    composicao = (f"{adultos} adulto{'s' if adultos > 1 else ''}"
                  + (f" + {criancas} criança{'s' if criancas > 1 else ''}"
                     if criancas else ""))
    pessoas = adultos + criancas
    ue = unidades_equivalentes(adultos, criancas, escala_chave)
    origem = (f"Contas Nacionais {ancora['ano_base']} · {composicao} · "
              f"escala {ESCALAS[escala_chave]['nome']}")
    vezes_ano = 12

    st.divider()
    st.metric(f"Despesa mensal — {composicao}", euro(valor_cabaz))
    st.caption(
        f"{pessoas} pessoa{'s' if pessoas > 1 else ''} · intervalo entre escalas de "
        f"{euro(faixa['minimo'])} a {euro(faixa['maximo'])}"
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
        colunas[1].metric("Agravamento nos últimos 12 meses", euro(resumo["contributo_total"]),
                          percentagem(resumo["variacao_implicita"]))
        colunas[2].metric("Despesa há 12 meses", euro(resumo["valor_ha_um_ano"]))
        if resumo["maior"]:
            maior = resumo["maior"]
            colunas[3].metric(f"{maior['emoji']} Maior contributo",
                              euro(maior["contributo"]),
                              percentagem(maior["variacao"]))
    colunas[4].metric("Equivalente anual", euro(valor_cabaz * vezes_ano))

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
        dm = dados.get("dimensao_media") or 2.5
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
        janela = var_pt.tail(meses)["valor"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Variação mais recente", percentagem(var_pt["valor"].iloc[-1]),
                  help=f"Mês de referência: {mes_pt(var_pt['time'].iloc[-1])}")
        c2.metric("Média do período", percentagem(janela.mean()))
        c3.metric("Máximo do período", percentagem(janela.max()))
        c4.metric("Mínimo do período", percentagem(janela.min()))

    st.caption(
        "Frequência mensal — a mais fina publicada por fonte oficial. Existem séries semanais "
        "de cabazes publicadas por entidades privadas, mas não são dados oficiais nem têm "
        "acesso automático, e as variações semanais são muito voláteis por efeitos de base."
    )

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
          A <strong>variação homóloga</strong> compara o preço de um mês com o mesmo mês do ano
          anterior. «+4,2 %» significa que os alimentos custavam mais 4,2 % do que um ano antes.
          Não é o preço; é o <em>ritmo a que o preço está a subir</em>.
          <br><br>
          Estar acima da UE-27 significa que os preços sobem mais depressa aqui —
          <strong>não que sejam mais caros aqui</strong>. São coisas diferentes: um país pode ter
          preços altos a subir devagar, ou preços baixos a subir depressa.
        </div>
        """, unsafe_allow_html=True)

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
                etiquetas.append(
                    f"{valor:.1f} %  ({gap:+.1f} p.p.)".replace(".", ","))

        figc = go.Figure(go.Bar(
            y=ordenado["pais"], x=ordenado["valor"], orientation="h",
            marker_color=cores, text=etiquetas, textposition="outside",
            hovertemplate="%{y}: %{x:.1f} %<extra></extra>",
        ))
        if valor_ue is not None:
            figc.add_vline(
                x=valor_ue, line_width=2, line_dash="dash", line_color="#64748b",
                annotation_text=f"média UE-27: {valor_ue:.1f} %".replace(".", ","),
                annotation_position="top",
            )
        figc.update_layout(
            height=max(330, 34 * len(ordenado)),
            margin=dict(t=42, b=40, l=10, r=120),
            xaxis_title="Variação homóloga dos preços alimentares (%)",
            plot_bgcolor="#fff", showlegend=False,
        )
        figc.update_xaxes(gridcolor="#eef1f4", zerolinecolor="#cbd5e1")
        st.plotly_chart(figc, use_container_width=True)
        st.caption(
            "Barras ordenadas pela variação homóloga. A linha tracejada é a média da UE-27: "
            "à direita, inflação alimentar mais rápida do que na UE; à esquerda, mais lenta. "
            "Entre parênteses, a distância à média em pontos percentuais. Portugal a verde."
        )

        if valor_ue is not None:
            tabela_b = ranking[["pais", "valor"]].copy()
            tabela_b["Face à UE-27 (p.p.)"] = (tabela_b["valor"] - valor_ue).round(1)
            tabela_b.columns = ["País", "Variação homóloga (%)", "Face à UE-27 (p.p.)"]
            tabela_b = tabela_b.sort_values("Variação homóloga (%)", ascending=False)
            st.download_button(
                "⬇️ Descarregar comparação (CSV com fonte)",
                csv_com_fonte(tabela_b, "Comparacao europeia da inflacao alimentar", dados,
                              extra=[("Mes de referencia", ultimo),
                                     ("Indicador", "Variacao homologa do IHPC, classe CP011")]),
                f"despesa_alimentar_ue27_{date.today()}.csv", "text/csv",
            )

# ==========================================================================
# ABA 5 — Metodologia e fontes
# ==========================================================================
with aba5:
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
        st.warning("""
**Porque não se usa a norma da UE por defeito.** A escala OCDE modificada é a norma europeia
para o *rendimento*, e foi construída para o consumo total, em que a partilha da habitação gera
fortes economias de escala. Na alimentação essas economias são bem mais fracas — não se partilha
uma refeição como se partilha um teto. Aplicá-la ao consumo alimentar **subestimaria** o custo
dos agregados maiores, que são justamente o grupo politicamente sensível.
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

**Parâmetros que não são dados oficiais**

| Parâmetro | Origem | Nota |
|---|---|---|
| Taxas de IVA | Predefinidas, editáveis | Limitadas às do Código do IVA; correspondência ao grupo COICOP é aproximada |
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
