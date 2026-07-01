from __future__ import annotations

from uuid import UUID

import pytest

from domain.catalog import Model
from domain.image import (
    FallbackPromptService,
    ImageGenerationService,
    ImageNotFoundError,
    ImageRender,
    ImageScoreRecalculated,
    ImageVoteService,
    NormalizedPrompt,
    PromptRejectedError,
    PromptSource,
)
from domain.image.policies import PromptModerationPolicy
from domain.image.vo import ActiveState, HiddenReason, HiddenState
from domain.user.vo import UserRole

from .factories import (
    FakeImageGenerator,
    FakeImageRepo,
    FakeImageVoteRepo,
    FakePromptCatalog,
    FakeTextGenerator,
    dt,
    mk_image,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_inserts_vote_recalculates_and_saves() -> None:
    image = mk_image()
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()
    voter_id = UUID(int=2)

    result = await ImageVoteService.vote(
        image_id=image.id,
        voter_id=voter_id,
        value=1,
        image_repo=image_repo,
        vote_repo=vote_repo,
        at=dt(13),
    )

    assert result.score == 4
    assert image_repo.save_calls == 1
    assert len(vote_repo.votes) == 1
    events = result.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], ImageScoreRecalculated)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_same_vote_is_noop_without_save() -> None:
    image = mk_image()
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()
    voter_id = UUID(int=2)

    first = await ImageVoteService.vote(
        image_id=image.id,
        voter_id=voter_id,
        value=1,
        image_repo=image_repo,
        vote_repo=vote_repo,
        at=dt(13),
    )
    first.pull_events()
    saved_before = image_repo.save_calls

    result = await ImageVoteService.vote(
        image_id=image.id,
        voter_id=voter_id,
        value=1,
        image_repo=image_repo,
        vote_repo=vote_repo,
        at=dt(14),
    )

    assert result.score == 4
    assert image_repo.save_calls == saved_before
    assert result.pull_events() == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_changes_vote_and_recalculates() -> None:
    image = mk_image()
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()
    voter_id = UUID(int=2)

    await ImageVoteService.vote(
        image_id=image.id,
        voter_id=voter_id,
        value=1,
        image_repo=image_repo,
        vote_repo=vote_repo,
        at=dt(13),
    )

    result = await ImageVoteService.vote(
        image_id=image.id,
        voter_id=voter_id,
        value=-1,
        image_repo=image_repo,
        vote_repo=vote_repo,
        at=dt(14),
    )

    assert result.score == 2
    assert image_repo.save_calls == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_hides_image_when_score_drops_to_zero() -> None:
    image = mk_image()
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()

    result = image
    for voter in (2, 3, 4):
        result = await ImageVoteService.vote(
            image_id=image.id,
            voter_id=UUID(int=voter),
            value=-1,
            image_repo=image_repo,
            vote_repo=vote_repo,
            at=dt(13),
        )

    assert result.score == 0
    assert result.is_hidden
    assert isinstance(result.state, HiddenState)
    assert result.state.reason == HiddenReason.SCORE


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_shows_score_hidden_when_score_becomes_selectable() -> None:
    image = mk_image(score=0, state=HiddenState(reason=HiddenReason.SCORE))
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()

    result = await ImageVoteService.vote(
        image_id=image.id,
        voter_id=UUID(int=2),
        value=1,
        image_repo=image_repo,
        vote_repo=vote_repo,
        at=dt(13),
    )

    assert result.score == 4
    assert isinstance(result.state, ActiveState)
    assert result.is_selectable


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_raises_when_image_missing() -> None:
    image = mk_image()
    with pytest.raises(ImageNotFoundError) as exc_info:
        await ImageVoteService.vote(
            image_id=image.id,
            voter_id=UUID(int=2),
            value=1,
            image_repo=FakeImageRepo(),
            vote_repo=FakeImageVoteRepo(),
            at=dt(13),
        )
    assert str(image.id) in exc_info.value.image_id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_updates_score_but_keeps_admin_hidden() -> None:
    image = mk_image()
    image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(11))
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()

    result = await ImageVoteService.vote(
        image_id=image.id,
        voter_id=UUID(int=2),
        value=1,
        image_repo=image_repo,
        vote_repo=vote_repo,
        at=dt(13),
    )

    assert result.score == 4
    assert isinstance(result.state, HiddenState)
    assert result.state.reason == HiddenReason.ADMIN
    assert not result.is_selectable


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generation_by_user_success() -> None:
    model = Model.parse("gigachat-2-lite")
    user_input = NormalizedPrompt.parse("frog meme")
    catalog = FakePromptCatalog()
    txt_gen = FakeTextGenerator(response="enriched frog")
    img_gen = FakeImageGenerator(content=b"png")

    render = await ImageGenerationService.by_user(
        model=model,
        user_input=user_input,
        catalog=catalog,
        moderation=PromptModerationPolicy(),
        txt_gen=txt_gen,
        img_gen=img_gen,
    )

    assert isinstance(render, ImageRender)
    assert render.content == b"png"
    assert render.prompts.source == PromptSource.USER
    assert render.prompts.enriched is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generation_by_user_rejects_banned_prompt() -> None:
    with pytest.raises(PromptRejectedError):
        await ImageGenerationService.by_user(
            model=Model.parse("gigachat-2-lite"),
            user_input=NormalizedPrompt.parse("naked frog"),
            catalog=FakePromptCatalog(),
            moderation=PromptModerationPolicy(),
            txt_gen=FakeTextGenerator(),
            img_gen=FakeImageGenerator(),
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generation_by_user_uses_primary_when_enrichment_fails() -> None:
    render = await ImageGenerationService.by_user(
        model=Model.parse("gigachat-2-lite"),
        user_input=NormalizedPrompt.parse("frog meme"),
        catalog=FakePromptCatalog(),
        moderation=PromptModerationPolicy(),
        txt_gen=FakeTextGenerator(fail=True),
        img_gen=FakeImageGenerator(),
    )

    assert render.prompts.enriched is None
    assert str(render.prompts.effective()) == "frog meme"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("txt_fail", [False, True])
async def test_generation_random_paths(txt_fail: bool) -> None:
    render = await ImageGenerationService.random(
        model=Model.parse("gigachat-2-lite"),
        catalog=FakePromptCatalog(),
        txt_gen=FakeTextGenerator(response="random frog", fail=txt_fail),
        img_gen=FakeImageGenerator(content=b"rnd"),
    )

    assert render.content == b"rnd"
    if txt_fail:
        assert render.prompts.source == PromptSource.FALLBACK
    else:
        assert render.prompts.source == PromptSource.LLM


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fallback_prompt_service_builds_from_catalog() -> None:
    prompt = await FallbackPromptService.build(FakePromptCatalog())
    assert "Wednesday meme frog" in str(prompt)
