"""Schema da saída da LLM para o estudo geral (docs/CONTEUDO_E_LLM.md §5).

Só estrutura e limites de tamanho. Regras de conteúdo (ex.: sem citação bíblica entre aspas,
leitura complementar entre os candidatos) ficam no pipeline de geração (tarefa 3.7).
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

Paragraph = Annotated[str, Field(min_length=40, max_length=1500)]


class ComplementaryReadingChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_index: int = Field(ge=0, description="Índice do candidato escolhido na lista numerada")
    reason: str = Field(min_length=5, max_length=300)


class StudyLlmOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=40, description="1 a 3 palavras, estilo 'SUPERE'")
    body: list[Paragraph] = Field(min_length=3, max_length=5, description="3 a 5 parágrafos")
    application: str = Field(min_length=10, max_length=400, description="1 a 2 frases")
    prayer: str = Field(min_length=10, max_length=600, description="2 a 4 frases")
    complementary_reading: ComplementaryReadingChoice
    keywords: list[Annotated[str, Field(min_length=2, max_length=30)]] = Field(min_length=2, max_length=4)

    @field_validator("title")
    @classmethod
    def _title_words(cls, v: str) -> str:
        v = v.strip()
        if not 1 <= len(v.split()) <= 3:
            raise ValueError("o título deve ter de 1 a 3 palavras")
        return v

    @field_validator("keywords")
    @classmethod
    def _normalize_keywords(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for k in v:
            k = k.strip().lstrip("#").strip().lower()
            if k and k not in out:
                out.append(k)
        if len(out) < 2:
            raise ValueError("informe de 2 a 4 palavras-chave distintas")
        return out
