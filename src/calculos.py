"""
Cálculos analíticos: decomposição da despesa alimentar e simulação de alterações do IVA.

Notas metodológicas
-------------------
**Decomposição.** Não existe fonte pública com o preço dos produtos individuais.
O que se faz aqui é imputar o valor total pelas nove classes
COICOP, usando os ponderadores oficiais do IHPC, e aplicar a cada classe a sua
variação oficial. É uma reconstituição defensável e replicável — não é a
observação produto a produto.

**Contributo homólogo.** Se uma classe vale hoje Vᵢ e cresceu gᵢ %, há um ano
valia Vᵢ/(1+gᵢ). O acréscimo absoluto é Vᵢ·gᵢ/(1+gᵢ). A soma destes acréscimos
iguala exatamente a variação do total — a decomposição é aditiva.

**Simulação de IVA.** O parâmetro decisivo não é a taxa, é a repercussão: a
avaliação internacional (França 2009, Suécia) é consistentemente cética quanto
à transmissão integral das descidas de IVA para o preço final. Por isso a
repercussão é explícita e ajustável, e o resultado é sempre condicional a ela.
"""

from __future__ import annotations

import pandas as pd

from .config import CLASSES, POR_CODIGO


# --------------------------------------------------------------------------
# Decomposição da despesa alimentar
# --------------------------------------------------------------------------
def decompor(valor_total: float,
             pesos: dict[str, float],
             variacoes: dict[str, float]) -> pd.DataFrame:
    """
    Reparte a despesa alimentar pelas classes e calcula o contributo de cada uma
    para a variação homóloga.

    Devolve um DataFrame com uma linha por classe.
    """
    total_pesos = sum(v for v in pesos.values() if v and v > 0)

    linhas = []
    for classe in CLASSES:
        cod = classe["cod"]
        peso = float(pesos.get(cod) or 0.0)
        quota = peso / total_pesos if total_pesos > 0 else 0.0
        valor = valor_total * quota

        var = variacoes.get(cod)
        if var is not None and pd.notna(var) and (1 + var / 100) != 0:
            contributo = valor * (var / 100) / (1 + var / 100)
        else:
            var, contributo = None, None

        linhas.append({
            "codigo": cod,
            "classe": classe["nome"],
            "emoji": classe["emoji"],
            "cor": classe["cor"],
            "ponderador": peso,
            "quota": quota,
            "valor": valor,
            "variacao": var,
            "contributo": contributo,
            "iva_defeito": classe["iva"],
        })

    return pd.DataFrame(linhas)


def resumo_decomposicao(df: pd.DataFrame, valor_total: float) -> dict:
    """Indicadores agregados da decomposição."""
    contributos = df["contributo"].dropna()
    total_contributo = float(contributos.sum()) if not contributos.empty else None

    resultado = {
        "valor": valor_total,
        "contributo_total": total_contributo,
        "valor_ha_um_ano": None,
        "variacao_implicita": None,
        "maior": None,
    }

    if total_contributo is not None:
        antes = valor_total - total_contributo
        resultado["valor_ha_um_ano"] = antes
        if antes > 0:
            resultado["variacao_implicita"] = total_contributo / antes * 100

        com_dados = df.dropna(subset=["contributo"])
        if not com_dados.empty:
            resultado["maior"] = com_dados.loc[com_dados["contributo"].idxmax()].to_dict()

    return resultado


# --------------------------------------------------------------------------
# Simulação de IVA
# --------------------------------------------------------------------------
def simular_iva(df: pd.DataFrame,
                taxas_atuais: dict[str, float],
                taxas_cenario: dict[str, float],
                repercussao: float) -> pd.DataFrame:
    """
    Para cada classe:

    - `base`      preço sem IVA = valor / (1 + t₀)
    - `mecanico`  variação com repercussão integral = base·(1+t₁) − valor
    - `efetivo`   variação observada = ρ · mecanico
    - `margem`    parte capturada pelo operador = (1−ρ) · mecanico
    - `iva_antes` / `iva_depois`  imposto contido no preço

    `repercussao` é uma fração entre 0 e 1.
    """
    linhas = []
    for _, linha in df.iterrows():
        cod = linha["codigo"]
        valor = float(linha["valor"])
        t0 = float(taxas_atuais.get(cod, linha["iva_defeito"]))
        t1 = float(taxas_cenario.get(cod, t0))

        base = valor / (1 + t0 / 100)
        preco_cheio = base * (1 + t1 / 100)
        mecanico = preco_cheio - valor
        efetivo = repercussao * mecanico
        novo_valor = valor + efetivo

        iva_antes = valor - base
        iva_depois = novo_valor * (t1 / 100) / (1 + t1 / 100)

        linhas.append({
            "codigo": cod,
            "classe": linha["classe"],
            "emoji": linha["emoji"],
            "cor": linha["cor"],
            "valor": valor,
            "taxa_atual": t0,
            "taxa_cenario": t1,
            "base": base,
            "mecanico": mecanico,
            "efetivo": efetivo,
            "margem": mecanico - efetivo,
            "novo_valor": novo_valor,
            "iva_antes": iva_antes,
            "iva_depois": iva_depois,
        })

    return pd.DataFrame(linhas)


def resumo_iva(sim: pd.DataFrame, valor_total: float,
               vezes_ano: int, agregados: int) -> dict:
    """Agrega o resultado da simulação e extrapola ordens de grandeza."""
    mecanico = float(sim["mecanico"].sum())
    efetivo = float(sim["efetivo"].sum())
    margem = float(sim["margem"].sum())
    iva_antes = float(sim["iva_antes"].sum())
    iva_depois = float(sim["iva_depois"].sum())

    poupanca_mes = -efetivo          # positiva quando a despesa desce
    poupanca_ano = poupanca_mes * vezes_ano
    receita_mes = iva_depois - iva_antes

    return {
        "novo_valor": valor_total + efetivo,
        "mecanico": mecanico,
        "efetivo": efetivo,
        "poupanca_mes": poupanca_mes,
        "poupanca_ano": poupanca_ano,
        "margem": -margem,
        "iva_antes": iva_antes,
        "iva_depois": iva_depois,
        "receita_mes": receita_mes,
        "poupanca_agregada_milhoes": poupanca_ano * agregados / 1e6,
        "receita_agregada_milhoes": receita_mes * vezes_ano * agregados / 1e6,
    }


# --------------------------------------------------------------------------
# Composição do agregado e escalas de equivalência
# --------------------------------------------------------------------------
# Uma despesa média por agregado esconde uma diferença que importa para
# política: um agregado de uma pessoa e um casal com dois filhos não gastam o
# mesmo. As escalas de equivalência são o instrumento oficial para comparar
# agregados de composição diferente.
#
# Ressalva importante: estas escalas foram construídas para o consumo *total*,
# em que a partilha de habitação gera fortes economias de escala. Na
# alimentação as economias de escala são bem mais fracas — não se partilha uma
# refeição como se partilha um teto. Por isso a escala OCDE modificada tende a
# **subestimar** o custo alimentar de agregados maiores, e a aplicação
# apresenta sempre um intervalo em vez de um valor único.

ESCALAS = {
    "per_capita": {
        "nome": "Per capita (sem economias de escala)",
        "primeiro": 1.0, "adulto": 1.0, "crianca": 1.0,
        "nota": "Limite superior: cada pessoa custa o mesmo.",
    },
    "ocde_original": {
        "nome": "OCDE original (1 / 0,7 / 0,5)",
        "primeiro": 1.0, "adulto": 0.7, "crianca": 0.5,
        "nota": "Intermédia — a mais adequada para despesa alimentar.",
    },
    "ocde_modificada": {
        "nome": "OCDE modificada (1 / 0,5 / 0,3)",
        "primeiro": 1.0, "adulto": 0.5, "crianca": 0.3,
        "nota": "Norma da UE para rendimento; subestima o custo alimentar.",
    },
}


def unidades_equivalentes(adultos: int, criancas: int, escala: str) -> float:
    """Unidades de consumo equivalente de um agregado, segundo a escala."""
    e = ESCALAS[escala]
    adultos = max(int(adultos), 1)
    criancas = max(int(criancas), 0)
    return e["primeiro"] + e["adulto"] * (adultos - 1) + e["crianca"] * criancas


def despesa_do_agregado(despesa_media_agregado: float,
                        dimensao_media: float,
                        adultos: int,
                        criancas: int,
                        escala: str) -> float:
    """
    Converte a despesa média nacional por agregado na despesa estimada de um
    agregado com a composição indicada.

    O agregado médio é modelado com `dimensao_media` pessoas adultas — é uma
    aproximação, necessária porque a dimensão média é publicada sem
    decomposição por idade.
    """
    e = ESCALAS[escala]
    eq_medio = e["primeiro"] + e["adulto"] * (max(dimensao_media, 1.0) - 1)
    if eq_medio <= 0:
        return despesa_media_agregado
    por_unidade = despesa_media_agregado / eq_medio
    return por_unidade * unidades_equivalentes(adultos, criancas, escala)


def intervalo_agregado(despesa_media_agregado: float, dimensao_media: float,
                       adultos: int, criancas: int) -> dict:
    """Intervalo entre a escala mais generosa e a mais restritiva."""
    valores = {
        chave: despesa_do_agregado(despesa_media_agregado, dimensao_media,
                                   adultos, criancas, chave)
        for chave in ESCALAS
    }
    return {
        "minimo": min(valores.values()),
        "maximo": max(valores.values()),
        "por_escala": valores,
    }
