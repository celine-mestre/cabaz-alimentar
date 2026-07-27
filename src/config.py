"""
Configuração da aplicação — classes de produto, países e identidade gráfica.

As nove classes correspondem à divisão 01.1 da COICOP (Classificação do Consumo
Individual por Objetivo), a nomenclatura que o INE e o Eurostat usam para
organizar a despesa das famílias.
"""

# --------------------------------------------------------------------------
# Identidade gráfica SGGov (Manual de Normas Gráficas, 2025)
# --------------------------------------------------------------------------
VERDE = "#0E7433"
AZUL = "#2B5683"
DOURADO = "#BE9C54"
VERMELHO = "#D02117"
AMARELO = "#FFD200"
CINZENTO = "#171715"

# --------------------------------------------------------------------------
# Classes de produtos alimentares (COICOP 01.1)
# --------------------------------------------------------------------------
# `iva` é a taxa predefinida, editável na aplicação. O Código do IVA classifica
# por produto (Lista I), não por classe COICOP: a correspondência é aproximada
# e deve ser afinada antes de qualquer uso em decisão.
CLASSES = [
    {"cod": "CP0111", "nome": "Pão e cereais",        "emoji": "🍞", "cor": "#C98B3A", "iva": 6},
    {"cod": "CP0112", "nome": "Carne",                "emoji": "🥩", "cor": "#C0392B", "iva": 6},
    {"cod": "CP0113", "nome": "Peixe e marisco",      "emoji": "🐟", "cor": "#2980B9", "iva": 6},
    {"cod": "CP0114", "nome": "Leite, queijo e ovos", "emoji": "🥛", "cor": "#8E9AAF", "iva": 6},
    {"cod": "CP0115", "nome": "Óleos e gorduras",     "emoji": "🫒", "cor": "#B8A02E", "iva": 6},
    {"cod": "CP0116", "nome": "Fruta",                "emoji": "🍎", "cor": "#D35400", "iva": 6},
    {"cod": "CP0117", "nome": "Legumes e hortícolas", "emoji": "🥦", "cor": "#0E7433", "iva": 6},
    {"cod": "CP0118", "nome": "Açúcar e doces",       "emoji": "🍬", "cor": "#A0568F", "iva": 23},
    {"cod": "CP0119", "nome": "Outros alimentos",     "emoji": "🧺", "cor": "#6B7280", "iva": 23},
]

CODIGOS = [c["cod"] for c in CLASSES]
POR_CODIGO = {c["cod"]: c for c in CLASSES}

# Agregado alimentar (soma das nove classes)
COICOP_ALIMENTAR = "CP011"

# --------------------------------------------------------------------------
# Agregados especiais do índice — permitem separar o que é choque conjuntural
# do que é inflação estrutural, e situar a alimentação no conjunto dos preços.
# --------------------------------------------------------------------------
AGREGADOS = [
    {"cod": "CP00",           "nome": "Todos os produtos",        "cor": "#171715", "larg": 2.6},
    {"cod": "FOOD",           "nome": "Alimentação e bebidas",    "cor": "#0E7433", "larg": 2.6},
    {"cod": "FOOD_NP",        "nome": "Alimentos não transformados", "cor": "#D02117", "larg": 2.0},
    {"cod": "FOOD_P",         "nome": "Alimentos transformados",  "cor": "#BE9C54", "larg": 2.0},
    {"cod": "NRG",            "nome": "Energia",                  "cor": "#7a5ea8", "larg": 1.8},
    {"cod": "TOT_X_NRG_FOOD", "nome": "Subjacente (sem energia nem alimentos)",
     "cor": "#2B5683", "larg": 1.8},
]
COD_AGREGADOS = [a["cod"] for a in AGREGADOS]

# --------------------------------------------------------------------------
# Países para comparação europeia
# --------------------------------------------------------------------------
PAISES = {
    "PT": "Portugal",
    "EU27_2020": "UE-27",
    "ES": "Espanha",
    "FR": "França",
    "IT": "Itália",
    "DE": "Alemanha",
    "EL": "Grécia",
    "IE": "Irlanda",
    "PL": "Polónia",
    "NL": "Países Baixos",
    "BE": "Bélgica",
    "AT": "Áustria",
}

PAISES_POR_DEFEITO = ["PT", "EU27_2020", "ES", "FR"]

# --------------------------------------------------------------------------
# Número de agregados familiares — divisor da despesa nacional
# --------------------------------------------------------------------------
# Valor de referência oficial. Os Censos são a fonte autoritativa para o número
# de agregados: é um apuramento exaustivo, não uma estimativa por amostragem.
AGREGADOS_CENSOS = 4_149_096
AGREGADOS_FONTE = "INE, Censos 2021 (resultados definitivos)"
AGREGADOS_ANO = 2021

# Dimensão média do agregado — apenas usada se o Eurostat não responder.
# O valor corrente é obtido de ilc_lvph01 (EU-SILC) em cada sessão: está em
# queda em toda a Europa, pelo que uma constante desatualiza-se depressa.
DIMENSAO_RECUO = 2.4
DIMENSAO_RECUO_FONTE = "Eurostat, ilc_lvph01 (EU-SILC), 2025"

# --------------------------------------------------------------------------
# Metadados institucionais
# --------------------------------------------------------------------------
ORGANISMO = "Secretaria-Geral do Governo"
UNIDADE = "DSSD · Unidade de Pesquisa e Estatísticas"
RODAPE = (
    "Ferramenta de trabalho interno — não constitui posição oficial da "
    "Secretaria-Geral do Governo. Os dados são obtidos em direto do Eurostat; "
    "o valor de referência do cabaz e as taxas de IVA são parâmetros do utilizador."
)

MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez"]


def mes_pt(periodo: str) -> str:
    """Converte '2026-06' em 'jun/26'."""
    try:
        ano, mes = str(periodo).split("-")[:2]
        return f"{MESES_PT[int(mes) - 1]}/{ano[2:]}"
    except (ValueError, IndexError):
        return str(periodo)


def euro(valor, casas: int = 2) -> str:
    """Formata em euros com convenção portuguesa (vírgula decimal)."""
    if valor is None:
        return "—"
    txt = f"{valor:,.{casas}f}".replace(",", "\u00a0").replace(".", ",")
    return f"{txt} €"


def percentagem(valor, casas: int = 1, sinal: bool = True) -> str:
    if valor is None:
        return "—"
    pre = "+" if (sinal and valor > 0) else ""
    return f"{pre}{valor:.{casas}f}".replace(".", ",") + " %"
