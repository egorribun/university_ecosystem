import asyncio

from dishka import AsyncContainer, Provider, Scope, make_async_container, provide


class QueryBus:
    def __init__(self, container: AsyncContainer):
        self.container = container

class SomeHandler:
    pass

class MyProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def query_bus(self, container: AsyncContainer) -> QueryBus:
        return QueryBus(container)

    @provide(scope=Scope.REQUEST)
    def handler(self) -> SomeHandler:
        return SomeHandler()

async def main():
    container = make_async_container(MyProvider())
    async with container() as request_container:
        bus = await request_container.get(QueryBus)
        print("Bus Container:", bus.container)
        print("Resolved Handler:", await bus.container.get(SomeHandler))

asyncio.run(main())
