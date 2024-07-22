import asyncio
import sys
import time
from collections.abc import Generator

from bot import EcoCordClient
from ecosystem import EcosystemManager


async def run_discord_bot() -> None:
    loop = asyncio.get_event_loop()

    client = EcoCordClient()

    await client.start_ecosystem()

    gif_task = asyncio.create_task(client.send_gifs())

    try:
        await client.run_bot()
    except KeyboardInterrupt:
        await client.stop_ecosystem()
        gif_task.cancel()
        await client.close()
    finally:
        await loop.shutdown_asyncgens()


def run_gif_generator(duration: float | None = None) -> Generator[tuple[str, float], None, None]:
    manager = EcosystemManager(generate_gifs=True)
    manager.start(show_controls=False)

    start_time = time.time()
    try:
        while duration is None or time.time() - start_time < duration:
            gif_data = manager.get_latest_gif()
            if gif_data:
                yield gif_data
            time.sleep(0.01)
    finally:
        manager.stop()


def run_pygame(show_controls: bool = True, generate_gifs: bool = False) -> EcosystemManager:
    manager = EcosystemManager(generate_gifs=generate_gifs)
    manager.start(show_controls=show_controls)
    return manager


def main() -> None:
    if "--discord" in sys.argv:
        print("Running with Discord integration...")
        asyncio.run(run_discord_bot())
    elif "--gifs" in sys.argv:
        print("Running in GIF generation mode...")
        for gif_path, timestamp in run_gif_generator(duration=180):
            print(f"New GIF generated at {timestamp}: {gif_path}")
    else:
        print("Running in interactive mode...")
        manager = run_pygame(show_controls=True, generate_gifs=False)
        try:
            while True:
                pass
        except KeyboardInterrupt:
            manager.stop()


if __name__ == "__main__":
    main()
