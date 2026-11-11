"""Central factory for constructing FORGEX runtime components."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forgex.runtime.resource_manager import RuntimeResourceManager
from forgex.runtime.runtime_config import RuntimeConfig
from forgex.runtime.supervisor import ProcessSupervisor
from forgex.runtime.supervisor_adapter import SupervisorAdapter


@dataclass(slots=True)
class RuntimeComponents:
    """A collection of initialized runtime components."""

    config: RuntimeConfig
    resources: RuntimeResourceManager
    supervisor: ProcessSupervisor
    adapter: SupervisorAdapter

    async def shutdown(self) -> None:
        """Gracefully shut down runtime components."""
        await self.supervisor.shutdown()
        await self.resources.close()


class RuntimeFactory:
    """Construct configured runtime components."""

    @staticmethod
    def create(
        config: RuntimeConfig | None = None,
    ) -> RuntimeComponents:
        """Create the complete supervised runtime stack."""

        runtime_config = config or RuntimeConfig()

        resources = RuntimeResourceManager(runtime_config.resource_limits())

        supervisor = ProcessSupervisor(
            limits=runtime_config.resource_limits(),
            resource_manager=resources,
            terminate_grace_period=(runtime_config.termination_grace_period),
            read_chunk_size=runtime_config.output_chunk_size,
        )

        adapter = SupervisorAdapter(supervisor)

        return RuntimeComponents(
            config=runtime_config,
            resources=resources,
            supervisor=supervisor,
            adapter=adapter,
        )

    @staticmethod
    def create_from_file(
        config_path: str | Path,
    ) -> RuntimeComponents:
        """Load configuration and construct runtime components."""

        from forgex.runtime.config_loader import RuntimeConfigLoader

        config = RuntimeConfigLoader(config_path).load()

        return RuntimeFactory.create(config)


__all__ = ["RuntimeFactory", "RuntimeComponents"]
