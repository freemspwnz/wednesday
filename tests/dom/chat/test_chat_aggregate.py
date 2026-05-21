from zoneinfo import ZoneInfo

import pytest

from domain.chat import (
    ActiveState,
    Chat,
    ChatActivated,
    ChatDeactivated,
    ChatProfile,
    ChatProfileChanged,
    ChatSchedule,
    ChatScheduleAdded,
    ChatScheduleCleared,
    ChatScheduleDayChanged,
    ChatScheduleRemoved,
    ChatScheduleTimezoneChanged,
    ChatType,
    InactiveState,
    InvalidStateTransitionError,
    ManagementAccessDeniedError,
    StaleWriteError,
    ValidationError,
    Weekday,
)
from domain.chat.policies import ManagementAccessCode, ManagementAllowed, ManagementDenied

from .factories import (
    admin,
    default_schedules,
    dt,
    member,
    mk_chat,
    owner,
    private_profile,
    system,
)


@pytest.mark.unit
def test_chat_register_and_restore_and_ensure() -> None:
    chat = mk_chat(now=dt(10))
    assert isinstance(chat.state, ActiveState)
    assert chat.created_at == chat.updated_at == dt(10)

    restored = Chat.restore(
        id=chat.id,
        profile=chat.profile,
        state=chat.state,
        schedules=chat.schedules,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
    )
    assert Chat.ensure(restored) is restored


@pytest.mark.unit
def test_chat_commands_emit_expected_events() -> None:
    chat = mk_chat(now=dt(10))

    new_profile = ChatProfile(type=ChatType.GROUP, telegram_id=-1001, title="Squad")
    chat.change_profile(actor=owner(), new_profile=new_profile, at=dt(11))
    chat.change_schedule_day(actor=owner(), new_weekday=Weekday.FRIDAY, at=dt(12))
    chat.change_schedule_timezone(actor=owner(), timezone=ZoneInfo("Europe/London"), at=dt(13))
    chat.add_schedule(actor=owner(), schedule=ChatSchedule(9, 30), at=dt(14))
    chat.remove_schedule(actor=owner(), schedule=ChatSchedule(9, 30), at=dt(15))
    chat.add_schedule(actor=owner(), schedule=ChatSchedule(10, 0), at=dt(16))
    chat.clear_schedules(actor=owner(), at=dt(17))
    chat.deactivate(actor=owner(), at=dt(18))
    chat.activate(actor=owner(), at=dt(19))

    events = chat.pull_events()
    assert [type(evt) for evt in events] == [
        ChatProfileChanged,
        ChatScheduleDayChanged,
        ChatScheduleTimezoneChanged,
        ChatScheduleAdded,
        ChatScheduleRemoved,
        ChatScheduleAdded,
        ChatScheduleCleared,
        ChatDeactivated,
        ChatActivated,
    ]


@pytest.mark.unit
def test_chat_noop_commands_do_not_touch_updated_at() -> None:
    chat = mk_chat(now=dt(10))
    at_before = chat.updated_at

    chat.change_profile(actor=owner(), new_profile=chat.profile, at=dt(11))
    chat.change_schedule_day(actor=owner(), new_weekday=chat.schedules.weekday, at=dt(11))
    chat.change_schedule_timezone(actor=owner(), timezone=chat.schedules.timezone, at=dt(11))
    chat.remove_schedule(actor=owner(), schedule=ChatSchedule(7, 0), at=dt(11))
    chat.clear_schedules(actor=owner(), at=dt(11))

    assert chat.updated_at == at_before
    assert chat.pull_events() == []


@pytest.mark.unit
def test_add_schedule_with_duplicate_is_noop() -> None:
    chat = mk_chat(now=dt(10))
    slot = ChatSchedule(8, 0)
    chat.add_schedule(actor=owner(), schedule=slot, at=dt(11))
    chat.pull_events()
    updated_at_before = chat.updated_at

    chat.add_schedule(actor=owner(), schedule=slot, at=dt(12))

    assert chat.updated_at == updated_at_before
    assert chat.pull_events() == []


@pytest.mark.unit
def test_change_profile_emits_old_and_new() -> None:
    chat = mk_chat(now=dt(10))
    old = chat.profile
    new = ChatProfile(type=ChatType.GROUP, telegram_id=-1001, title="X")

    chat.change_profile(actor=owner(), new_profile=new, at=dt(11))
    events = chat.pull_events()

    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, ChatProfileChanged)
    assert ev.old_profile == old
    assert ev.new_profile == new
    assert chat.profile == new


@pytest.mark.unit
def test_change_schedule_day_emits_old_and_new() -> None:
    chat = mk_chat(now=dt(10))
    old = chat.schedules.weekday

    chat.change_schedule_day(actor=owner(), new_weekday=Weekday.FRIDAY, at=dt(11))
    events = chat.pull_events()

    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, ChatScheduleDayChanged)
    assert ev.old_weekday == old
    assert ev.new_weekday == Weekday.FRIDAY
    assert chat.schedules.weekday == Weekday.FRIDAY


@pytest.mark.unit
def test_change_schedule_timezone_emits_old_and_new() -> None:
    chat = mk_chat(now=dt(10))
    old = chat.schedules.timezone
    london = ZoneInfo("Europe/London")

    chat.change_schedule_timezone(actor=owner(), timezone=london, at=dt(11))
    events = chat.pull_events()

    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, ChatScheduleTimezoneChanged)
    assert ev.old_timezone == old
    assert ev.new_timezone == london
    assert chat.schedules.timezone == london


@pytest.mark.unit
def test_change_profile_denied_for_member_role() -> None:
    chat = mk_chat(now=dt(10))
    new_profile = ChatProfile(type=ChatType.GROUP, telegram_id=-1001, title="Y")
    with pytest.raises(ManagementAccessDeniedError):
        chat.change_profile(actor=member(), new_profile=new_profile, at=dt(11))


@pytest.mark.unit
def test_admin_can_change_profile() -> None:
    chat = mk_chat(now=dt(10))
    new_profile = ChatProfile(type=ChatType.SUPERGROUP, telegram_id=-1001, title="Admins")

    chat.change_profile(actor=admin(), new_profile=new_profile, at=dt(11))

    assert isinstance(chat.pull_events()[0], ChatProfileChanged)


@pytest.mark.unit
def test_system_actor_can_manage() -> None:
    chat = mk_chat(now=dt(10))
    chat.change_schedule_day(actor=system(), new_weekday=Weekday.MONDAY, at=dt(11))
    assert isinstance(chat.pull_events()[0], ChatScheduleDayChanged)


@pytest.mark.unit
def test_deactivate_and_activate_emit_lifecycle_events() -> None:
    chat = mk_chat(now=dt(10))

    chat.deactivate(actor=owner(), at=dt(11))
    assert isinstance(chat.state, InactiveState)
    d1 = chat.pull_events()
    assert len(d1) == 1
    assert isinstance(d1[0], ChatDeactivated)

    chat.activate(actor=owner(), at=dt(12))
    assert isinstance(chat.state, ActiveState)
    d2 = chat.pull_events()
    assert len(d2) == 1
    assert isinstance(d2[0], ChatActivated)


@pytest.mark.unit
def test_activate_when_already_active_raises() -> None:
    chat = mk_chat(now=dt(10))
    with pytest.raises(InvalidStateTransitionError):
        chat.activate(actor=owner(), at=dt(11))


@pytest.mark.unit
def test_deactivate_when_already_inactive_raises() -> None:
    chat = Chat.restore(
        id=mk_chat().id,
        profile=private_profile(),
        state=InactiveState(),
        schedules=default_schedules(),
        created_at=dt(9),
        updated_at=dt(9),
    )
    with pytest.raises(InvalidStateTransitionError):
        chat.deactivate(actor=owner(), at=dt(10))


@pytest.mark.unit
def test_command_rejects_non_monotonic_at() -> None:
    chat = mk_chat(now=dt(10))
    chat.change_schedule_day(actor=owner(), new_weekday=Weekday.TUESDAY, at=dt(12))
    chat.pull_events()

    with pytest.raises(StaleWriteError):
        chat.change_schedule_day(actor=owner(), new_weekday=Weekday.THURSDAY, at=dt(11))


@pytest.mark.unit
def test_pull_events_clears_buffer() -> None:
    chat = mk_chat(now=dt(10))
    chat.change_schedule_day(actor=owner(), new_weekday=Weekday.SATURDAY, at=dt(11))

    assert len(chat.pull_events()) == 1
    assert chat.pull_events() == []


@pytest.mark.unit
def test_change_profile_rejects_naive_datetime() -> None:
    from datetime import datetime as _dt

    chat = mk_chat(now=dt(10))
    new_profile = ChatProfile(type=ChatType.GROUP, telegram_id=-1001, title="Z")
    with pytest.raises(ValidationError):
        chat.change_profile(actor=owner(), new_profile=new_profile, at=_dt.now())  # type: ignore[arg-type]


@pytest.mark.unit
def test_management_unknown_decision_is_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = mk_chat(now=dt(10))
    new_profile = ChatProfile(type=ChatType.GROUP, telegram_id=-1001, title="X")

    monkeypatch.setattr(
        "domain.chat.chat.ManagementAccessPolicy.evaluate",
        lambda _: object(),
    )
    with pytest.raises(ValidationError):
        chat.change_profile(actor=owner(), new_profile=new_profile, at=dt(11))

    monkeypatch.setattr(
        "domain.chat.chat.ManagementAccessPolicy.evaluate",
        lambda _: ManagementAllowed(),
    )
    chat.change_profile(actor=owner(), new_profile=new_profile, at=dt(11))

    monkeypatch.setattr(
        "domain.chat.chat.ManagementAccessPolicy.evaluate",
        lambda _: ManagementDenied(code=ManagementAccessCode.NOT_ENOUGH_RIGHTS),
    )
    with pytest.raises(ManagementAccessDeniedError):
        chat.change_profile(actor=owner(), new_profile=new_profile, at=dt(12))
