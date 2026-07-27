"""
Testes dos cálculos analíticos.

Executar:  python -m pytest tests/ -v
"""
import pandas as pd
import pytest

from src.calculos import decompor, resumo_iva, simular_iva
from src.config import CODIGOS


@pytest.fixture
def decomposicao():
    pesos = {c: 100.0 for c in CODIGOS}        # nove classes com peso igual
    variacoes = {c: 10.0 for c in CODIGOS}     # todas a +10 %
    return decompor(900.0, pesos, variacoes)


def test_quotas_somam_um(decomposicao):
    assert decomposicao["quota"].sum() == pytest.approx(1.0)


def test_valores_somam_o_cabaz(decomposicao):
    assert decomposicao["valor"].sum() == pytest.approx(900.0)


def test_contributo_e_aditivo(decomposicao):
    """A soma dos contributos tem de igualar a variação do total."""
    total = decomposicao["valor"].sum()
    antes = sum(r.valor / (1 + r.variacao / 100) for r in decomposicao.itertuples())
    assert decomposicao["contributo"].sum() == pytest.approx(total - antes)


def test_contributo_conhecido():
    """100 € que cresceram 25 % valiam 80 € há um ano: contributo de 20 €."""
    df = decompor(100.0, {"CP0111": 1.0}, {"CP0111": 25.0})
    assert df.loc[df["codigo"] == "CP0111", "contributo"].iloc[0] == pytest.approx(20.0)


def test_variacao_em_falta_nao_quebra():
    df = decompor(100.0, {c: 1.0 for c in CODIGOS}, {})
    assert df["contributo"].isna().all()
    assert df["valor"].sum() == pytest.approx(100.0)


# ------------------------------------------------------------ simulação de IVA
def _uma_classe(valor, iva):
    return pd.DataFrame([{
        "codigo": "CP0111", "classe": "Teste", "emoji": "🍞", "cor": "#000",
        "valor": valor, "iva_defeito": iva,
    }])


def test_base_sem_iva():
    sim = simular_iva(_uma_classe(106.0, 6), {"CP0111": 6}, {"CP0111": 6}, 1.0)
    assert sim["base"].iloc[0] == pytest.approx(100.0)


def test_repercussao_integral():
    """106 € a 6 % passando a 0 %, com repercussão total, dá 100 €."""
    sim = simular_iva(_uma_classe(106.0, 6), {"CP0111": 6}, {"CP0111": 0}, 1.0)
    assert sim["novo_valor"].iloc[0] == pytest.approx(100.0)


def test_repercussao_nula_nao_altera_preco():
    sim = simular_iva(_uma_classe(106.0, 6), {"CP0111": 6}, {"CP0111": 0}, 0.0)
    assert sim["novo_valor"].iloc[0] == pytest.approx(106.0)
    assert sim["iva_depois"].iloc[0] == pytest.approx(0.0)
    assert sim["margem"].iloc[0] == pytest.approx(-6.0)


def test_repercussao_parcial_reparte():
    """Com 40 %, o consumidor poupa 2,40 € e a margem capta 3,60 €."""
    sim = simular_iva(_uma_classe(106.0, 6), {"CP0111": 6}, {"CP0111": 0}, 0.4)
    assert -sim["efetivo"].iloc[0] == pytest.approx(2.40)
    assert -sim["margem"].iloc[0] == pytest.approx(3.60)


def test_subida_de_taxa():
    sim = simular_iva(_uma_classe(106.0, 6), {"CP0111": 6}, {"CP0111": 23}, 1.0)
    assert sim["novo_valor"].iloc[0] == pytest.approx(123.0)


def test_receita_perdida_e_independente_da_repercussao():
    """O Estado perde o mesmo em qualquer cenário; muda quem fica com o dinheiro."""
    perdas = []
    for rho in (0.0, 0.4, 1.0):
        sim = simular_iva(_uma_classe(106.0, 6), {"CP0111": 6}, {"CP0111": 0}, rho)
        perdas.append(resumo_iva(sim, 106.0, 52, 1)["receita_cabaz"])
    assert all(p == pytest.approx(-6.0) for p in perdas)


# --------------------------------- inversão do efeito da escala
def test_efeito_da_escala_inverte_na_dimensao_media():
    """
    Como a escala é aplicada ao agregado em análise e ao agregado médio de
    referência, o efeito de trocar de escala inverte-se conforme o agregado seja
    menor ou maior do que a média nacional. Não é um erro: é o que qualquer
    normalização por escala de equivalência produz.
    """
    from src.calculos import despesa_do_agregado

    media, dim = 665.70, 2.5

    # agregado MENOR do que a média: coeficientes menores dão valor MAIOR
    casal_orig = despesa_do_agregado(media, dim, 2, 0, "ocde_original")
    casal_modi = despesa_do_agregado(media, dim, 2, 0, "ocde_modificada")
    assert casal_modi > casal_orig

    # agregado MAIOR do que a média: coeficientes menores dão valor MENOR
    familia_orig = despesa_do_agregado(media, dim, 2, 3, "ocde_original")
    familia_modi = despesa_do_agregado(media, dim, 2, 3, "ocde_modificada")
    assert familia_modi < familia_orig

    # o valor é sempre crescente no número de pessoas, seja qual for a escala
    for escala in ("per_capita", "ocde_original", "ocde_modificada"):
        serie = [despesa_do_agregado(media, dim, 1, c, escala) for c in range(0, 5)]
        assert serie == sorted(serie)


def test_esforco_constante_quando_escalas_coincidem():
    """
    Se a despesa e o rendimento usarem a mesma escala de equivalência, o esforço
    alimentar é constante seja qual for a composição do agregado — ambos os lados
    escalam de forma idêntica. A variação observada na aplicação resulta, portanto,
    da diferença entre a escala escolhida para a despesa e a OCDE modificada, que
    o EU-SILC impõe ao rendimento. Propriedade a preservar.
    """
    from src.calculos import despesa_do_agregado, unidades_equivalentes

    media, dim, rendimento_eq = 422.54, 2.4, 11500.0
    esforcos = []
    for adultos, criancas in [(1, 0), (2, 0), (2, 2), (2, 4), (3, 1)]:
        desp = despesa_do_agregado(media, dim, adultos, criancas, "ocde_modificada")
        rend = rendimento_eq * unidades_equivalentes(adultos, criancas, "ocde_modificada") / 12
        esforcos.append(desp / rend * 100)
    assert max(esforcos) - min(esforcos) < 1e-9

    # com escalas diferentes, o esforço tem de crescer com a dimensão
    crescentes = []
    for adultos, criancas in [(1, 0), (2, 0), (2, 2), (2, 4)]:
        desp = despesa_do_agregado(media, dim, adultos, criancas, "ocde_original")
        rend = rendimento_eq * unidades_equivalentes(adultos, criancas, "ocde_modificada") / 12
        crescentes.append(desp / rend * 100)
    assert crescentes == sorted(crescentes)
