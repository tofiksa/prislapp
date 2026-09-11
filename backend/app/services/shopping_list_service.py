"""S06-A: handlelister med eierskap, idempotens, slettemarkører og inkrementell sync.

Reglene som styrer modulen:

- `user_id` kommer bare fra autentisering. Fremmed liste, linje eller vare gir
  404, også når ID-en står i request body.
- Samme `(user_id, operation, mutation_id)` med samme innhold og samme ressurs
  gir det lagrede svaret. Annet innhold gir 409. Nøklene bor i en egen tabell,
  slik at en listemutasjon aldri kolliderer med en kvitteringsmutasjon.
- `expected_version` som ikke matcher er en konflikt, aldri en stille
  overskriving. REST svarer 409; `/sync` legger konflikten i `conflicts`, slik
  at resten av batchen kan utføres.
- Sletting er en slettemarkør. En klient som har vært uten nett må få vite at
  raden er borte, ellers legger den den inn igjen. Serveren gjenoppliver aldri
  en slettet liste fordi klienten sendte en endring på den.
- Avkryssing er en listehandling. Den oppretter ingen prisobservasjon; en
  avkrysset liste er ikke en kvittering.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.list_copy import (
    MappedListLine,
    SourceListLine,
    SourceReceiptLine,
    copy_list_lines,
    map_receipt_lines,
)
from app.errors import ApiError, FieldError, invalid_cursor
from app.models.account_ledger import AccountLedger
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_item import ReceiptItem
from app.models.receipt_revision import ReceiptRevision, ReceiptRevisionLine, RevisionStatus
from app.models.shopping_list import (
    ShoppingList,
    ShoppingListItem,
    ShoppingListMutation,
    ShoppingListOperation,
    ShoppingListStatus,
    ShoppingListSyncState,
)
from app.models.user_product import UserProduct
from app.schemas.shopping_list import (
    ShoppingListCopyRequest,
    ShoppingListCreateRequest,
    ShoppingListFromReceiptRequest,
    ShoppingListItemCreateRequest,
    ShoppingListItemPatchRequest,
    ShoppingListPatchRequest,
    SyncRequest,
)
from app.schemas.v2 import decimal_string
from app.services.pagination import decode_cursor, encode_cursor, keyset, page_size

# Grensen gjelder aktive linjer, altså ikke-slettede. Avkryssede linjer teller
# med; de er fortsatt en del av handleturen.
MAX_ACTIVE_ITEMS = 200
QUANTITY_QUANTUM = Decimal("0.001")
DEFAULT_FROM_RECEIPT_NAME = "Handleliste"

LIST_CURSOR_SCOPE = "shopping-lists:created"
SYNC_CURSOR_VERSION = 1
# Slettemarkører beholdes minst så lenge. En eldre markør kan peke forbi rader
# som er ryddet, så den kan ikke bevise hva klienten mangler.
TOMBSTONE_RETENTION = timedelta(days=90)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """SQLite gir naive tidspunkt tilbake. Alt lagres i UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def payload_hash(request: BaseModel, *scope: object) -> str:
    """Stabil hash av innholdet og ressursen, uten selve mutasjons-ID-en.

    Ressursen er med fordi en gjenbrukt endrings-ID på en annen liste eller
    linje er nytt innhold, ikke en retry av det samme.
    """
    payload = request.model_dump(
        mode="json",
        exclude={"mutation_id", "operation", "list_id", "item_id"},
    )
    canonical = json.dumps(
        {"scope": [str(part) for part in scope], "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class MutationRejected(ApiError):
    """Én mutasjon er ikke utført.

    REST-rutene lar den passere som en vanlig feil i v2-formatet. `/sync`
    fanger den og legger den i `conflicts`, slik at de øvrige mutasjonene i
    batchen kan utføres.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        field_errors: list[FieldError] | None = None,
        server: dict | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        super().__init__(status_code, code, message, field_errors, retryable=False, extra=extra)
        # Serverens utgave hører til konfliktsvaret, ikke til feilkroppen.
        self.server = server

    def as_conflict(self, mutation: BaseModel) -> dict:
        return {
            "operation": getattr(mutation, "operation", ""),
            "mutation_id": str(mutation.mutation_id),
            "code": self.code,
            "message": self.message,
            "field_errors": [
                {"field": error.field, "code": error.code, "message": error.message}
                for error in self.field_errors
            ],
            # Klientens utgave beholdes som gjenopprettbart utkast hos klienten.
            "local": mutation.model_dump(mode="json", exclude={"operation", "mutation_id"}),
            "server": self.server,
        }


def _not_found() -> MutationRejected:
    """Samme svar for ukjent og fremmed ID, slik at eierskap ikke lekker."""
    return MutationRejected(404, "NOT_FOUND", "Fant ikke ressursen.")


def _validation_error(field: str, code: str, message: str) -> MutationRejected:
    return MutationRejected(
        400,
        "VALIDATION_ERROR",
        "Endringen kan ikke lagres slik den er.",
        [FieldError(field, code, message)],
    )


def _duplicate_id(field: str) -> MutationRejected:
    return MutationRejected(
        409,
        "DUPLICATE_ID",
        "ID-en er allerede i bruk. Bruk en ny ID for en ny rad.",
        [FieldError(field, "id_taken", "ID-en finnes allerede.")],
    )


def _mutation_conflict() -> MutationRejected:
    return MutationRejected(
        409,
        "MUTATION_CONFLICT",
        "Samme endrings-ID er allerede brukt med et annet innhold.",
        [
            FieldError(
                "mutation_id",
                "payload_mismatch",
                "Bruk en ny endrings-ID for nytt innhold.",
            ),
        ],
    )


def _version_conflict(current_version: int, server: dict) -> MutationRejected:
    return MutationRejected(
        409,
        "VERSION_CONFLICT",
        "Raden er endret et annet sted. Sammenlign verdiene og velg.",
        [
            FieldError(
                "expected_version",
                "stale_version",
                f"Gjeldende versjon er {current_version}.",
            ),
        ],
        server=server,
        extra={"current_version": current_version},
    )


def _list_deleted(server: dict) -> MutationRejected:
    """Serveren gjenoppliver ikke en slettet liste fordi klienten redigerte den."""
    return MutationRejected(
        404,
        "LIST_DELETED",
        "Listen er slettet. Den gjenopprettes ikke av en endring.",
        [FieldError("list_id", "list_deleted", "Listen har en slettemarkør.")],
        server=server,
    )


def _item_deleted(server: dict) -> MutationRejected:
    return MutationRejected(
        404,
        "ITEM_DELETED",
        "Linjen er slettet. Den gjenopprettes ikke av en endring.",
        [FieldError("item_id", "item_deleted", "Linjen har en slettemarkør.")],
        server=server,
    )


def _list_archived(server: dict) -> MutationRejected:
    return MutationRejected(
        409,
        "LIST_ARCHIVED",
        "Listen er arkivert. Gjør den aktiv igjen før du endrer linjene.",
        [FieldError("status", "list_archived", "Gjeldende status er archived.")],
        server=server,
    )


def _item_limit() -> MutationRejected:
    return MutationRejected(
        409,
        "LIST_ITEM_LIMIT",
        f"Listen kan ha maks {MAX_ACTIVE_ITEMS} aktive linjer.",
        [
            FieldError(
                "items",
                "active_item_limit",
                f"Grensen er {MAX_ACTIVE_ITEMS} aktive linjer.",
            ),
        ],
    )


def _cursor_expired() -> MutationRejected:
    return MutationRejected(
        409,
        "CURSOR_EXPIRED",
        "Synkroniseringsmarkøren kan ikke brukes. Avklar de lokale endringene mot snapshotet.",
        [FieldError("cursor", "expired_cursor", "Markøren er utløpt eller ugyldig.")],
    )


def encode_sync_cursor(
    user_id: uuid.UUID,
    sequence: int,
    issued_at: datetime | None = None,
) -> str:
    """Markøren bærer kontoen, synsekvensen og når den ble utstedt."""
    payload = json.dumps(
        {
            "v": SYNC_CURSOR_VERSION,
            "u": str(user_id),
            "s": sequence,
            "t": (issued_at or _now()).isoformat(),
        },
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


@dataclass(frozen=True)
class SyncCursor:
    """`sequence is None` betyr fullt snapshot.

    `replay_allowed` er falsk når markøren ikke kan brukes. Da avspilles ingen
    lokale mutasjoner før klienten har avklart dem mot snapshotet.
    """

    sequence: int | None
    replay_allowed: bool


@dataclass(frozen=True)
class Applied:
    response: dict
    list_id: uuid.UUID
    item_id: uuid.UUID | None = None


def item_response(item: ShoppingListItem) -> dict:
    return {
        "id": str(item.id),
        "user_product_id": None if item.user_product_id is None else str(item.user_product_id),
        "free_text": item.free_text,
        "quantity": decimal_string(item.quantity),
        "quantity_unit": item.quantity_unit,
        "checked": item.checked,
        "position": item.position,
        "version": item.version,
        "deleted": item.deleted_at is not None,
    }


def list_response(shopping_list: ShoppingList, items: list[ShoppingListItem]) -> dict:
    return {
        "id": str(shopping_list.id),
        "name": shopping_list.name,
        "status": shopping_list.status,
        "version": shopping_list.version,
        "deleted": shopping_list.deleted_at is not None,
        "content_revision": shopping_list.content_seq,
        "created_at": _as_utc(shopping_list.created_at).isoformat(),
        "updated_at": _as_utc(shopping_list.updated_at).isoformat(),
        "items": [item_response(item) for item in items],
    }


class ShoppingListService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # --- REST -----------------------------------------------------------

    async def create_list(
        self,
        user_id: uuid.UUID,
        request: ShoppingListCreateRequest,
    ) -> dict:
        return await self._single(
            user_id,
            ShoppingListOperation.LIST_CREATE,
            request,
            (),
            lambda: self._create_list(user_id, request),
        )

    async def patch_list(
        self,
        user_id: uuid.UUID,
        list_id: uuid.UUID,
        request: ShoppingListPatchRequest,
    ) -> dict:
        return await self._single(
            user_id,
            ShoppingListOperation.LIST_PATCH,
            request,
            (list_id,),
            lambda: self._patch_list(user_id, list_id, request),
        )

    async def copy_list(
        self,
        user_id: uuid.UUID,
        list_id: uuid.UUID,
        request: ShoppingListCopyRequest,
    ) -> dict:
        return await self._single(
            user_id,
            ShoppingListOperation.LIST_COPY,
            request,
            (list_id,),
            lambda: self._copy_list(user_id, list_id, request),
        )

    async def create_list_from_receipt(
        self,
        user_id: uuid.UUID,
        request: ShoppingListFromReceiptRequest,
    ) -> dict:
        return await self._single(
            user_id,
            ShoppingListOperation.LIST_FROM_RECEIPT,
            request,
            (request.receipt_id,),
            lambda: self._create_list_from_receipt(user_id, request),
        )

    async def create_item(
        self,
        user_id: uuid.UUID,
        list_id: uuid.UUID,
        request: ShoppingListItemCreateRequest,
    ) -> dict:
        return await self._single(
            user_id,
            ShoppingListOperation.ITEM_CREATE,
            request,
            (list_id,),
            lambda: self._create_item(user_id, list_id, request),
        )

    async def patch_item(
        self,
        user_id: uuid.UUID,
        list_id: uuid.UUID,
        item_id: uuid.UUID,
        request: ShoppingListItemPatchRequest,
    ) -> dict:
        return await self._single(
            user_id,
            ShoppingListOperation.ITEM_PATCH,
            request,
            (list_id, item_id),
            lambda: self._patch_item(user_id, list_id, item_id, request),
        )

    async def get_list(self, user_id: uuid.UUID, list_id: uuid.UUID) -> dict:
        shopping_list = await self._list_row(user_id, list_id)
        if shopping_list.deleted_at is not None:
            # REST viser ikke slettemarkører. Sync gjør det.
            raise _not_found()
        return list_response(shopping_list, await self._items(list_id))

    async def list_lists(
        self,
        user_id: uuid.UUID,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> tuple[list[dict], str | None]:
        size = page_size(limit)
        expression = ShoppingList.created_at
        filters = [ShoppingList.user_id == user_id, ShoppingList.deleted_at.is_(None)]
        if cursor:
            key, row_id = decode_cursor(cursor, LIST_CURSOR_SCOPE)
            filters.append(
                keyset(
                    expression,
                    ShoppingList.id,
                    self._cursor_timestamp(key),
                    row_id,
                    descending=False,
                ),
            )

        result = await self.db.execute(
            sa.select(ShoppingList)
            .where(*filters)
            .order_by(expression.asc(), ShoppingList.id.asc())
            .limit(size + 1),
        )
        rows = list(result.scalars().all())
        page = rows[:size]
        grouped = await self._items_by_list(
            user_id,
            [row.id for row in page],
            include_deleted=False,
        )
        responses = [list_response(row, grouped.get(row.id, [])) for row in page]
        if len(rows) <= size:
            return responses, None
        last = page[-1]
        return responses, encode_cursor(
            LIST_CURSOR_SCOPE,
            _as_utc(last.created_at).isoformat(),
            last.id,
        )

    # --- Sync -----------------------------------------------------------

    async def sync(self, user_id: uuid.UUID, request: SyncRequest) -> dict:
        cursor = await self._parse_sync_cursor(user_id, request.cursor)
        conflicts: list[dict] = []

        if not cursor.replay_allowed:
            # Utløpt markør: klienten får snapshot og må avklare de lokale
            # endringene selv. Ingenting avspilles blindt.
            conflicts = [_cursor_expired().as_conflict(m) for m in request.mutations]
        else:
            for mutation in request.mutations:
                conflict = await self._apply_sync_mutation(user_id, mutation)
                if conflict is not None:
                    conflicts.append(conflict)
        await self.db.commit()

        # Sekvensen stemples før listene leses, ikke etter. Committer en annen
        # enhet i mellomtiden, dekker markøren en endring klienten aldri fikk,
        # og neste inkrementelle sync hopper over den for alltid. Motsatt vei
        # er ufarlig: en endring som allerede er levert, leveres én gang til.
        sequence = await self._sequence(user_id)
        full_snapshot = cursor.sequence is None
        lists = (
            await self._snapshot(user_id)
            if full_snapshot
            else await self._delta(user_id, cursor.sequence)
        )
        return {
            "cursor": encode_sync_cursor(user_id, sequence),
            "price_data_version": await self._price_data_version(user_id),
            "full_snapshot": full_snapshot,
            # Sammenslåing av private produkter kommer i S03-B.
            "replaced_product_ids": [],
            "lists": lists,
            "conflicts": conflicts,
        }

    async def _apply_sync_mutation(self, user_id: uuid.UUID, mutation: BaseModel) -> dict | None:
        operation = ShoppingListOperation(mutation.operation)
        try:
            # Hver mutasjon får sitt eget savepoint, slik at en avvist mutasjon
            # ikke ruller tilbake de uavhengige endringene som ble utført.
            async with self.db.begin_nested():
                digest = payload_hash(mutation, *self._sync_scope(operation, mutation))
                await self._lock_mutation(user_id, operation, mutation.mutation_id)
                replay = await self._replay(user_id, operation, mutation.mutation_id, digest)
                if replay is not None:
                    # Allerede utført én gang. Tilstanden ligger i `lists`.
                    return None
                applied = await self._sync_handler(user_id, operation, mutation)
                self._record(user_id, operation, mutation, digest, applied)
        except MutationRejected as rejected:
            return rejected.as_conflict(mutation)
        return None

    @staticmethod
    def _sync_scope(operation: ShoppingListOperation, mutation: BaseModel) -> tuple:
        if operation is ShoppingListOperation.LIST_CREATE:
            return ()
        if operation is ShoppingListOperation.ITEM_PATCH:
            return (mutation.list_id, mutation.item_id)
        return (mutation.list_id,)

    async def _sync_handler(
        self,
        user_id: uuid.UUID,
        operation: ShoppingListOperation,
        mutation: BaseModel,
    ) -> Applied:
        if operation is ShoppingListOperation.LIST_CREATE:
            return await self._create_list(user_id, mutation)
        if operation is ShoppingListOperation.LIST_PATCH:
            return await self._patch_list(user_id, mutation.list_id, mutation)
        if operation is ShoppingListOperation.ITEM_CREATE:
            return await self._create_item(user_id, mutation.list_id, mutation)
        return await self._patch_item(user_id, mutation.list_id, mutation.item_id, mutation)

    async def _parse_sync_cursor(self, user_id: uuid.UUID, cursor: str | None) -> SyncCursor:
        if cursor is None:
            # Første sync. Klienten har ingen serverstate å komme i konflikt med.
            return SyncCursor(None, replay_allowed=True)

        padded = cursor + "=" * (-len(cursor) % 4)
        try:
            payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
            if payload["v"] != SYNC_CURSOR_VERSION or payload["u"] != str(user_id):
                raise ValueError("markøren hører til en annen konto eller versjon")
            sequence = int(payload["s"])
            issued_at = _as_utc(datetime.fromisoformat(payload["t"]))
        except (binascii.Error, KeyError, TypeError, ValueError, UnicodeDecodeError):
            return SyncCursor(None, replay_allowed=False)

        if _now() - issued_at > TOMBSTONE_RETENTION:
            # Slettemarkører kan være ryddet. Da vet ikke serveren hva klienten
            # mangler, og bare et fullt snapshot er sant.
            return SyncCursor(None, replay_allowed=False)
        if sequence < 0 or sequence > await self._sequence(user_id):
            return SyncCursor(None, replay_allowed=False)
        return SyncCursor(sequence, replay_allowed=True)

    async def _snapshot(self, user_id: uuid.UUID) -> list[dict]:
        """Alt klienten trenger, inkludert slettemarkører."""
        return await self._sync_lists(user_id, changed_since=None)

    async def _delta(self, user_id: uuid.UUID, sequence: int) -> list[dict]:
        """Lister og linjer endret siden markøren, inkludert slettemarkører.

        En linjeendring løfter `content_seq` på listen, så listen følger med når
        en av linjene er endret. Linjene som sendes er bare de endrede.
        """
        return await self._sync_lists(user_id, changed_since=sequence)

    async def _sync_lists(self, user_id: uuid.UUID, changed_since: int | None) -> list[dict]:
        filters = [ShoppingList.user_id == user_id]
        if changed_since is not None:
            filters.append(ShoppingList.content_seq > changed_since)
        result = await self.db.execute(
            sa.select(ShoppingList)
            .where(*filters)
            .order_by(ShoppingList.created_at.asc(), ShoppingList.id.asc()),
        )
        rows = list(result.scalars().all())
        grouped = await self._items_by_list(
            user_id,
            [row.id for row in rows],
            include_deleted=True,
            changed_since=changed_since,
        )
        return [list_response(row, grouped.get(row.id, [])) for row in rows]

    # --- Mutasjoner -----------------------------------------------------

    async def _create_list(
        self,
        user_id: uuid.UUID,
        request: ShoppingListCreateRequest,
    ) -> Applied:
        name = self._validated_name(request.name)
        if request.id is not None:
            await self._assert_free_id(ShoppingList, user_id, request.id, "id")

        sequence = await self._next_sequence(user_id)
        now = _now()
        shopping_list = ShoppingList(
            id=request.id or uuid.uuid4(),
            user_id=user_id,
            name=name,
            status=ShoppingListStatus.ACTIVE.value,
            version=1,
            content_seq=sequence,
            created_at=now,
            updated_at=now,
        )
        self.db.add(shopping_list)
        await self.db.flush()
        return Applied(list_response(shopping_list, []), shopping_list.id)

    async def _patch_list(
        self,
        user_id: uuid.UUID,
        list_id: uuid.UUID,
        request: ShoppingListPatchRequest,
    ) -> Applied:
        shopping_list = await self._list_row(user_id, list_id)
        if shopping_list.deleted_at is not None:
            raise _list_deleted(list_response(shopping_list, []))
        if request.expected_version != shopping_list.version:
            raise _version_conflict(
                shopping_list.version,
                list_response(shopping_list, await self._items(list_id)),
            )

        name = None if request.name is None else self._validated_name(request.name)
        sequence = await self._next_sequence(user_id)
        if name is not None:
            shopping_list.name = name
        if request.status is not None:
            shopping_list.status = request.status.value
        if request.deleted:
            # `deleted: false` gjenoppretter ikke. Gjenoppretting er en egen,
            # eksplisitt handling, ikke en bieffekt av en retting.
            shopping_list.deleted_at = _now()
        self._touch(shopping_list, sequence, bump_version=True)
        await self.db.flush()
        items = [] if shopping_list.deleted_at is not None else await self._items(list_id)
        return Applied(list_response(shopping_list, items), shopping_list.id)

    async def _copy_list(
        self,
        user_id: uuid.UUID,
        list_id: uuid.UUID,
        request: ShoppingListCopyRequest,
    ) -> Applied:
        source = await self._list_row(user_id, list_id)
        if source.deleted_at is not None:
            raise _not_found()
        mapped = copy_list_lines(
            self._source_list_lines(await self._items(list_id)),
            unchecked_only=request.unchecked_only,
        )
        name = self._validated_name(request.name) if request.name is not None else source.name
        return await self._materialize_mapped_list(user_id, name, request.id, mapped)

    async def _create_list_from_receipt(
        self,
        user_id: uuid.UUID,
        request: ShoppingListFromReceiptRequest,
    ) -> Applied:
        receipt = await self._confirmed_owned_receipt(user_id, request.receipt_id)
        mapped = map_receipt_lines(
            await self._source_receipt_lines(receipt),
            await self._owned_product_ids(user_id),
        )
        name = (
            self._validated_name(request.name)
            if request.name is not None
            else DEFAULT_FROM_RECEIPT_NAME
        )
        return await self._materialize_mapped_list(user_id, name, request.id, mapped)

    async def _materialize_mapped_list(
        self,
        user_id: uuid.UUID,
        name: str,
        list_id: uuid.UUID | None,
        mapped: list[MappedListLine],
    ) -> Applied:
        if list_id is not None:
            await self._assert_free_id(ShoppingList, user_id, list_id, "id")
        if len(mapped) > MAX_ACTIVE_ITEMS:
            raise _item_limit()

        sequence = await self._next_sequence(user_id)
        now = _now()
        shopping_list = ShoppingList(
            id=list_id or uuid.uuid4(),
            user_id=user_id,
            name=name,
            status=ShoppingListStatus.ACTIVE.value,
            version=1,
            content_seq=sequence,
            created_at=now,
            updated_at=now,
        )
        self.db.add(shopping_list)
        items: list[ShoppingListItem] = []
        for position, line in enumerate(mapped):
            sequence = await self._next_sequence(user_id)
            item = ShoppingListItem(
                id=uuid.uuid4(),
                user_id=user_id,
                list_id=shopping_list.id,
                user_product_id=line.user_product_id,
                free_text=(
                    None
                    if line.user_product_id is not None
                    else self._validated_reference(None, line.free_text)
                ),
                quantity=self._validated_quantity(line.quantity),
                quantity_unit=line.quantity_unit,
                checked=False,
                position=position,
                version=1,
                sync_seq=sequence,
                created_at=now,
                updated_at=now,
            )
            self.db.add(item)
            items.append(item)
            self._touch(shopping_list, sequence, bump_version=False)
        await self.db.flush()
        return Applied(list_response(shopping_list, items), shopping_list.id)

    @staticmethod
    def _source_list_lines(items: list[ShoppingListItem]) -> list[SourceListLine]:
        return [
            SourceListLine(
                id=item.id,
                user_product_id=item.user_product_id,
                free_text=item.free_text,
                quantity=item.quantity,
                quantity_unit=item.quantity_unit,
                checked=item.checked,
                position=item.position,
                deleted=item.deleted_at is not None,
            )
            for item in items
        ]

    async def _source_receipt_lines(self, receipt: Receipt) -> list[SourceReceiptLine]:
        revision = await self._latest_confirmed_revision(receipt)
        if revision is not None:
            result = await self.db.execute(
                sa.select(ReceiptRevisionLine)
                .where(ReceiptRevisionLine.revision_id == revision.id)
                .order_by(ReceiptRevisionLine.position.asc(), ReceiptRevisionLine.id.asc()),
            )
            return [self._revision_source_line(line) for line in result.scalars().all()]

        result = await self.db.execute(
            sa.select(ReceiptItem)
            .where(ReceiptItem.receipt_id == receipt.id)
            .order_by(ReceiptItem.id.asc()),
        )
        return [
            SourceReceiptLine(
                line_type=item.line_type,
                raw_product_name=item.raw_product_name,
                user_product_id=None,
                quantity=item.quantity,
                quantity_unit=item.quantity_unit,
                deleted=False,
                position=index,
            )
            for index, item in enumerate(result.scalars().all())
        ]

    @staticmethod
    def _revision_source_line(line: ReceiptRevisionLine) -> SourceReceiptLine:
        deleted = False
        if getattr(line, "deleted_at", None) is not None:
            deleted = True
        elif bool(getattr(line, "deleted", False)):
            deleted = True
        return SourceReceiptLine(
            line_type=line.line_type,
            raw_product_name=line.raw_product_name,
            user_product_id=line.user_product_id,
            quantity=line.quantity,
            quantity_unit=line.quantity_unit,
            deleted=deleted,
            position=line.position,
        )

    async def _latest_confirmed_revision(self, receipt: Receipt) -> ReceiptRevision | None:
        result = await self.db.execute(
            sa.select(ReceiptRevision)
            .where(
                ReceiptRevision.receipt_id == receipt.id,
                ReceiptRevision.user_id == receipt.user_id,
                ReceiptRevision.status == RevisionStatus.CONFIRMED.value,
            )
            .order_by(ReceiptRevision.revision.desc())
            .limit(1),
        )
        return result.scalar_one_or_none()

    async def _confirmed_owned_receipt(
        self,
        user_id: uuid.UUID,
        receipt_id: uuid.UUID,
    ) -> Receipt:
        result = await self.db.execute(
            sa.select(Receipt).where(
                Receipt.id == receipt_id,
                Receipt.user_id == user_id,
            ),
        )
        receipt = result.scalar_one_or_none()
        if receipt is None or receipt.status != ReceiptStatus.CONFIRMED.value:
            raise _not_found()
        return receipt

    async def _owned_product_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        result = await self.db.execute(
            sa.select(UserProduct.id).where(UserProduct.user_id == user_id),
        )
        return set(result.scalars().all())

    async def _create_item(
        self,
        user_id: uuid.UUID,
        list_id: uuid.UUID,
        request: ShoppingListItemCreateRequest,
    ) -> Applied:
        shopping_list = await self._mutable_list(user_id, list_id)
        free_text = self._validated_reference(request.user_product_id, request.free_text)
        quantity = self._validated_quantity(request.quantity)
        if request.user_product_id is not None:
            await self._assert_owned_product(user_id, request.user_product_id)
        if request.id is not None:
            await self._assert_free_id(ShoppingListItem, user_id, request.id, "id")
        if await self._active_item_count(list_id) >= MAX_ACTIVE_ITEMS:
            # Avvises før noe er skrevet, så de 200 linjene står urørt og
            # klienten kan beholde linjen som utkast.
            raise _item_limit()

        sequence = await self._next_sequence(user_id)
        now = _now()
        item = ShoppingListItem(
            id=request.id or uuid.uuid4(),
            user_id=user_id,
            list_id=list_id,
            user_product_id=request.user_product_id,
            free_text=free_text,
            quantity=quantity,
            quantity_unit=request.quantity_unit.value,
            checked=request.checked,
            position=(
                request.position
                if request.position is not None
                else await self._next_position(list_id)
            ),
            version=1,
            sync_seq=sequence,
            created_at=now,
            updated_at=now,
        )
        self.db.add(item)
        self._touch(shopping_list, sequence, bump_version=False)
        await self.db.flush()
        return Applied(item_response(item), list_id, item.id)

    async def _patch_item(
        self,
        user_id: uuid.UUID,
        list_id: uuid.UUID,
        item_id: uuid.UUID,
        request: ShoppingListItemPatchRequest,
    ) -> Applied:
        shopping_list = await self._mutable_list(user_id, list_id)
        item = await self._item_row(user_id, list_id, item_id)
        if item.deleted_at is not None:
            raise _item_deleted(item_response(item))
        if request.expected_version != item.version:
            raise _version_conflict(item.version, item_response(item))

        quantity = (
            None if request.quantity is None else self._validated_quantity(request.quantity)
        )
        sequence = await self._next_sequence(user_id)
        if quantity is not None:
            item.quantity = quantity
        if request.quantity_unit is not None:
            item.quantity_unit = request.quantity_unit.value
        if request.checked is not None:
            # Eksplisitt verdi, ikke en toggle: en retry krysser ikke av og på.
            item.checked = request.checked
        if request.position is not None:
            item.position = request.position
        if request.deleted:
            item.deleted_at = _now()
        item.version += 1
        item.sync_seq = sequence
        item.updated_at = _now()
        self._touch(shopping_list, sequence, bump_version=False)
        await self.db.flush()
        return Applied(item_response(item), list_id, item.id)

    @staticmethod
    def _touch(shopping_list: ShoppingList, sequence: int, bump_version: bool) -> None:
        """`content_seq` følger enhver endring; `version` bare listens egne felter."""
        if bump_version:
            shopping_list.version += 1
        shopping_list.content_seq = sequence
        shopping_list.updated_at = _now()

    # --- Idempotens -----------------------------------------------------

    async def _single(
        self,
        user_id: uuid.UUID,
        operation: ShoppingListOperation,
        request: BaseModel,
        scope: tuple,
        handler,
    ) -> dict:
        """Én mutasjon i sin egen transaksjon, slik REST-rutene bruker den."""
        digest = payload_hash(request, *scope)
        await self._lock_mutation(user_id, operation, request.mutation_id)
        replay = await self._replay(user_id, operation, request.mutation_id, digest)
        if replay is not None:
            return replay

        try:
            applied = await handler()
        except MutationRejected:
            # Ingen delvis commit: alt i den avviste mutasjonen forkastes.
            await self.db.rollback()
            raise

        self._record(user_id, operation, request, digest, applied)
        try:
            await self.db.commit()
        except IntegrityError as error:
            # To samtidige forsøk med samme mutasjons-ID: den som mistet
            # kappløpet leverer det lagrede svaret i stedet for å skrive igjen.
            await self.db.rollback()
            replay = await self._replay(user_id, operation, request.mutation_id, digest)
            if replay is None:
                raise error
            return replay
        return applied.response

    def _record(
        self,
        user_id: uuid.UUID,
        operation: ShoppingListOperation,
        request: BaseModel,
        digest: str,
        applied: Applied,
    ) -> None:
        self.db.add(
            ShoppingListMutation(
                user_id=user_id,
                operation=operation.value,
                mutation_id=request.mutation_id,
                payload_hash=digest,
                list_id=applied.list_id,
                item_id=applied.item_id,
                response=applied.response,
            ),
        )

    async def _replay(
        self,
        user_id: uuid.UUID,
        operation: ShoppingListOperation,
        mutation_id: uuid.UUID,
        digest: str,
    ) -> dict | None:
        result = await self.db.execute(
            sa.select(ShoppingListMutation).where(
                ShoppingListMutation.user_id == user_id,
                ShoppingListMutation.operation == operation.value,
                ShoppingListMutation.mutation_id == mutation_id,
            ),
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        if record.payload_hash != digest:
            raise _mutation_conflict()
        return record.response

    async def _lock_mutation(
        self,
        user_id: uuid.UUID,
        operation: ShoppingListOperation,
        mutation_id: uuid.UUID,
    ) -> None:
        """Serialiser samtidige retries av samme mutasjon på tvers av prosesser."""
        if self.db.bind is None or self.db.bind.dialect.name != "postgresql":
            return
        key = hashlib.sha256(
            f"{user_id}:{operation.value}:{mutation_id}".encode(),
        ).digest()[:8]
        await self.db.execute(
            sa.text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int.from_bytes(key, "big", signed=True)},
        )

    # --- Oppslag --------------------------------------------------------

    async def _list_row(self, user_id: uuid.UUID, list_id: uuid.UUID) -> ShoppingList:
        result = await self.db.execute(
            sa.select(ShoppingList).where(
                ShoppingList.id == list_id,
                ShoppingList.user_id == user_id,
            ),
        )
        shopping_list = result.scalar_one_or_none()
        if shopping_list is None:
            raise _not_found()
        return shopping_list

    async def _mutable_list(self, user_id: uuid.UUID, list_id: uuid.UUID) -> ShoppingList:
        """Linjene kan bare endres i en aktiv liste.

        Arkivering og sletting er brukerens beslutning om hele listen. En linje
        skal ikke kunne endre den i det skjulte fra en annen enhet.
        """
        shopping_list = await self._list_row(user_id, list_id)
        if shopping_list.deleted_at is not None:
            raise _list_deleted(list_response(shopping_list, []))
        if shopping_list.status == ShoppingListStatus.ARCHIVED.value:
            raise _list_archived(list_response(shopping_list, []))
        return shopping_list

    async def _item_row(
        self,
        user_id: uuid.UUID,
        list_id: uuid.UUID,
        item_id: uuid.UUID,
    ) -> ShoppingListItem:
        result = await self.db.execute(
            sa.select(ShoppingListItem).where(
                ShoppingListItem.id == item_id,
                ShoppingListItem.list_id == list_id,
                ShoppingListItem.user_id == user_id,
            ),
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise _not_found()
        return item

    async def _items(self, list_id: uuid.UUID) -> list[ShoppingListItem]:
        result = await self.db.execute(
            sa.select(ShoppingListItem)
            .where(
                ShoppingListItem.list_id == list_id,
                ShoppingListItem.deleted_at.is_(None),
            )
            .order_by(ShoppingListItem.position.asc(), ShoppingListItem.id.asc()),
        )
        return list(result.scalars().all())

    async def _items_by_list(
        self,
        user_id: uuid.UUID,
        list_ids: list[uuid.UUID],
        include_deleted: bool,
        changed_since: int | None = None,
    ) -> dict[uuid.UUID, list[ShoppingListItem]]:
        if not list_ids:
            return {}
        filters = [
            ShoppingListItem.user_id == user_id,
            ShoppingListItem.list_id.in_(list_ids),
        ]
        if not include_deleted:
            filters.append(ShoppingListItem.deleted_at.is_(None))
        if changed_since is not None:
            filters.append(ShoppingListItem.sync_seq > changed_since)

        result = await self.db.execute(
            sa.select(ShoppingListItem)
            .where(*filters)
            .order_by(ShoppingListItem.position.asc(), ShoppingListItem.id.asc()),
        )
        grouped: dict[uuid.UUID, list[ShoppingListItem]] = {}
        for item in result.scalars().all():
            grouped.setdefault(item.list_id, []).append(item)
        return grouped

    async def _assert_owned_product(self, user_id: uuid.UUID, product_id: uuid.UUID) -> None:
        result = await self.db.execute(
            sa.select(UserProduct.id).where(
                UserProduct.id == product_id,
                UserProduct.user_id == user_id,
            ),
        )
        if result.scalar_one_or_none() is None:
            # En annen eiers vare-ID i request body gir samme svar som ukjent ID.
            raise _not_found()

    async def _assert_free_id(
        self,
        model,
        user_id: uuid.UUID,
        row_id: uuid.UUID,
        field: str,
    ) -> None:
        result = await self.db.execute(
            sa.select(model.user_id).where(model.id == row_id),
        )
        owner = result.scalar_one_or_none()
        if owner is None:
            return
        if owner != user_id:
            raise _not_found()
        raise _duplicate_id(field)

    async def _active_item_count(self, list_id: uuid.UUID) -> int:
        result = await self.db.execute(
            sa.select(sa.func.count())
            .select_from(ShoppingListItem)
            .where(
                ShoppingListItem.list_id == list_id,
                ShoppingListItem.deleted_at.is_(None),
            ),
        )
        return int(result.scalar_one())

    async def _next_position(self, list_id: uuid.UUID) -> int:
        result = await self.db.execute(
            sa.select(sa.func.max(ShoppingListItem.position)).where(
                ShoppingListItem.list_id == list_id,
                ShoppingListItem.deleted_at.is_(None),
            ),
        )
        highest = result.scalar_one()
        return 0 if highest is None else int(highest) + 1

    # --- Sekvens og versjoner -------------------------------------------

    async def _sequence(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            sa.select(ShoppingListSyncState.sequence).where(
                ShoppingListSyncState.user_id == user_id,
            ),
        )
        return int(result.scalar_one_or_none() or 0)

    async def _next_sequence(self, user_id: uuid.UUID) -> int:
        """Kontoens neste synsekvens.

        Økningen skjer i SQL, slik at to samtidige skrivere ikke kan lese samme
        verdi og stemple to endringer med samme sekvensnummer.
        """
        bumped = await self._bump_sequence(user_id)
        if bumped is not None:
            return bumped
        try:
            # Kontoens første skriving. Savepointet gjør at et tapt kappløp om
            # sekvensraden blir en vanlig økning i stedet for en feil.
            async with self.db.begin_nested():
                self.db.add(ShoppingListSyncState(user_id=user_id, sequence=1))
                await self.db.flush()
        except IntegrityError:
            bumped = await self._bump_sequence(user_id)
            if bumped is None:  # pragma: no cover - raden finnes etter kappløpet
                raise
            return bumped
        return 1

    async def _bump_sequence(self, user_id: uuid.UUID) -> int | None:
        """Øker sekvensen. `None` betyr at kontoen ikke har en sekvensrad ennå."""
        result = await self.db.execute(
            sa.update(ShoppingListSyncState)
            .where(ShoppingListSyncState.user_id == user_id)
            .values(
                sequence=ShoppingListSyncState.sequence + 1,
                updated_at=_now(),
            )
            .execution_options(synchronize_session=False),
        )
        if result.rowcount == 0:
            return None
        return await self._sequence(user_id)

    async def _price_data_version(self, user_id: uuid.UUID) -> int:
        """Listeendringer rører den ikke. Den leses her, aldri økes."""
        result = await self.db.execute(
            sa.select(AccountLedger.price_data_version).where(
                AccountLedger.user_id == user_id,
            ),
        )
        return int(result.scalar_one_or_none() or 1)

    # --- Validering -----------------------------------------------------

    @staticmethod
    def _validated_name(name: str) -> str:
        stripped = name.strip()
        if not stripped:
            raise _validation_error("name", "required", "Listen må ha et navn.")
        return stripped

    @staticmethod
    def _validated_reference(
        user_product_id: uuid.UUID | None,
        free_text: str | None,
    ) -> str | None:
        """Enten privat vare eller fritekst. Fritekst er ikke bevis for en vare."""
        stripped = (free_text or "").strip() or None
        if (user_product_id is None) == (stripped is None):
            raise _validation_error(
                "free_text",
                "product_or_free_text",
                "Linjen må peke på én vare eller ha fritekst, ikke begge.",
            )
        return stripped

    @staticmethod
    def _validated_quantity(quantity: Decimal) -> Decimal:
        if quantity <= 0:
            raise _validation_error("quantity", "not_positive", "Mengden må være over null.")
        if -quantity.as_tuple().exponent > 3:
            raise _validation_error(
                "quantity",
                "too_many_decimals",
                "Mengden kan ha inntil tre desimaler.",
            )
        return quantity.quantize(QUANTITY_QUANTUM)

    @staticmethod
    def _cursor_timestamp(key: str) -> datetime:
        try:
            return _as_utc(datetime.fromisoformat(key))
        except ValueError as exc:
            raise invalid_cursor() from exc
