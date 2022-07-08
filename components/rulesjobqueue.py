from telegram.ext import JobQueue


class RulesJobQueue(JobQueue):
    """Subclass of JobQueue to add custom stop behavior."""

    async def stop(self, wait: bool = True) -> None:
        """Declines all join requests and stops the job queue. That way, users will know that
        they have to apply to join again."""
        # We loop instead of `asyncio.gather`-ing to minimize the rist of timeouts & flood limits
        for job in self.jobs():
            if job.name.startswith("JOIN_TIMEOUT"):
                await job.run(self.application)
        await super().stop(wait)
