# For development and git commit, the __version__ is set to the build placeholder 0.0.0
# For release, the __version__ is modified by poetry dynamic versioning with the GitHub tagged version
__version__ = "0.0.0"

import epyqlib._build

__version_tag__ = "v{}".format(__version__)
__build_tag__ = epyqlib._build.job_id
