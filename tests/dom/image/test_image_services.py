"""Tests for image domain services."""

import pytest

from domain.catalog import Model
from domain.image import (
    ActiveState,
    HiddenReason,
    HiddenState,
    ImageGenerationService,
    ImageLifecycleService,
    ImageNotFoundError,
    ImageRatingChanged,
    ImageVoteService,
    NormalizedPrompt,
    PromptModerationPolicy,
    PromptRejectedError,
    PromptSource,
    Vote,
)

from .factories import (
    FakeGenerator,
    FakeImageRepo,
    FakeImageVoteRepo,
    FakePromptCatalog,
    dt,
    mk_image,
    mk_rating,
    mk_user_id,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_persists_new_vote() -> None:
    vote_repo = FakeImageVoteRepo()
    vote = Vote(image_id=mk_image().id, voter_id=mk_user_id(501), value=1)

    await ImageVoteService.vote(vote=vote, repo=vote_repo)

    assert vote_repo.votes[vote.image_id, vote.voter_id].value == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_updates_existing_vote() -> None:
    image = mk_image()
    vote_repo = FakeImageVoteRepo()
    await vote_repo.upsert(Vote(image_id=image.id, voter_id=mk_user_id(1), value=1))

    await ImageVoteService.vote(
        vote=Vote(image_id=image.id, voter_id=mk_user_id(1), value=-1),
        repo=vote_repo,
    )

    assert vote_repo.votes[image.id, mk_user_id(1)].value == -1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_noop_when_same_value() -> None:
    image = mk_image()
    vote_repo = FakeImageVoteRepo()
    await vote_repo.upsert(Vote(image_id=image.id, voter_id=mk_user_id(1), value=1))

    await ImageVoteService.vote(
        vote=Vote(image_id=image.id, voter_id=mk_user_id(1), value=1),
        repo=vote_repo,
    )

    assert len(vote_repo.votes) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lifecycle_apply_vote_updates_rating() -> None:
    image = mk_image(rating=mk_rating(likes=1))
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)

    result = await ImageLifecycleService.apply_vote(
        image_id=image.id,
        new=1,
        old=None,
        repo=image_repo,
        at=dt(11),
    )

    assert result.rating == mk_rating(likes=2)
    events = result.pull_events()
    assert isinstance(events[0], ImageRatingChanged)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lifecycle_apply_vote_hides_when_rating_not_selectable() -> None:
    image = mk_image(rating=mk_rating(likes=0))
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)

    result = await ImageLifecycleService.apply_vote(
        image_id=image.id,
        new=-1,
        old=None,
        repo=image_repo,
        at=dt(11),
    )

    assert result.rating == mk_rating(likes=0, dislikes=1)
    assert isinstance(result.state, HiddenState)
    assert result.state.reason == HiddenReason.RATING


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lifecycle_apply_vote_shows_rating_hidden_when_selectable() -> None:
    image = mk_image(rating=mk_rating(likes=0, dislikes=1), state=HiddenState(reason=HiddenReason.RATING))
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)

    result = await ImageLifecycleService.apply_vote(
        image_id=image.id,
        new=1,
        old=None,
        repo=image_repo,
        at=dt(11),
    )

    assert result.rating == mk_rating(likes=1, dislikes=1)
    assert isinstance(result.state, ActiveState)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lifecycle_apply_vote_keeps_admin_hidden() -> None:
    image = mk_image(state=HiddenState(reason=HiddenReason.ADMIN))
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)

    result = await ImageLifecycleService.apply_vote(
        image_id=image.id,
        new=1,
        old=None,
        repo=image_repo,
        at=dt(11),
    )

    assert result.rating == mk_rating(likes=4)
    assert isinstance(result.state, HiddenState)
    assert result.state.reason == HiddenReason.ADMIN


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lifecycle_apply_vote_not_found() -> None:
    with pytest.raises(ImageNotFoundError):
        await ImageLifecycleService.apply_vote(
            image_id=mk_image(image_id=404).id,
            new=1,
            old=None,
            repo=FakeImageRepo(),
            at=dt(11),
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generation_by_user_returns_render() -> None:
    gen = FakeGenerator(text_response="enriched frog", image_content=b"png")
    render = await ImageGenerationService.by_user(
        model=Model.parse("gigachat-2-lite"),
        prompt=NormalizedPrompt.parse("frog meme"),
        catalog=FakePromptCatalog(),
        policy=PromptModerationPolicy(),
        gen=gen,
    )
    assert render.content == b"png"
    assert render.prompts.source == PromptSource.USER
    assert render.prompts.enriched is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generation_by_user_rejects_banned_prompt() -> None:
    with pytest.raises(PromptRejectedError):
        await ImageGenerationService.by_user(
            model=Model.parse("gigachat-2-lite"),
            prompt=NormalizedPrompt.parse("naked frog"),
            catalog=FakePromptCatalog(),
            policy=PromptModerationPolicy(),
            gen=FakeGenerator(),
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generation_by_user_continues_when_enrichment_fails() -> None:
    render = await ImageGenerationService.by_user(
        model=Model.parse("gigachat-2-lite"),
        prompt=NormalizedPrompt.parse("frog meme"),
        catalog=FakePromptCatalog(),
        policy=PromptModerationPolicy(),
        gen=FakeGenerator(fail_text=True, image_content=b"png"),
    )
    assert render.content == b"png"
    assert render.prompts.enriched is None


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("txt_fail", [False, True])
async def test_generation_random_returns_render(txt_fail: bool) -> None:
    render = await ImageGenerationService.random(
        model=Model.parse("gigachat-2-lite"),
        catalog=FakePromptCatalog(),
        gen=FakeGenerator(
            text_response="random frog",
            image_content=b"rnd",
            fail_text=txt_fail,
        ),
    )
    assert render.content == b"rnd"
    if txt_fail:
        assert render.prompts.source == PromptSource.FALLBACK
    else:
        assert render.prompts.source == PromptSource.LLM


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generation_fallback_prompt_builds_from_components() -> None:
    prompt = await ImageGenerationService.fallback_prompt(catalog=FakePromptCatalog())
    assert "Wednesday meme frog" in str(prompt)
