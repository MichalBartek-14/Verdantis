"""
Download-to-temp-then-move helper, shared by both entry scripts.

On Windows, writing a large file directly into a path under the user's
Documents tree can hit a transient `PermissionError: [Errno 13]` mid-write
- Windows Search Indexer (and/or antivirus real-time scanning) grabs an
exclusive lock on freshly-written files there for indexing/scanning before
the writer is done, racing the openEO client's own streaming write.
Downloading to a plain OS temp file first (outside any indexed folder)
sidesteps that race entirely; the final move into outputs/ is a single
fast filesystem operation on an already-complete file, not a long-lived
open-for-write handle, so it isn't vulnerable to the same race.
"""
import os
import tempfile
from pathlib import Path


def download_to_path(download_fn, final_path) -> Path:
    """Call `download_fn(tmp_path)` to download into a system temp file,
    then atomically replace `final_path` with the completed file.
    `download_fn` should be a callable taking a single Path argument, e.g.
    `lambda p: cube.download(p, format="NetCDF")` or
    `lambda p: job.get_results().download_file(p)`.

    Uses os.replace() rather than shutil.move()/os.rename(): on Windows,
    plain rename fails outright if final_path already exists (a re-run
    overwriting a previous output), whereas os.replace() is guaranteed
    cross-platform to atomically overwrite an existing destination."""
    final_path = Path(final_path)
    fd, tmp_name = tempfile.mkstemp(suffix=final_path.suffix)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        download_fn(tmp_path)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp_path, final_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return final_path
