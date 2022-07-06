import asyncio

from telegram.ext import JobQueue


class RulesJobQueue(JobQueue):
    """Subclass of JobQueue to add custom stop behavior."""

    async def stop(self, wait: bool = True) -> None:
        """Declines all join requests and stops the job queue. That way, users will know that
        they have to apply to join again."""
        await asyncio.gather(
            *(
                job.run(self.application)
                for job in self.jobs()
                if job.name.startswith("JOIN_TIMEOUT")
            )
        )
        await super().stop(wait)
