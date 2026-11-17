"""Download the Orekit and Hipparchus JARs into the project root.

    python -m scripts.fetch_dependencies

The JARs are not stored in git.  Each file is downloaded from Maven Central and
verified against Maven's published SHA-1 checksum; files that are already
present with the correct checksum are skipped.
"""
import hashlib
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
MAVEN = 'https://repo1.maven.org/maven2'
OREKIT_VERSION = '13.1.2'
HIPPARCHUS_VERSION = '4.0.2'
HIPPARCHUS_MODULES = ('clustering', 'core', 'fft', 'filtering', 'fitting', 'geometry',
                      'ode', 'optim', 'samples', 'stat')

ARTIFACTS = [('org/orekit', 'orekit', OREKIT_VERSION)] + [
    ('org/hipparchus', f'hipparchus-{module}', HIPPARCHUS_VERSION) for module in HIPPARCHUS_MODULES]


def _sha1(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def main():
    for group, artifact, version in ARTIFACTS:
        name = f'{artifact}-{version}.jar'
        url = f'{MAVEN}/{group}/{artifact}/{version}/{name}'
        expected = _fetch(url + '.sha1').decode('ascii').split()[0].strip()
        target = ROOT / name
        if target.is_file() and _sha1(target) == expected:
            print(f'ok        {name}')
            continue
        data = _fetch(url)
        if hashlib.sha1(data).hexdigest() != expected:
            sys.exit(f'Checksum mismatch for {name}; file not written.')
        target.write_bytes(data)
        print(f'download  {name}')
    print('Orekit data is versioned in orekit-data/orekit-data-main (kept in git for reproducibility).')


if __name__ == '__main__':
    main()
