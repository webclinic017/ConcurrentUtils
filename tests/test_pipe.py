import pytest
import asyncio
from concurrent.futures import ThreadPoolExecutor
import zmq.asyncio

from task_utils.pipe import pipe, ConcurrentPipeEnd
from task_utils.pipe import zmq_tcp_pipe, zmq_tcp_pipe_end, zmq_inproc_pipe, zmq_inproc_pipe_end, ZmqPipeEnd


@pytest.mark.asyncio
async def test_pipe():
    a, b = pipe()

    # send the reply in the background
    async def reply():
        b.send_nowait(await b.recv() + 1)
        await b.send(await b.recv() + 1)

    asyncio.create_task(reply())
    assert await a.request_sendnowait(1) == 2
    assert await a.request(2) == 3

    with pytest.raises(ValueError):
        await a.send(1, eof=True)

    with pytest.raises(ValueError):
        await a.send()

    a.send_nowait(eof=True)
    with pytest.raises(EOFError):
        a.send_nowait('foo')
    with pytest.raises(EOFError):
        assert await b.recv()
    with pytest.raises(EOFError):
        assert await b.recv()


@pytest.mark.asyncio
async def test_concurrent_pipe():
    loop = asyncio.get_event_loop()
    p = ThreadPoolExecutor()

    a, b = pipe()
    b = ConcurrentPipeEnd(b, loop=loop)

    # send the reply in the background
    async def reply():
        await b.send(await b.recv() + 1)
        await b.send(await b.recv() + 1)

    loop.run_in_executor(p, asyncio.run, reply())
    assert await a.request_sendnowait(1) == 2
    assert await a.request(2) == 3

    with pytest.raises(ValueError):
        await a.send(1, eof=True)

    with pytest.raises(ValueError):
        await a.send()

    a.send_nowait(eof=True)
    with pytest.raises(EOFError):
        a.send_nowait('foo')
    with pytest.raises(EOFError):
        assert await b.recv()
    with pytest.raises(EOFError):
        assert await b.recv()


def test_ZmqPipeEnd_errors():
    ctx = zmq.asyncio.Context()

    with pytest.raises(ValueError):
        ZmqPipeEnd(ctx, zmq.PUSH, 'tcp://*', port=0, bind=True)


@pytest.mark.asyncio
async def test_zmq_tcp_pipe():
    ctx = zmq.asyncio.Context()
    a, b = await zmq_tcp_pipe(ctx)

    await b.send("foo")
    assert await a.recv() == "foo"

    await a.send(eof=True)
    with pytest.raises(EOFError):
        await b.recv()
    with pytest.raises(EOFError):
        await b.recv()
    with pytest.raises(EOFError):
        await a.send("bar")

    ctx.destroy()


@pytest.mark.asyncio
async def test_zmq_tcp_pipe_end_errors():
    ctx = zmq.asyncio.Context()

    with pytest.raises(ValueError):
        await zmq_tcp_pipe_end(ctx, 'c')

    with pytest.raises(ValueError):
        await zmq_tcp_pipe_end(ctx, 'b')


@pytest.mark.asyncio
async def test_zmq_tcp_pipe_separate():
    async def task():
        ctx = zmq.asyncio.Context()
        b = await zmq_tcp_pipe_end(ctx, 'b', port=60123)
        assert await b.recv() == "foo"
        ctx.destroy()

    task = asyncio.create_task(task())

    ctx = zmq.asyncio.Context()
    a = await zmq_tcp_pipe_end(ctx, 'a', port=60123)
    await a.send("foo")
    ctx.destroy()

    await task


@pytest.mark.asyncio
async def test_zmq_inproc_pipe():
    ctx = zmq.asyncio.Context()
    a, b = await zmq_inproc_pipe(ctx, 'inproc://pipe')

    await b.send("foo")
    assert await a.recv() == "foo"

    await a.send(eof=True)
    with pytest.raises(EOFError):
        await b.recv()
    with pytest.raises(EOFError):
        await b.recv()
    with pytest.raises(EOFError):
        await a.send("bar")

    ctx.destroy()


@pytest.mark.asyncio
async def test_zmq_inproc_pipe_end_errors():
    ctx = zmq.asyncio.Context()

    with pytest.raises(ValueError):
        await zmq_inproc_pipe_end(ctx, 'c', 'inproc://pipe')


@pytest.mark.asyncio
async def test_zmq_inproc_pipe_separate():
    ctx = zmq.asyncio.Context()

    async def task():
        b = await zmq_inproc_pipe_end(ctx, 'b', 'inproc://pipe')
        assert await b.recv() == "foo"

    a = await zmq_inproc_pipe_end(ctx, 'a', 'inproc://pipe', initialize=False)
    # bind must happen strictly before connect, so don't start task earlier:
    task = asyncio.create_task(task())
    # can't initialize before connect is possible
    await a.initialize()
    await a.send("foo")
    await task

    ctx.destroy()
