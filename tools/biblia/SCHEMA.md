# Schema do `blivre.sqlite` e compatibilidade com o Room

O mesmo arquivo é usado pelo servidor (somente leitura) e embarcado no app via
`Room.databaseBuilder(...).createFromAsset("blivre.sqlite")`. O Room **valida** o banco ao abrir
(tabelas, colunas, afinidade, NOT NULL, PK, índices, FKs e o SQL das tabelas FTS). Qualquer
divergência derruba o app em tempo de execução, então o DDL de `blivre/importar.py` (`SCHEMA_DDL`)
segue exatamente o formato que o Room gera.

`PRAGMA user_version` = `SCHEMA_VERSION` (hoje **1**) = `version` do `@Database`.

## Tabelas

| Tabela | Colunas | Observações |
|---|---|---|
| `books` | `id` INTEGER PK, `usfm` TEXT (único), `name_pt`, `abbrev_pt`, `testament` (`OT`/`NT`), `ordinal`, `chapters` | `id` = `ordinal` (1–66) |
| `verses` | `id` INTEGER PK, `book_id` → books, `chapter`, `verse`, `text` | `id` = livro×1.000.000 + cap×1.000 + vers. (João 3.16 = `43003016`); índice único (book_id, chapter, verse) |
| `verses_fts` | `text` | FTS4 `content=verses`, `tokenize=unicode61 remove_diacritics=1` (busca sem acento); `rowid` = `verses.id` |
| `footnotes` | `id` PK, `verse_id` → verses, `ordinal`, `position`, `kind` (`note`/`quote_source`), `quote` (nulo), `text` | Notas `\f` e referências de citação `\rq` da fonte; `position` = offset no texto limpo |
| `superscriptions` | PK (`book_id`, `chapter`), `text` | Títulos de salmos (`\d`), exibidos antes do v. 1 |
| `metadata` | `key` PK, `value` | `source_id`, `source_url`, `source_sha256`, `translation`, `license`, `attribution` |

## Entidades Room (Fase 5 — `core/bible`)

```kotlin
@Entity(tableName = "books", indices = [Index(value = ["usfm"], unique = true)])
data class BookEntity(
    @PrimaryKey val id: Int,
    val usfm: String,
    @ColumnInfo(name = "name_pt") val namePt: String,
    @ColumnInfo(name = "abbrev_pt") val abbrevPt: String,
    val testament: String,
    val ordinal: Int,
    val chapters: Int,
)

@Entity(
    tableName = "verses",
    foreignKeys = [ForeignKey(entity = BookEntity::class, parentColumns = ["id"], childColumns = ["book_id"])],
    indices = [Index(value = ["book_id", "chapter", "verse"], unique = true)],
)
data class VerseEntity(
    @PrimaryKey val id: Int,
    @ColumnInfo(name = "book_id") val bookId: Int,
    val chapter: Int,
    val verse: Int,
    val text: String,
)

@Fts4(contentEntity = VerseEntity::class, tokenizer = FtsOptions.TOKENIZER_UNICODE61,
      tokenizerArgs = ["remove_diacritics=1"])
@Entity(tableName = "verses_fts")
data class VerseFts(val text: String)

@Entity(
    tableName = "footnotes",
    foreignKeys = [ForeignKey(entity = VerseEntity::class, parentColumns = ["id"], childColumns = ["verse_id"])],
    indices = [Index(value = ["verse_id"])],
)
data class FootnoteEntity(
    @PrimaryKey val id: Int,
    @ColumnInfo(name = "verse_id") val verseId: Int,
    val ordinal: Int,
    val position: Int,
    val kind: String,
    val quote: String?,
    val text: String,
)

@Entity(
    tableName = "superscriptions",
    primaryKeys = ["book_id", "chapter"],
    foreignKeys = [ForeignKey(entity = BookEntity::class, parentColumns = ["id"], childColumns = ["book_id"])],
)
data class SuperscriptionEntity(
    @ColumnInfo(name = "book_id") val bookId: Int,
    val chapter: Int,
    val text: String,
)

@Entity(tableName = "metadata")
data class MetadataEntity(@PrimaryKey val key: String, val value: String)

@Database(
    entities = [BookEntity::class, VerseEntity::class, VerseFts::class, FootnoteEntity::class,
                SuperscriptionEntity::class, MetadataEntity::class],
    version = 1,
    exportSchema = true,
)
abstract class BlivreDatabase : RoomDatabase()
```

O banco é somente leitura no app, então os gatilhos de sincronização FTS que o Room cria
(`room_fts_content_sync_*`) não são necessários: o Room não os valida.

## Procedimento de verificação

1. No app, `exportSchema = true` com `room { schemaDirectory("$projectDir/schemas") }` no Gradle.
2. `./gradlew :app:kspDebugKotlin` gera
   `android/app/schemas/com.marcosparra.manadiario.core.bible.BlivreDatabase/1.json`.
3. `cd tools/biblia && uv run pytest tests/test_room_schema.py`: o teste
   `test_banco_bate_com_schema_exportado_pelo_app` deixa de ser pulado e compara o banco com esse JSON.
4. Mudou o schema? Atualize `SCHEMA_DDL`, `SCHEMA_VERSION`, as entidades e este arquivo **juntos**.
   Teste instrumentado da Fase 5 (5.5): abrir o asset e ler João 3.16.
