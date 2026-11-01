import datetime as dt
import uuid

import pytest
from sqlalchemy import text, update

from app.core.crypto import CryptoError, FieldCipher, parse_keys
from app.db.models import Note
from tests.conftest import FIELD_KEY

K1 = "1:" + "A" * 43
K2 = "2:" + "B" * 43
TEXTO = "Hoje entendi que Ele cuida de mim. Jo 10.11 🙏 — confissão: estava ansioso com a cirurgia."

# --- criptografia --------------------------------------------------------------------------------


def test_cifra_e_decifra_com_aad():
    c = FieldCipher(K1)
    enc = c.encrypt(TEXTO, "note:u1:2026-11-01")
    assert TEXTO.encode() not in enc and enc[:2] == bytes([1, 1])
    assert c.decrypt(enc, "note:u1:2026-11-01") == TEXTO
    with pytest.raises(CryptoError):  # bytes copiados para outro usuário/data não decifram
        c.decrypt(enc, "note:u2:2026-11-01")
    adulterado = enc[:-1] + bytes([enc[-1] ^ 1])
    with pytest.raises(CryptoError):
        c.decrypt(adulterado, "note:u1:2026-11-01")


def test_rotacao_de_chave():
    antiga = FieldCipher(K1)
    enc = antiga.encrypt("texto", "a")
    nova = FieldCipher(f"{K2},{K1}")  # nova chave na frente, antiga só para decifrar
    assert nova.decrypt(enc, "a") == "texto"
    assert nova.needs_reencrypt(enc)
    assert nova.encrypt("texto", "a")[1] == 2
    with pytest.raises(CryptoError):
        FieldCipher(K2).decrypt(enc, "a")  # chave 1 removida cedo demais


@pytest.mark.parametrize(
    "spec", [None, "", "curta", "1:" + "A" * 10, "1:" + "A" * 43 + ",1:" + "B" * 43, "0:" + "A" * 43]
)
def test_chaves_invalidas(spec):
    with pytest.raises(CryptoError):
        parse_keys(spec)


def test_chave_sem_id_vale_como_1():
    assert set(parse_keys("A" * 43)) == {1}


# --- API --------------------------------------------------------------------------------------------

HOJE = dt.datetime.now(dt.UTC).astimezone(dt.timezone(dt.timedelta(hours=-3))).date()
ONTEM = HOJE - dt.timedelta(days=1)


async def test_criar_ler_editar(api_db, login):
    client, maker = api_db
    h, body = await login()
    r = await client.put(f"/v1/notes/{ONTEM}", headers=h, json={"body": TEXTO, "base_version": 0})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 1

    r = await client.get(f"/v1/notes/{ONTEM}", headers=h)
    assert r.json()["body"] == TEXTO and r.json()["deleted"] is False

    r = await client.put(f"/v1/notes/{ONTEM}", headers=h, json={"body": TEXTO + " Amém.", "base_version": 1})
    assert r.json()["version"] == 2

    # o banco guarda só bytes cifrados
    async with maker() as s:
        raw = (
            await s.execute(
                text("SELECT encrypted_body FROM notes WHERE user_id = :u"),
                {"u": uuid.UUID(body["user"]["id"])},
            )
        ).scalar()
    assert isinstance(raw, bytes) and b"cirurgia" not in raw and b"cirurgia" not in raw


async def test_conflito_entre_aparelhos(api_db, login):
    client, _ = api_db
    h, _ = await login()
    await client.put(f"/v1/notes/{HOJE}", headers=h, json={"body": "versão do celular", "base_version": 0})
    await client.put(f"/v1/notes/{HOJE}", headers=h, json={"body": "editada no celular", "base_version": 1})
    # o tablet ainda estava na versão 1
    r = await client.put(
        f"/v1/notes/{HOJE}", headers=h, json={"body": "editada no tablet", "base_version": 1}
    )
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "note_conflict"
    assert err["details"]["body"] == "editada no celular" and err["details"]["version"] == 2
    # criar de novo uma que já existe também é conflito
    r = await client.put(f"/v1/notes/{HOJE}", headers=h, json={"body": "x", "base_version": 0})
    assert r.status_code == 409


async def test_excluir_com_tombstone_e_recriar(api_db, login):
    client, _ = api_db
    h, _ = await login()
    await client.put(f"/v1/notes/{ONTEM}", headers=h, json={"body": "texto", "base_version": 0})
    assert (
        await client.delete(f"/v1/notes/{ONTEM}", headers=h, params={"base_version": 9})
    ).status_code == 409
    assert (
        await client.delete(f"/v1/notes/{ONTEM}", headers=h, params={"base_version": 1})
    ).status_code == 204
    assert (await client.get(f"/v1/notes/{ONTEM}", headers=h)).status_code == 404
    assert (
        await client.delete(f"/v1/notes/{ONTEM}", headers=h, params={"base_version": 2})
    ).status_code == 204
    # recriar sobre o tombstone exige a versão dele (2)
    assert (
        await client.put(f"/v1/notes/{ONTEM}", headers=h, json={"body": "nova", "base_version": 0})
    ).status_code == 409
    r = await client.put(f"/v1/notes/{ONTEM}", headers=h, json={"body": "nova", "base_version": 2})
    assert r.status_code == 200 and r.json()["version"] == 3


async def test_pull_incremental_inclui_exclusoes(api_db, login):
    client, maker = api_db
    h, _ = await login()
    d1, d2 = ONTEM - dt.timedelta(days=1), ONTEM
    await client.put(f"/v1/notes/{d1}", headers=h, json={"body": "um", "base_version": 0})
    await client.put(f"/v1/notes/{d2}", headers=h, json={"body": "dois", "base_version": 0})

    primeira = (await client.get("/v1/notes", headers=h)).json()
    assert {i["date"] for i in primeira["items"]} == {str(d1), str(d2)}
    assert primeira["full_sync_required"] is False

    # depois do pull: edição de d1 e exclusão de d2
    async with maker() as s:  # empurra as escritas antigas para antes do server_time
        await s.execute(update(Note).values(updated_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5)))
        await s.commit()
    since = (await client.get("/v1/notes", headers=h)).json()["server_time"]
    await client.put(f"/v1/notes/{d1}", headers=h, json={"body": "um editado", "base_version": 1})
    await client.delete(f"/v1/notes/{d2}", headers=h, params={"base_version": 1})

    r = (await client.get("/v1/notes", headers=h, params={"updated_since": since})).json()
    por_data = {i["date"]: i for i in r["items"]}
    assert set(por_data) == {str(d1), str(d2)}
    assert por_data[str(d1)]["body"] == "um editado"
    assert por_data[str(d2)]["deleted"] is True and por_data[str(d2)]["body"] is None


async def test_since_muito_antigo_pede_sync_completo(api_db, login):
    client, _ = api_db
    h, _ = await login()
    antigo = (dt.datetime.now(dt.UTC) - dt.timedelta(days=45)).isoformat()
    r = (await client.get("/v1/notes", headers=h, params={"updated_since": antigo})).json()
    assert r["full_sync_required"] is True


async def test_isolamento_entre_usuarios(api_db, login):
    client, _ = api_db
    h1, _ = await login()
    h2, _ = await login()
    await client.put(
        f"/v1/notes/{HOJE}", headers=h1, json={"body": "segredo do usuário 1", "base_version": 0}
    )
    assert (await client.get(f"/v1/notes/{HOJE}", headers=h2)).status_code == 404
    assert (await client.get("/v1/notes", headers=h2)).json()["items"] == []


async def test_validacoes(api_db, login):
    client, _ = api_db
    h, _ = await login()
    futuro = HOJE + dt.timedelta(days=5)
    r = await client.put(f"/v1/notes/{futuro}", headers=h, json={"body": "x", "base_version": 0})
    assert r.status_code == 422 and r.json()["error"]["code"] == "future_date"
    r = await client.put(f"/v1/notes/{HOJE}", headers=h, json={"body": "x" * 10_001, "base_version": 0})
    assert r.status_code == 422
    r = await client.put(f"/v1/notes/{HOJE}", headers=h, json={"body": "x", "base_version": -1})
    assert r.status_code == 422
    assert (await client.get("/v1/notes")).status_code == 401


async def test_export_inclui_texto_das_anotacoes(api_db, login):
    client, _ = api_db
    h, _ = await login()
    await client.put(f"/v1/notes/{HOJE}", headers=h, json={"body": TEXTO, "base_version": 0})
    notes = (await client.get("/v1/me/export", headers=h)).json()["notes"]
    assert notes == [{"date": str(HOJE), "body": TEXTO, "version": 1, "updated_at": notes[0]["updated_at"]}]


async def test_limpeza_de_tombstones(api_db, login):
    from app.notes.service import NotesService

    client, maker = api_db
    h, body = await login()
    uid = uuid.UUID(body["user"]["id"])
    await client.put(f"/v1/notes/{ONTEM}", headers=h, json={"body": "x", "base_version": 0})
    await client.delete(f"/v1/notes/{ONTEM}", headers=h, params={"base_version": 1})
    async with maker() as s:
        svc = NotesService(s, FieldCipher(FIELD_KEY))
        await svc.purge_tombstones()  # tombstones recentes (menos de 30 dias) ficam
        n = (await s.execute(text("SELECT count(*) FROM notes WHERE user_id = :u"), {"u": uid})).scalar()
        assert n == 1
        removidos = await svc.purge_tombstones(now=dt.datetime.now(dt.UTC) + dt.timedelta(days=31))
        assert removidos >= 1
        n = (await s.execute(text("SELECT count(*) FROM notes WHERE user_id = :u"), {"u": uid})).scalar()
        assert n == 0
