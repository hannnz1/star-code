"""Development installs precede frontend compilation; release wheels require it."""
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        if version == 'editable':
            return
        frontend = Path(self.root) / 'frontend/dist'
        if not (frontend / 'index.html').is_file():
            raise RuntimeError('Build the frontend before packaging: npm --prefix frontend run build')
        build_data['force_include'][str(frontend)] = 'muse/_web'
