from bot.services.download_queue import DownloadQueue, queue_ahead_count


def test_queue_ahead_count_within_capacity():
    assert queue_ahead_count(position=0, max_concurrent=3) == 0
    assert queue_ahead_count(position=2, max_concurrent=3) == 0


def test_queue_ahead_count_beyond_capacity():
    assert queue_ahead_count(position=3, max_concurrent=3) == 1
    assert queue_ahead_count(position=5, max_concurrent=3) == 3


async def test_first_entry_has_position_zero():
    queue = DownloadQueue()
    token = await queue.enter()
    assert await queue.position(token) == 0


async def test_positions_increase_in_arrival_order():
    queue = DownloadQueue()
    first = await queue.enter()
    second = await queue.enter()
    third = await queue.enter()

    assert await queue.position(first) == 0
    assert await queue.position(second) == 1
    assert await queue.position(third) == 2


async def test_leave_shifts_positions_of_remaining_entries():
    queue = DownloadQueue()
    first = await queue.enter()
    second = await queue.enter()
    third = await queue.enter()

    await queue.leave(first)

    assert await queue.position(second) == 0
    assert await queue.position(third) == 1


async def test_leaving_unknown_token_is_a_noop():
    queue = DownloadQueue()
    token = await queue.enter()
    await queue.leave(999)  # не в очереди — не должно падать
    assert await queue.position(token) == 0
