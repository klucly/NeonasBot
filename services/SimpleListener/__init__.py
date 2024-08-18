from service_setup import SetupServiceData
import asyncio


class SimpleListener:
    def __init__(self, setup_data: SetupServiceData):
        self.setup_data = setup_data
        self.setup_data.logger.info("SimpleListener: Starting")

    async def handle_connection(self, reader, writer):
        self.setup_data.logger.info("SimpleListener: New connection")
        ...

    async def run(self):
        server = await asyncio.start_server(self.handle_connection, "0.0.0.0", 8080)
        async with server:
            await server.serve_forever()
